"""Diagnóstico: quando não há solução, descobre o MOTIVO e a REGRA que o causou.

Devolve o failure do contrato: code (o tipo de falha), rule_id (a regra) e message.
Vai do motivo mais barato de descobrir ao mais caro: primeiro os domínios vazios
(sem busca), e só no fim volta a correr o solver.
"""
from dataclasses import replace  # cria uma cópia de um dataclass trocando só alguns campos

from app.csp.modelo import Problema
from app.csp.regras import POR_ID
from app.csp.solver import Estatisticas, resolver


def falha(code: str, activity_id: str | None, rule_id: str | None, message: str) -> dict:
    """Monta o dict no formato do Failure do schemas.py."""
    return {"code": code, "activity_id": activity_id, "rule_id": rule_id, "message": message}


def regra_decisiva(problema: Problema, pid: str):
    """A regra que deixou a atividade sem opções.

    As regras unárias são aplicadas por ordem, das estruturais (capacidade, duração,
    abertura) às de ocupação (recurso livre, intervalo). A DECISIVA é a última, nessa
    ordem, que eliminou alguma opção: as opções que sobreviveram a todas as anteriores
    morreram nela.
    """
    eliminados = problema.eliminados.get(pid, {})
    decisiva = None
    for regra in problema.regras_do_tipo("unaria"):
        if eliminados.get(regra.id, 0) > 0:
            decisiva = regra  # continua o for: fica com a ÚLTIMA
    return decisiva


def diagnosticar(problema: Problema, stats: Estatisticas) -> dict:
    # 1) Uma atividade sem nenhuma opção: o motivo é dela, não da combinação
    for pid, dominio in problema.dominios.items():
        if dominio:
            continue
        pedido = problema.pedidos[pid]
        if not any(r["resource_type"] == pedido.resource_type for r in problema.recursos):
            return falha("NO_RESOURCE", pid, None, f"Não há nenhum recurso do tipo '{pedido.resource_type}'.")
        regra = regra_decisiva(problema, pid)
        code = "NO_CAPACITY" if regra.id == "CAPACIDADE" else "NO_FREE_SLOT"
        return falha(code, pid, regra.id, regra.explicar(pedido))

    # 2) A busca parou no limite de nós antes de achar algo
    if stats.limite_atingido:
        return falha("LIMIT_REACHED", None, None, "A busca atingiu o limite antes de encontrar uma solução.")

    # 3) Todas têm opções, mas juntas não cabem. A culpa é da vaga?
    #    Teste: tirar a vaga e ver se o resto tem solução.
    vagas = [pid for pid, p in problema.pedidos.items() if p.covers_day]
    if vagas:
        sem_vaga = replace(
            problema,
            pedidos={pid: p for pid, p in problema.pedidos.items() if pid not in vagas},
            dominios={pid: d for pid, d in problema.dominios.items() if pid not in vagas},
        )
        solucao, _, _ = resolver(sem_vaga, otimizar=False)  # basta saber se EXISTE solução
        if solucao is not None:
            regra = POR_ID["VAGA_COBRE_O_DIA"]
            return falha("PARKING_NOT_COVERED", None, regra.id, regra.explicar(None))

    # 4) Sobra o conflito entre as atividades
    regra = POR_ID["SEM_SOBREPOSICAO"]
    return falha("CONFLICT", None, regra.id, regra.explicar(None))