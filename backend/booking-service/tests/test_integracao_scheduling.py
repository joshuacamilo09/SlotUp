"""Integração booking -> scheduling, com o scheduling DE VERDADE (sem simulação).

Os outros testes do booking simulam o scheduling. Estes falam com ele por HTTP:
  * scheduling no ar: o pedido que o booking monta é aceite e o plano faz sentido;
  * scheduling derrubado: o plano B funciona (503 rápido no planear, 409 sem sugestões).

Os testes "no ar" precisam do scheduling a correr no seu computador. Noutro terminal:
    cd backend/scheduling-service && source .venv/bin/activate
    uvicorn app.main:app --port 8013
Sem ele, esses testes são pulados (SKIPPED) e os de "derrubado" correm na mesma.
O do Docker não serve: não tem porta no host.
"""
import os
import time
import uuid
from datetime import datetime

import httpx
import pytest

from app import scheduling_client
from app.config import get_settings
from app.scheduling_client import planear as planear_real  # a função verdadeira, antes da simulação do conftest
from tests.test_reservations import (  # noqa: F401  (fixtures do pytest)
    MONDAY_8_TO_20,
    RESOURCES_URL,
    admin,
    at,
    book,
    category,
    helpers,
    next_monday,
    user,
)

PLANEAR = "/api/reservas/planear"
SCHEDULING_LOCAL = os.environ.get("SCHEDULING_TEST_URL", "http://localhost:8013")


def _scheduling_no_ar() -> bool:
    try:
        return httpx.get(f"{SCHEDULING_LOCAL}/openapi.json", timeout=0.5).status_code == 200
    except httpx.HTTPError:
        return False


# Decorador: pula o teste (com o motivo) quando o scheduling local não está a correr
precisa_do_scheduling = pytest.mark.skipif(
    not _scheduling_no_ar(), reason=f"scheduling não está no ar em {SCHEDULING_LOCAL} (uvicorn app.main:app --port 8013)"
)


# --------------------------------------------------------------------------- ajudantes
@pytest.fixture
def scheduling_real(monkeypatch):
    """Desfaz a simulação do conftest e aponta o cliente para o scheduling local."""
    monkeypatch.setattr(scheduling_client, "planear", planear_real)
    monkeypatch.setattr(get_settings(), "scheduling_url", SCHEDULING_LOCAL)


@pytest.fixture
def scheduling_derrubado(monkeypatch):
    """O cliente verdadeiro, mas a apontar para uma porta onde nada responde."""
    monkeypatch.setattr(scheduling_client, "planear", planear_real)
    monkeypatch.setattr(get_settings(), "scheduling_url", "http://127.0.0.1:9")  # porta 9: fechada


def recurso_unico(client, admin, category_id: str) -> tuple[str, str]:
    """Um recurso de um tipo só dele (para o plano não usar os recursos do seed). Devolve (tipo, id)."""
    tipo = f"teste{uuid.uuid4().hex[:8]}"
    body = {"category_id": category_id, "name": f"Sala {tipo}", "resource_type": tipo, "capacity": 8,
            "schedule": MONDAY_8_TO_20}
    response = client.post(RESOURCES_URL, json=body, headers=admin)
    assert response.status_code == 201, response.text
    return tipo, response.json()["id"]


def atividade(tipo: str, pessoas: int = 2) -> dict:
    return {"id": "a1", "resource_type": tipo, "people": pessoas, "duration_min": 60, "preferred_start": "10:00"}


def fora_da_reserva(inicio: str, fim: str) -> bool:
    """True se [inicio, fim] não toca na reserva das 10:00-11:00 nem nos 10 min de intervalo à volta."""
    return fim <= "09:50" or inicio >= "11:10"  # "HH:MM" compara-se bem como texto


# --------------------------------------------------------------------------- scheduling no ar
@precisa_do_scheduling
def test_planear_e_confirmar_com_o_scheduling_real(client, helpers, admin, category, scheduling_real):
    day = next_monday()
    tipo, rid = recurso_unico(client, admin, category)
    assert book(client, helpers.bearer(helpers.make_token()), rid, at(day, 10), at(day, 11)).status_code == 201
    eu = helpers.bearer(helpers.make_token())

    corpo = client.post(PLANEAR, json={"day": str(day), "activities": [atividade(tipo)]}, headers=eu).json()
    assert corpo["status"] == "OK", corpo
    [item] = corpo["plan"]["items"]
    assert item["resource_id"] == rid
    assert fora_da_reserva(item["start"], item["end"])  # o CSP respeitou a ocupação e o intervalo

    # O plano que veio do CSP é aceite pelas regras do booking ao confirmar
    itens = [{chave: item[chave] for chave in ("activity_id", "resource_id", "start", "end")}]
    response = client.post(f"{PLANEAR}/confirmar", json={"day": str(day), "items": itens}, headers=eu)
    assert response.status_code == 201, response.text


@precisa_do_scheduling
def test_sem_solucao_com_o_scheduling_real(client, user, admin, category, scheduling_real):
    tipo, rid = recurso_unico(client, admin, category)  # capacidade 8
    corpo = client.post(PLANEAR, json={"day": str(next_monday()), "activities": [atividade(tipo, pessoas=20)]},
                        headers=user).json()
    assert corpo["status"] == "NO_SOLUTION" and corpo["failure"]["code"] == "NO_CAPACITY"
    assert corpo["failure"]["reasons"] == [
        {"rule_id": "CAPACIDADE", "resource_id": rid, "message": f"Sala {tipo}: só tem lugar para 8 (pedido: 20 pessoas)."}
    ]


@precisa_do_scheduling
def test_409_traz_sugestoes_do_scheduling_real(client, helpers, admin, category, scheduling_real):
    day = next_monday()
    _, rid = recurso_unico(client, admin, category)
    book(client, helpers.bearer(helpers.make_token()), rid, at(day, 10), at(day, 11))

    response = book(client, helpers.bearer(helpers.make_token()), rid, at(day, 10), at(day, 11))
    assert response.status_code == 409
    sugestoes = response.json()["alternatives"]
    assert 1 <= len(sugestoes) <= 3
    for sugestao in sugestoes:
        inicio, fim = datetime.fromisoformat(sugestao["start_at"]), datetime.fromisoformat(sugestao["end_at"])
        assert sugestao["resource_id"] == rid
        assert fora_da_reserva(inicio.strftime("%H:%M"), fim.strftime("%H:%M"))


# --------------------------------------------------------------------------- scheduling derrubado
def test_scheduling_derrubado_planear_da_503_rapido(client, user, scheduling_derrubado):
    inicio = time.perf_counter()
    response = client.post(PLANEAR, json={"day": str(next_monday()), "activities": [atividade("sala")]}, headers=user)
    assert response.status_code == 503 and "indisponível" in response.json()["detail"]
    assert time.perf_counter() - inicio < 2  # o timeout curto não deixa o usuário à espera


def test_scheduling_derrubado_reservar_continua_a_funcionar(client, helpers, admin, category, scheduling_derrubado):
    day = next_monday()
    _, rid = recurso_unico(client, admin, category)
    assert book(client, helpers.bearer(helpers.make_token()), rid, at(day, 10), at(day, 11)).status_code == 201

    response = book(client, helpers.bearer(helpers.make_token()), rid, at(day, 10), at(day, 11))
    assert response.status_code == 409
    assert response.json() == {"detail": "Este horário já está reservado", "alternatives": []}