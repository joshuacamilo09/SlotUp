"""Planear o meu dia: o booking monta o pedido do contrato e pede o plano ao CSP.

POST /api/reservas/planear             {day, activities: [...]}   -> proposta (não reserva)
POST /api/reservas/planear/confirmar   {day, items: [...]}        -> reserva tudo ou nada

O booking é a fonte da verdade: lê do banco os recursos ativos dos tipos pedidos,
o horário semanal de cada um e a ocupação do dia (HELD + CONFIRMED), e envia tudo
ao scheduling, que não tem banco.

Esta rota NÃO reserva nada: só devolve uma proposta. Quem reserva é o "Confirmar
plano", que volta a verificar tudo no banco (entretanto alguém pode ter reservado).
"""
import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import scheduling_client
from app.config import Settings, get_settings
from app.database import get_db
from app.models import Category, Notification, Reservation, Resource
from app.routers.reservations import _NO_OVERLAP, ACTIVE_STATUSES, _constraint_name, check_slot
from app.schemas import ConfirmarPlanoIn, PlanearIn, PlanoOut, ReservationCreate, ReservationOut
from app.security import CurrentUser, current_user

log = logging.getLogger("booking.planner")
router = APIRouter(prefix="/api/reservas/planear", tags=["planear"])

FAVORITO_DIAS = 90  # o recurso favorito vem das reservas dos últimos 90 dias


def _hhmm(valor: datetime | time) -> str:
    return valor.strftime("%H:%M")


