import socket

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.config import get_settings
from app.database import SessionLocal

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict:
    """O processo está vivo? (liveness probe do Kubernetes)"""
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> dict:
    """Consegue servir pedidos? Testa a base de dados (readiness probe)."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "Base de dados indisponível") from None
    return {"status": "ok"}


@router.get("/whoami")
def whoami() -> dict:
    """Devolve o nome da instância: prova o balanceamento de carga na demo."""
    return {"service": get_settings().service_name, "instance": socket.gethostname()}
