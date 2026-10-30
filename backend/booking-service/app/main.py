import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from app.routers import categories, health, resources, session_check

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("booking")

app = FastAPI(title="SlotUp · booking-service")
app.include_router(health.router)
app.include_router(categories.router)
app.include_router(resources.router)
app.include_router(session_check.router)


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