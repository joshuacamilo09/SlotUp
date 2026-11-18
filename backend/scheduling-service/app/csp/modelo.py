"""Modelo do CSP: lê o pedido (formato do contrato) e monta variáveis e domínios.

As horas são guardadas como MINUTOS desde a meia-noite (09:30 -> 570).
Assim comparar e somar horas é só aritmética de inteiros.

As regras rígidas ficam no regras.py. Aqui só se monta o problema e se aplicam
as regras unárias (as de uma atividade só) para gerar os domínios.
"""
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------- parâmetros
PASSO_MIN = 15               # discretização: os horários andam de 15 em 15 min
MINUTOS_NO_DIA = 24 * 60
FOLGA_RECURSO_MIN = 10       # INTERVALO_RECURSO: padrão, quando o recurso não traz buffer_min
FOLGA_DESLOCAMENTO_MIN = 10  # SEM_SOBREPOSICAO / VAGA_COBRE_O_DIA: tempo de deslocamento

# DURACAO: (mínima, máxima) por tipo, usada quando o recurso não traz params
DURACAO_PADRAO = {
    "mesa": (15, 12 * 60),
    "sala": (15, 4 * 60),
    "quadra": (60, 90),
    "personal": (60, 60),
}
DURACAO_GENERICA = (PASSO_MIN, 12 * 60)  # tipo novo criado pelo admin e sem params


# ---------------------------------------------------------------- estruturas de dados
@dataclass(frozen=True)
class Valor:
    """Um valor do domínio: um recurso num horário de início (e o fim que daí resulta)."""
    resource_id: str
    inicio: int | None  # None no estacionamento: o horário vem da VAGA_COBRE_O_DIA
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
    covers_day: bool = False


@dataclass
class Problema:
    """Tudo o que o solver e as regras precisam."""
    day: date
    agora: datetime
    modo: str                                    # "plan" ou "suggest"
    pedidos: dict[str, Pedido]                   # id da atividade -> Pedido
    recursos: list[dict]                         # os recursos recebidos
    busy: dict[str, list[tuple[int, int]]]       # id do recurso -> ocupado, SEM folga (RECURSO_LIVRE)
    folgas: dict[str, int]                       # id do recurso -> minutos de folga (INTERVALO_RECURSO)
    aberturas: dict[str, list[tuple[int, int]]]  # id do recurso -> janelas de abertura
    regras: list                                 # as regras ligadas neste modo (regras.py)
    # field(default_factory=dict): cada Problema recebe o SEU dict vazio
    dominios: dict[str, list[Valor]] = field(default_factory=dict)
    # id da atividade -> {id da regra: quantas opções ela eliminou} (para o diagnóstico)
    eliminados: dict[str, dict[str, int]] = field(default_factory=dict)
    # init=False: não se passa ao criar; é calculado no __post_init__
    por_tipo: dict[str, list] = field(init=False, repr=False)

    def __post_init__(self):
        """Corre logo depois do __init__ automático do dataclass.

        Separa as regras por tipo UMA vez: o solver pergunta por elas milhares
        de vezes, e filtrar a lista em cada pergunta deixava a busca 2x mais lenta.
        """
        self.por_tipo = {t: [r for r in self.regras if r.tipo == t] for t in ("pedido", "unaria", "binaria", "global")}

    def regras_do_tipo(self, tipo: str) -> list:
        """As regras ligadas de um tipo ("pedido", "unaria", "binaria" ou "global")."""
        return self.por_tipo[tipo]


# ---------------------------------------------------------------- funções de apoio
def para_minutos(hhmm: str) -> int:
    """'09:30' -> 570"""
    horas, minutos = hhmm.split(":")
    return int(horas) * 60 + int(minutos)


def para_hhmm(minutos: int) -> str:
    """570 -> '09:30'"""
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def sobrepoe(a_inicio: int, a_fim: int, b_inicio: int, b_fim: int) -> bool:
    """Dois intervalos se cruzam? (encostar, como 10:00-11:00 e 11:00-12:00, não conta)"""
    return a_inicio < b_fim and b_inicio < a_fim


def livre_com_folga(problema: Problema, resource_id: str, inicio: int, fim: int) -> bool:
    """O recurso está livre, contando a folga dele antes e depois de cada reserva?"""
    folga = problema.folgas.get(resource_id, FOLGA_RECURSO_MIN)
    return not any(
        sobrepoe(inicio, fim, b_inicio - folga, b_fim + folga)
        for b_inicio, b_fim in problema.busy.get(resource_id, [])
    )


def duracao_permitida(recurso: dict) -> tuple[int, int]:
    """(mínima, máxima) do recurso. O que vier em params ganha ao padrão do tipo."""
    padrao = DURACAO_PADRAO.get(recurso["resource_type"], DURACAO_GENERICA)
    params = recurso.get("params") or {}
    minimo = params.get("min_duration_min") or padrao[0]
    maximo = params.get("max_duration_min") or padrao[1]
    return minimo, maximo


