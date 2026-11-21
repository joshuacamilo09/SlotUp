"""Testes do CSP do SlotUp.

Rodar dentro de scheduling-service/:  python3 -m pytest -v
"""
import json
import copy
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


def test_r2_duracao_vem_do_recurso(dados):
    # Com max_duration_min=120 nas quadras, os 120 min passam a ser aceitos
    dados["activities"][3]["duration_min"] = 120
    for recurso in dados["resources"]:
        if recurso["resource_type"] == "quadra":
            recurso["max_duration_min"] = 120
    problema = montar_problema(dados, agora=AGORA)
    assert problema.dominios["padel"]  # lista não vazia conta como True


def test_r9_buffer_do_recurso(dados):
    # Sem folga na sala grande, a reunião já pode começar às 15h00 em ponto
    for recurso in dados["resources"]:
        if recurso["id"] == "sala-grande":
            recurso["buffer_min"] = 0
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
        "estacionamento": ("vaga-02", "08:45", "19:45"),
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
    problema = montar_problema(dados, agora=AGORA)
    solucao, _, stats = resolver(problema, limite_nos=10)
    assert stats.limite_atingido and stats.limite == "nos"
    assert solucao is not None  # anytime: a melhor achada até ao limite


def test_limite_de_tempo(dados):
    problema = montar_problema(dados, agora=AGORA)
    solucao, _, stats = resolver(problema, limite_ms=0)  # prazo já passado: pára no primeiro nó
    assert stats.limite_atingido and stats.limite == "tempo"
    assert solucao is None


def test_api_limite_de_tempo_explica_a_falha(cliente, dados, monkeypatch):
    # A rota passa a usar um resolver com limite de 0 ms
    monkeypatch.setattr("app.routers.plan.resolver", lambda problema: resolver(problema, limite_ms=0))
    corpo = cliente.post("/api/scheduling/plan", json=dados).json()
    assert corpo["status"] == "NO_SOLUTION"
    assert corpo["failure"]["code"] == "LIMIT_REACHED" and "tempo máximo" in corpo["failure"]["message"]
    assert corpo["stats"]["limit_reached"] and corpo["stats"]["limit"] == "time"


def test_api_pedido_grande_demais_da_422_claro(cliente, dados):
    base = dados["activities"][1]  # o trabalho (mesa)
    dados["activities"] = [{**base, "id": f"a{i}"} for i in range(11)]
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 422
    assert "No máximo 10 itens em 'activities'" in str(resposta.json()["detail"])


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

def test_api_plan_so_estacionamento_da_422(cliente, dados):
    # Fica só a atividade com covers_day (a vaga)
    dados["activities"] = [a for a in dados["activities"] if a.get("covers_day")]
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 422
    assert "pelo menos uma atividade" in str(resposta.json()["detail"])

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

# ---------------------------------------------------------------- explicação da falha
def test_failure_explica_cada_recurso(cliente, dados):
    # Reunião para 6: a sala pequena (4 lugares) não serve e a sala grande está ocupada o dia todo
    dados["busy"].append({"resource_id": "sala-grande", "start": "08:00", "end": "20:00"})
    falha = cliente.post("/api/scheduling/plan", json=dados).json()["failure"]
    assert falha["code"] == "NO_FREE_SLOT" and falha["activity_id"] == "reuniao"
    motivos = {m["resource_id"]: m for m in falha["reasons"]}  # resource_id -> motivo
    assert set(motivos) == {"sala-pequena", "sala-grande"}  # um motivo por sala, nenhum de outro tipo
    assert motivos["sala-pequena"]["rule_id"] == "CAPACIDADE"
    assert "só tem lugar para 4" in motivos["sala-pequena"]["message"]
    assert motivos["sala-grande"]["rule_id"] == "RECURSO_LIVRE"
    assert motivos["sala-grande"]["message"].startswith("Sala Grande:")


def test_failure_da_combinacao_nao_tem_motivos_por_recurso(cliente, dados):
    dados["busy"].append({"resource_id": "vaga-02", "start": "10:00", "end": "17:00"})
    falha = cliente.post("/api/scheduling/plan", json=dados).json()["failure"]
    assert falha["code"] == "PARKING_NOT_COVERED" and falha["reasons"] == []

