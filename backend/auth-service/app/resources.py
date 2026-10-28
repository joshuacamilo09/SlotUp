import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Uuid, column, delete, exists, select, table
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from app.database import get_db
from app.models import AvailabilityRule, Category, Resource
from app.schemas import (
    ResourceCreate,
    ResourceDeleteOut,
    ResourceOut,
    ResourceUpdate,
    ScheduleReplace,
    default_schedule,
)
from app.security import CurrentUser, current_user, require_admin

log = logging.getLogger("booking.resources")
router = APIRouter(prefix="/api/reservas/recursos", tags=["recursos"])

# Restrição única (category_id, name), migração 0001
_UNIQUE_NAME = "resources_category_id_name_key"
# Código SQLSTATE do PostgreSQL para "violação de chave estrangeira"
_FOREIGN_KEY_VIOLATION = "23503"

# Só precisamos da coluna resource_id da tabela `reservations` (migração 0002)
_reservations = table("reservations", column("resource_id", Uuid))


def _constraint_name(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


def _commit_or_409(db: Session) -> None:
    """Grava; se o nome já existir nessa categoria, devolve 409.

    Como nas categorias: quem decide é a restrição única do PostgreSQL (atómica), e não um
    SELECT antes do INSERT, porque dois admins em réplicas diferentes podiam passar os dois.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _constraint_name(exc) == _UNIQUE_NAME:
            raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um recurso com esse nome nesta categoria") from None
        raise


def _get(db: Session, resource_id: uuid.UUID, *, lock: bool = False) -> Resource | None:
    """Lê o recurso com a categoria e o horário. lock=True bloqueia a linha até ao commit.

    populate_existing: lê sempre da base de dados, mesmo que a sessão já tenha o objeto.
    """
    stmt = select(Resource).where(Resource.id == resource_id).execution_options(populate_existing=True)
    if lock:
        stmt = stmt.with_for_update(of=Resource)
    return db.scalars(stmt).unique().one_or_none()


def _get_or_404(db: Session, resource_id: uuid.UUID, user: CurrentUser, *, lock: bool = False) -> Resource:
    resource = _get(db, resource_id, lock=lock)
    # Para um utilizador normal, um recurso inativo (ou de categoria inativa) é como se não existisse
    hidden = resource is not None and user.role != "ADMIN" and not (resource.is_active and resource.category.is_active)
    if resource is None or hidden:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurso não encontrado")
    return resource


def _check_category(db: Session, category_id: uuid.UUID) -> None:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A categoria não existe")
    if not category.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "A categoria está desativada")


def _new_rules(rules) -> list[AvailabilityRule]:
    return [AvailabilityRule(weekday=r.weekday, open_time=r.open_time, close_time=r.close_time) for r in rules]


# --------------------------------------------------------------------------- leitura
@router.get("", response_model=list[ResourceOut])
def list_resources(
    category_id: uuid.UUID | None = Query(None, description="Só os recursos desta categoria"),
    include_inactive: bool = Query(False, description="Só para ADMIN: inclui os recursos desativados"),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[Resource]:
    if include_inactive and user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores")
    stmt = (
        select(Resource)
        .join(Resource.category)
        .options(contains_eager(Resource.category))
        .order_by(Category.name, Resource.name)
    )
    if category_id is not None:
        stmt = stmt.where(Resource.category_id == category_id)
    if not include_inactive:
        stmt = stmt.where(Resource.is_active.is_(True), Category.is_active.is_(True))
    return list(db.scalars(stmt).unique())


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(
    resource_id: uuid.UUID,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Resource:
    return _get_or_404(db, resource_id, user)


# --------------------------------------------------------------------------- escrita (ADMIN)
@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def create_resource(
    body: ResourceCreate,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Resource:
    _check_category(db, body.category_id)
    schedule = body.schedule if body.schedule is not None else default_schedule()
    resource = Resource(
        category_id=body.category_id,
        name=body.name,
        resource_type=body.resource_type,
        description=body.description,
        capacity=body.capacity,
        attributes=body.attributes,
        rules=_new_rules(schedule),
    )
    db.add(resource)
    _commit_or_409(db)
    created = _get(db, resource.id)
    log.info("recurso_criado admin_id=%s recurso_id=%s nome=%r", admin.id, created.id, created.name)
    return created


@router.patch("/{resource_id}", response_model=ResourceOut)
def update_resource(
    resource_id: uuid.UUID,
    body: ResourceUpdate,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Resource:
    resource = _get_or_404(db, resource_id, admin, lock=True)
    changes = body.model_dump(exclude_unset=True)
    if "category_id" in changes and changes["category_id"] != resource.category_id:
        _check_category(db, changes["category_id"])
    for field, value in changes.items():
        setattr(resource, field, value)
    _commit_or_409(db)
    updated = _get(db, resource_id)
    log.info("recurso_editado admin_id=%s recurso_id=%s campos=%s", admin.id, resource_id, sorted(changes))
    return updated


@router.put("/{resource_id}/horarios", response_model=ResourceOut)
def replace_schedule(
    resource_id: uuid.UUID,
    body: ScheduleReplace,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Resource:
    """Substitui o horário inteiro (dias e horas). `rules: []` deixa o recurso sem horário (fechado)."""
    _get_or_404(db, resource_id, admin, lock=True)  # o lock evita dois admins a trocarem o horário ao mesmo tempo
    # Apaga primeiro e só depois insere: como a restrição única é (recurso, dia, abertura), inserir antes
    # de apagar chocaria com as linhas antigas.
    db.execute(delete(AvailabilityRule).where(AvailabilityRule.resource_id == resource_id))
    db.add_all(
        AvailabilityRule(resource_id=resource_id, weekday=r.weekday, open_time=r.open_time, close_time=r.close_time)
        for r in body.rules
    )
    db.commit()
    updated = _get(db, resource_id)
    log.info("horario_alterado admin_id=%s recurso_id=%s intervalos=%s", admin.id, resource_id, len(body.rules))
    return updated


def _deactivate(db: Session, resource_id: uuid.UUID) -> None:
    resource = _get(db, resource_id, lock=True)
    resource.is_active = False
    db.commit()


@router.delete("/{resource_id}", response_model=ResourceDeleteOut)
def delete_resource(
    resource_id: uuid.UUID,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ResourceDeleteOut:
    """Sem reservas: apaga. Com reservas (mesmo antigas): desativa, para não perder o histórico."""
    resource = _get_or_404(db, resource_id, admin, lock=True)
    has_reservations = db.scalar(select(exists().where(_reservations.c.resource_id == resource_id)))
    if not has_reservations:
        try:
            db.delete(resource)
            db.commit()
            log.info("recurso_apagado admin_id=%s recurso_id=%s", admin.id, resource_id)
            return ResourceDeleteOut(action="deleted", resource_id=resource_id)
        except IntegrityError as exc:
            db.rollback()
            # Alguém criou uma reserva (ou entrou na fila de espera) entre a nossa verificação e o DELETE:
            # a chave estrangeira recusa e passamos à desativação.
            if getattr(exc.orig, "sqlstate", None) != _FOREIGN_KEY_VIOLATION:
                raise
    _deactivate(db, resource_id)
    log.info("recurso_desativado admin_id=%s recurso_id=%s motivo=tem_reservas", admin.id, resource_id)
    return ResourceDeleteOut(action="deactivated", resource_id=resource_id)