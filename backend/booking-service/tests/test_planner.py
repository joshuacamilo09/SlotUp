"""Planear o meu dia (POST /api/reservas/planear) e confirmar o plano (POST .../confirmar).

Correm contra o PostgreSQL real, mas SEM o scheduling: trocamos o
scheduling_client.planear por uma função falsa que guarda o pedido recebido.
Assim testamos o que é do booking: montar o pedido do contrato a partir do banco.
"""
import uuid

import pytest
from sqlalchemy import bindparam, text

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
    "failure": {"code": "NO_FREE_SLOT", "activity_id": "a1", "rule_id": "RECURSO_LIVRE", "message": "ocupado",
                "reasons": [{"rule_id": "RECURSO_LIVRE", "resource_id": "00000000-0000-0000-0000-000000000001",
                             "message": "Sala A: não tem nenhum horário livre com esta duração nesse dia."}]},
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
    assert body["failure"]["reasons"][0]["message"].startswith("Sala A:")


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
        ("nenhuma", []),
        ("so_estacionamento", [VAGA]),
    ],
)
def test_pedidos_invalidos_dao_422_sem_chamar_o_scheduling(client, user, scheduling, label, atividades):
    assert planear(client, user, *atividades).status_code == 422, label
    assert scheduling["pedidos"] == []


# =========================================================================== confirmar o plano
CONFIRMAR = f"{PLANEAR}/confirmar"


def item(activity_id: str, rid: str, inicio: str, fim: str) -> dict:
    return {"activity_id": activity_id, "resource_id": rid, "start": inicio, "end": fim}


def confirmar(client, headers, *itens, dia=None):
    return client.post(CONFIRMAR, json={"day": str(dia or next_monday()), "items": list(itens)}, headers=headers)


def reservas_de(client, headers) -> list[dict]:
    return client.get("/api/reservas/reservas/minhas", headers=headers).json()


def test_confirmar_sem_token_da_401(client):
    assert client.post(CONFIRMAR, json={}).status_code == 401


def test_confirmar_cria_todas_as_reservas(client, helpers, admin, category):
    eu = helpers.bearer(helpers.make_token())
    sala_a, sala_b = create_resource(client, admin, category), create_resource(client, admin, category)

    response = confirmar(client, eu, item("a1", sala_a, "09:00", "10:00"), item("a2", sala_b, "14:00", "15:30"))
    assert response.status_code == 201, response.text
    criadas = response.json()
    assert [r["status"] for r in criadas] == ["CONFIRMED", "CONFIRMED"]
    assert sorted(r["resource_id"] for r in reservas_de(client, eu)) == sorted([sala_a, sala_b])
    with SessionLocal() as db:  # um email por reserva (outbox)
        emails = db.scalar(text("SELECT count(*) FROM notifications WHERE reservation_id IN :ids")
                           .bindparams(bindparam("ids", expanding=True)), {"ids": [r["id"] for r in criadas]})
    assert emails == 2


def test_conflito_nao_reserva_nada_e_diz_qual_atividade(client, helpers, admin, category):
    day = next_monday()
    eu, outro = helpers.bearer(helpers.make_token()), helpers.bearer(helpers.make_token())
    sala_a, sala_b = create_resource(client, admin, category), create_resource(client, admin, category)
    # Entre gerar o plano e confirmar, outra pessoa reservou a sala B
    assert book(client, outro, sala_b, at(day, 14), at(day, 15)).status_code == 201

    response = confirmar(client, eu, item("a1", sala_a, "09:00", "10:00"), item("a2", sala_b, "14:00", "15:00"))
    assert response.status_code == 409
    assert response.json()["activity_id"] == "a2" and "Nada foi reservado" in response.json()["detail"]
    assert reservas_de(client, eu) == []  # a sala A (que estava livre) também não ficou reservada