# ---------------------------------------------------------------- modo suggest
def _sugestao(dados, **mudancas):
    """O pedido de sugestões: só a reunião (sala para 6 às 14:00; a sala grande está ocupada 14-15)."""
    reuniao = {**dados["activities"][2], **mudancas}  # ** junta os dois dicts; o da direita ganha
    return {**dados, "mode": "suggest", "max_alternatives": 3, "activities": [reuniao]}


def test_api_suggest_devolve_as_melhores_opcoes(cliente, dados):
    resposta = cliente.post("/api/scheduling/plan", json=_sugestao(dados))
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "OK" and corpo["mode"] == "suggest"
    opcoes = corpo["alternatives"]
    assert len(opcoes) == 3 and corpo["plan"] == opcoes[0]
    custos = [o["cost"] for o in opcoes]
    assert custos == sorted(custos)  # da melhor para a pior
    for opcao in opcoes:
        [item] = opcao["items"]
        assert item["resource_id"] == "sala-grande"  # a única sala que comporta 6 pessoas
        # Nenhuma opção bate na reserva das 14:00-15:00 nem no intervalo de 10 min à volta
        assert item["end"] <= "13:50" or item["start"] >= "15:10"


def test_api_suggest_respeita_o_maximo_de_alternativas(cliente, dados):
    pedido = _sugestao(dados)
    pedido["max_alternatives"] = 1
    assert len(cliente.post("/api/scheduling/plan", json=pedido).json()["alternatives"]) == 1


def test_api_suggest_sem_opcoes_explica_porque(cliente, dados):
    corpo = cliente.post("/api/scheduling/plan", json=_sugestao(dados, people=20)).json()
    assert corpo["status"] == "NO_SOLUTION" and corpo["alternatives"] is None
    assert corpo["failure"]["rule_id"] == "CAPACIDADE"


def test_api_suggest_exige_uma_so_atividade(cliente, dados):
    pedido = _sugestao(dados)
    pedido["activities"].append(dados["activities"][1])
    assert cliente.post("/api/scheduling/plan", json=pedido).status_code == 422

