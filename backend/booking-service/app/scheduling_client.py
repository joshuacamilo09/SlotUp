"""Cliente HTTP do scheduling-service (o CSP).

O booking é o único que fala com o scheduling, pela rede interna do Docker
(http://scheduling:8003). O Nginx não tem rota para ele: o browser nunca o chama.

Plano B: se o scheduling estiver em baixo, demorar ou responder com erro, levantamos
SchedulingIndisponivel. O main.py transforma-a num 503 com uma mensagem amigável.
As reservas normais (uma a uma) nunca passam por aqui, por isso continuam a funcionar.
"""
import logging

import httpx

from app.config import get_settings

log = logging.getLogger("booking.scheduling")

# Timeout curto: 0,5 s para ligar e 3 s no total. O solver costuma responder em
# menos de 100 ms; se demorar mais do que isto, é melhor desistir do que deixar o
# usuário (e a thread do servidor) presos à espera.
TIMEOUT = httpx.Timeout(3.0, connect=0.5)


class SchedulingIndisponivel(Exception):
    """O scheduling não respondeu a tempo, está em baixo ou respondeu com erro."""


def _chamar(caminho: str, pedido: dict) -> dict:
    """POST ao scheduling. Devolve o JSON da resposta (o PlanOut do contrato)."""
    url = f"{get_settings().scheduling_url}{caminho}"
    try:
        resposta = httpx.post(url, json=pedido, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        # HTTPError cobre timeout, ligação recusada, nome não encontrado (DNS)...
        log.warning("scheduling_indisponivel caminho=%s erro=%s", caminho, exc.__class__.__name__)
        raise SchedulingIndisponivel from exc

    if resposta.status_code != 200:
        # 422 = o booking montou mal o pedido (é bug nosso); 5xx = erro do scheduling.
        # Para o usuário é igual: o planeador não está disponível agora.
        log.error("scheduling_erro caminho=%s status=%s corpo=%s", caminho, resposta.status_code, resposta.text[:300])
        raise SchedulingIndisponivel

    # NO_SOLUTION também vem com 200: "não há plano" é uma resposta válida, não um erro
    return resposta.json()


def planear(pedido: dict) -> dict:
    """Pede um plano ao CSP (modo "plan" ou "suggest", vai dentro do pedido)."""
    return _chamar("/api/scheduling/plan", pedido)