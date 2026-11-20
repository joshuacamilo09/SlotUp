"""Cliente do scheduling: resposta normal e plano B (timeout, em baixo, erro).

Não precisam do scheduling nem da BD: trocamos o httpx.post por uma função falsa.
"""
import httpx
import pytest

from app import scheduling_client
from app.scheduling_client import SchedulingIndisponivel, planear

PEDIDO = {"mode": "plan", "day": "2026-12-10", "activities": [], "resources": [], "busy": []}


def responde(status: int, corpo: dict | None = None):
    """Um httpx.post falso que devolve sempre a mesma resposta."""
    def falso(url, json, timeout):
        return httpx.Response(status, json=corpo or {}, request=httpx.Request("POST", url))
    return falso


def falha(erro: type[httpx.HTTPError]):
    """Um httpx.post falso que levanta sempre o mesmo erro de rede."""
    def falso(url, json, timeout):
        raise erro("simulado", request=httpx.Request("POST", url))
    return falso


def test_devolve_o_json_do_scheduling(monkeypatch):
    plano = {"status": "OK", "plan": {"cost": 0, "items": []}}
    # monkeypatch troca o httpx.post só durante este teste
    monkeypatch.setattr(scheduling_client.httpx, "post", responde(200, plano))
    assert planear(PEDIDO) == plano


def test_sem_solucao_nao_e_erro(monkeypatch):
    sem = {"status": "NO_SOLUTION", "failure": {"code": "NO_FREE_SLOT"}}
    monkeypatch.setattr(scheduling_client.httpx, "post", responde(200, sem))
    assert planear(PEDIDO)["status"] == "NO_SOLUTION"


def test_chama_o_endereco_e_o_timeout_certos(monkeypatch):
    chamada = {}

    def falso(url, json, timeout):
        chamada.update(url=url, json=json, timeout=timeout)  # guarda o que recebeu
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(scheduling_client.httpx, "post", falso)
    planear(PEDIDO)
    assert chamada["url"].endswith("/api/scheduling/plan")
    assert chamada["json"] == PEDIDO
    assert chamada["timeout"].connect == 0.5 and chamada["timeout"].read == 3.0


@pytest.mark.parametrize("erro", [httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout])
def test_plano_b_quando_o_scheduling_nao_responde(monkeypatch, erro):
    monkeypatch.setattr(scheduling_client.httpx, "post", falha(erro))
    with pytest.raises(SchedulingIndisponivel):
        planear(PEDIDO)


@pytest.mark.parametrize("status", [422, 500, 501, 503])
def test_plano_b_quando_o_scheduling_responde_com_erro(monkeypatch, status):
    monkeypatch.setattr(scheduling_client.httpx, "post", responde(status))
    with pytest.raises(SchedulingIndisponivel):
        planear(PEDIDO)