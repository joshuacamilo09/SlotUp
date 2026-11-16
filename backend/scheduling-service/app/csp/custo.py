"""Regras flexíveis (F1 a F3): cada uma soma pontos de custo. Menor custo = melhor dia.

Os pesos dizem quanto cada regra "vale". Com estes valores:
- 1 min de distância do horário pedido custa 1 ponto (F1);
- 10 min de tempo ocioso entre atividades custam 1 ponto (F2);
- não ficar com o recurso favorito custa 30 pontos (F3) = mudar 30 min de horário.
São valores para o grupo confirmar.
"""
from app.csp.modelo import FOLGA_DESLOCAMENTO_MIN, Problema, Valor
from app.csp.restricoes import tem_horario

PESO_F1 = 1.0   # por minuto de distância do horário pedido
PESO_F2 = 0.1   # por minuto de tempo ocioso
PESO_F3 = 30.0  # por não ficar com o recurso favorito


def custo_valor(problema: Problema, pid: str, valor: Valor) -> float:
    """Custo de UM pedido sozinho (F1 + F3).

    Só depende do próprio valor, então pode ser somado à medida que a busca
    avança. É isso que permite cortar ramos (branch and bound).
    """
    pedido = problema.pedidos[pid]
    custo = 0.0
    # F1: abs() é o valor absoluto, tanto faz ser 30 min antes ou 30 min depois
    if tem_horario(valor) and pedido.desired_start is not None:
        custo += PESO_F1 * abs(valor.inicio - pedido.desired_start)
    # F3: só conta se o usuário indicou um favorito
    if pedido.favorite_resource_id and valor.resource_id != pedido.favorite_resource_id:
        custo += PESO_F3
    return custo


def custo_buracos(atribuicao: dict[str, Valor]) -> float:
    """F2: tempo ocioso entre atividades seguidas (os 10 min de deslocamento não contam).

    Depende de TODAS as atividades juntas, por isso só é calculado no fim.
    """
    # Ordena as atividades pela hora de início
    atividades = sorted((v for v in atribuicao.values() if tem_horario(v)), key=lambda v: v.inicio)
    ocioso = 0
    # zip(lista, lista[1:]) dá os pares seguidos: (1ª, 2ª), (2ª, 3ª), ...
    for anterior, seguinte in zip(atividades, atividades[1:]):
        ocioso += max(0, seguinte.inicio - anterior.fim - FOLGA_DESLOCAMENTO_MIN)
    return PESO_F2 * ocioso


def custo_total(problema: Problema, atribuicao: dict[str, Valor]) -> float:
    """Custo de uma solução completa: F1 + F3 de cada pedido, mais F2 do dia todo."""
    return sum(custo_valor(problema, pid, v) for pid, v in atribuicao.items()) + custo_buracos(atribuicao)

def detalhar_custo(problema: Problema, atribuicao: dict[str, Valor]) -> dict:
    """Custo separado por regra, para a demo e o relatório mostrarem de onde vem cada ponto."""
    linhas = []
    for pid, valor in atribuicao.items():
        pedido = problema.pedidos[pid]
        # As mesmas contas de custo_valor, mas guardando F1 e F3 em separado
        f1 = 0.0
        if tem_horario(valor) and pedido.desired_start is not None:
            f1 = PESO_F1 * abs(valor.inicio - pedido.desired_start)
        f3 = 0.0
        if pedido.favorite_resource_id and valor.resource_id != pedido.favorite_resource_id:
            f3 = PESO_F3
        linhas.append((pid, f1, f3))  # uma tupla por pedido
    return {"pedidos": linhas, "f2": custo_buracos(atribuicao), "total": custo_total(problema, atribuicao)}