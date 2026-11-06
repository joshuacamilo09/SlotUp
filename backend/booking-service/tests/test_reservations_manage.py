"""Minhas reservas, todas as reservas (admin), ver uma reserva e cancelar.

Correm contra o PostgreSQL real e reutilizam os ajudantes de test_reservations.py.
Reservas no passado (ou já a decorrer) não se criam pela API, por isso entram
direto no banco com insert_reservation().
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from tests.test_reservations import (  # noqa: F401  (fixtures do pytest)
    admin,
    at,
    book,
    category,
    create_resource,
    helpers,
    next_monday,
)

URL = "/api/reservas/reservas"
AVAILABILITY = "/api/reservas/recursos/{rid}/disponibilidade"


# --------------------------------------------------------------------------- ajudantes
class Person:
    """Um usuário com id fixo: todos os pedidos dele usam o mesmo token."""

    def __init__(self, helpers, role="USER"):
        self.id = uuid.uuid4()
        self.email = f"p-{self.id.hex[:8]}@slotup.pt"
        self.headers = helpers.bearer(helpers.make_token(sub=str(self.id), email=self.email, role=role))


@pytest.fixture
def ana(helpers):
    return Person(helpers)


@pytest.fixture
def rui(helpers):
    return Person(helpers)


def insert_reservation(person: Person, resource_id: str, start: datetime, end: datetime) -> str:
    """Grava uma reserva CONFIRMED direto no banco (para reservas no passado ou já a decorrer)."""
    reservation_id = uuid.uuid4()
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO reservations (id, user_id, user_email, resource_id, start_at, end_at)"
                 " VALUES (:id, :uid, :email, :rid, :start, :end)"),
            {"id": reservation_id, "uid": person.id, "email": person.email, "rid": resource_id,
             "start": start, "end": end},
        )
        db.commit()
    return str(reservation_id)


def hours_from_now(hours: float) -> datetime:
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=hours)


def cancel(client, headers, reservation_id: str):
    return client.post(f"{URL}/{reservation_id}/cancelar", headers=headers)


def notifications(reservation_id: str, kind: str) -> list[tuple]:
    with SessionLocal() as db:
        return [tuple(row) for row in db.execute(
            text("SELECT recipient_email, payload->>'cancelled_by' FROM notifications"
                 " WHERE reservation_id = :id AND type = :type"),
            {"id": reservation_id, "type": kind},
        ).all()]


# --------------------------------------------------------------------------- minhas reservas
def test_minhas_reservas_sem_token_da_401(client):
    assert client.get(f"{URL}/minhas").status_code == 401


def test_minhas_reservas_so_mostra_as_do_proprio(client, admin, category, ana, rui):
    day = next_monday()
    rid = create_resource(client, admin, category)
    mine = book(client, ana.headers, rid, at(day, 9), at(day, 10)).json()
    book(client, rui.headers, rid, at(day, 10), at(day, 11))

    response = client.get(f"{URL}/minhas", headers=ana.headers)
    assert response.status_code == 200
    data = response.json()
    assert [r["id"] for r in data] == [mine["id"]]
    assert response.headers["X-Total-Count"] == "1"
    # A resposta traz os nomes, para o frontend não ter de os pedir à parte
    assert data[0]["resource_name"].startswith("Sala ") and data[0]["category_name"].startswith("teste-")
    assert "user_id" not in data[0]


def test_minhas_reservas_futuras_e_passadas(client, admin, category, ana):
    day = next_monday()
    rid = create_resource(client, admin, category)
    future_late = book(client, ana.headers, rid, at(day, 15), at(day, 16)).json()["id"]
    future_early = book(client, ana.headers, rid, at(day, 9), at(day, 10)).json()["id"]
    past_old = insert_reservation(ana, rid, hours_from_now(-72), hours_from_now(-71))
    past_recent = insert_reservation(ana, rid, hours_from_now(-5), hours_from_now(-4))
    ongoing = insert_reservation(ana, rid, hours_from_now(-1), hours_from_now(1))

    def ids(periodo):
        return [r["id"] for r in client.get(f"{URL}/minhas", params={"periodo": periodo}, headers=ana.headers).json()]

    # Futuras: a mais próxima primeiro; a que está a decorrer conta como futura
    assert ids("futuras") == [ongoing, future_early, future_late]
    # Passadas: a mais recente primeiro
    assert ids("passadas") == [past_recent, past_old]
    assert sorted(ids("todas")) == sorted([future_late, future_early, past_old, past_recent, ongoing])


def test_minhas_reservas_filtro_por_status_e_paginacao(client, admin, category, ana):
    day = next_monday()
    rid = create_resource(client, admin, category)
    first = book(client, ana.headers, rid, at(day, 9), at(day, 10)).json()["id"]
    book(client, ana.headers, rid, at(day, 10), at(day, 11))
    book(client, ana.headers, rid, at(day, 11), at(day, 12))
    cancel(client, ana.headers, first)

    cancelled = client.get(f"{URL}/minhas", params={"status": "CANCELLED"}, headers=ana.headers).json()
    assert [r["id"] for r in cancelled] == [first]
    assert cancelled[0]["cancelled_at"] is not None

    page = client.get(f"{URL}/minhas", params={"periodo": "futuras", "limit": 2, "offset": 2}, headers=ana.headers)
    assert page.headers["X-Total-Count"] == "3" and len(page.json()) == 1


@pytest.mark.parametrize("params", [{"periodo": "ontem"}, {"status": "PENDENTE"}, {"limit": 0}, {"limit": 201}])
def test_minhas_reservas_parametros_invalidos_dao_422(client, ana, params):
    assert client.get(f"{URL}/minhas", params=params, headers=ana.headers).status_code == 422


# --------------------------------------------------------------------------- todas as reservas (admin)
def test_todas_as_reservas_so_para_admin(client, ana):
    assert client.get(URL, headers=ana.headers).status_code == 403
    assert client.get(URL).status_code == 401


def test_admin_ve_reservas_de_todos_com_user_id(client, admin, category, ana, rui):
    day = next_monday()
    rid = create_resource(client, admin, category)
    a = book(client, ana.headers, rid, at(day, 9), at(day, 10)).json()["id"]
    r = book(client, rui.headers, rid, at(day, 10), at(day, 11)).json()["id"]

    data = client.get(URL, params={"resource_id": rid}, headers=admin).json()
    assert {row["id"] for row in data} == {a, r}
    assert {row["user_id"] for row in data} == {str(ana.id), str(rui.id)}


def test_admin_filtra_por_email_status_e_periodo(client, admin, category, ana, rui):
    day = next_monday()
    rid = create_resource(client, admin, category)
    a1 = book(client, ana.headers, rid, at(day, 9), at(day, 10)).json()["id"]
    a2 = book(client, ana.headers, rid, at(day, 10), at(day, 11)).json()["id"]
    book(client, rui.headers, rid, at(day, 11), at(day, 12))
    cancel(client, ana.headers, a2)
    old = insert_reservation(ana, rid, hours_from_now(-30), hours_from_now(-29))

    def ids(**params):
        return {row["id"] for row in client.get(URL, params={"resource_id": rid, **params}, headers=admin).json()}

    assert ids(user_email=ana.email.upper()) == {a1, a2, old}  # o email não diferencia maiúsculas
    assert ids(user_email=ana.email, status="CONFIRMED", periodo="futuras") == {a1}
    assert ids(periodo="passadas") == {old}


# --------------------------------------------------------------------------- ver uma reserva
def test_ver_uma_reserva_dono_e_admin_sim_outro_usuario_404(client, admin, category, ana, rui):
    day = next_monday()
    rid = create_resource(client, admin, category)
    reservation = book(client, ana.headers, rid, at(day, 9), at(day, 10)).json()["id"]

    assert client.get(f"{URL}/{reservation}", headers=ana.headers).status_code == 200
    assert client.get(f"{URL}/{reservation}", headers=admin).status_code == 200
    assert client.get(f"{URL}/{reservation}", headers=rui.headers).status_code == 404
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=ana.headers).status_code == 404
    assert client.get(f"{URL}/nao-e-um-uuid", headers=ana.headers).status_code == 422


# --------------------------------------------------------------------------- cancelar
def test_dono_cancela_e_o_horario_volta_a_ficar_livre(client, admin, category, ana, rui):
    day = next_monday()
    rid = create_resource(client, admin, category)
    reservation = book(client, ana.headers, rid, at(day, 10), at(day, 11)).json()["id"]
    assert book(client, rui.headers, rid, at(day, 10), at(day, 11)).status_code == 409

    response = cancel(client, ana.headers, reservation)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED" and response.json()["cancelled_at"]

    # Livre na disponibilidade e reservável por outra pessoa
    busy = client.get(AVAILABILITY.format(rid=rid), params={"day": str(day)}, headers=rui.headers).json()["busy"]
    assert busy == []
    assert book(client, rui.headers, rid, at(day, 10), at(day, 11)).status_code == 201

    # Email (outbox) para o dono
    assert notifications(reservation, "RESERVATION_CANCELLED") == [(ana.email, "USER")]


def test_nao_cancela_a_reserva_de_outra_pessoa(client, admin, category, ana, rui):
    day = next_monday()
    rid = create_resource(client, admin, category)
    reservation = book(client, ana.headers, rid, at(day, 10), at(day, 11)).json()["id"]

    assert cancel(client, rui.headers, reservation).status_code == 404
    with SessionLocal() as db:
        assert db.scalar(text("SELECT status FROM reservations WHERE id = :id"), {"id": reservation}) == "CONFIRMED"


def test_cancelar_duas_vezes_da_409(client, admin, category, ana):
    day = next_monday()
    rid = create_resource(client, admin, category)
    reservation = book(client, ana.headers, rid, at(day, 10), at(day, 11)).json()["id"]
    assert cancel(client, ana.headers, reservation).status_code == 200
    assert cancel(client, ana.headers, reservation).status_code == 409
    assert len(notifications(reservation, "RESERVATION_CANCELLED")) == 1


def test_usuario_nao_cancela_depois_de_comecar_mas_o_admin_sim(client, admin, category, ana):
    rid = create_resource(client, admin, category)
    ongoing = insert_reservation(ana, rid, hours_from_now(-1), hours_from_now(1))

    assert cancel(client, ana.headers, ongoing).status_code == 409
    response = cancel(client, admin, ongoing)
    assert response.status_code == 200
    # O email vai para o dono, e diz que foi o admin
    assert notifications(ongoing, "RESERVATION_CANCELLED") == [(ana.email, "ADMIN")]


def test_ninguem_cancela_uma_reserva_que_ja_terminou(client, admin, category, ana):
    rid = create_resource(client, admin, category)
    past = insert_reservation(ana, rid, hours_from_now(-5), hours_from_now(-4))
    assert cancel(client, ana.headers, past).status_code == 409
    assert cancel(client, admin, past).status_code == 409


def test_cancelar_reserva_inexistente_ou_sem_token(client, ana):
    assert cancel(client, ana.headers, str(uuid.uuid4())).status_code == 404
    assert client.post(f"{URL}/{uuid.uuid4()}/cancelar").status_code == 401


def test_dono_e_admin_cancelam_ao_mesmo_tempo_so_um_consegue(client, admin, category, ana):
    """Corrida entre cancelamentos: só um vence e só sai um email.

    Para a corrida acontecer de certeza, o teste bloqueia a linha da reserva noutra
    ligação, dispara os 8 pedidos (ficam todos à espera) e só depois a liberta.
    Sem o FOR UPDATE na rota, todos leriam CONFIRMED e mais do que um "cancelaria".
    """
    day = next_monday()
    rid = create_resource(client, admin, category)
    reservation = book(client, ana.headers, rid, at(day, 10), at(day, 11)).json()["id"]

    requests = [ana.headers, admin] * 4
    with ThreadPoolExecutor(max_workers=8) as pool:
        with SessionLocal() as blocker:
            blocker.execute(text("SELECT 1 FROM reservations WHERE id = :id FOR UPDATE"), {"id": reservation})
            futures = [pool.submit(lambda h: cancel(client, h, reservation).status_code, h) for h in requests]
            time.sleep(0.5)  # tempo para os 8 pedidos chegarem ao banco e ficarem à espera
            blocker.commit()  # liberta a linha
        codes = [f.result() for f in futures]

    assert sorted(codes) == [200] + [409] * 7
    assert len(notifications(reservation, "RESERVATION_CANCELLED")) == 1