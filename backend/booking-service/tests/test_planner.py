"""Planear o meu dia (POST /api/reservas/planear).

Correm contra o PostgreSQL real, mas SEM o scheduling: trocamos o
scheduling_client.planear por uma função falsa que guarda o pedido recebido.
Assim testamos o que é do booking: montar o pedido do contrato a partir do banco.
"""
import uuid

import pytest
from sqlalchemy import text

from app import scheduling_client
from app.database import SessionLocal
from app.scheduling_client import SchedulingIndisponivel
from tests.test_reservations import (  # noqa: F401  (fixtures do pytest)
    RESOURCES_URL,
    admin,
    at,
    book,
    category,
    create_resource,
    helpers,
    next_monday,
    user,
)

PLANEAR = "/api/reservas/planear"
SEM_SOLUCAO = {
    "status": "NO_SOLUTION", "mode": "plan", "plan": None, "alternatives": None,
    "failure": {"code": "NO_FREE_SLOT", "activity_id": "a1", "rule_id": "RECURSO_LIVRE", "message": "ocupado"},
    "stats": {"nodes": 0, "solutions": 0, "prunes": 0, "time_ms": 0.1, "limit_reached": False},
}


# --------------------------------------------------------------------------- ajudantes
@pytest.fixture
def scheduling(monkeypatch):
    """Um scheduling falso: guarda os pedidos e devolve `resposta` (por omissão, sem solução)."""
    falso = {"pedidos": [], "resposta": SEM_SOLUCAO}

    def planear(pedido):
        falso["pedidos"].append(pedido)
        return falso["resposta"]

    monkeypatch.setattr(scheduling_client, "planear", planear)
    return falso


def sala(minutos=60, inicio="09:00", fim=None, id="a1", pessoas=1) -> dict:
    atividade = {"id": id, "resource_type": "sala", "people": pessoas, "duration_min": minutos, "preferred_start": inicio}
    if fim:
        atividade["preferred_end"] = fim
    return atividade


def planear(client, headers, *atividades, dia=None):
    body = {"day": str(dia or next_monday()), "activities": list(atividades)}
    return client.post(PLANEAR, json=body, headers=headers)


def do_recurso(lista: list[dict], rid: str) -> list[dict]:
    return [x for x in lista if x.get("id", x.get("resource_id")) == rid]


# --------------------------------------------------------------------------- autenticação
def test_sem_token_da_401(client):
    assert client.post(PLANEAR, json={}).status_code == 401


# --------------------------------------------------------------------------- o pedido ao scheduling
def test_monta_o_pedido_do_contrato(client, admin, user, category, scheduling):
    rid = create_resource(client, admin, category)
    response = planear(client, user, sala(fim="13:00", pessoas=4))
    assert response.status_code == 200, response.text

    [pedido] = scheduling["pedidos"]
    assert pedido["mode"] == "plan" and pedido["day"] == str(next_monday())
    assert "T" in pedido["now"] and "+" not in pedido["now"]  # hora local, sem fuso
    assert pedido["activities"] == [{"id": "a1", "resource_type": "sala", "people": 4, "duration_min": 60,
                                     "preferred_start": "09:00", "preferred_end": "13:00", "covers_day": False}]
    [recurso] = do_recurso(pedido["resources"], rid)
    assert recurso["schedule"] == [{"weekday": 0, "open_time": "08:00", "close_time": "20:00"}]
    assert (recurso["min_duration_min"], recurso["max_duration_min"], recurso["buffer_min"]) == (15, 240, 10)
    assert all(r["resource_type"] == "sala" for r in pedido["resources"])  # só os tipos pedidos


