"""Ligação entre o solver e as regras: o solver pergunta aqui, sem saber que regras existem.

Assim ligar ou desligar uma regra (regras.py) não obriga a mexer no solver.
"""
from app.csp.modelo import FOLGA_DESLOCAMENTO_MIN, Problema, Valor


def tem_horario(valor: Valor) -> bool:
    """O estacionamento é o único valor sem horário próprio."""
    return valor.inicio is not None


def intervalo_estacionamento(atribuicao: dict[str, Valor]) -> tuple[int, int] | None:
    """De quando a quando a vaga tem de estar reservada: da 1ª à última atividade, mais a folga."""
    com_horario = [v for v in atribuicao.values() if tem_horario(v)]
    if not com_horario:
        return None
    inicio = min(v.inicio for v in com_horario) - FOLGA_DESLOCAMENTO_MIN
    fim = max(v.fim for v in com_horario) + FOLGA_DESLOCAMENTO_MIN
    return inicio, fim


def verificar_pedido(problema: Problema) -> None:
    """Regras do tipo "pedido": se uma falhar, o pedido está errado (a rota responde 422)."""
    for regra in problema.regras_do_tipo("pedido"):
        if not regra.verificar_pedido(problema):
            raise ValueError(f"{regra.nome}: {regra.mensagem} ({regra.id})")


def compativeis(problema: Problema, a: Valor, b: Valor) -> bool:
    """Regras binárias: dois valores escolhidos podem estar juntos no mesmo plano?"""
    return all(regra.compativeis(problema, a, b) for regra in problema.regras_do_tipo("binaria"))


def vaga_valida(problema: Problema, vaga: Valor, atribuicao: dict[str, Valor]) -> bool:
    """Regras globais: a vaga serve para as atividades já escolhidas?"""
    return all(regra.vaga_valida(problema, vaga, atribuicao) for regra in problema.regras_do_tipo("global"))