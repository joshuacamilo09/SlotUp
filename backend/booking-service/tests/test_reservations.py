"""Testes da criação de reservas (POST /api/reservas/reservas).

Correm contra o PostgreSQL real. Todas as datas são numa segunda-feira futura (o
recurso de teste abre à segunda, das 08:00 às 20:00), dentro dos 30 dias permitidos.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app.database import SessionLocal

URL = "/api/reservas/reservas"
RESOURCES_URL = "/api/reservas/recursos"
TZ = ZoneInfo("Europe/Lisbon")
MONDAY_8_TO_20 = [{"weekday": 0, "open_time": "08:00", "close_time": "20:00"}]

def next_monday() -> date:
    """Uma segunda-feira no futuro (entre 1 e 7 dias a partir de hoje)."""
    today = datetime.now(TZ).date()
    return today + timedelta(days=7 - today.weekday())

def at(day: date, hour: int, minute: int=0) -> datetime:
    """Data e hora local do complexo, com fuso."""
    return datetime.combine(day, time(hour, minute), tzinfo=TZ)

# --------------------------------------------------------------------------- fixtures
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
    """Cria uma categoria de teste; no fim apaga-a, com recursos, reservas e notificações."""
    category_id = uuid.uuid4()
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO categories (id, name) VALUES (:id, :name)"),
            {"id": category_id, "name": f"teste-{category_id.hex[:12]}"},
        )
        db.commit()

    yield str(category_id)

    of_category = "SELECT id FROM resources WHERE category_id = :id"
    of_reservations = f"SELECT id FROM reservations WHERE resource_id IN ({of_category})"
    of_waitlist = f"SELECT id FROM waitlist_entries WHERE resource_id IN ({of_category})"
    with SessionLocal() as db:
        # ordem: notificações (apontam para reservas e pedidos da fila) -> fila -> reservas -> recursos -> categoria
        db.execute(text(f"DELETE FROM notifications WHERE reservation_id IN ({of_reservations})"
                        f" OR waitlist_entry_id IN ({of_waitlist})"), {"id": category_id})
        db.execute(text(f"DELETE FROM waitlist_entries WHERE resource_id IN ({of_category})"), {"id": category_id})
        db.execute(text(f"DELETE FROM reservations WHERE resource_id IN ({of_category})"), {"id": category_id})
        db.execute(text("DELETE FROM resources WHERE category_id = :id"), {"id": category_id})
        db.execute(text("DELETE FROM categories WHERE id = :id"), {"id": category_id})
        db.commit()

# --------------------------------------------------------------------------- ajudantes
def create_resource(client, admin, category_id: str) -> str:
    body = {"category_id": category_id, "name": f"Sala {uuid.uuid4().hex[:8]}", "resource_type": "sala", 
            "schedule": MONDAY_8_TO_20}
    response = client.post(RESOURCES_URL, json=body, headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["id"]

def _iso(value) -> str:
    """Aceita um datetime ou um texto já pronto (ex.: hora sem fuso)."""
    return value if isinstance(value, str) else value.isoformat()

def book(client, headers, resource_id: str, start, end):
    body = {"resource_id": resource_id, "start_at": _iso(start), "end_at": _iso(end)}
    return client.post(URL, json=body, headers=headers)

# --------------------------------------------------------------------------- autenticação
def test_sem_token_da_401(client):
    day = next_monday()
    body = {"resource_id": str(uuid.uuid4()), "start_at": _iso(at(day, 10)), "end_at": _iso(at(day, 11))}
    assert client.post(URL, json=body).status_code == 401

def test_token_pre_auth_da_401(client, helpers):
    day = next_monday()
    headers = helpers.bearer(helpers.make_token(typ="pre_auth"))
    assert book(client, headers, str(uuid.uuid4()), at(day, 10), at(day, 11)).status_code == 401

# --------------------------------------------------------------------------- criar
def test_cria_reserva_confirmada_com_dados_do_token(client, helpers, admin, category):
    day = next_monday()
    rid = create_resource(client, admin, category)
    user_id = uuid.uuid4()
    headers = helpers.bearer(helpers.make_token(sub=str(user_id), email="rui@slotup.pt"))

    response = book(client, headers, rid, at(day, 10), at(day, 11))
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert data["user_email"] == "rui@slotup.pt"
    assert "user_id" not in data
    assert datetime.fromisoformat(data["start_at"]) == at(day, 10)

    with SessionLocal() as db:
        saved_user = db.scalar(text("SELECT user_id FROM reservations WHERE id = :id"), {"id": data["id"]})
        notifications = db.execute(
            text("SELECT type, status, recipient_email FROM notifications WHERE reservation_id = :id"),
            {"id": data["id"]},
        ).all()
    assert saved_user == user_id
    assert [tuple(n) for n in notifications] == [("RESERVATION_CREATED", "PENDING", "rui@slotup.pt")]

def test_hora_sem_fuso_vale_como_hora_local(client, admin, user, category):
    day = next_monday()
    rid = create_resource(client, admin, category)
    response = book(client, user, rid, f"{day}T10:00", f"{day}T11:00")
    assert response.status_code == 201, response.text
    assert datetime.fromisoformat(response.json()["start_at"]) == at(day, 10)

@pytest.mark.parametrize(
    "start, end, expected",
    [
        ((10, 0), (11, 0), 409),
        ((10, 30), (11, 30), 409),
        ((11, 0), (12, 0), 201),
        ((9, 0), (10, 0), 201),
    ],
)

def test_sobreposicao_com_reserva_existente(client, admin, user, category, start, end, expected):
    day = next_monday()
    rid = create_resource(client, admin, category)
    assert book(client, user, rid, at(day, 10), at(day, 11)).status_code == 201
    assert book(client, user, rid, at(day, *start), at(day, *end)).status_code == expected

def test_reserva_cancelada_nao_ocupa_o_horario(client, admin, user, category):
    day = next_monday()
    rid = create_resource(client, admin, category)
    first = book(client, user, rid, at(day, 10), at(day, 11)).json()
    with SessionLocal() as db:
        db.execute(text("UPDATE reservations SET status = 'CANCELLED', cancelled_at = now() WHERE id = :id"),
                   {"id": first["id"]})
        db.commit()
    assert book(client, user, rid, at(day, 10), at(day, 11)).status_code == 201

def test_reservas_simultaneas_no_mesmo_horario_so_uma_vence(client, helpers, admin, category):
    """A demo de consistência: 8 pessoas diferentes pedem o mesmo horário ao mesmo tempo."""
    day = next_monday()
    rid = create_resource(client, admin, category)
    people = [helpers.bearer(helpers.make_token()) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda h: book(client, h, rid, at(day, 15), at(day, 16)).status_code, people))
    assert sorted(codes) == [201] + [409] * 7
    with SessionLocal() as db:
        assert db.scalar(text("SELECT count(*) FROM reservations WHERE resource_id = :id"), {"id": rid}) == 1

# --------------------------------------------------------------------------- pedidos inválidos
def _invalid_cases():
    monday = next_monday()
    return [
        ("antes_de_abrir", at(monday, 7), at(monday, 9)),
        ("passa_do_fecho", at(monday, 19, 30), at(monday, 20, 30)),
        ("dia_fechado", at(monday + timedelta(days=1), 10), at(monday + timedelta(days=1), 11)),
        ("fora_da_grade_de_15_min", at(monday, 10, 10), at(monday, 11)),
        ("no_passado", at(monday - timedelta(days=14), 10), at(monday - timedelta(days=14), 11)),
        ("mais_de_30_dias", at(monday + timedelta(days=35), 10), at(monday + timedelta(days=35), 11)),
        ("fim_antes_do_inicio", at(monday, 11), at(monday, 10)),
        ("fuso_misturado", at(monday, 10).isoformat(), f"{monday}T11:00"),
    ]

@pytest.mark.parametrize("label, start, end", _invalid_cases())
def test_pedidos_invalidos_dao_422(client, admin, user, category, label, start, end):
    rid = create_resource(client, admin, category)
    assert book(client, user, rid, start, end).status_code == 422, label

def test_nao_aceita_user_id_nem_status_no_pedido(client, admin, user, category):
    day = next_monday()
    rid = create_resource(client, admin, category)
    body = {"resource_id": rid, "start_at": _iso(at(day, 10)), "end_at": _iso(at(day, 11)),
            "user_id": str(uuid.uuid4()), "status": "HELD"}
    assert client.post(URL, json=body, headers=user).status_code == 422

def test_recurso_inexistente_da_404(client, user):
    day = next_monday()
    assert book(client, user, str(uuid.uuid4()), at(day, 10), at(day, 11)).status_code == 404

def test_recurso_desativado_da_404_ate_para_o_admin(client, admin, category):
    day = next_monday()
    rid = create_resource(client, admin, category)
    client.patch(f"{RESOURCES_URL}/{rid}", json={"is_active": False}, headers=admin)
    assert book(client, admin, rid, at(day, 10), at(day, 11)).status_code == 404