# ---------------------------------------------------------------- leitura do pedido
def ler_pedido(dados: dict) -> Pedido:
    """Converte uma atividade do JSON num Pedido."""
    return Pedido(
        id=dados["id"],
        resource_type=dados["resource_type"],
        duration_min=dados.get("duration_min"),
        desired_start=para_minutos(dados["preferred_start"]) if "preferred_start" in dados else None,
        people=dados["people"],
        favorite_resource_id=dados.get("favorite_resource_id"),
        covers_day=dados.get("covers_day", False),
    )


def candidatos(pedido: Pedido, recurso: dict):
    """Todos os (início, fim) a experimentar num recurso, de 15 em 15 min.

    É um GERADOR (usa yield): vai entregando um par de cada vez, sem montar a lista
    inteira na memória. Quem decide se cada par serve são as regras unárias.
    """
    if pedido.covers_day:
        yield None, None  # a vaga: só se escolhe o recurso
        return
    for inicio in range(0, MINUTOS_NO_DIA - pedido.duration_min + 1, PASSO_MIN):
        yield inicio, inicio + pedido.duration_min


def gerar_dominio(problema: Problema, pedido: Pedido) -> list[Valor]:
    """Todos os (recurso, início) de UMA atividade que passam em todas as regras unárias.

    É a consistência de nó. Para cada opção eliminada, conta QUAL regra a eliminou
    (a primeira que falhou): o diagnóstico usa essa contagem para explicar a falha.
    """
    unarias = problema.regras_do_tipo("unaria")
    eliminados: dict[str, int] = {}
    valores = []
    for recurso in problema.recursos:
        if recurso["resource_type"] != pedido.resource_type:
            continue  # o tipo define a variável: não é uma regra
        for inicio, fim in candidatos(pedido, recurso):
            # next(): a primeira regra que NÃO permite; None se todas permitirem
            falhou = next((r for r in unarias if not r.permite(problema, pedido, recurso, inicio, fim)), None)
            if falhou is None:
                valores.append(Valor(recurso["id"], inicio, fim))
            else:
                # dict.get(chave, 0) + 1: soma 1 ao contador dessa regra
                eliminados[falhou.id] = eliminados.get(falhou.id, 0) + 1
    problema.eliminados[pedido.id] = eliminados
    return valores


def carregar_cenario(caminho: str, agora: datetime | None = None, desligar: set[str] | None = None) -> Problema:
    """Lê um arquivo JSON de cenário (mesmo formato do contrato) e devolve o Problema."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return montar_problema(dados, agora, desligar)


def montar_problema(dados: dict, agora: datetime | None = None, desligar: set[str] | None = None) -> Problema:
    """Monta o Problema a partir do pedido (formato do contrato).

    agora:    fixa a hora (demo e testes); sem ele, vem do campo now do pedido.
    desligar: ids de regras a desligar (testes e benchmark; a API nunca usa).
    """
    # Import aqui dentro: o regras.py importa este arquivo, e um import no topo
    # dos dois lados seria uma importação circular
    from app.csp.regras import regras_ativas

    if agora is None:
        agora = datetime.fromisoformat(dados["now"]) if "now" in dados else datetime.now()
    modo = dados.get("mode", "plan")
    recursos = dados["resources"]

    # Folga de cada recurso. `is not None` porque buffer_min = 0 é válido (e 0 é "falso" num `or`)
    folgas = {}
    for r in recursos:
        buffer = (r.get("params") or {}).get("buffer_min")
        folgas[r["id"]] = buffer if buffer is not None else FOLGA_RECURSO_MIN

    # Ocupação crua, sem folga: a folga é a regra INTERVALO_RECURSO que soma
    busy: dict[str, list[tuple[int, int]]] = {}
    for item in dados.get("busy", []):
        busy.setdefault(item["resource_id"], []).append((para_minutos(item["start"]), para_minutos(item["end"])))

    pedidos: dict[str, Pedido] = {}
    for item in dados["activities"]:
        pedido = ler_pedido(item)
        if pedido.id in pedidos:
            raise ValueError(f"Atividade repetida: '{pedido.id}'")
        pedidos[pedido.id] = pedido

    problema = Problema(
        day=date.fromisoformat(dados["day"]),
        agora=agora,
        modo=modo,
        pedidos=pedidos,
        recursos=recursos,
        busy=busy,
        folgas=folgas,
        aberturas={
            r["id"]: [(para_minutos(j["open_time"]), para_minutos(j["close_time"])) for j in r["opening"]]
            for r in recursos
        },
        regras=regras_ativas(modo, desligar),
    )
    # Os domínios vêm depois: as regras unárias precisam do Problema já montado
    problema.dominios = {pid: gerar_dominio(problema, p) for pid, p in pedidos.items()}
    return problema