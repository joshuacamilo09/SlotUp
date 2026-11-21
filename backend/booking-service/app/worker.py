"""Worker do booking: o trabalho que não depende de nenhum pedido HTTP.

De WORKER_INTERVAL_SECONDS em WORKER_INTERVAL_SECONDS:
  1. Vagas seguradas na fila: as ofertas (reservas HELD) cujos 15 minutos passaram
     são canceladas, e o horário passa ao seguinte da fila (app/waitlist.py).
  2. Emails: envia os pedidos de email pendentes da tabela notifications (app/emails.py).

Correr:   python -m app.worker          (fica sempre a correr; no Compose é o booking-worker)
          python -m app.worker --once   (uma volta só e sai; útil para testar)

Pode haver mais do que um worker ao mesmo tempo: o FOR UPDATE SKIP LOCKED garante
que cada oferta e cada email são tratados por um só.
"""
import logging
import signal
import sys
import time
from datetime import datetime, timezone

from app import emails, waitlist
from app.config import Settings, get_settings
from app.database import SessionLocal

log = logging.getLogger("booking.worker")
_stop = False


def tick(settings: Settings, send: emails.Sender) -> dict:
    """Uma volta do worker. Devolve o que fez (para o log e para os testes)."""
    with SessionLocal() as db:
        holds, stale = waitlist.expire(db, datetime.now(timezone.utc))
        db.commit()
    with SessionLocal() as db:
        sent, failed = emails.send_pending(db, datetime.now(timezone.utc), settings, send)
    return {"ofertas_expiradas": holds, "pedidos_expirados": stale, "emails_enviados": sent, "emails_falhados": failed}


def _parar(*_):
    global _stop
    _stop = True  # o docker compose stop manda SIGTERM: acaba a volta atual e sai


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    send = emails.smtp_sender(settings)
    signal.signal(signal.SIGTERM, _parar)
    signal.signal(signal.SIGINT, _parar)
    log.info("worker_iniciado intervalo=%ss smtp=%s:%s", settings.worker_interval_seconds,
             settings.smtp_host, settings.smtp_port)

    while not _stop:
        try:
            feito = tick(settings, send)
            if any(feito.values()):
                log.info("worker_volta %s", " ".join(f"{k}={v}" for k, v in feito.items()))
        except Exception:
            # Base de dados em baixo, por exemplo: regista e tenta outra vez na próxima volta
            log.exception("worker_erro")
        if "--once" in sys.argv:
            break
        for _ in range(settings.worker_interval_seconds):  # dorme 1 s de cada vez, para parar depressa
            if _stop:
                break
            time.sleep(1)
    log.info("worker_parado")


if __name__ == "__main__":
    main()