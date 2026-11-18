"""Rota do CSP: POST /api/scheduling/plan (formato do documentacao/contrato-scheduling.md)."""
from fastapi import APIRouter, HTTPException

from app.csp.diagnostico import diagnosticar
from app.csp.modelo import montar_problema
from app.csp.solver import formatar_solucao, resolver
from app.schemas import Failure, PlanIn, PlanItem, PlanOut, PlanStats, Solution

router = APIRouter(prefix="/api/scheduling", tags=["scheduling"])


@router.post("/plan", response_model=PlanOut)
def planear(body: PlanIn) -> PlanOut:
    """Modo plan: o melhor plano do dia, ou o motivo de não haver nenhum."""
    # 501 = "Not Implemented": a rota existe e o pedido é válido, mas este modo ainda não está pronto
    if body.mode == "suggest":
        raise HTTPException(status_code=501, detail="O modo suggest ainda não está implementado")

    # Pydantic -> dict, que é o que o modelo.py sabe ler (exclude_none tira os campos não enviados)
    dados = body.model_dump(mode="json", exclude_none=True)
    try:
        problema = montar_problema(dados)
        solucao, custo, stats = resolver(problema)
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro))  # R3 e afins: o pedido está errado

    estatisticas = PlanStats(
        nodes=stats.nos,
        solutions=stats.solucoes,
        prunes=stats.podas,
        time_ms=round(stats.tempo_ms, 2),
        limit_reached=stats.limite_atingido,
    )

    # Sem solução é uma resposta válida (200), com o motivo em failure
    if solucao is None:
        return PlanOut(
            status="NO_SOLUTION",
            mode=body.mode,
            plan=None,
            alternatives=None,
            failure=Failure(**diagnosticar(problema, stats)),  # ** espalha o dict como argumentos
            stats=estatisticas,
        )

    nomes = {r.id: r.name for r in body.resources}  # id -> nome legível
    itens = [
        PlanItem(
            activity_id=item["activity_id"],
            resource_id=item["resource_id"],
            resource_name=nomes[item["resource_id"]],
            start=item["start"],
            end=item["end"],
        )
        for item in formatar_solucao(problema, solucao)
    ]
    return PlanOut(
        status="OK",
        mode=body.mode,
        plan=Solution(cost=custo, items=itens),
        alternatives=None,
        failure=None,
        stats=estatisticas,
    )