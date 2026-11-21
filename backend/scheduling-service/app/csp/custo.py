"""Regras flexíveis (F1 a F3): cada uma soma pontos de custo. Menor custo = melhor dia.

Os pesos dizem quanto cada regra "vale". Com estes valores:
- 1 min fora da janela preferida custa 1 ponto (F1);
- 10 min de tempo ocioso entre atividades custam 1 ponto (F2);
- não ficar com o recurso favorito custa 30 pontos (F3) = mudar 30 min de horário.
São valores para o grupo confirmar.
"""
from app.csp.modelo import FOLGA_DESLOCAMENTO_MIN, Problema, Valor
from app.csp.restricoes import tem_horario

PESO_F1 = 1.0   # por minuto fora da janela preferida
PESO_F2 = 0.1   # por minuto de tempo ocioso
PESO_F3 = 30.0  # por não ficar com o recurso favorito

def fora_da_janela(pedido, valor: Valor) -> int:
    """F1: minutos que a atividade fica FORA da janela preferida (0 se couber inteira)."""
    inicio_janela = pedido.desired_start
    # Sem preferred_end, a janela é a "hora específica": do início pedido até início + duração
    fim_janela = pedido.desired_end if pedido.desired_end is not None else inicio_janela + (valor.fim - valor.inicio)
    # max(0, ...): só conta o lado que sai da janela; o que fica dentro não custa nada
    return max(0, inicio_janela - valor.inicio) + max(0, valor.fim - fim_janela)

def custo_valor(problema: Problema, pid: str, valor: Valor) -> float:
    """Custo de UM pedido sozinho (F1 + F3).

    Só depende do próprio valor, então pode ser somado à medida que a busca
    avança. É isso que permite cortar ramos (branch and bound).
    """
    pedido = problema.pedidos[pid]
    custo = 0.0
    # F1: minutos fora da janela preferida (antes ou depois, tanto faz)
    if tem_horario(valor) and pedido.desired_start is not None:
        custo += PESO_F1 * fora_da_janela(pedido, valor)
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
            f1 = PESO_F1 * fora_da_janela(pedido, valor)
        f3 = 0.0
        if pedido.favorite_resource_id and valor.resource_id != pedido.favorite_resource_id:
            f3 = PESO_F3
        linhas.append((pid, f1, f3))  # uma tupla por pedido
    return {"pedidos": linhas, "f2": custo_buracos(atribuicao), "total": custo_total(problema, atribuicao)}

def ordenar(problema: Problema, pid: str, valores: list[Valor]) -> list[Valor]:
    """Opções da atividade da mais perto para a mais longe do que o usuário pediu.

    O critério é o custo da própria opção (F1 + F3): a distância em minutos do
    horário preferido, mais 30 se não for o recurso favorito. Sem favorito, é pura
    proximidade. Ordenar pelo custo também é o que o branch and bound precisa: o
    primeiro valor de cada domínio tem de ser o mais barato.

    Empates (ex.: 15 min antes ou 15 min depois): vem primeiro o mais cedo, e depois
    o recurso por id, para o resultado ser sempre o mesmo para o mesmo pedido.
    """
    # A chave é uma tupla: o Python compara o 1.º elemento e, se empatar, o 2.º, e assim por diante.
    # A vaga não tem início (None): -1 só serve para a tupla poder ser comparada.
    chave = lambda v: (custo_valor(problema, pid, v), v.inicio if v.inicio is not None else -1, v.resource_id)
    return sorted(valores, key=chave)


def melhores_opcoes(problema: Problema, pid: str, quantas: int) -> list[Valor]:
    """As `quantas` opções mais próximas do pedido (a base das sugestões de conflito)."""
    # [:quantas]: fatia com os primeiros `quantas` elementos da lista
    return ordenar(problema, pid, problema.dominios[pid])[:quantas]