def test_item_que_viola_uma_regra_da_422_e_nao_reserva_nada(client, helpers, admin, category):
    eu = helpers.bearer(helpers.make_token())
    sala_a = create_resource(client, admin, category)
    # O segundo item começa antes de a sala abrir (08:00)
    response = confirmar(client, eu, item("a1", sala_a, "09:00", "10:00"), item("a2", sala_a, "07:00", "08:00"))
    assert response.status_code == 422
    assert reservas_de(client, eu) == []


def test_recurso_inexistente_da_404(client, user):
    assert confirmar(client, user, item("a1", str(uuid.uuid4()), "09:00", "10:00")).status_code == 404


@pytest.mark.parametrize(
    "label, itens",
    [
        ("ids_repetidos", [item("a1", str(uuid.uuid4()), "09:00", "10:00")] * 2),
        ("fim_antes_do_inicio", [item("a1", str(uuid.uuid4()), "10:00", "09:00")]),
        ("hora_invalida", [item("a1", str(uuid.uuid4()), "9h", "10:00")]),
        ("campo_a_mais", [{**item("a1", str(uuid.uuid4()), "09:00", "10:00"), "resource_name": "Sala"}]),
        ("nenhum", []),
    ],
)
def test_confirmar_pedidos_invalidos_dao_422(client, user, label, itens):
    assert confirmar(client, user, *itens).status_code == 422, label


# =========================================================================== sugestões no 409 do Criar reserva
def test_conflito_ao_reservar_traz_sugestoes_do_csp(client, helpers, admin, category, scheduling):
    day = next_monday()
    rid = create_resource(client, admin, category)
    outro = helpers.bearer(helpers.make_token())
    assert book(client, outro, rid, at(day, 10), at(day, 11)).status_code == 201
    scheduling["resposta"] = {
        "status": "OK", "mode": "suggest", "failure": None, "stats": SEM_SOLUCAO["stats"], "plan": None,
        "alternatives": [{"cost": 15, "items": [{"activity_id": "pedido", "resource_id": rid,
                                                 "resource_name": "Sala X", "start": "11:15", "end": "12:15"}]}],
    }

    response = book(client, helpers.bearer(helpers.make_token()), rid, at(day, 10), at(day, 11))
    assert response.status_code == 409
    corpo = response.json()
    assert corpo["detail"] == "Este horário já está reservado"  # a mensagem de sempre continua igual
    assert corpo["alternatives"] == [{"resource_id": rid, "resource_name": "Sala X",
                                      "start_at": at(day, 11, 15).isoformat(), "end_at": at(day, 12, 15).isoformat()}]

    # O pedido ao CSP: modo suggest, a mesma hora e duração, e o recurso pedido como favorito
    [pedido] = scheduling["pedidos"]
    assert pedido["mode"] == "suggest" and pedido["max_alternatives"] == 3
    assert pedido["activities"] == [{"id": "pedido", "resource_type": "sala", "people": 1, "duration_min": 60,
                                     "preferred_start": "10:00", "favorite_resource_id": rid}]
    assert {"resource_id": rid, "start": "10:00", "end": "11:00"} in pedido["busy"]


def test_conflito_sem_scheduling_continua_409_sem_sugestoes(client, helpers, admin, category):
    # Sem a fixture "scheduling": vale a do conftest, que simula o scheduling em baixo (plano B)
    day = next_monday()
    rid = create_resource(client, admin, category)
    book(client, helpers.bearer(helpers.make_token()), rid, at(day, 10), at(day, 11))

    response = book(client, helpers.bearer(helpers.make_token()), rid, at(day, 10), at(day, 11))
    assert response.status_code == 409
    assert response.json() == {"detail": "Este horário já está reservado", "alternatives": []}

def test_mais_de_5_atividades_explica_o_limite(client, user, scheduling):
    response = planear(client, user, *[sala(id=f"a{i}") for i in range(6)])
    assert response.status_code == 422
    assert "No máximo 5 atividades" in str(response.json()["detail"])   