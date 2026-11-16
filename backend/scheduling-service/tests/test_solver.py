"""Testes do CSP do SlotUp.

Rodar dentro de scheduling-service/:  python3 -m pytest -v
"""
import json
from datetime import datetime
from itertools import product  # product(A, B) = todas as combinações (a, b)
from pathlib import Path

import pytest
from fastapi.testclient import TestClient  # simula pedidos HTTP sem subir o servidor

from app.csp.custo import custo_total
from app.csp.modelo import Valor, montar_problema
from app.csp.restricoes import compativeis, estacionamento_valido
from app.csp.solver import formatar_solucao, resolver
from app.main import app
from benchmark import gerar_cenario  # reaproveita o gerador de cenários aleatórios

# __file__ é este arquivo; .parent.parent sobe de tests/ para scheduling-service/
CENARIO = Path(__file__).parent.parent / "dados" / "cenario_basico.json"
AGORA = datetime(2026, 11, 17, 9, 0)  # "agora" fixo: os testes dão o mesmo resultado em qualquer dia
CONFIGS = [(False, False), (True, False), (False, True), (True, True)]  # (usar_fc, usar_mrv)


# ---------------------------------------------------------------- fixtures
# Uma fixture é preparada pelo pytest e passada a cada teste que a pede pelo nome
@pytest.fixture
def dados():
    """Cenário básico novo em cada teste (assim um teste pode alterá-lo à vontade)."""
    return json.loads(CENARIO.read_text(encoding="utf-8"))


@pytest.fixture
def cliente():
    return TestClient(app)


@pytest.fixture
def agora_fixo(monkeypatch):
    """Na API, o modelo usa a hora real. Aqui trocamos por AGORA durante o teste.

    monkeypatch substitui uma função só enquanto o teste corre e depois desfaz.
    """
    monkeypatch.setattr("app.routers.plan.montar_problema", lambda d: montar_problema(d, agora=AGORA))


# ---------------------------------------------------------------- restrições unárias (modelo.py)
def test_dominios_aplicam_restricoes_unarias(dados):
    problema = montar_problema(dados, agora=AGORA)
    tamanhos = {pid: len(d) for pid, d in problema.dominios.items()}
    assert tamanhos == {"estacionamento": 2, "trabalho": 86, "reuniao": 36, "padel": 97}


def test_r4_sala_pequena_fica_de_fora(dados):
    # 6 pessoas: a sala pequena (capacidade 4) não pode aparecer no domínio
    problema = montar_problema(dados, agora=AGORA)
    assert all(v.resource_id == "sala-grande" for v in problema.dominios["reuniao"])


def test_r9_folga_depois_de_reserva_existente(dados):
    # A sala grande está ocupada até às 15h00: 15h00 fica de fora (sem os 10 min), 15h15 entra
    problema = montar_problema(dados, agora=AGORA)
    inicios = {v.inicio for v in problema.dominios["reuniao"]}
    assert 15 * 60 not in inicios
    assert 15 * 60 + 15 in inicios


def test_r2_duracao_invalida(dados):
    dados["requests"][3]["duration_min"] = 75  # o padel só aceita 60 ou 90 min
    # pytest.raises: o teste passa só se o bloco lançar este erro, com "R2" na mensagem
    with pytest.raises(ValueError, match="R2"):
        montar_problema(dados, agora=AGORA)


def test_r3_dia_no_passado(dados):
    dados["day"] = "2026-11-01"
    with pytest.raises(ValueError, match="R3"):
        montar_problema(dados, agora=AGORA)


# ---------------------------------------------------------------- restrições binárias e globais
def test_r6_atividades_seguidas_precisam_de_folga():
    mesa = Valor("mesa-01", 540, 780)                           # 09:00-13:00
    assert not compativeis(mesa, Valor("sala-grande", 780, 840))  # 13:00: sem tempo para ir
    assert compativeis(mesa, Valor("sala-grande", 795, 855))      # 13:15: ok


def test_r8_duas_vagas(dados):
    dados["requests"].append({"id": "outra-vaga", "resource_type": "vaga", "covers_day": True})
    problema = montar_problema(dados, agora=AGORA)
    with pytest.raises(ValueError, match="R8"):
        resolver(problema)


# ---------------------------------------------------------------- solver
def test_melhor_solucao_do_cenario_basico(dados):
    problema = montar_problema(dados, agora=AGORA)
    solucao, custo, _ = resolver(problema)
    assert custo == 127.0
    itens = {i["request_id"]: (i["resource_id"], i["start"], i["end"]) for i in formatar_solucao(problema, solucao)}
    assert itens == {
        "estacionamento": ("vaga-02", "08:50", "19:40"),
        "trabalho": ("mesa-01", "09:00", "13:00"),
        "reuniao": ("sala-grande", "15:15", "16:15"),
        "padel": ("padel-2", "18:00", "19:30"),
    }


