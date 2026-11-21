import time
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from app.csp.custo import custo_valor, melhores_opcoes
from app.csp.diagnostico import diagnosticar
from app.csp.modelo import montar_problema, para_hhmm
from app.csp.solver import Estatisticas, formatar_solucao, resolver
from app.exemplos import EXEMPLOS_PLAN
from app.schemas import Failure, PlanIn, PlanItem, PlanOut, PlanStats, Solution

router = APIRouter(prefix="/api/scheduling", tags=["scheduling"])


def _estatisticas(stats: Estatisticas) -> PlanStats:
    return PlanStats(nodes=stats.nos, solutions=stats.solucoes, prunes=stats.podas,
                     time_ms=round(stats.tempo_ms, 2), limit_reached=stats.limite_atingido,
                     limit={"nos": "nodes", "tempo": "time"}.get(stats.limite))  # .get: None se não parou


@router.post(
    "/plan",
    response_model=PlanOut,
    summary="Planear o dia ou sugerir horários (CSP)",
    description=(
        "Só o booking chama esta rota, pela rede interna. Com `mode=plan` devolve o plano de menor custo "
        "para todas as atividades; com `mode=suggest` (1 atividade) devolve as melhores alternativas.\n\n"
        "A resposta é **200 mesmo sem solução**: aí `status` é `NO_SOLUTION` e `failure` explica porquê. "
        "A busca pára aos 2 s ou 200 mil nós (`stats.limit`)."
    ),
    response_description="O plano, as sugestões ou o motivo da falha",
    responses={422: {"description": "Pedido inválido: campo em falta ou desconhecido, regra do pedido (ex.: 2 vagas) ou acima dos limites de tamanho"}},
)
def planear(body: Annotated[PlanIn, Body(openapi_examples=EXEMPLOS_PLAN)]) -> PlanOut:
    dados = body.model_dump(mode="json", exclude_none=True)
    try:
        problema = montar_problema(dados)
        if body.mode == "suggest":
            return _sugerir(body, problema)
        solucao, custo, stats = resolver(problema)
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro))
    estatisticas = _estatisticas(stats)
    if solucao is None:
        return PlanOut(status="NO_SOLUTION", mode=body.mode, plan=None, alternatives=None,
                       failure=Failure(**diagnosticar(problema, stats)), stats=estatisticas)
    nomes = {r.id: r.name for r in body.resources}
    itens = [PlanItem(activity_id=i["activity_id"], resource_id=i["resource_id"], resource_name=nomes[i["resource_id"]],
                      start=i["start"], end=i["end"]) for i in formatar_solucao(problema, solucao)]
    return PlanOut(status="OK", mode=body.mode, plan=Solution(cost=custo, items=itens),
                   alternatives=None, failure=None, stats=estatisticas)


def _sugerir(body: PlanIn, problema) -> PlanOut:
    """Modo suggest: as melhores opções para UMA atividade cujo horário estava ocupado.

    Com uma só atividade não há combinações a procurar: o domínio dela (já filtrado
    pelas regras unárias: capacidade, duração, abertura, livre, intervalo...) ordenado
    pelo custo (F1 + F3) já dá as melhores opções. É a mesma ordem que a busca usa.
    """
    [pid] = problema.pedidos  # o PlanIn garante: no suggest há exatamente 1 atividade
    inicio = time.perf_counter()
    opcoes = melhores_opcoes(problema, pid, body.max_alternatives)
    stats = Estatisticas(nos=len(problema.dominios[pid]), solucoes=len(opcoes),
                         tempo_ms=(time.perf_counter() - inicio) * 1000)

    if not opcoes:
        # Nenhuma opção livre: o diagnóstico diz que regra a tirou (ex.: CAPACIDADE, RECURSO_LIVRE)
        return PlanOut(status="NO_SOLUTION", mode="suggest", plan=None, alternatives=None,
                       failure=Failure(**diagnosticar(problema, stats)), stats=_estatisticas(stats))

    nomes = {r.id: r.name for r in body.resources}
    # Cada opção é uma Solution com um só item, da melhor para a pior
    solucoes = [
        Solution(cost=custo_valor(problema, pid, valor), items=[PlanItem(
            activity_id=pid, resource_id=valor.resource_id, resource_name=nomes[valor.resource_id],
            start=para_hhmm(valor.inicio), end=para_hhmm(valor.fim),
        )])
        for valor in opcoes
    ]
    # plan = a melhor; alternatives = todas, por ordem (a primeira é a mesma do plan)
    return PlanOut(status="OK", mode="suggest", plan=solucoes[0], alternatives=solucoes,
                   failure=None, stats=_estatisticas(stats))