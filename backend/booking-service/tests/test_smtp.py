"""Servidor SMTP na nuvem (Gmail) e proteção das contas de exemplo.

* Com SMTP_STARTTLS=true a ligação é cifrada e o certificado do servidor é CONFIRMADO
  (sem isso, alguém no meio podia fazer-se passar pelo Gmail e ficar com a senha).
* Os endereços de domínios em MAIL_SKIP_DOMAINS não são enviados: ficam FAILED, com o
  motivo em last_error (as contas de exemplo são @slotup.pt, que não é nosso).
"""
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage

from app import emails
from app.config import get_settings
from app.database import SessionLocal
from tests.test_reservations import admin, at, book, category, create_resource, helpers, next_monday  # noqa: F401
from tests.test_reservations_manage import ana, rui  # noqa: F401
from tests.test_waitlist import busy_slot, eva  # noqa: F401
from tests.test_worker import Carteiro, notification, quatro_eventos  # noqa: F401


class SmtpFalso:
    """Faz de smtplib.SMTP: regista o que o envio lhe pediu, sem rede."""

    ultimo = None

    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.contexto, self.login_com, self.enviada = None, None, None
        SmtpFalso.ultimo = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.contexto = context

    def login(self, user, password):
        self.login_com = (user, password)

    def send_message(self, message):
        self.enviada = message


def _gmail():
    return get_settings().model_copy(update={
        "smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_starttls": True,
        "smtp_user": "slotup.projeto@gmail.com", "smtp_password": "senha-de-app",
    })


def test_com_starttls_o_certificado_do_servidor_e_confirmado(monkeypatch):
    monkeypatch.setattr(emails.smtplib, "SMTP", SmtpFalso)
    mensagem = EmailMessage()
    emails.smtp_sender(_gmail())(mensagem)

    smtp = SmtpFalso.ultimo
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 587)
    assert smtp.contexto is not None
    assert smtp.contexto.verify_mode == ssl.CERT_REQUIRED and smtp.contexto.check_hostname
    assert smtp.login_com == ("slotup.projeto@gmail.com", "senha-de-app")
    assert smtp.enviada is mensagem


def test_com_o_mailpit_nao_ha_starttls_nem_login(monkeypatch):
    monkeypatch.setattr(emails.smtplib, "SMTP", SmtpFalso)
    emails.smtp_sender(get_settings())(EmailMessage())
    smtp = SmtpFalso.ultimo
    assert (smtp.host, smtp.port) == ("mailpit", 1025)
    assert smtp.contexto is None and smtp.login_com is None


def _send_com(ids, carteiro, skip):
    settings = get_settings().model_copy(update={"mail_skip_domains": skip})
    with SessionLocal() as db:
        return emails.send_pending(db, datetime.now(timezone.utc), settings, carteiro, only_ids=ids)


def test_dominios_em_mail_skip_domains_nao_sao_enviados(quatro_eventos):
    carteiro = Carteiro()
    # os utilizadores dos testes são @slotup.pt; maiúsculas e espaços não contam
    assert _send_com(quatro_eventos, carteiro, " SlotUp.pt , outro.pt") == (0, 0)
    assert carteiro.enviados == []
    for nid in quatro_eventos:
        n = notification(nid)
        assert n["status"] == "FAILED" and n["attempts"] == 0
        assert n["last_error"] == "Não enviado: o domínio slotup.pt está em MAIL_SKIP_DOMAINS"


def test_os_outros_dominios_sao_enviados_normalmente(quatro_eventos):
    carteiro = Carteiro()
    assert _send_com(quatro_eventos, carteiro, "outro.pt") == (4, 0)
    assert len(carteiro.enviados) == 4


def test_por_omissao_nao_se_salta_nenhum_dominio():
    assert get_settings().mail_skip_domains_set == set()