def _limites_do_dia(dia: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Meia-noite do dia e meia-noite do dia seguinte, em hora local."""
    inicio = datetime.combine(dia, time(0, 0), tzinfo=tz)
    return inicio, datetime.combine(dia + timedelta(days=1), time(0, 0), tzinfo=tz)


def recurso_do_contrato(recurso: Resource) -> dict:
    """Um recurso no formato ResourceIn do contrato (os nomes são os do ResourceOut)."""
    return {
        "id": str(recurso.id),
        "name": recurso.name,
        "resource_type": recurso.resource_type,
        "capacity": recurso.capacity,
        "schedule": [
            {"weekday": regra.weekday, "open_time": _hhmm(regra.open_time), "close_time": _hhmm(regra.close_time)}
            for regra in recurso.rules
        ],
        "min_duration_min": recurso.min_duration_min,
        "max_duration_min": recurso.max_duration_min,
        "buffer_min": recurso.buffer_min,
    }


def intervalo_do_dia(inicio: datetime, fim: datetime, dia: date, tz: ZoneInfo) -> tuple[str, str] | None:
    """Uma reserva (o banco guarda em UTC) como "HH:MM"–"HH:MM" do dia planeado.

    Corta o que passa da meia-noite (o contrato só fala de UM dia). Devolve None se,
    depois do corte, não sobrar nada desse dia.
    """
    meia_noite, meia_noite_seguinte = _limites_do_dia(dia, tz)
    inicio = max(inicio.astimezone(tz), meia_noite)  # astimezone: de UTC para a hora local
    fim = min(fim.astimezone(tz), meia_noite_seguinte)
    # O contrato não tem "24:00": o que acaba à meia-noite fica a acabar às 23:59
    fim_txt = "23:59" if fim == meia_noite_seguinte else _hhmm(fim)
    inicio_txt = _hhmm(inicio)
    return (inicio_txt, fim_txt) if inicio_txt < fim_txt else None


def _recursos(db: Session, tipos: set[str]) -> list[Resource]:
    """Os recursos ATIVOS (e de categorias ativas) dos tipos pedidos."""
    consulta = (
        select(Resource)
        .join(Resource.category)
        .where(Resource.is_active, Category.is_active, Resource.resource_type.in_(tipos))
        .order_by(Resource.name)
    )
    return list(db.scalars(consulta))


def _ocupacao(db: Session, recursos: list[Resource], dia: date, tz: ZoneInfo) -> list[dict]:
    """As reservas HELD e CONFIRMED desses recursos que tocam no dia (as mesmas da constraint)."""
    meia_noite, meia_noite_seguinte = _limites_do_dia(dia, tz)
    consulta = select(Reservation.resource_id, Reservation.start_at, Reservation.end_at).where(
        Reservation.resource_id.in_([r.id for r in recursos]),
        Reservation.status.in_(ACTIVE_STATUSES),
        # Sobrepõe o dia: começa antes do fim do dia E acaba depois do início
        Reservation.start_at < meia_noite_seguinte,
        Reservation.end_at > meia_noite,
    )
    ocupado = []
    for resource_id, inicio, fim in db.execute(consulta):
        intervalo = intervalo_do_dia(inicio, fim, dia, tz)
        if intervalo:
            ocupado.append({"resource_id": str(resource_id), "start": intervalo[0], "end": intervalo[1]})
    return ocupado


def _favoritos(db: Session, user_id, tipos: set[str], agora: datetime) -> dict[str, str]:
    """Para cada tipo, o recurso que o usuário mais reservou nos últimos FAVORITO_DIAS.

    É o favorite_resource_id do contrato (custo F3): opcional, só desempata.
    """
    consulta = (
        select(Resource.resource_type, Reservation.resource_id)
        .select_from(Reservation)
        .join(Reservation.resource)
        .where(
            Reservation.user_id == user_id,
            Reservation.status == "CONFIRMED",
            Reservation.start_at >= agora - timedelta(days=FAVORITO_DIAS),
            Resource.is_active,
            Resource.resource_type.in_(tipos),
        )
        .group_by(Resource.resource_type, Reservation.resource_id)
        # O mais reservado primeiro; o id desempata, para o resultado ser sempre o mesmo
        .order_by(func.count().desc(), Reservation.resource_id)
    )
    favoritos: dict[str, str] = {}
    for tipo, resource_id in db.execute(consulta):
        favoritos.setdefault(tipo, str(resource_id))  # setdefault: fica o primeiro de cada tipo
    return favoritos


@router.post("", response_model=PlanoOut)
def planear_dia(
    body: PlanearIn,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tz = ZoneInfo(settings.local_timezone)
    agora = datetime.now(tz)
    tipos = {a.resource_type for a in body.activities}

    recursos = _recursos(db, tipos)
    favoritos = _favoritos(db, user.id, tipos, agora)

    atividades = []
    for atividade in body.activities:
        dados = atividade.model_dump(exclude_none=True)  # exclude_none: não envia os campos vazios
        if atividade.resource_type in favoritos:
            dados["favorite_resource_id"] = favoritos[atividade.resource_type]
        atividades.append(dados)

    pedido = {
        "mode": "plan",
        "day": body.day.isoformat(),
        # O contrato quer a hora local SEM fuso (ex.: 2026-12-09T15:30)
        "now": agora.replace(tzinfo=None).isoformat(timespec="minutes"),
        "activities": atividades,
        "resources": [recurso_do_contrato(r) for r in recursos],
        "busy": _ocupacao(db, recursos, body.day, tz),
    }

    # Se o scheduling falhar, levanta SchedulingIndisponivel e o main.py responde 503
    resposta = scheduling_client.planear(pedido)
    log.info(
        "plano_pedido user_id=%s dia=%s atividades=%s recursos=%s estado=%s",
        user.id, body.day, len(atividades), len(recursos), resposta.get("status"),
    )
    return resposta


@router.post("/confirmar", response_model=list[ReservationOut], status_code=status.HTTP_201_CREATED)
def confirmar_plano(
    body: ConfirmarPlanoIn,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Reserva o plano inteiro, TUDO OU NADA, numa só transação.

    Entre gerar o plano e confirmar, alguém pode ter reservado um dos horários. Por
    isso o plano não é de confiança: cada item passa pelas mesmas regras de uma reserva
    normal (check_slot) e o banco volta a verificar a sobreposição (reservations_no_overlap).
    Se UM item falhar, nenhum fica gravado e o usuário gera o plano de novo.
    """
    # 1) Valida TODOS os itens antes de gravar qualquer um (422 regra / 404 recurso)
    validados = []
    for item in body.items:
        # Sem fuso: o check_slot trata-as como hora local do complexo, como numa reserva normal
        pedido = ReservationCreate(
            resource_id=item.resource_id,
            start_at=datetime.combine(body.day, time.fromisoformat(item.start)),
            end_at=datetime.combine(body.day, time.fromisoformat(item.end)),
        )
        recurso, inicio, fim = check_slot(db, pedido, settings)
        validados.append((item, recurso, inicio, fim))

    # 2) Grava um a um, na MESMA transação. O flush() manda o INSERT já, e é aí que o
    #    banco confere a sobreposição; o commit só acontece no fim, se todos passarem.
    reservas = []
    for item, recurso, inicio, fim in validados:
        reserva = Reservation(
            user_id=user.id, user_email=user.email, resource_id=recurso.id,
            start_at=inicio, end_at=fim, status="CONFIRMED",
        )
        db.add(reserva)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()  # desfaz TAMBÉM as reservas anteriores deste plano: tudo ou nada
            if _constraint_name(exc) != _NO_OVERLAP:
                raise
            log.info("plano_conflito user_id=%s recurso_id=%s atividade=%s", user.id, recurso.id, item.activity_id)
            # JSONResponse em vez de HTTPException: assim vai também o activity_id do conflito
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": f"{recurso.name} já não está livre das {item.start} às {item.end}. "
                              "Nada foi reservado: gere o plano de novo.",
                    "activity_id": item.activity_id,
                },
            )
        reservas.append(reserva)
        # Pedido de email na mesma transação (outbox), como no Criar reserva
        db.add(Notification(
            user_id=user.id, recipient_email=user.email, type="RESERVATION_CREATED", reservation_id=reserva.id,
            payload={"resource_name": recurso.name, "start_at": inicio.isoformat(), "end_at": fim.isoformat()},
        ))

    db.commit()
    for reserva in reservas:
        db.refresh(reserva)
    log.info("plano_confirmado user_id=%s dia=%s reservas=%s", user.id, body.day, len(reservas))
    return reservas