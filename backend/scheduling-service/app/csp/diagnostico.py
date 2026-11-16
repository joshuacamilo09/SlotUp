"""Diagnóstico: quando não há solução, descobre o MOTIVO (o failure.code do contrato).

Vai do motivo mais simples ao mais caro de descobrir: primeiro olha para os domínios
vazios (sem precisar de busca), e só no fim volta a correr o solver.
"""
from dataclasses import replace  # cria uma cópia de um dataclass trocando só alguns campos

from app.csp.modelo import Problema
from app.csp.solver import Estatisticas, resolver


def falha(code: str, activity_id: str | None, message: str) -> dict:
    """Monta o dict no formato do Failure do schemas.py."""
    return {"code": code, "activity_id": activity_id, "message": message}


def diagnosticar(problema: Problema, stats: Estatisticas) -> dict:
    # 1) Uma atividade sem nenhuma opção: o motivo é dela, não da combinação
    for pid, dominio in problema.dominios.items():
        if dominio:
            continue  # tem opções: passa à próxima
        pedido = problema.pedidos[pid]
        do_tipo = [r for r in problema.recursos if r["resource_type"] == pedido.resource_type]
        if not do_tipo:
            return falha("NO_RESOURCE", pid, f"Não há nenhum recurso do tipo '{pedido.resource_type}'.")
        # all(): True se TODOS os recursos do tipo forem pequenos demais (R4)
        if all(r["capacity"] < pedido.people for r in do_tipo):
            return falha("NO_CAPACITY", pid, f"Nenhum recurso do tipo '{pedido.resource_type}' comporta {pedido.people} pessoas.")
        # Há recursos que cabem, mas nenhum horário passou em R1, R2, R5 ou R9
        return falha("NO_FREE_SLOT", pid, f"Não há nenhum horário livre para '{pid}' neste dia.")

    # 2) A busca parou no limite de nós antes de achar algo
    if stats.limite_atingido:
        return falha("LIMIT_REACHED", None, "A busca atingiu o limite antes de encontrar uma solução.")

    # 3) Todas têm opções, mas juntas não cabem. A culpa é da vaga (R7)?
    #    Teste: tirar a vaga e ver se o resto tem solução.
    vagas = [pid for pid, p in problema.pedidos.items() if p.covers_day]
    if vagas:
        sem_vaga = replace(
            problema,
            pedidos={pid: p for pid, p in problema.pedidos.items() if pid not in vagas},
            dominios={pid: d for pid, d in problema.dominios.items() if pid not in vagas},
        )
        # otimizar=False: basta saber se EXISTE uma solução, não qual é a melhor
        solucao, _, _ = resolver(sem_vaga, otimizar=False)
        if solucao is not None:
            return falha("PARKING_NOT_COVERED", None, "Nenhuma vaga fica livre durante todo o dia planeado.")

    # 4) Sobra o conflito entre as atividades (R6)
    return falha("CONFLICT", None, "As atividades não cabem todas no mesmo dia sem se sobreporem.")