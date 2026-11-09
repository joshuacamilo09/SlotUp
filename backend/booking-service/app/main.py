import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from app.config import get_settings
from app.routers import availability, categories, health, reservations, resources, session_check, waitlist

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("booking")

app = FastAPI(title="SlotUp · booking-service")
app.include_router(health.router)
app.include_router(categories.router)
app.include_router(resources.router)
app.include_router(availability.router)
app.include_router(reservations.router)
app.include_router(waitlist.router)
app.include_router(session_check.router)

@app.middleware("http")
async def served_by_header(request: Request, call_next):
    """Cabeçalho X-Served-By em todas as respostas: mostra que réplica atendeu o pedido.

    Útil na demo das réplicas e do failover: no DevTools do browser (separador Rede)
    ou com curl -i vê-se cada pedido a cair no servidor 1 ou no servidor 2.
    """
    # Um middleware corre em TODOS os pedidos: o call_next passa o pedido à rota
    # e devolve a resposta, à qual acrescentamos o cabeçalho antes de a enviar.
    response = await call_next(request)
    response.headers["X-Served-By"] = get_settings().instance_name
    return response

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