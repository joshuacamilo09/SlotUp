"""Limite de 1 vaga de estacionamento por utilizador e por dia (app/parking.py).

A categoria de teste tem um nome aleatório. Para o booking a tratar como a categoria
das vagas, trocamos PARKING_CATEGORY só durante estes testes.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from app.config import get_settings
from app.main import app
from tests.test_reservations import (  # noqa: F401  (fixtures do pytest)
    RESOURCES_URL,
    admin,
    at,
    book,
    category,
    create_resource,
    helpers,
    next_monday,
)
from tests.test_reservations_manage import Person, ana, cancel, rui  # noqa: F401
from tests.test_waitlist import entry, join  # noqa: F401
from sqlalchemy import text
from app.database import SessionLocal

FILA = "/api/reservas/fila"
ALL_DAY = [{"weekday": d, "open_time": "00:00", "close_time": "23:59"} for d in range(7)]


@pytest.fixture
def parking(client, admin, category):
    """A categoria de teste passa a ser a do estacionamento. Devolve uma função que cria vagas."""
    name = client.get(f"/api/reservas/categorias/{category}", headers=admin).json()["name"]
    settings = get_settings().model_copy(update={"parking_category": name})
    app.dependency_overrides[get_settings] = lambda: settings

    def nova_vaga() -> str:
        body = {"category_id": category, "name": f"Vaga {uuid.uuid4().hex[:8]}", "resource_type": "vaga_carro",
                "schedule": ALL_DAY, "max_duration_min": 1440}
        response = client.post(RESOURCES_URL, json=body, headers=admin)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    yield nova_vaga
    app.dependency_overrides.pop(get_settings, None)


def test_segunda_vaga_no_mesmo_dia_da_409(client, parking, ana):
    day = next_monday()
    vaga1, vaga2 = parking(), parking()
    assert book(client, ana.headers, vaga1, at(day, 8), at(day, 12)).status_code == 201

    response = book(client, ana.headers, vaga2, at(day, 14), at(day, 18))
    assert response.status_code == 409
    assert "vaga de estacionamento" in response.json()["detail"]


def test_vaga_noutro_dia_pode(client, parking, ana):
    day = next_monday()
    vaga1, vaga2 = parking(), parking()
    assert book(client, ana.headers, vaga1, at(day, 8), at(day, 12)).status_code == 201
    tuesday = day + timedelta(days=1)
    assert book(client, ana.headers, vaga2, at(tuesday, 8), at(tuesday, 12)).status_code == 201


def test_cancelar_liberta_a_vaga_do_dia(client, parking, ana):
    day = next_monday()
    vaga1, vaga2 = parking(), parking()
    first = book(client, ana.headers, vaga1, at(day, 8), at(day, 12)).json()["id"]
    assert book(client, ana.headers, vaga2, at(day, 14), at(day, 18)).status_code == 409

    assert cancel(client, ana.headers, first).status_code == 200
    assert book(client, ana.headers, vaga2, at(day, 14), at(day, 18)).status_code == 201


def test_outros_utilizadores_nao_contam(client, parking, ana, rui):
    day = next_monday()
    vaga1, vaga2 = parking(), parking()
    assert book(client, ana.headers, vaga1, at(day, 8), at(day, 12)).status_code == 201
    assert book(client, rui.headers, vaga2, at(day, 8), at(day, 12)).status_code == 201


def test_recursos_que_nao_sao_vagas_nao_tem_limite(client, admin, category, ana):
    """Sem a troca de PARKING_CATEGORY, a categoria de teste não é a das vagas."""
    day = next_monday()
    sala1, sala2 = create_resource(client, admin, category), create_resource(client, admin, category)
    assert book(client, ana.headers, sala1, at(day, 8), at(day, 10)).status_code == 201
    assert book(client, ana.headers, sala2, at(day, 14), at(day, 16)).status_code == 201


def test_pedidos_simultaneos_so_um_passa(client, parking, ana):
    """5 pedidos ao mesmo tempo, do mesmo utilizador, em 5 vagas diferentes: só 1 pode passar."""
    day = next_monday()
    vagas = [parking() for _ in range(5)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = list(pool.map(lambda v: book(client, ana.headers, v, at(day, 9), at(day, 17)).status_code, vagas))
    assert sorted(codes) == [201, 409, 409, 409, 409]


def test_nao_entra_na_fila_de_outra_vaga_no_mesmo_dia(client, parking, ana, rui):
    day = next_monday()
    vaga1, vaga2 = parking(), parking()
    assert book(client, rui.headers, vaga1, at(day, 8), at(day, 18)).status_code == 201   # vaga1 ocupada pelo Rui
    assert book(client, ana.headers, vaga2, at(day, 8), at(day, 18)).status_code == 201   # a Ana já tem a vaga2

    response = join(client, ana, vaga1, at(day, 8), at(day, 18))
    assert response.status_code == 409
    assert "vaga de estacionamento" in response.json()["detail"]


def test_nao_aceita_oferta_se_ja_tem_outra_vaga_nesse_dia(client, parking, ana, rui):
    day = next_monday()
    vaga1, vaga2 = parking(), parking()
    rui_reserva = book(client, rui.headers, vaga1, at(day, 8), at(day, 18)).json()["id"]
    entry_id = join(client, ana, vaga1, at(day, 8), at(day, 18)).json()["id"]   # Ana na fila da vaga1
    assert book(client, ana.headers, vaga2, at(day, 8), at(day, 18)).status_code == 201  # e reserva a vaga2

    assert cancel(client, rui.headers, rui_reserva).status_code == 200   # a vaga1 é oferecida à Ana
    assert entry(client, ana, entry_id)["status"] == "OFFERED"

    response = client.post(f"{FILA}/{entry_id}/aceitar", headers=ana.headers)
    assert response.status_code == 409
    assert "vaga de estacionamento" in response.json()["detail"]

PLANO = "/api/reservas/planear/confirmar"


def confirmar(client, person, day, *items):
    """Confirma um plano. Cada item é (activity_id, resource_id, "HH:MM", "HH:MM")."""
    body = {"day": day.isoformat(),
            "items": [{"activity_id": a, "resource_id": r, "start": s, "end": e} for a, r, s, e in items]}
    return client.post(PLANO, json=body, headers=person.headers)


def test_confirmar_plano_com_vaga_quando_ja_tem_outra_da_409(client, parking, ana):
    day = next_monday()
    vaga1, vaga2 = parking(), parking()
    assert book(client, ana.headers, vaga1, at(day, 8), at(day, 12)).status_code == 201  # a vaga do dia

    response = confirmar(client, ana, day, ("a1", vaga2, "14:00", "18:00"))
    assert response.status_code == 409
    assert "vaga de estacionamento" in response.json()["detail"]
    assert response.json()["activity_id"] == "a1"


def test_plano_com_duas_vagas_nao_grava_nada(client, parking, ana):
    """Tudo ou nada: a 1.ª vaga do plano passa, a 2.ª é recusada, e a 1.ª é desfeita."""
    day = next_monday()
    vaga1, vaga2 = parking(), parking()
    response = confirmar(client, ana, day, ("a1", vaga1, "08:00", "12:00"), ("a2", vaga2, "14:00", "18:00"))
    assert response.status_code == 409
    assert response.json()["activity_id"] == "a2"

    with SessionLocal() as db:
        gravadas = db.scalar(text("SELECT count(*) FROM reservations WHERE resource_id IN (:a, :b)"),
                             {"a": vaga1, "b": vaga2})
    assert gravadas == 0  # nem a primeira ficou