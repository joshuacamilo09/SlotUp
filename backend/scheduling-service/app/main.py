import logging

from fastapi import FastAPI

from app.routers import health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# Serviço interno: só o booking-service lhe fala (não passa pelo Ingress).
# O algoritmo CSP entra aqui em /api/scheduling/... (tarefas da componente de IA).
app = FastAPI(title="SlotUp · scheduling-service")
app.include_router(health.router)
