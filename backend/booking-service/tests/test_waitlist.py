"""Fila de espera: entrar, oferta ao cancelar, aceitar, sair/recusar e expirar.

Correm contra o PostgreSQL real e reutilizam os ajudantes dos outros ficheiros de testes.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app import waitlist
from app.database import SessionLocal
from tests.test_reservations import (  # noqa: F401  (fixtures do pytest)
    admin,
    at,
    book,
    category,
    create_resource,
    _iso,
    helpers,
    next_monday,
)
from tests.test_reservations_manage import Person, ana, cancel, rui  # noqa: F401

FILA = "/api/reservas/fila"


# --------------------------------------------------------------------------- ajudantes
@pytest.fixture
def eva(helpers):
    return Person(helpers)


def join(client, person, rid, start, end):
    body = {"resource_id": rid, "start_at": _iso(start), "end_at": _iso(end)}
    return client.post(FILA, json=body, headers=person.headers)


def my_entries(client, person) -> list[dict]:
    return client.get(f"{FILA}/minhas", headers=person.headers).json()


def entry(client, person, entry_id) -> dict:
    return next(e for e in my_entries(client, person) if e["id"] == entry_id)


def reservation_status(reservation_id) -> str:
    with SessionLocal() as db:
        return db.scalar(text("SELECT status FROM reservations WHERE id = :id"), {"id": reservation_id})


def notification_types(waitlist_entry_id) -> list[str]:
    with SessionLocal() as db:
        return sorted(db.scalars(
            text("SELECT type FROM notifications WHERE waitlist_entry_id = :id"), {"id": waitlist_entry_id}
        ).all())


def expire_offer_now(reservation_id) -> None:
    """Põe o prazo da oferta no passado e corre o job de expiração."""
    with SessionLocal() as db:
        db.execute(text("UPDATE reservations SET hold_expires_at = now() - interval '1 minute' WHERE id = :id"),
                   {"id": reservation_id})
        db.commit()
        waitlist.expire(db, datetime.now(timezone.utc))
        db.commit()


@pytest.fixture
def busy_slot(client, admin, category, ana):
    """Um recurso com a Ana a ocupar segunda-feira das 10h às 11h."""
    day = next_monday()
    rid = create_resource(client, admin, category)
    reservation = book(client, ana.headers, rid, at(day, 10), at(day, 11)).json()["id"]
    return {"rid": rid, "day": day, "start": at(day, 10), "end": at(day, 11), "reservation": reservation}


# --------------------------------------------------------------------------- entrar na fila
def test_entrar_na_fila_sem_token_da_401(client):
    assert client.post(FILA, json={}).status_code == 401


def test_entrar_na_fila_de_um_horario_ocupado(client, busy_slot, rui, eva):
    first = join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"])
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["status"] == "WAITING" and body["position"] == 1 and body["reservation_id"] is None
    assert body["resource_name"].startswith("Sala ")
    assert notification_types(body["id"]) == ["WAITLIST_JOINED"]

    second = join(client, eva, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()
    assert second["position"] == 2


def test_nao_entra_na_fila_de_um_horario_livre(client, busy_slot, rui):
    day = busy_slot["day"]
    response = join(client, rui, busy_slot["rid"], at(day, 14), at(day, 15))
    assert response.status_code == 409 and "livre" in response.json()["detail"]


def test_nao_entra_na_fila_do_proprio_horario(client, busy_slot, ana):
    assert join(client, ana, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).status_code == 409


def test_nao_entra_duas_vezes_na_fila_do_mesmo_horario(client, busy_slot, rui):
    assert join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).status_code == 201
    assert join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).status_code == 409


def test_entrar_na_fila_segue_as_regras_de_uma_reserva(client, busy_slot, rui):
    day, rid = busy_slot["day"], busy_slot["rid"]
    assert join(client, rui, rid, at(day, 10, 5), at(day, 11)).status_code == 422  # fora dos 15 min
    assert join(client, rui, rid, at(day, 6), at(day, 7)).status_code == 422  # fora do horário de abertura
    assert join(client, rui, str(uuid.uuid4()), busy_slot["start"], busy_slot["end"]).status_code == 404


# --------------------------------------------------------------------------- oferta ao cancelar
def test_ao_cancelar_o_primeiro_da_fila_recebe_a_oferta(client, busy_slot, ana, rui, eva, helpers):
    rui_entry = join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    eva_entry = join(client, eva, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]

    assert cancel(client, ana.headers, busy_slot["reservation"]).status_code == 200

    offered = entry(client, rui, rui_entry)
    assert offered["status"] == "OFFERED" and offered["position"] is None
    assert offered["hold_expires_at"] is not None
    assert reservation_status(offered["reservation_id"]) == "HELD"
    assert notification_types(rui_entry) == ["WAITLIST_JOINED", "WAITLIST_OFFERED"]

    # A Eva continua à espera, agora em primeiro
    assert entry(client, eva, eva_entry)["position"] == 1
    # O horário está guardado para o Rui: mais ninguém o consegue reservar
    other = Person(helpers)
    assert book(client, other.headers, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).status_code == 409


def test_aceitar_a_oferta_confirma_a_reserva(client, busy_slot, ana, rui):
    rui_entry = join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    cancel(client, ana.headers, busy_slot["reservation"])

    response = client.post(f"{FILA}/{rui_entry}/aceitar", headers=rui.headers)
    assert response.status_code == 200, response.text
    reservation = response.json()
    assert reservation["status"] == "CONFIRMED" and reservation["user_email"] == rui.email

    assert entry(client, rui, rui_entry)["status"] == "ACCEPTED"
    mine = client.get("/api/reservas/reservas/minhas", headers=rui.headers).json()
    assert [r["id"] for r in mine] == [reservation["id"]]
    # Aceitar outra vez já não é possível
    assert client.post(f"{FILA}/{rui_entry}/aceitar", headers=rui.headers).status_code == 409


def test_so_o_dono_aceita_e_so_com_oferta(client, busy_slot, ana, rui, eva):
    rui_entry = join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    assert client.post(f"{FILA}/{rui_entry}/aceitar", headers=rui.headers).status_code == 409  # ainda WAITING
    cancel(client, ana.headers, busy_slot["reservation"])
    assert client.post(f"{FILA}/{rui_entry}/aceitar", headers=eva.headers).status_code == 404  # não é dela


# --------------------------------------------------------------------------- sair e recusar
def test_sair_da_fila(client, busy_slot, rui, eva):
    rui_entry = join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    eva_entry = join(client, eva, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]

    response = client.post(f"{FILA}/{rui_entry}/sair", headers=rui.headers)
    assert response.status_code == 200 and response.json()["status"] == "CANCELLED"
    assert entry(client, eva, eva_entry)["position"] == 1  # a Eva sobe na fila
    assert client.post(f"{FILA}/{rui_entry}/sair", headers=rui.headers).status_code == 409
    assert client.post(f"{FILA}/{eva_entry}/sair", headers=rui.headers).status_code == 404  # não é dele


def test_recusar_a_oferta_passa_ao_seguinte(client, busy_slot, ana, rui, eva):
    rui_entry = join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    eva_entry = join(client, eva, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    cancel(client, ana.headers, busy_slot["reservation"])
    rui_hold = entry(client, rui, rui_entry)["reservation_id"]

    response = client.post(f"{FILA}/{rui_entry}/sair", headers=rui.headers)
    assert response.status_code == 200 and response.json()["status"] == "CANCELLED"
    assert reservation_status(rui_hold) == "CANCELLED"
    assert entry(client, eva, eva_entry)["status"] == "OFFERED"


def test_cancelar_a_reserva_da_oferta_tambem_e_recusar(client, busy_slot, ana, rui, eva):
    rui_entry = join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    eva_entry = join(client, eva, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    cancel(client, ana.headers, busy_slot["reservation"])
    rui_hold = entry(client, rui, rui_entry)["reservation_id"]

    assert cancel(client, rui.headers, rui_hold).status_code == 200
    assert entry(client, rui, rui_entry)["status"] == "CANCELLED"
    assert entry(client, eva, eva_entry)["status"] == "OFFERED"


# --------------------------------------------------------------------------- expirar
def test_oferta_expirada_passa_ao_seguinte(client, busy_slot, ana, rui, eva):
    rui_entry = join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    eva_entry = join(client, eva, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    cancel(client, ana.headers, busy_slot["reservation"])
    rui_hold = entry(client, rui, rui_entry)["reservation_id"]

    expire_offer_now(rui_hold)

    assert entry(client, rui, rui_entry)["status"] == "EXPIRED"
    assert reservation_status(rui_hold) == "CANCELLED"
    assert entry(client, eva, eva_entry)["status"] == "OFFERED"


def test_aceitar_fora_de_prazo_da_409_e_passa_ao_seguinte(client, busy_slot, ana, rui, eva):
    rui_entry = join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    eva_entry = join(client, eva, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    cancel(client, ana.headers, busy_slot["reservation"])
    rui_hold = entry(client, rui, rui_entry)["reservation_id"]
    with SessionLocal() as db:  # prazo no passado, mas o job ainda não correu
        db.execute(text("UPDATE reservations SET hold_expires_at = now() - interval '1 minute' WHERE id = :id"),
                   {"id": rui_hold})
        db.commit()

    response = client.post(f"{FILA}/{rui_entry}/aceitar", headers=rui.headers)
    assert response.status_code == 409 and "expirou" in response.json()["detail"]
    assert entry(client, rui, rui_entry)["status"] == "EXPIRED"
    assert entry(client, eva, eva_entry)["status"] == "OFFERED"


def test_pedido_cujo_horario_ja_comecou_expira(client, admin, category, rui):
    rid = create_resource(client, admin, category)
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    entry_id = uuid.uuid4()
    with SessionLocal() as db:
        db.execute(text(
            "INSERT INTO waitlist_entries (id, user_id, user_email, resource_id, desired_start, desired_end)"
            " VALUES (:id, :uid, :email, :rid, :start, :end)"),
            {"id": entry_id, "uid": rui.id, "email": rui.email, "rid": rid,
             "start": start, "end": start + timedelta(hours=2)})
        db.commit()
        waitlist.expire(db, datetime.now(timezone.utc))
        db.commit()
    assert entry(client, rui, str(entry_id))["status"] == "EXPIRED"


# --------------------------------------------------------------------------- horários parciais
def test_horario_libertado_grande_serve_dois_pedidos_pequenos(client, admin, category, ana, rui, eva):
    day = next_monday()
    rid = create_resource(client, admin, category)
    big = book(client, ana.headers, rid, at(day, 10), at(day, 12)).json()["id"]
    rui_entry = join(client, rui, rid, at(day, 10), at(day, 11)).json()["id"]
    eva_entry = join(client, eva, rid, at(day, 11), at(day, 12)).json()["id"]

    cancel(client, ana.headers, big)
    assert entry(client, rui, rui_entry)["status"] == "OFFERED"
    assert entry(client, eva, eva_entry)["status"] == "OFFERED"


def test_pedido_maior_do_que_o_horario_libertado_continua_a_espera(client, admin, category, ana, rui, eva):
    day = next_monday()
    rid = create_resource(client, admin, category)
    first = book(client, ana.headers, rid, at(day, 10), at(day, 11)).json()["id"]
    book(client, rui.headers, rid, at(day, 11), at(day, 12))
    eva_entry = join(client, eva, rid, at(day, 10), at(day, 12)).json()["id"]

    cancel(client, ana.headers, first)  # 10h–11h fica livre, mas 11h–12h continua ocupado
    assert entry(client, eva, eva_entry)["status"] == "WAITING"