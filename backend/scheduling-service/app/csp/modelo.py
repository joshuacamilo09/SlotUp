"""Modelo do CSP: lê o cenário e monta variáveis e domínios.

As horas são guardadas como MINUTOS desde a meia-noite (09:30 -> 570).
Assim comparar e somar horas é só aritmética de inteiros.
"""
import json  # para ler o arquivo .json
import math  # para arredondar para cima (math.ceil)
from dataclasses import dataclass  # cria classes simples só com dados, sem escrever __init__
from datetime import date, datetime, timedelta
from pathlib import Path  # forma moderna de lidar com caminhos de arquivos

# ---------------------------------------------------------------- parâmetros das regras
PASSO_MIN = 15               # discretização: os horários andam de 15 em 15 min
FOLGA_RECURSO_MIN = 10       # R9: folga entre reservas seguidas do mesmo recurso
FOLGA_DESLOCAMENTO_MIN = 10  # R6/R7: tempo para o usuário ir de uma atividade para outra
ANTECEDENCIA_MAX_DIAS = 30   # R3: igual ao booking

# R2: durações permitidas por tipo de recurso (em minutos)
# range(15, 241, 15) = 15, 30, 45, ..., 240 (o fim do range não entra, por isso o +1)
DURACOES = {
    "mesa": range(15, 12 * 60 + 1, PASSO_MIN),
    "sala": range(15, 4 * 60 + 1, PASSO_MIN),
    "padel": {60, 90},       # um set: só estes dois valores
    "personal": {60},
}


# ---------------------------------------------------------------- estruturas de dados
@dataclass(frozen=True)  # frozen=True: imutável, pode ser usado dentro de sets e como chave de dict
class Valor:
    """Um valor do domínio: um recurso num horário."""
    resource_id: str
    inicio: int | None  # None no estacionamento: o horário é calculado depois (R7)
    fim: int | None


@dataclass
class Pedido:
    """Uma variável do CSP: um serviço que o usuário quer."""
    id: str
    resource_type: str
    duration_min: int | None = None
    desired_start: int | None = None   # em minutos
    people: int = 1
    favorite_resource_id: str | None = None
    covers_day: bool = False           # True = estacionamento (cobre o dia todo, R7)


@dataclass
class Problema:
    """Tudo o que o solver precisa."""
    day: date
    pedidos: dict[str, Pedido]                 # id do pedido -> Pedido
    dominios: dict[str, list[Valor]]           # id do pedido -> valores possíveis
    busy: dict[str, list[tuple[int, int]]]     # id do recurso -> intervalos ocupados
    aberturas: dict[str, list[tuple[int, int]]]  # id do recurso -> janelas de abertura (em minutos)

# ---------------------------------------------------------------- funções de apoio
def para_minutos(hhmm: str) -> int:
    """'09:30' -> 570"""
    horas, minutos = hhmm.split(":")  # separa a string em duas partes
    return int(horas) * 60 + int(minutos)


def para_hhmm(minutos: int) -> str:
    """570 -> '09:30'"""
    # // é divisão inteira, % é o resto; :02d põe zero à esquerda (9 -> 09)
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def arredondar_para_cima(minutos: int) -> int:
    """Leva ao próximo múltiplo de 15 min: 610 (10:10) -> 615 (10:15)"""
    return math.ceil(minutos / PASSO_MIN) * PASSO_MIN


def sobrepoe(a_inicio: int, a_fim: int, b_inicio: int, b_fim: int) -> bool:
    """Dois intervalos se cruzam? (encostar, como 10:00-11:00 e 11:00-12:00, não conta)"""
    return a_inicio < b_fim and b_inicio < a_fim


def recurso_livre(resource_id: str, inicio: int, fim: int, busy: dict) -> bool:
    """R5 + R9: o recurso está livre, já contando a folga antes e depois das outras reservas."""
    # .get(chave, []) devolve uma lista vazia se o recurso não tiver nada ocupado
    for b_inicio, b_fim in busy.get(resource_id, []):
        if sobrepoe(inicio, fim, b_inicio - FOLGA_RECURSO_MIN, b_fim + FOLGA_RECURSO_MIN):
            return False
    return True


