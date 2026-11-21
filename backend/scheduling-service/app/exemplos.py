"""Exemplos de pedidos para o Swagger (/docs): aparecem num menu ao lado do "Try it out".

São pequenos de propósito: um dia com 2 atividades e 3 recursos chega para ver
o plano, as sugestões e uma falha. O cenário completo está em dados/cenario_basico.json.
"""

# Todos os dias, das 08:00 às 20:00
_ABERTO = [{"weekday": d, "open_time": "08:00", "close_time": "20:00"} for d in range(7)]

_RECURSOS = [
    {"id": "mesa-01", "name": "Mesa 01", "resource_type": "mesa", "capacity": 1, "schedule": _ABERTO,
     "min_duration_min": 15, "max_duration_min": 720, "buffer_min": 10},
    {"id": "sala-pequena", "name": "Sala Pequena", "resource_type": "sala", "capacity": 4, "schedule": _ABERTO,
     "min_duration_min": 15, "max_duration_min": 240, "buffer_min": 10},
    {"id": "sala-grande", "name": "Sala Grande", "resource_type": "sala", "capacity": 8, "schedule": _ABERTO,
     "min_duration_min": 15, "max_duration_min": 240, "buffer_min": 10},
]
_OCUPADO = [{"resource_id": "sala-grande", "start": "14:00", "end": "15:00"}]
_BASE = {"day": "2026-12-10", "now": "2026-12-09T09:00", "resources": _RECURSOS, "busy": _OCUPADO}

_TRABALHO = {"id": "trabalho", "resource_type": "mesa", "people": 1, "duration_min": 240,
             "preferred_start": "08:00", "preferred_end": "13:00"}
_REUNIAO = {"id": "reuniao", "resource_type": "sala", "people": 6, "duration_min": 60, "preferred_start": "14:00"}

EXEMPLOS_PLAN = {
    "plan": {
        "summary": "Planear o dia (mesa de manhã + reunião às 14:00)",
        "description": "A sala grande está ocupada das 14 às 15: o CSP move a reunião para o horário livre mais perto.",
        "value": {**_BASE, "mode": "plan", "activities": [_TRABALHO, _REUNIAO]},
    },
    "suggest": {
        "summary": "Sugerir horários para uma atividade",
        "description": "O que o booking pede quando uma reserva dá 409: as melhores alternativas, da melhor para a pior.",
        "value": {**_BASE, "mode": "suggest", "max_alternatives": 3, "activities": [_REUNIAO]},
    },
    "sem_solucao": {
        "summary": "Sem solução (12 pessoas)",
        "description": "Nenhuma sala comporta 12 pessoas: a resposta traz failure com o motivo de cada sala.",
        "value": {**_BASE, "mode": "plan", "activities": [{**_REUNIAO, "people": 12}]},
    },
}