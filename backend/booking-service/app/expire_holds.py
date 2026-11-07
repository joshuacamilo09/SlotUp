"""Job: fecha as ofertas da fila de espera que passaram do prazo e passa o horário ao seguinte.

Corre uma vez e sai:
    python -m app.expire_holds

No Kubernetes (Sprint 4) vai ser um CronJob a cada minuto. Pode correr em várias
réplicas ao mesmo tempo: o FOR UPDATE SKIP LOCKED em app/waitlist.py garante que
cada oferta é tratada por uma só.
"""
import logging
from datetime import datetime, timezone

from app import waitlist
from app.database import SessionLocal


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with SessionLocal() as db:
        holds, stale = waitlist.expire(db, datetime.now(timezone.utc))
        db.commit()
    logging.getLogger("booking.expire_holds").info("ofertas_expiradas=%s pedidos_expirados=%s", holds, stale)


if __name__ == "__main__":
    main()