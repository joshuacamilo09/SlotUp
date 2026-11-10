"""Rota do CSP: POST /api/scheduling/plan ("Planear o meu dia")."""
from fastapi import APIRouter, HTTPException

from app.csp.modelo import montar_problema
from app.csp.solver import formatar_solucao, resolver
from app.schemas import PlanIn, PlanItemOut, PlanOut, PlanStats

# O prefixo segue o comentário do main.py: as rotas do CSP ficam em /api/scheduling/...
router = APIRouter(prefix="/api/scheduling", tags=["scheduling"])


@router.post("/plan", response_model=PlanOut)
def planear_dia(body: PlanIn) -> PlanOut:
    """Recebe os pedidos, os recursos e o que está ocupado; devolve a melhor combinação."""
    # Converte o Pydantic de volta em dict, que é o que o modelo.py sabe ler.
    # mode="json": a data volta a ser texto; exclude_none: tira os campos não enviados
    dados = body.model_dump(mode="json", exclude_none=True)

    try:
        problema = montar_problema(dados)
        solucao, custo, stats = resolver(problema)
    except ValueError as erro:
        # As regras que falham logo à partida (R2, R3, R8) dão 422 com a mensagem
        raise HTTPException(status_code=422, detail=str(erro))

    estatisticas = PlanStats(
        nodes=stats.nos,
        solutions=stats.solucoes,
        prunes=stats.podas,
        time_ms=round(stats.tempo_ms, 2),
        limit_reached=stats.limite_atingido,
    )

    # Sem solução não é um erro do pedido: é uma resposta válida (200) com status próprio.
    # Na 3ª entrega, é aqui que o booking pode oferecer a fila de espera.
    if solucao is None:
        return PlanOut(status="NO_SOLUTION", cost=None, items=[], stats=estatisticas)

    # Dicionário id -> nome, para a resposta mostrar nomes legíveis
    nomes = {r.id: r.name for r in body.resources}
    itens = [
        # **item "espalha" o dict como argumentos: request_id=..., resource_id=..., ...
        PlanItemOut(resource_name=nomes[item["resource_id"]], **item)
        for item in formatar_solucao(problema, solucao)
    ]
    return PlanOut(status="OK", cost=custo, items=itens, stats=estatisticas)