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
from app.csp.regras import ATIVAS_POR_MODO, POR_ID
from app.csp.restricoes import compativeis, vaga_valida
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


def test_r2_duracao_fora_do_limite(dados):
    # A quadra aceita 60 a 90 min por padrão: 120 tira todas as quadras do domínio
    dados["activities"][3]["duration_min"] = 120
    problema = montar_problema(dados, agora=AGORA)
    assert problema.dominios["padel"] == []


def test_r2_params_do_recurso_ganham_ao_padrao(dados):
    # Com max_duration_min=120 nas quadras, os 120 min passam a ser aceitos
    dados["activities"][3]["duration_min"] = 120
    for recurso in dados["resources"]:
        if recurso["resource_type"] == "quadra":
            recurso["params"] = {"max_duration_min": 120}
    problema = montar_problema(dados, agora=AGORA)
    assert problema.dominios["padel"]  # lista não vazia conta como True


def test_r9_buffer_do_recurso(dados):
    # Sem folga na sala grande, a reunião já pode começar às 15h00 em ponto
    for recurso in dados["resources"]:
        if recurso["id"] == "sala-grande":
            recurso["params"] = {"buffer_min": 0}
    problema = montar_problema(dados, agora=AGORA)
    inicios = {v.inicio for v in problema.dominios["reuniao"]}
    assert 15 * 60 in inicios

def test_sem_passado_dia_anterior(dados):
    dados["day"] = "2026-11-01"
    problema = montar_problema(dados, agora=AGORA)
    assert all(d == [] for d in problema.dominios.values())  # nenhuma atividade tem opções



# ---------------------------------------------------------------- restrições binárias e globais
def test_r6_atividades_seguidas_precisam_de_folga():
    regra = POR_ID["SEM_SOBREPOSICAO"]
    mesa = Valor("mesa-01", 540, 780)                                         # 09:00-13:00
    assert not regra.compativeis(None, mesa, Valor("sala-grande", 780, 840))  # 13:00: sem tempo para ir
    assert regra.compativeis(None, mesa, Valor("sala-grande", 795, 855))      # 13:15: ok


def test_r8_duas_vagas(dados):
    dados["activities"].append({"id": "outra-vaga", "resource_type": "vaga_carro", "covers_day": True, "people":1})
    problema = montar_problema(dados, agora=AGORA)
    with pytest.raises(ValueError, match="UMA_VAGA_POR_DIA"):
        resolver(problema)


# ---------------------------------------------------------------- solver
def test_melhor_solucao_do_cenario_basico(dados):
    problema = montar_problema(dados, agora=AGORA)
    solucao, custo, _ = resolver(problema)
    assert custo == 127.0
    itens = {i["activity_id"]: (i["resource_id"], i["start"], i["end"]) for i in formatar_solucao(problema, solucao)}
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
        if not all(compativeis(problema, a, b) for i, a in enumerate(combinacao) for b in combinacao[i + 1:]):
            continue
        atribuicao = dict(zip(ids, combinacao))  # zip junta ids e valores em pares
        for vaga in problema.dominios["estacionamento"]:
            if vaga_valida(problema, vaga, atribuicao):
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
    assert corpo["plan"]["cost"] == 127.0
    assert corpo["plan"]["items"][0]["resource_name"] == "Vaga 02"
    assert corpo["failure"] is None


def test_api_plan_sem_solucao(cliente, dados, agora_fixo):
    dados["busy"].append({"resource_id": "sala-grande", "start": "08:00", "end": "20:00"})
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "NO_SOLUTION"
    assert resposta.json()["failure"]["code"] == "NO_FREE_SLOT"


def test_api_plan_regra_violada_da_422(cliente, dados, agora_fixo):
    dados["activities"].append({"id": "outra-vaga", "resource_type": "vaga_carro", "covers_day": True, "people":1})
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 422
    assert "R8" in str(resposta.json()["detail"])


def test_api_plan_campo_desconhecido_da_422(cliente, dados):
    dados["activities"][0]["is_admin"] = True  # extra="forbid" no schema
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 422

# Cada caso: (o que muda no cenário, o failure.code esperado)
@pytest.mark.parametrize("mudar,codigo", [
    (lambda d: d["activities"][2].update(people=9), "NO_CAPACITY"),
    (lambda d: d["activities"][3].update(resource_type="piscina"), "NO_RESOURCE"),
    (lambda d: d["busy"].append({"resource_id": "vaga-02", "start": "10:00", "end": "17:00"}), "PARKING_NOT_COVERED"),
])
def test_api_motivo_da_falha(cliente, dados, mudar, codigo):
    mudar(dados)
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.json()["failure"]["code"] == codigo


def test_api_suggest_ainda_nao_implementado(cliente, dados):
    dados["mode"] = "suggest"
    dados["activities"] = [dados["activities"][1]]  # suggest exige 1 atividade só
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 501

# ---------------------------------------------------------------- regras ligáveis
# Cada caso: (o que muda no cenário, a regra que deve aparecer no rule_id)
@pytest.mark.parametrize("mudar,regra", [
    (lambda d: d["activities"][2].update(people=9), "CAPACIDADE"),
    (lambda d: d["activities"][3].update(duration_min=120), "DURACAO"),
    (lambda d: [r.update(opening=[]) for r in d["resources"] if r["resource_type"] == "sala"], "HORARIO_ABERTURA"),
    (lambda d: d.update(day="2026-11-01"), "SEM_PASSADO"),
    (lambda d: d.update(day="2027-02-01"), "ANTECEDENCIA"),
    (lambda d: d["busy"].append({"resource_id": "sala-grande", "start": "08:00", "end": "20:00"}), "RECURSO_LIVRE"),
    (lambda d: d["busy"].append({"resource_id": "vaga-02", "start": "10:00", "end": "17:00"}), "VAGA_COBRE_O_DIA"),
])
def test_cada_regra_aparece_no_failure(cliente, dados, mudar, regra):
    mudar(dados)
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.json()["failure"]["rule_id"] == regra


def test_intervalo_recurso_e_a_regra_decisiva(cliente, dados):
    # A sala grande fica livre só das 10:00 às 11:00, entre duas reservas:
    # cabe a reunião de 60 min SEM folga, mas não com os 10 min de intervalo
    dados["busy"] += [
        {"resource_id": "sala-grande", "start": "08:00", "end": "10:00"},
        {"resource_id": "sala-grande", "start": "11:00", "end": "20:00"},
    ]
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.json()["failure"]["rule_id"] == "INTERVALO_RECURSO"


def test_desligar_uma_regra_muda_o_resultado(dados):
    # Com o INTERVALO_RECURSO desligado, a reunião pode começar logo às 15:00
    problema = montar_problema(dados, agora=AGORA, desligar={"INTERVALO_RECURSO"})
    inicios = {v.inicio for v in problema.dominios["reuniao"]}
    assert 15 * 60 in inicios


def test_sem_sobreposicao_so_no_modo_plano():
    assert "SEM_SOBREPOSICAO" in ATIVAS_POR_MODO["plan"]
    assert "SEM_SOBREPOSICAO" not in ATIVAS_POR_MODO["suggest"]


def test_todas_as_regras_tem_id_nome_e_mensagem():
    for regra in POR_ID.values():
        assert regra.id and regra.nome and regra.mensagem
        assert regra.tipo in {"pedido", "unaria", "binaria", "global"}