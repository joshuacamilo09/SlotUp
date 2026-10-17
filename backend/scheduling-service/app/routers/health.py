import socket

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> dict:
    """Este serviço não tem base de dados: só faz cálculos, por isso está pronto se estiver vivo."""
    return {"status": "ok"}


@router.get("/whoami")
def whoami() -> dict:
    return {"service": get_settings().service_name, "instance": socket.gethostname()}