def test_otimizar_melhora_a_primeira_solucao(dados):
    problema = montar_problema(dados, agora=AGORA)
    _, custo_primeira, _ = resolver(problema, otimizar=False)
    _, custo_melhor, _ = resolver(problema)
    assert custo_melhor < custo_primeira


# parametrize: o pytest corre este teste 4 vezes, uma por configuração
@pytest.mark.parametrize("usar_fc,usar_mrv", CONFIGS)
def test_todas_as_configuracoes_chegam_ao_mesmo_custo(dados, usar_fc, usar_mrv):
    # FC e MRV só mudam a VELOCIDADE da busca, nunca o resultado
    problema = montar_problema(dados, agora=AGORA)
    _, custo, _ = resolver(problema, usar_fc=usar_fc, usar_mrv=usar_mrv)
    assert custo == 127.0


def test_sem_solucao_quando_nenhuma_sala_cabe(dados):
    dados["busy"].append({"resource_id": "sala-grande", "start": "08:00", "end": "20:00"})
    problema = montar_problema(dados, agora=AGORA)
    solucao, _, _ = resolver(problema)
    assert solucao is None


def test_sem_solucao_quando_nenhuma_vaga_cobre_o_dia(dados):
    # A vaga 01 já está ocupada; com a vaga 02 também ocupada a meio do dia, nenhuma serve
    dados["busy"].append({"resource_id": "vaga-02", "start": "10:00", "end": "17:00"})
    problema = montar_problema(dados, agora=AGORA)
    solucao, _, stats_fc = resolver(problema, otimizar=False)
    assert solucao is None
    # A propagação da R7 no FC descobre isso com muito menos trabalho do que o backtracking puro
    _, _, stats_bt = resolver(problema, usar_fc=False, usar_mrv=False, otimizar=False)
    assert stats_fc.nos < stats_bt.nos


def test_limite_de_nos(dados):
    # Com um limite minúsculo, a busca para cedo mas ainda devolve uma solução válida
    problema = montar_problema(dados, agora=AGORA)
    solucao, _, stats = resolver(problema, limite_nos=10)
    assert stats.limite_atingido
    assert solucao is not None


# ---------------------------------------------------------------- comparação com força bruta
def _forca_bruta(problema) -> float:
    """Testa TODAS as combinações possíveis e devolve o menor custo (lento, só para cenários pequenos)."""
    ids = [pid for pid, p in problema.pedidos.items() if not p.covers_day]
    melhor = float("inf")
    # O * "espalha" a lista de domínios como argumentos separados do product
    for combinacao in product(*(problema.dominios[pid] for pid in ids)):
        # R6 entre todos os pares da combinação
        if not all(compativeis(a, b) for i, a in enumerate(combinacao) for b in combinacao[i + 1:]):
            continue
        atribuicao = dict(zip(ids, combinacao))  # zip junta ids e valores em pares
        for vaga in problema.dominios["estacionamento"]:
            if estacionamento_valido(problema, vaga, atribuicao):
                # {**a, chave: valor} = cópia de a com mais uma chave
                melhor = min(melhor, custo_total(problema, {**atribuicao, "estacionamento": vaga}))
    return melhor


@pytest.mark.parametrize("semente", range(10))
@pytest.mark.parametrize("ocupacao_vagas", [0.1, 0.6])  # com e sem solução
def test_solver_igual_a_forca_bruta(semente, ocupacao_vagas):
    """Prova prática de que o branch and bound é EXATO: dá sempre o mesmo custo que testar tudo."""
    problema = montar_problema(gerar_cenario(semente, 2, 0.5, ocupacao_vagas), agora=AGORA)
    esperado = _forca_bruta(problema)
    for usar_fc, usar_mrv in CONFIGS:
        _, custo, _ = resolver(problema, usar_fc=usar_fc, usar_mrv=usar_mrv)
        assert custo == esperado


# ---------------------------------------------------------------- API
def test_api_plan_ok(cliente, dados, agora_fixo):
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "OK"
    assert corpo["cost"] == 127.0
    assert corpo["items"][0]["resource_name"] == "Vaga 02"


def test_api_plan_sem_solucao(cliente, dados, agora_fixo):
    dados["busy"].append({"resource_id": "sala-grande", "start": "08:00", "end": "20:00"})
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "NO_SOLUTION"


def test_api_plan_regra_violada_da_422(cliente, dados, agora_fixo):
    dados["requests"].append({"id": "outra-vaga", "resource_type": "vaga", "covers_day": True})
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 422
    assert "R8" in resposta.json()["detail"]


def test_api_plan_campo_desconhecido_da_422(cliente, dados):
    dados["requests"][0]["is_admin"] = True  # extra="forbid" no schema
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 422