# ---------------------------------------------------------------- leitura do cenário
def ler_pedido(dados: dict) -> Pedido:
    """Converte um pedido do JSON num Pedido e valida a duração (R2)."""
    pedido = Pedido(
        id=dados["id"],
        resource_type=dados["resource_type"],
        duration_min=dados.get("duration_min"),
        # expressão condicional: converte só se o campo existir
        desired_start=para_minutos(dados["desired_start"]) if "desired_start" in dados else None,
        people=dados.get("people", 1),
        favorite_resource_id=dados.get("favorite_resource_id"),
        covers_day=dados.get("covers_day", False),
    )
    if not pedido.covers_day:
        if pedido.duration_min is None:
            raise ValueError(f"O pedido '{pedido.id}' precisa de duration_min")
        permitidas = DURACOES.get(pedido.resource_type)
        # `in` funciona tanto em range como em set
        if permitidas is not None and pedido.duration_min not in permitidas:
            raise ValueError(f"Duração inválida em '{pedido.id}': {pedido.duration_min} min (R2)")
    return pedido


def gerar_dominio(pedido: Pedido, recursos: list[dict], busy: dict, inicio_minimo: int) -> list[Valor]:
    """Todos os (recurso, horário) que passam nas regras de UM só pedido.

    Isto é a "consistência de nó": as restrições unárias (R1, R2, R4, R5, R9)
    são aplicadas aqui, uma vez, e o solver já começa com domínios menores.
    """
    valores = []
    for recurso in recursos:
        if recurso["resource_type"] != pedido.resource_type:
            continue  # tipo errado: passa ao próximo recurso
        if recurso["capacity"] < pedido.people:
            continue  # R4: não cabe toda a gente
        if pedido.covers_day:
            # Estacionamento: só escolhemos a vaga; o horário vem da R7 no solver
            valores.append(Valor(recurso["id"], None, None))
            continue
        for janela in recurso["schedule"]:  # R1: só dentro do horário de abertura
            abre = para_minutos(janela["open_time"])
            fecha = para_minutos(janela["close_time"])
            # R3: se o dia é hoje, nada antes de agora
            inicio = arredondar_para_cima(max(abre, inicio_minimo))
            while inicio + pedido.duration_min <= fecha:  # cabe antes de fechar?
                fim = inicio + pedido.duration_min
                if recurso_livre(recurso["id"], inicio, fim, busy):
                    valores.append(Valor(recurso["id"], inicio, fim))
                inicio += PASSO_MIN
    return valores


def carregar_cenario(caminho: str, agora: datetime | None = None) -> Problema:
    """Lê um arquivo JSON de cenário e devolve o Problema."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return montar_problema(dados, agora)


def montar_problema(dados: dict, agora: datetime | None = None) -> Problema:
    """Monta o Problema a partir de um dict (do arquivo ou, no futuro, do pedido HTTP).

    `agora` pode ser passado nos testes, para o resultado não depender do relógio.
    """
    day = date.fromisoformat(dados["day"])  # "2026-11-18" -> date(2026, 11, 18)
    agora = agora or datetime.now()          # `or`: se agora for None, usa a hora atual
    hoje = agora.date()

    # R3: nada no passado e nada além do limite
    if day < hoje or day > hoje + timedelta(days=ANTECEDENCIA_MAX_DIAS):
        raise ValueError(f"O dia {day} tem de estar entre hoje e daqui a {ANTECEDENCIA_MAX_DIAS} dias (R3)")
    inicio_minimo = agora.hour * 60 + agora.minute if day == hoje else 0

    # Agrupa os intervalos ocupados por recurso
    busy: dict[str, list[tuple[int, int]]] = {}
    for item in dados.get("busy", []):
        # setdefault cria a lista vazia na primeira vez que vê o recurso
        busy.setdefault(item["resource_id"], []).append(
            (para_minutos(item["start"]), para_minutos(item["end"]))
        )

    pedidos: dict[str, Pedido] = {}
    for item in dados["requests"]:
        pedido = ler_pedido(item)
        if pedido.id in pedidos:
            raise ValueError(f"Pedido repetido: '{pedido.id}'")
        pedidos[pedido.id] = pedido

    recursos = dados["resources"]
    # dict comprehension: monta {id_do_pedido: domínio} numa linha
    dominios = {pid: gerar_dominio(p, recursos, busy, inicio_minimo) for pid, p in pedidos.items()}

        # Guarda as janelas de abertura de cada recurso (a R7 precisa delas para a vaga)
    aberturas = {
        r["id"]: [(para_minutos(j["open_time"]), para_minutos(j["close_time"])) for j in r["schedule"]]
        for r in recursos
    }
    return Problema(day=day, pedidos=pedidos, dominios=dominios, busy=busy, aberturas=aberturas)