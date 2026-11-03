"""Testes da disponibilidade (GET /api/reservas/recursos/{id}/disponibilidade).

Correm contra o PostgreSQL real. Como ainda não existe a rota de criar reservas,
as reservas são inseridas direto no banco. Todas as datas são numa segunda-feira
FUTURA, para as "horas que já passaram" não interferirem nos resultados.
"""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app.database import SessionLocal

URL = "/api/reservas/recursos"
TZ = ZoneInfo("Europe/Lisbon")
MONDAY_8_TO_20 = [{"weekday": 0, "open_time": "08:00", "close_time": "20:00"}]

def next_monday() -> date:
    """Uma segunda-feira no futuro (entre 1 e 7 dias a partir de hoje)."""
    today = datetime.now(TZ).date()
    return today + timedelta(days=7 - today.weekday()) # weekday(): 0 = segunda

def at(day: date, hour: int, minute: int = 0) -> datetime:
    """Data e hora local do complexo, com fuso (ex.: at(dia, 10) = 10:00 em Lisboa)."""
    return datetime.combine(day, time(hour, minute), tzinfo=TZ)

# ---------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def helpers(request):
    """O conftest.py (make_token e bearer), tal como o pytest já o carregou."""
    for plugin in request.config.pluginmanager.get_plugins():
        if hasattr(plugin, "make_token") and hasattr(plugin, "bearer"):
            return plugin
    raise RuntimeError("Não encontrei o conftest.py com make_token e bearer")

@pytest.fixture
def admin(helpers):
    return helpers.bearer(helpers.make_token(role="ADMIN"))

@pytest.fixture
def user(helpers):
    return helpers.bearer(helpers.make_token(role="USER"))

@pytest.fixture
def category():
    """Cria uma categoria de teste; no fim apaga-a, com os recursos e as reservas dela."""
    category_id = uuid.uuid4()
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO categories (id, name) VALUES (:id, :name)"),
            {"id": category_id, "name": f"teste-{category_id.hex[:12]}"},
        )
        db.commit()

    yield str(category_id) # o teste roda aqui; o que vem depois é a limpeza

    of_category = "SELECT id FROM resources WHERE category_id = :id"
    with SessionLocal() as db:
        db.execute(text(f"DELETE FROM reservations WHERE resource_id IN ({of_category})"), {"id": category_id})
        db.execute(text("DELETE FROM resources WHERE category_id = :id"), {"id": category_id})
        db.execute(text("DELETE FROM categories WHERE id = :id"), {"id": category_id})
        db.commit()

# -------------------------------------------------------------------------------- ajudantes
def create_resource(client, admin, category_id: str, schedule: list[dict]) -> str:
    body = {"category_id": category_id, "name": f"Sala {uuid.uuid4().hex[:8]}", "resource_type": "sala", "schedule": schedule}
    response = client.post(URL, json=body, headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["id"]

def add_reservation(resource_id: str, start: datetime, end: datetime, status: str = "CONFIRMED") -> None:
    """Insere uma reserva direto no banco, respeitando os CHECKs da migração 0002."""
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO reservations (user_id, user_email, resource_id, start_at, end_at, status, "
                "hold_expires_at, cancelled_at) "
                "VALUES (:user, 'ana@slotup.pt', :resource, :start, :end, :status, :hold, :cancelled)"
            ),
            {
                "user": uuid.uuid4(),
                "resource": resource_id,
                "start": start,
                "end": end,
                "status": status,
                "hold": end if status == "HELD" else None,
                "cancelled": datetime.now(TZ) if status == "CANCELLED" else None,
            },
        )
        db.commit()