# ---------------------------------------------------------------- regras ligáveis
# Cada caso: (o que muda no cenário, a regra que deve aparecer no rule_id)
@pytest.mark.parametrize("mudar,regra", [
    (lambda d: d["activities"][2].update(people=9), "CAPACIDADE"),
    (lambda d: d["activities"][3].update(duration_min=120), "DURACAO"),
    (lambda d: [r.update(schedule=[]) for r in d["resources"] if r["resource_type"] == "sala"], "HORARIO_ABERTURA"),
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

def test_recurso_fechado_no_dia_da_semana(cliente, dados):
    # 12/12/2026 é um sábado: as mesas e as salas só abrem de segunda a sexta
    dados["day"] = "2026-12-12"
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    falha = resposta.json()["failure"]
    assert falha["code"] == "NO_FREE_SLOT"
    assert falha["rule_id"] == "HORARIO_ABERTURA"

def test_aceita_horas_no_formato_do_booking(cliente, dados):
    # O booking serializa as horas como "08:00:00": o contrato aceita os dois formatos
    for recurso in dados["resources"]:
        for regra in recurso["schedule"]:
            regra["open_time"] += ":00"
            regra["close_time"] += ":00"
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.json()["plan"]["cost"] == 127.0

# ---------------------------------------------------------------- horários preferidos
def test_dominio_ordenado_por_proximidade(dados):
    from app.csp.custo import melhores_opcoes
    problema = montar_problema(dados, agora=AGORA)
    # Reunião pedida às 14:00 (sala grande ocupada 14-15h): 12:45 e 15:15 estão as duas a
    # 75 min; no empate vem primeiro a mais cedo. Depois, 12:30 e 15:30, a 90 min
    inicios = [v.inicio for v in melhores_opcoes(problema, "reuniao", 4)]
    assert inicios == [12 * 60 + 45, 15 * 60 + 15, 12 * 60 + 30, 15 * 60 + 30]


def test_padel_no_horario_pedido_vem_primeiro(dados):
    from app.csp.custo import melhores_opcoes
    problema = montar_problema(dados, agora=AGORA)
    primeira = melhores_opcoes(problema, "padel", 1)[0]
    assert (primeira.resource_id, primeira.inicio) == ("padel-2", 18 * 60)  # padel-1 está ocupado às 18h


def test_primeira_solucao_ja_fica_perto_do_pedido(dados):
    # Mesmo sem otimizar, a busca experimenta primeiro os horários mais próximos
    problema = montar_problema(dados, agora=AGORA)
    _, custo, _ = resolver(problema, otimizar=False)
    assert custo <= 200

# ---------------------------------------------------------------- janela preferida
def test_fora_da_janela():
    from app.csp.custo import fora_da_janela
    from app.csp.modelo import Pedido
    manha = Pedido(id="t", resource_type="mesa", duration_min=180, desired_start=8 * 60, desired_end=13 * 60)
    assert fora_da_janela(manha, Valor("mesa-01", 10 * 60, 13 * 60)) == 0    # 10:00-13:00: cabe inteira
    assert fora_da_janela(manha, Valor("mesa-01", 11 * 60, 14 * 60)) == 60   # termina 1 h depois da janela
    hora = Pedido(id="r", resource_type="sala", duration_min=60, desired_start=14 * 60)
    assert fora_da_janela(hora, Valor("sala-grande", 15 * 60 + 15, 16 * 60 + 15)) == 75  # igual ao F1 antigo


def test_janela_prefere_o_que_cabe_dentro(dados):
    from app.csp.custo import custo_valor, melhores_opcoes
    # Reunião "à tarde, até às 18h": às 15:15 (primeira livre na sala grande) já cabe na janela
    dados["activities"][2].update(preferred_start="15:00", preferred_end="18:00")
    problema = montar_problema(dados, agora=AGORA)
    primeira = melhores_opcoes(problema, "reuniao", 1)[0]
    assert primeira.inicio == 15 * 60 + 15
    assert custo_valor(problema, "reuniao", primeira) == 0


@pytest.mark.parametrize("mudar", [
    lambda d: d["activities"][2].update(preferred_end="13:00"),                           # fim antes do início (14:00)
    lambda d: d["activities"][0].update(preferred_start="08:00", preferred_end="20:00"),  # a vaga não leva horário
])
def test_janela_invalida_da_422(cliente, dados, mudar):
    mudar(dados)
    resposta = cliente.post("/api/scheduling/plan", json=dados)
    assert resposta.status_code == 422

# ---------------------------------------------------------------- regras que a API não consegue violar
def test_regra_multiplo_15():
    # Pela API não dá para violar (a grade de candidatos e o schema já são de 15 em 15),
    # por isso testamos a regra diretamente: (problema, pedido, recurso, início, fim)
    regra = POR_ID["MULTIPLO_15"]
    assert regra.permite(None, None, None, 540, 600)       # 09:00-10:00
    assert not regra.permite(None, None, None, 545, 600)   # começa às 09:05
    assert not regra.permite(None, None, None, 540, 610)   # dura 70 min
    assert regra.permite(None, None, None, None, None)     # a vaga não tem horário próprio


# ---------------------------------------------------------------- mesma entrada, mesmo resultado
def test_mesma_entrada_mesma_resposta(cliente, dados):
    respostas = [cliente.post("/api/scheduling/plan", json=dados).json() for _ in range(5)]
    for resposta in respostas:
        resposta["stats"]["time_ms"] = 0  # o tempo muda de corrida para corrida; o resto não pode
    assert all(r == respostas[0] for r in respostas)


@pytest.mark.parametrize("semente", range(5))
def test_ordem_do_pedido_nao_muda_o_plano(semente):
    # Os mesmos dados com as atividades, os recursos e a ocupação por outra ordem
    dados = gerar_cenario(semente, 4, 0.5, 0.1)
    baralhado = copy.deepcopy(dados)  # deepcopy: cópia completa, para não mexer no original
    for lista in ("activities", "resources", "busy"):
        baralhado[lista].reverse()
    resultados = []
    for pedido in (dados, baralhado):
        problema = montar_problema(pedido, agora=AGORA)
        solucao, custo, _ = resolver(problema)
        resultados.append((custo, sorted(map(str, formatar_solucao(problema, solucao))) if solucao else None))
    assert resultados[0] == resultados[1]