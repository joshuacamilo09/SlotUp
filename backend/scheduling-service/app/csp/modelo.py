"""Modelo do CSP: lê o pedido (formato do contrato) e monta variáveis e domínios.

As horas são guardadas como MINUTOS desde a meia-noite (09:30 -> 570).
Assim comparar e somar horas é só aritmética de inteiros.
"""
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------- parâmetros das regras
PASSO_MIN = 15               # discretização: os horários andam de 15 em 15 min
FOLGA_RECURSO_MIN = 10       # R9: padrão, quando o recurso não traz buffer_min
FOLGA_DESLOCAMENTO_MIN = 10  # R6/R7: tempo para o usuário ir de uma atividade para outra
ANTECEDENCIA_MAX_DIAS = 30   # R3: igual ao booking

# NOVO (R2): duração (mínima, máxima) por tipo, usada quando o recurso não traz params.
# Os tipos são os do booking (seed.py). As vagas não estão aqui: cobrem o dia, não têm duração.
DURACAO_PADRAO = {
    "mesa": (15, 12 * 60),
    "sala": (15, 4 * 60),
    "quadra": (60, 90),
    "personal": (60, 60),
}
# Um tipo novo criado pelo admin (ex.: "cabine") e sem params: de 15 min a 12 h
DURACAO_GENERICA = (PASSO_MIN, 12 * 60)


# ---------------------------------------------------------------- estruturas de dados
@dataclass(frozen=True)
class Valor:
    """Um valor do domínio: um recurso num horário."""
    resource_id: str
    inicio: int | None  # None no estacionamento: o horário é calculado depois (R7)
    fim: int | None


@dataclass
class Pedido:
    """Uma variável do CSP: uma atividade que o usuário quer."""
    id: str
    resource_type: str
    duration_min: int | None = None
    desired_start: int | None = None   # em minutos (no JSON chama-se preferred_start)
    people: int = 1
    favorite_resource_id: str | None = None
    covers_day: bool = False           # True = estacionamento (cobre o dia todo, R7)


@dataclass
class Problema:
    """Tudo o que o solver precisa."""
    day: date
    pedidos: dict[str, Pedido]                   # id da atividade -> Pedido
    dominios: dict[str, list[Valor]]             # id da atividade -> valores possíveis
    busy: dict[str, list[tuple[int, int]]]       # id do recurso -> intervalos ocupados, JÁ com a folga R9
    aberturas: dict[str, list[tuple[int, int]]]  # id do recurso -> janelas de abertura (em minutos)
    recursos: list[dict]                         # NOVO: os recursos recebidos (o diagnóstico de falhas precisa deles)


# ---------------------------------------------------------------- funções de apoio
def para_minutos(hhmm: str) -> int:
    """'09:30' -> 570"""
    horas, minutos = hhmm.split(":")
    return int(horas) * 60 + int(minutos)


def para_hhmm(minutos: int) -> str:
    """570 -> '09:30'"""
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def arredondar_para_cima(minutos: int) -> int:
    """Leva ao próximo múltiplo de 15 min: 610 (10:10) -> 615 (10:15)"""
    return math.ceil(minutos / PASSO_MIN) * PASSO_MIN


def sobrepoe(a_inicio: int, a_fim: int, b_inicio: int, b_fim: int) -> bool:
    """Dois intervalos se cruzam? (encostar, como 10:00-11:00 e 11:00-12:00, não conta)"""
    return a_inicio < b_fim and b_inicio < a_fim


def recurso_livre(resource_id: str, inicio: int, fim: int, busy: dict) -> bool:
    """R5 + R9: o recurso está livre? (NOVO: a folga já vem somada nos intervalos do busy)"""
    for b_inicio, b_fim in busy.get(resource_id, []):
        if sobrepoe(inicio, fim, b_inicio, b_fim):
            return False
    return True


def duracao_permitida(recurso: dict) -> tuple[int, int]:
    """NOVO (R2): (mínima, máxima) do recurso. O que vier em params ganha ao padrão do tipo."""
    padrao = DURACAO_PADRAO.get(recurso["resource_type"], DURACAO_GENERICA)
    params = recurso.get("params") or {}  # `or {}`: se params não vier, usa um dict vazio
    minimo = params.get("min_duration_min") or padrao[0]
    maximo = params.get("max_duration_min") or padrao[1]
    return minimo, maximo


# ---------------------------------------------------------------- leitura do pedido
def ler_pedido(dados: dict) -> Pedido:
    """Converte uma atividade do JSON num Pedido.

    NOVO: não valida mais a duração aqui. Como cada recurso pode ter a sua
    duração mínima e máxima, a R2 passou para o gerar_dominio, recurso a recurso.
    """
    return Pedido(
        id=dados["id"],
        resource_type=dados["resource_type"],
        duration_min=dados.get("duration_min"),
        desired_start=para_minutos(dados["preferred_start"]) if "preferred_start" in dados else None,
        people=dados["people"],  # obrigatório no contrato
        favorite_resource_id=dados.get("favorite_resource_id"),
        covers_day=dados.get("covers_day", False),
    )


