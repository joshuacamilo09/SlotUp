"""Solver do CSP: backtracking + forward checking (FC) + MRV + branch and bound.

- Regras rígidas: decidem se uma combinação é VÁLIDA.
- Regras flexíveis (custo.py): decidem qual das válidas é a MELHOR.

usar_fc, usar_mrv e otimizar servem para o benchmark: corremos o mesmo problema
com e sem cada técnica e comparamos.
"""
import math  # math.inf = infinito, o "melhor custo" antes de haver qualquer solução
import time
from dataclasses import dataclass

from app.csp.custo import custo_total, custo_valor, ordenar
from app.csp.modelo import Problema, Valor, para_hhmm
from app.csp.restricoes import compativeis, intervalo_estacionamento, tem_horario, vaga_valida, verificar_pedido

# Proteção da API: um pedido enorme não pode deixar o serviço preso numa busca sem fim.
# O limite que chegar primeiro pára a busca; a melhor solução achada até ali continua
# válida (branch and bound é "anytime"), só pode não ser a ótima.
LIMITE_NOS_PADRAO = 200_000      # o _ é só para ler melhor: 200000
LIMITE_TEMPO_MS_PADRAO = 2_000   # 2 s: abaixo dos 3 s que o booking espera pela resposta


@dataclass
class Estatisticas:
    """Números da busca, para o benchmark e para o relatório."""
    nos: int = 0                   # quantos valores o backtracking experimentou
    solucoes: int = 0              # quantas soluções válidas encontrou pelo caminho
    podas: int = 0                 # quantas vezes o branch and bound cortou um ramo
    tempo_ms: float = 0.0
    limite_atingido: bool = False  # True = parou antes de terminar (a solução pode não ser a ótima)
    limite: str | None = None      # QUAL limite parou a busca: "nos" ou "tempo"


class _LimiteAtingido(Exception):
    """Exceção interna: serve para "saltar" de dentro da recursão quando passa do limite.

    Leva o nome do limite ("nos" ou "tempo") para as estatísticas.
    """


@dataclass
class _Busca:
    """Estado partilhado por todas as chamadas recursivas (o _ indica uso interno)."""
    problema: Problema
    usar_fc: bool
    usar_mrv: bool
    otimizar: bool
    limite_nos: int
    stats: Estatisticas
    prazo: float = math.inf  # o relógio (time.perf_counter) a partir do qual a busca pára
    melhor_custo: float = math.inf
    melhor_solucao: dict | None = None


def resolver(problema: Problema, usar_fc: bool = True, usar_mrv: bool = True,
             otimizar: bool = True, limite_nos: int = LIMITE_NOS_PADRAO,
             limite_ms: float = LIMITE_TEMPO_MS_PADRAO):
    """Procura a solução de menor custo (ou a primeira válida, se otimizar=False).

    Devolve (solução, custo, estatísticas). A solução é um dict {id_do_pedido: Valor},
    ou None se não houver nenhuma combinação possível.
    """
    verificar_pedido(problema)  # regras do pedido inteiro (ex.: UMA_VAGA_POR_DIA): se falhar, nem começamos
    stats = Estatisticas()

    # Se um domínio já começa vazio, é impossível: não vale a pena procurar
    for dominio in problema.dominios.values():
        if not dominio:
            return None, math.inf, stats

    dominios = {pid: ordenar(problema, pid, valores) for pid, valores in problema.dominios.items()}

    busca = _Busca(problema, usar_fc, usar_mrv, otimizar, limite_nos, stats)
    inicio = time.perf_counter()  # relógio de alta precisão
    busca.prazo = inicio + limite_ms / 1000  # milissegundos -> segundos
    try:
        _backtrack(busca, {}, 0.0, dominios)
    except _LimiteAtingido as limite:
        # Branch and bound é um algoritmo "anytime": a melhor solução até aqui é válida
        stats.limite_atingido = True
        stats.limite = str(limite)  # "nos" ou "tempo"
    stats.tempo_ms = (time.perf_counter() - inicio) * 1000  # segundos -> milissegundos
    return busca.melhor_solucao, busca.melhor_custo, stats


def _escolher_variavel(problema, atribuicao, dominios, usar_mrv):
    """Escolhe o próximo pedido a decidir.

    O estacionamento fica sempre para o fim, porque a R7 depende de todas as
    outras atividades. Entre as outras, o MRV ("Minimum Remaining Values")
    escolhe a que tem MENOS opções: se ela vai falhar, que falhe cedo.
    """
    livres = [pid for pid in problema.pedidos if pid not in atribuicao]
    com_horario = [pid for pid in livres if not problema.pedidos[pid].covers_day]
    candidatos = com_horario or livres  # se já não houver atividades, sobra a vaga
    if usar_mrv:
        # key=...: compara os candidatos pelo tamanho do domínio de cada um
        return min(candidatos, key=lambda pid: len(dominios[pid]))
    return candidatos[0]  # sem MRV: a ordem em que vieram no JSON


def _consistente(problema, valor, atribuicao) -> bool:
    """O valor respeita as regras em relação ao que já foi escolhido?"""
    if tem_horario(valor):
        # R6: all() é True só se for compatível com TODOS os já escolhidos
        return all(compativeis(problema, valor, outro) for outro in atribuicao.values())
    # É a vaga: aqui todas as atividades já têm horário, então verifica a R7
    return vaga_valida(problema, valor, atribuicao)