def availability(client, headers, resource_id: str, day: date) -> dict:
    response = client.get(f"{URL}/{resource_id}/disponibilidade", params={"day": day.isoformat()}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()

def pairs(intervals: list[dict]) -> list[tuple[datetime, datetime]]:
    """Converte a resposta JSON em pares (início, fim) comparáveis com at(...)."""
    return [(datetime.fromisoformat(i["start"]), datetime.fromisoformat(i["end"])) for i in intervals]

# --------------------------------------------------------------------------- testes
def test_sem_token_da_401(client):
    assert client.get(f"{URL}/{uuid.uuid4()}/disponibilidade", params={"day": "2030-01-07"}).status_code == 401

def test_sem_reservas_tudo_livre(client, admin, user, category):
    day = next_monday()
    rid = create_resource(client, admin, category, MONDAY_8_TO_20)
    data = availability(client, user, rid, day)
    assert data["timezone"] == "Europe/Lisbon"
    assert pairs(data["opening"]) == [(at(day, 8), at(day, 20))]
    assert data["busy"] == []
    assert pairs(data["free"]) == [(at(day, 8), at(day, 20))]

def test_reserva_divide_o_livre_e_nao_revela_quem_reservou(client, admin, user, category):
    day = next_monday()
    rid = create_resource(client, admin, category, MONDAY_8_TO_20)
    add_reservation(rid, at(day, 10), at(day, 11))
    data = availability(client, user, rid, day)
    assert pairs(data["busy"]) == [(at(day, 10), at(day, 11))]
    assert pairs(data["free"]) == [(at(day, 8), at(day, 10)), (at(day, 11), at(day, 20))]
    assert set(data["busy"][0]) == {"start", "end"} # sem user_id nem email

@pytest.mark.parametrize("status, blocks", [("CONFIRMED", True), ("HELD", True), ("CANCELLED", False)])
def test_so_held_e_confirmed_ocupam(client, admin, user, category, status, blocks):
    day = next_monday()
    rid = create_resource(client, admin, category, MONDAY_8_TO_20)
    add_reservation(rid, at(day, 9), at(day, 10), status=status)
    busy = availability(client, user, rid, day)["busy"]
    assert (len(busy) == 1) is blocks

def test_dia_fechado_nao_tem_nada_livre(client, admin, user, category):
    tuesday = next_monday() + timedelta(days=1)
    rid = create_resource(client, admin, category, MONDAY_8_TO_20)
    data = availability(client, user, rid, tuesday)
    assert data["opening"] == [] and data["free"] == []

def test_dois_intervalos_e_reserva_no_meio(client, admin, user, category):
    day = next_monday()
    schedule = [
        {"weekday": 0, "open_time": "09:00", "close_time": "13:00"},
        {"weekday": 0, "open_time": "14:00", "close_time": "18:00"},
    ]
    rid = create_resource(client, admin, category, schedule)
    add_reservation(rid, at(day, 12), at(day, 15))
    assert pairs(availability(client, user, rid, day)["free"]) == [(at(day, 9), at(day, 12)), (at(day, 15), at(day, 18))]

def test_reserva_que_vem_da_noite_anterior_e_cortada_a_meia_noite(client, admin, user, category):
    day = next_monday()
    every_day = [{"weekday": d, "open_time": "00:00", "close_time": "23:59"} for d in range(7)]
    rid = create_resource(client, admin, category, every_day)
    add_reservation(rid, at(day - timedelta(days=1), 22), at(day, 2))
    data = availability(client, user, rid, day)
    assert pairs(data["busy"]) == [(at(day, 0), at(day, 2))]
    assert pairs(data["free"]) == [(at(day, 2), at(day, 23, 59))]

def test_dia_passado_nao_tem_nada_livre(client, admin, user, category):
    past_monday = next_monday() - timedelta(days=14)
    rid = create_resource(client, admin, category, MONDAY_8_TO_20)
    data = availability(client, user, rid, past_monday)
    assert len(data["opening"]) == 1
    assert data["free"] == []

def test_recurso_desativado_so_o_admin_ve(client, admin, user, category):
    rid = create_resource(client, admin, category, MONDAY_8_TO_20)
    client.patch(f"{URL}/{rid}", json={"is_active": False}, headers=admin)
    params = {"day": next_monday().isoformat()}
    assert client.get(f"{URL}/{rid}/disponibilidade", params=params, headers=user).status_code == 404
    assert client.get(f"{URL}/{rid}/disponibilidade", params=params, headers=admin).status_code == 200

def test_recurso_inexistente_da_404(client, user):
    params = {"day": next_monday().isoformat()}
    assert client.get(f"{URL}/{uuid.uuid4()}/disponibilidade", params=params, headers=user).status_code == 404

@pytest.mark.parametrize("params", [{}, {"day": "09-11-2026"}, {"day": "2026-02-30"}])
def test_dia_em_falta_ou_invalido_da_422(client, user, params):
    assert client.get(f"{URL}/{uuid.uuid4()}/disponibilidade", params=params, headers=user).status_code == 422