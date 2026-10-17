"""Endpoints provisórios para provar a validação do token e os papéis (Sprint 1).

Apagar quando existirem os endpoints reais de reservas (Sprint 3).
"""
from fastapi import APIRouter, Depends

from app.security import CurrentUser, current_user, require_admin

router = APIRouter(prefix="/api/booking", tags=["scaffolding"])


@router.get("/me")
def me(user: CurrentUser = Depends(current_user)) -> dict:
    return {"id": str(user.id), "email": user.email, "role": user.role}


@router.get("/admin/check")
def admin_check(user: CurrentUser = Depends(require_admin)) -> dict:
    return {"ok": True, "admin": user.email}
