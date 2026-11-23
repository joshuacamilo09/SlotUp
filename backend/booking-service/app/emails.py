"""Envio dos emails guardados na tabela notifications (padrão outbox).

As rotas só GRAVAM o pedido de email, na mesma transação da reserva. Quem envia é
o worker (app/worker.py), que chama send_pending() de poucos em poucos segundos.

* Um email de cada vez: SELECT ... FOR UPDATE SKIP LOCKED + commit depois de enviar.
  Com dois workers, cada email é apanhado por um só (o outro salta-o).
* Se o envio falhar, fica PENDING com nova tentativa mais tarde (30 s, 1 min, 2 min...).
* Endereços de domínios em MAIL_SKIP_DOMAINS não são enviados (ficam logo FAILED, com o
  motivo em last_error): com um servidor de email a sério, as contas de exemplo
  (@slotup.pt) não são nossas.
  Ao fim de EMAIL_MAX_ATTEMPTS tentativas passa a FAILED e não volta a ser tentado.
"""
import logging
import smtplib
import ssl
from collections.abc import Callable
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Notification

log = logging.getLogger("booking.emails")

# Assunto e texto de cada um dos 4 eventos. {recurso}, {dia}, {inicio}, {fim} e {ate}
# são preenchidos com os dados do payload, já na hora local do complexo.
TEMPLATES = {
    "RESERVATION_CREATED": (
        "Reserva confirmada: {recurso}",
        "A sua reserva está confirmada.\n\nRecurso: {recurso}\nDia: {dia}\nHorário: {inicio} – {fim}",
    ),
    "RESERVATION_CANCELLED": (
        "Reserva cancelada: {recurso}",
        "A sua reserva foi cancelada.\n\nRecurso: {recurso}\nDia: {dia}\nHorário: {inicio} – {fim}",
    ),
    "WAITLIST_JOINED": (
        "Está na fila de espera: {recurso}",
        "Entrou na fila de espera. Avisamos assim que o horário ficar livre.\n\n"
        "Recurso: {recurso}\nDia: {dia}\nHorário: {inicio} – {fim}",
    ),
    "WAITLIST_OFFERED": (
        "O horário ficou livre: {recurso}",
        "O horário que pediu ficou livre e está guardado para si até às {ate}.\n"
        "Aceite a oferta na página das suas reservas. Depois dessa hora passa ao seguinte da fila.\n\n"
        "Recurso: {recurso}\nDia: {dia}\nHorário: {inicio} – {fim}",
    ),
}

Sender = Callable[[EmailMessage], None]


def build_message(notification: Notification, settings: Settings) -> EmailMessage:
    """Monta o email a partir do tipo e do payload. Tipo desconhecido: ValueError."""
    if notification.type not in TEMPLATES:
        raise ValueError(f"Tipo de notificação desconhecido: {notification.type}")
    subject, body = TEMPLATES[notification.type]

    tz = ZoneInfo(settings.local_timezone)
    data = notification.payload or {}

    def local(campo: str) -> datetime | None:
        return datetime.fromisoformat(data[campo]).astimezone(tz) if data.get(campo) else None

    start, end, until = local("start_at"), local("end_at"), local("hold_expires_at")
    values = {
        "recurso": data.get("resource_name", "recurso"),
        "dia": start.strftime("%d/%m/%Y") if start else "",
        "inicio": start.strftime("%H:%M") if start else "",
        "fim": end.strftime("%H:%M") if end else "",
        "ate": until.strftime("%H:%M") if until else "",
    }

    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = notification.recipient_email
    message["Subject"] = subject.format(**values)
    message.set_content("Olá,\n\n" + body.format(**values) + "\n\nSlotUp")
    return message


def smtp_sender(settings: Settings) -> Sender:
    """Envio a sério, por SMTP (em desenvolvimento, o Mailpit; na demo, o Gmail)."""
    def send(message: EmailMessage) -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                # Contexto que CONFIRMA o certificado do servidor. O starttls() sem contexto
                # cifra a ligação mas aceita qualquer certificado: alguém no meio podia
                # fazer-se passar pelo Gmail e ficar com a senha.
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    return send


def _retry_delay(attempts: int) -> timedelta:
    """30 s, 1 min, 2 min, 4 min... no máximo 1 hora entre tentativas."""
    return timedelta(seconds=min(30 * 2 ** (attempts - 1), 3600))


def send_pending(db: Session, now: datetime, settings: Settings, send: Sender, limit: int = 50,
                 only_ids: list | None = None) -> tuple[int, int]:
    """Envia os emails pendentes cuja hora chegou. Devolve (enviados, falhados).

    only_ids: só estes emails (usado nos testes, para não mexer nos emails de outros testes).
    """
    sent = failed = 0
    for _ in range(limit):
        query = (
            select(Notification)
            .where(Notification.status == "PENDING", Notification.next_attempt_at <= now)
            .order_by(Notification.next_attempt_at, Notification.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if only_ids is not None:
            query = query.where(Notification.id.in_(only_ids))
        notification = db.scalars(query).first()
        if notification is None:
            break

        
        domain = notification.recipient_email.rsplit("@", 1)[-1].lower()
        if domain in settings.mail_skip_domains_set:
            notification.status = "FAILED"
            notification.last_error = f"Não enviado: o domínio {domain} está em MAIL_SKIP_DOMAINS"
            log.info("email_nao_enviado id=%s dominio=%s (MAIL_SKIP_DOMAINS)", notification.id, domain)
            db.commit()
            continue

        try:
            send(build_message(notification, settings))
        except Exception as exc:  # SMTP em baixo, endereço recusado, payload estragado...
            notification.attempts += 1
            notification.last_error = f"{type(exc).__name__}: {exc}"[:500]
            if notification.attempts >= settings.email_max_attempts:
                notification.status = "FAILED"
                log.error("email_falhou_de_vez id=%s tentativas=%s erro=%s",
                          notification.id, notification.attempts, notification.last_error)
            else:
                notification.next_attempt_at = now + _retry_delay(notification.attempts)
                log.warning("email_falhou id=%s tentativa=%s erro=%s",
                            notification.id, notification.attempts, notification.last_error)
            failed += 1
        else:
            notification.status = "SENT"
            notification.sent_at = now
            notification.attempts += 1
            sent += 1
            log.info("email_enviado id=%s tipo=%s", notification.id, notification.type)
        db.commit()  # liberta o lock deste email antes de pegar no seguinte
    return sent, failed