def test_ocupacao_tem_held_e_confirmed_e_nao_tem_cancelled(client, helpers, admin, user, category, scheduling):
    day = next_monday()
    rid = create_resource(client, admin, category)
    outro = helpers.bearer(helpers.make_token())
    book(client, outro, rid, at(day, 10), at(day, 11))
    cancelada = book(client, outro, rid, at(day, 14), at(day, 15)).json()["id"]
    with SessionLocal() as db:
        db.execute(text("UPDATE reservations SET status = 'CANCELLED', cancelled_at = now() WHERE id = :id"),
                   {"id": cancelada})
        db.commit()

    planear(client, user, sala())
    ocupado = do_recurso(scheduling["pedidos"][0]["busy"], rid)
    assert ocupado == [{"resource_id": rid, "start": "10:00", "end": "11:00"}]


def test_recurso_desativado_nao_entra(client, admin, user, category, scheduling):
    rid = create_resource(client, admin, category)
    client.patch(f"{RESOURCES_URL}/{rid}", json={"is_active": False}, headers=admin)
    planear(client, user, sala())
    assert do_recurso(scheduling["pedidos"][0]["resources"], rid) == []


def test_favorito_e_o_recurso_mais_reservado(client, helpers, admin, category, scheduling):
    day = next_monday()
    eu = helpers.bearer(helpers.make_token(sub=str(uuid.uuid4())))
    preferida = create_resource(client, admin, category)
    book(client, eu, preferida, at(day, 9), at(day, 10))
    book(client, eu, preferida, at(day, 11), at(day, 12))

    planear(client, eu, sala())
    assert scheduling["pedidos"][0]["activities"][0]["favorite_resource_id"] == preferida


def test_sem_historico_nao_ha_favorito(client, user, scheduling):
    planear(client, user, sala())
    assert "favorite_resource_id" not in scheduling["pedidos"][0]["activities"][0]


# --------------------------------------------------------------------------- a resposta
def test_devolve_o_plano_sem_custo_nem_estatisticas(client, user, scheduling):
    rid = str(uuid.uuid4())
    scheduling["resposta"] = {
        "status": "OK", "mode": "plan", "alternatives": None, "failure": None, "stats": SEM_SOLUCAO["stats"],
        "plan": {"cost": 12.5, "items": [{"activity_id": "a1", "resource_id": rid, "resource_name": "Sala A",
                                          "start": "09:00", "end": "10:00"}]},
    }
    body = planear(client, user, sala()).json()
    assert body == {"status": "OK", "failure": None, "plan": {"items": [
        {"activity_id": "a1", "resource_id": rid, "resource_name": "Sala A", "start": "09:00", "end": "10:00"}]}}


def test_sem_solucao_devolve_o_motivo(client, user, scheduling):
    body = planear(client, user, sala()).json()
    assert body["status"] == "NO_SOLUTION" and body["plan"] is None
    assert body["failure"]["rule_id"] == "RECURSO_LIVRE"


def test_plano_b_scheduling_indisponivel_da_503(client, user, monkeypatch):
    def em_baixo(pedido):
        raise SchedulingIndisponivel

    monkeypatch.setattr(scheduling_client, "planear", em_baixo)
    response = planear(client, user, sala())
    assert response.status_code == 503 and "indisponível" in response.json()["detail"]


# --------------------------------------------------------------------------- pedidos inválidos
VAGA = {"id": "v1", "resource_type": "vaga_carro", "covers_day": True}


@pytest.mark.parametrize(
    "label, atividades",
    [
        ("duas_vagas", [VAGA, {**VAGA, "id": "v2"}]),
        ("vaga_com_duracao", [{**VAGA, "duration_min": 60}]),
        ("ids_repetidos", [sala(), sala()]),
        ("mais_de_5", [sala(id=f"a{i}") for i in range(6)]),
        ("fora_dos_15_min", [sala(minutos=50)]),
        ("sem_horario", [{"id": "a1", "resource_type": "sala", "duration_min": 60}]),
        ("janela_ao_contrario", [sala(inicio="13:00", fim="08:00")]),
        ("so_estacionamento", [VAGA]),
        ("nenhuma", []),
    ],
)
def test_pedidos_invalidos_dao_422_sem_chamar_o_scheduling(client, user, scheduling, label, atividades):
    assert planear(client, user, *atividades).status_code == 422, label
    assert scheduling["pedidos"] == []