def gerar_dominio(pedido: Pedido, recursos: list[dict], busy: dict, inicio_minimo: int) -> list[Valor]:
    """Todos os (recurso, horário) que passam nas regras de UMA só atividade.

    Consistência de nó: as restrições unárias (R1, R2, R4, R5, R9) são aplicadas
    aqui, uma vez, e o solver já começa com domínios menores.
    """
    valores = []
    for recurso in recursos:
        if recurso["resource_type"] != pedido.resource_type:
            continue
        if recurso["capacity"] < pedido.people:
            continue  # R4: não cabe toda a gente
        if pedido.covers_day:
            valores.append(Valor(recurso["id"], None, None))
            continue
        minimo, maximo = duracao_permitida(recurso)
        # NOVO (R2): comparação encadeada, igual a "minimo <= duração and duração <= maximo"
        if not minimo <= pedido.duration_min <= maximo:
            continue  # este recurso não aceita esta duração: passa ao próximo
        for janela in recurso["opening"]:  # NOVO: no contrato chama-se opening
            abre = para_minutos(janela["open_time"])
            fecha = para_minutos(janela["close_time"])
            inicio = arredondar_para_cima(max(abre, inicio_minimo))
            while inicio + pedido.duration_min <= fecha:
                fim = inicio + pedido.duration_min
                if recurso_livre(recurso["id"], inicio, fim, busy):
                    valores.append(Valor(recurso["id"], inicio, fim))
                inicio += PASSO_MIN
    return valores


def carregar_cenario(caminho: str, agora: datetime | None = None) -> Problema:
    """Lê um arquivo JSON de cenário (mesmo formato do contrato) e devolve o Problema."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return montar_problema(dados, agora)


def montar_problema(dados: dict, agora: datetime | None = None) -> Problema:
    """Monta o Problema a partir do pedido (formato do contrato).

    NOVO: "agora" vem do campo now do pedido. O parâmetro `agora` continua
    a existir para a demo e os testes poderem fixar a hora.
    """
    day = date.fromisoformat(dados["day"])
    if agora is None:
        # fromisoformat: "2026-12-09T15:30" -> datetime(2026, 12, 9, 15, 30)
        agora = datetime.fromisoformat(dados["now"]) if "now" in dados else datetime.now()
    hoje = agora.date()

    # R3: nada no passado e nada além do limite
    if day < hoje or day > hoje + timedelta(days=ANTECEDENCIA_MAX_DIAS):
        raise ValueError(f"O dia {day} tem de estar entre hoje e daqui a {ANTECEDENCIA_MAX_DIAS} dias (R3)")
    inicio_minimo = agora.hour * 60 + agora.minute if day == hoje else 0

    recursos = dados["resources"]

    # NOVO (R9): folga de cada recurso. `is not None` porque buffer_min = 0 é um valor válido
    # (e 0 contaria como "falso" num `or`)
    folgas = {}
    for r in recursos:
        buffer = (r.get("params") or {}).get("buffer_min")
        folgas[r["id"]] = buffer if buffer is not None else FOLGA_RECURSO_MIN

    # Agrupa os intervalos ocupados por recurso, já alargados pela folga dele.
    # Assim o recurso_livre (e a R7, no restricoes.py) não precisa saber da folga.
    busy: dict[str, list[tuple[int, int]]] = {}
    for item in dados.get("busy", []):
        folga = folgas.get(item["resource_id"], FOLGA_RECURSO_MIN)
        busy.setdefault(item["resource_id"], []).append(
            (para_minutos(item["start"]) - folga, para_minutos(item["end"]) + folga)
        )

    pedidos: dict[str, Pedido] = {}
    for item in dados["activities"]:  # NOVO: no contrato chama-se activities
        pedido = ler_pedido(item)
        if pedido.id in pedidos:
            raise ValueError(f"Atividade repetida: '{pedido.id}'")
        pedidos[pedido.id] = pedido

    dominios = {pid: gerar_dominio(p, recursos, busy, inicio_minimo) for pid, p in pedidos.items()}

    # Janelas de abertura de cada recurso (a R7 precisa delas para a vaga)
    aberturas = {
        r["id"]: [(para_minutos(j["open_time"]), para_minutos(j["close_time"])) for j in r["opening"]]
        for r in recursos
    }
    return Problema(day=day, pedidos=pedidos, dominios=dominios, busy=busy, aberturas=aberturas, recursos=recursos)