import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import InterfaceError, OperationalError

from app.config import get_settings
from app.database import SessionLocal
from app.models import User
from app.routers import auth, health, users
from app.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("auth")


def bootstrap_admin() -> None:
    """Cria o administrador inicial (se ADMIN_EMAIL e ADMIN_PASSWORD estiverem definidos).

    O ON CONFLICT DO NOTHING torna isto seguro quando várias réplicas arrancam ao mesmo tempo.
    O administrador também tem de configurar o 2FA no primeiro login.
    """
    settings = get_settings()
    if not (settings.admin_email and settings.admin_password):
        return
    email = settings.admin_email.strip().lower()
    for attempt in range(1, 6):
        try:
            with SessionLocal() as db:
                if db.scalar(select(User.id).where(User.email == email)) is None:
                    db.execute(
                        pg_insert(User)
                        .values(
                            name=settings.admin_name or "Administrador",
                            email=email,
                            password_hash=hash_password(settings.admin_password),
                            role="ADMIN",
                        )
                        .on_conflict_do_nothing()
                    )
                    db.commit()
                    log.info("administrador_inicial_criado email=%s", email)
            return
        except Exception as exc:  # BD ainda a arrancar
            log.warning("bootstrap_admin tentativa %s/5 falhou: %s", attempt, exc.__class__.__name__)
            time.sleep(2)
    log.error("não foi possível criar o administrador inicial")


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap_admin()
    yield


app = FastAPI(title="SlotUp · auth-service", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)


@app.exception_handler(OperationalError)
@app.exception_handler(InterfaceError)
async def database_unavailable(_: Request, exc: Exception) -> JSONResponse:
    """BD em baixo ou a trocar de primário (failover): 503 em vez de 500.

    Um 503 diz ao cliente "tente outra vez daqui a pouco" e conta como falha
    temporária nas métricas, em vez de parecer um bug do serviço.
    """
    log.error("base_de_dados_indisponivel erro=%s", exc.__class__.__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "Base de dados temporariamente indisponível"},
        headers={"Retry-After": "5"},
    )