def _forward_check(problema, valor, atribuicao, dominios):
    """Depois de escolher `valor`, corta dos pedidos ainda livres o que deixou de ser possível.

    Devolve os domínios novos, ou None se algum ficar vazio (beco sem saída:
    voltamos atrás já, sem descer mais na árvore).
    """
    if not tem_horario(valor):
        return dominios  # a vaga não corta nada nos outros
    novos = dict(dominios)  # cópia rasa: não mexemos nos domínios do nível de cima
    for pid, pedido in problema.pedidos.items():
        if pid in atribuicao:
            continue
        if pedido.covers_day:
            # Propagação da R7: o intervalo que a vaga tem de cobrir só pode CRESCER
            # à medida que entram atividades. Se nenhuma vaga cobre o intervalo de
            # agora, nenhuma vai cobrir o final: corta já, em vez de descobrir no fim.
            if not any(vaga_valida(problema, vaga, atribuicao) for vaga in dominios[pid]):
                return None
            continue
        # R6: a filtragem mantém a ordem, então o domínio continua do mais barato ao mais caro
        filtrado = [v for v in dominios[pid] if compativeis(problema, valor, v)]
        if not filtrado:
            return None
        novos[pid] = filtrado
    return novos


def _limite_inferior_resto(problema, atribuicao, dominios, excluir=None) -> float:
    """Custo MÍNIMO possível dos pedidos que ainda faltam decidir.

    Como cada domínio está ordenado pelo custo, o mínimo é o primeiro valor.
    Nenhuma solução deste ramo pode custar menos do que isto, então serve
    para o branch and bound cortar mais cedo.
    """
    total = 0.0
    for pid in problema.pedidos:
        if pid in atribuicao or pid == excluir:
            continue
        total += custo_valor(problema, pid, dominios[pid][0])
    return total


def _backtrack(busca: _Busca, atribuicao: dict, custo_parcial: float, dominios: dict) -> bool:
    """Busca em profundidade. Devolve True quando é para parar tudo (modo "primeira solução")."""
    problema = busca.problema

    if len(atribuicao) == len(problema.pedidos):
        # Solução completa: soma a F2 (que só se calcula no fim) e compara com a melhor
        busca.stats.solucoes += 1
        custo = custo_total(problema, atribuicao)
        if custo < busca.melhor_custo:
            busca.melhor_custo = custo
            busca.melhor_solucao = dict(atribuicao)  # guarda uma cópia
        # Sem otimizar, a primeira chega; a otimizar, continua a procurar melhores
        return not busca.otimizar

    var = _escolher_variavel(problema, atribuicao, dominios, busca.usar_mrv)
    # Custo mínimo dos OUTROS pedidos livres (não depende do valor escolhido para var)
    resto = _limite_inferior_resto(problema, atribuicao, dominios, excluir=var) if busca.otimizar else 0.0

    for valor in dominios[var]:
        busca.stats.nos += 1
        if busca.stats.nos > busca.limite_nos:
            raise _LimiteAtingido("nos")  # sobe pela recursão até ao try do resolver
        if time.perf_counter() > busca.prazo:
            raise _LimiteAtingido("tempo")

        novo_custo = custo_parcial + custo_valor(problema, var, valor)

        # BRANCH AND BOUND: o melhor que este ramo pode dar é novo_custo + resto.
        # Se isso já empata ou passa o melhor, o ramo nunca vai ganhar. Como o
        # domínio está ordenado, os valores seguintes também não: break.
        if busca.otimizar and novo_custo + resto >= busca.melhor_custo:
            busca.stats.podas += 1
            break

        if not _consistente(problema, valor, atribuicao):
            continue  # viola uma regra rígida: experimenta o próximo valor

        atribuicao[var] = valor  # decide provisoriamente

        if busca.usar_fc:
            novos = _forward_check(problema, valor, atribuicao, dominios)
            if novos is None:
                del atribuicao[var]  # desfaz a decisão
                continue
            # Com os domínios já cortados pelo FC, o limite inferior pode ter subido:
            # vale a pena testar a poda outra vez (aqui é continue, não break,
            # porque outro valor pode cortar menos os domínios dos outros)
            if busca.otimizar and novo_custo + _limite_inferior_resto(problema, atribuicao, novos) >= busca.melhor_custo:
                busca.stats.podas += 1
                del atribuicao[var]
                continue
        else:
            novos = dominios

        parar = _backtrack(busca, atribuicao, novo_custo, novos)
        del atribuicao[var]  # backtracking: desfaz antes de experimentar o próximo
        if parar:
            return True
    return False


def formatar_solucao(problema: Problema, solucao: dict[str, Valor]) -> list[dict]:
    """Converte a solução em dicts legíveis (horas em HH:MM), ordenados por início."""
    intervalo = intervalo_estacionamento(solucao)
    itens = []
    for pid, valor in solucao.items():
        if tem_horario(valor):
            inicio, fim = valor.inicio, valor.fim
        else:
            inicio, fim = intervalo or (None, None)  # a vaga usa o intervalo da R7
        itens.append({
            "activity_id": pid,
            "resource_id": valor.resource_id,
            "start": para_hhmm(inicio) if inicio is not None else None,
            "end": para_hhmm(fim) if fim is not None else None,
        })
    return sorted(itens, key=lambda item: item["start"] or "")