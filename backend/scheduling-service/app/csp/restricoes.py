"""Restrições que envolvem mais do que um pedido (as unárias já ficaram no modelo.py).

- R6 (binária): o usuário não está em dois sítios ao mesmo tempo.
- R7 (global): a vaga cobre do início da 1ª atividade ao fim da última.
- R8 (global): no máximo 1 vaga de estacionamento por dia.
"""
from app.csp.modelo import FOLGA_DESLOCAMENTO_MIN, Problema, Valor, recurso_livre, sobrepoe


def tem_horario(valor: Valor) -> bool:
    """O estacionamento é o único valor sem horário próprio."""
    return valor.inicio is not None


def compativeis(a: Valor, b: Valor) -> bool:
    """R6: duas atividades do usuário não se cruzam, com 10 min para se deslocar.

    É uma restrição BINÁRIA (compara dois pedidos). O forward checking usa esta
    função para cortar dos outros domínios os valores que deixam de ser possíveis.
    Também cobre o caso de dois pedidos do usuário no mesmo recurso.
    """
    if not tem_horario(a) or not tem_horario(b):
        return True  # a vaga não entra na R6: ela fica ocupada "por baixo" das atividades
    # Alarga o intervalo de b em 10 min para cada lado e vê se a cai lá dentro
    return not sobrepoe(a.inicio, a.fim, b.inicio - FOLGA_DESLOCAMENTO_MIN, b.fim + FOLGA_DESLOCAMENTO_MIN)


def verificar_r8(problema: Problema) -> None:
    """R8: no máximo 1 pedido de estacionamento por dia.

    Não depende dos valores escolhidos, por isso basta verificar uma vez, antes
    de procurar solução. Se falhar, nem vale a pena correr o solver.
    """
    # list comprehension: junta os ids de todos os pedidos de estacionamento
    vagas = [p.id for p in problema.pedidos.values() if p.covers_day]
    if len(vagas) > 1:
        raise ValueError(f"No máximo 1 vaga de estacionamento por dia (R8): {vagas}")


def intervalo_estacionamento(atribuicao: dict[str, Valor]) -> tuple[int, int] | None:
    """R7: de quando a quando a vaga tem de estar reservada.

    Vai do início da primeira atividade ao fim da última, com 10 min de folga
    de cada lado (para estacionar e para chegar ao carro).
    """
    com_horario = [v for v in atribuicao.values() if tem_horario(v)]
    if not com_horario:
        return None  # só pediu estacionamento: não há nada a cobrir
    inicio = min(v.inicio for v in com_horario) - FOLGA_DESLOCAMENTO_MIN
    fim = max(v.fim for v in com_horario) + FOLGA_DESLOCAMENTO_MIN
    return inicio, fim


def estacionamento_valido(problema: Problema, vaga: Valor, atribuicao: dict[str, Valor]) -> bool:
    """R7: a vaga está aberta e livre (com a folga da R9) durante todo o intervalo.

    É uma restrição GLOBAL: só se pode verificar quando TODAS as atividades
    com horário já foram escolhidas, porque o intervalo depende de todas.
    """
    intervalo = intervalo_estacionamento(atribuicao)
    if intervalo is None:
        return True
    inicio, fim = intervalo
    # any(): True se pelo menos uma janela de abertura contém o intervalo inteiro (R1)
    dentro = any(abre <= inicio and fim <= fecha for abre, fecha in problema.aberturas.get(vaga.resource_id, []))
    return dentro and recurso_livre(vaga.resource_id, inicio, fim, problema.busy)