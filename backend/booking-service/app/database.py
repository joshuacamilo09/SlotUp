from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


# pool_pre_ping: recupera sozinho quando o primário da BD muda (failover)
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session

# Código SQLSTATE do PostgreSQL para "deadlock detected"
DEADLOCK_SQLSTATE = "40P01"
# Quantas vezes uma rota tenta a mesma transação antes de desistir (e responder 503)
TENTATIVAS_DEADLOCK = 3


def is_deadlock(exc: Exception) -> bool:
    """True se o banco cancelou a transação para desfazer um deadlock.

    Acontece quando vários pedidos inserem reservas sobrepostas AO MESMO TEMPO: cada um
    fica à espera da linha do outro na constraint reservations_no_overlap. O PostgreSQL
    cancela um deles; repetir a transação resolve (a constraint responde então com 409).
    """
    # exc.orig é o erro original do psycopg, que traz o código SQLSTATE
    return getattr(getattr(exc, "orig", None), "sqlstate", None) == DEADLOCK_SQLSTATE