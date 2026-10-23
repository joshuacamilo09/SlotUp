"""Categorias do complexo (Coworking, Estacionamento, Desporto, ...).

- Qualquer utilizador autenticado lista e consulta as categorias ATIVAS.
- Só o ADMIN cria, edita e desativa.
- Não há DELETE: os recursos (e, através deles, as reservas antigas) apontam
  para a categoria. Apagar partia esse histórico, por isso desativa-se com
  PATCH {"is_active": false}. Uma categoria inativa deixa de aparecer aos
  utilizadores, mas o admin continua a vê-la e pode reativá-la.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate
from app.security import CurrentUser, current_user, require_admin

log = logging.getLogger("booking.categories")
router = APIRouter(prefix="/api/reservas/categorias", tags=["categorias"])

# Índice único sobre lower(name), criado na migração 0005
_UNIQUE_NAME = "categories_name_lower_key"


def _commit_or_409(db: Session) -> None:
    """Grava; se o nome já existir, devolve 409.

    Não verificamos o nome com um SELECT antes de gravar: entre o SELECT e o
    INSERT, outro admin (noutra réplica do serviço) podia criar o mesmo nome.
    Quem decide é o índice único do PostgreSQL, que é atómico.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        diag = getattr(exc.orig, "diag", None)
        if getattr(diag, "constraint_name", None) == _UNIQUE_NAME:
            raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma categoria com esse nome") from None
        raise


def _get_or_404(db: Session, category_id: uuid.UUID, user: CurrentUser) -> Category:
    category = db.get(Category, category_id)
    # Para um utilizador normal, uma categoria inativa é como se não existisse
    if category is None or (not category.is_active and user.role != "ADMIN"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoria não encontrada")
    return category


@router.get("", response_model=list[CategoryOut])
def list_categories(
    include_inactive: bool = Query(False, description="Só para ADMIN: inclui as categorias desativadas"),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[Category]:
    if include_inactive and user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores")
    query = select(Category).order_by(Category.name)
    if not include_inactive:
        query = query.where(Category.is_active.is_(True))
    return list(db.scalars(query))


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(
    category_id: uuid.UUID,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Category:
    return _get_or_404(db, category_id, user)


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryCreate,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Category:
    category = Category(name=body.name, description=body.description)
    db.add(category)
    _commit_or_409(db)
    db.refresh(category)  # lê id, created_at e updated_at gerados pelo PostgreSQL
    log.info("categoria_criada admin_id=%s categoria_id=%s nome=%r", admin.id, category.id, category.name)
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Category:
    category = _get_or_404(db, category_id, admin)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(category, field, value)
    _commit_or_409(db)
    db.refresh(category)
    log.info("categoria_editada admin_id=%s categoria_id=%s campos=%s", admin.id, category.id, sorted(changes))
    return category