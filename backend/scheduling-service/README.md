# SlotUp · scheduling-service (protótipo de IA)

Protótipo da componente de Inteligência Artificial do SlotUp: um **Problema de Satisfação de Restrições (CSP)** que resolve o "Planear o meu dia".

O usuário pede vários serviços de uma vez (por exemplo estacionamento, mesa de coworking, sala de reunião e padel). O CSP devolve a **melhor combinação de recursos e horários** que respeita todas as regras do complexo.

- **Algoritmo:** backtracking + forward checking + heurística MRV + branch and bound.
- **Implementação:** Python puro, sem bibliotecas de CSP.
- **Interface:** API FastAPI (`POST /api/scheduling/plan`) e demonstração no terminal.

Milestone 2 da UC de Inteligência Artificial · Grupo 04.

## Estrutura

```
scheduling-service/
├── app/
│   ├── csp/
│   │   ├── modelo.py        # lê o cenário, monta variáveis e domínios (restrições unárias)
│   │   ├── restricoes.py    # restrições binárias e globais (R6, R7, R8)
│   │   ├── custo.py         # regras flexíveis (F1, F2, F3)
│   │   └── solver.py        # backtracking + FC + MRV + branch and bound
│   ├── routers/
│   │   ├── health.py
│   │   └── plan.py          # POST /api/scheduling/plan
│   ├── schemas.py           # formatos de entrada e saída (Pydantic)
│   ├── config.py
│   └── main.py
├── dados/
│   └── cenario_basico.json  # cenário de exemplo
├── tests/
│   └── test_solver.py       # testes das regras, do solver e da API
├── demo.py                  # demonstração no terminal
├── benchmark.py             # comparação BT, BT+FC, BT+MRV e BT+FC+MRV
├── requirements.txt
└── requirements-dev.txt
```

## Instalação

Requer **Python 3.10 ou superior** (testado com 3.14). Todos os comandos partem da raiz deste serviço.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

## Como executar

### 1. Demonstração no terminal

```bash
python3 demo.py                           # usa dados/cenario_basico.json
python3 demo.py dados/outro_cenario.json  # outro cenário no mesmo formato
```

A demonstração mostra, por ordem:
1. os serviços pedidos;
2. o tamanho de cada domínio depois das restrições unárias;
3. a **primeira** solução válida (só regras rígidas);
4. a **melhor** solução (com as regras flexíveis), com o custo detalhado e as estatísticas da busca.

### 2. API

```bash
uvicorn app.main:app --reload --port 8013
```

Noutro terminal:

```bash
curl -s -X POST http://localhost:8013/api/scheduling/plan \
  -H "Content-Type: application/json" \
  -d @dados/cenario_basico.json | python3 -m json.tool
```

Também dá para testar pelo navegador em **http://localhost:8013/docs** (Swagger).

> No projeto, este serviço corre na porta 8003 do Docker Compose. A porta 8013 é só para correr localmente sem conflito com os contentores.

### 3. Testes

```bash
python3 -m pytest -v
```

Os testes cobrem cada regra, a melhor solução do cenário básico, a API e uma **comparação com força bruta** em 20 cenários aleatórios: o solver chega sempre ao mesmo custo que a busca exaustiva, nas 4 configurações.

### 4. Benchmark

```bash
python3 benchmark.py
```

Gera cenários aleatórios **reproduzíveis** (sementes fixas), compara as 4 configurações do solver e grava os resultados em `resultados/benchmark.csv`. Demora cerca de 1 minuto, porque o backtracking puro é lento nos cenários maiores (é isso que o benchmark mostra).

## Formato do cenário

O mesmo JSON serve para a demonstração, para a API e para os testes:

| Campo | O que é | Na integração, vem de |
|---|---|---|
| `day` | Dia a planear (`AAAA-MM-DD`) | Escolha do usuário |
| `requests` | Serviços pedidos (as **variáveis** do CSP) | Tela "Planear o meu dia" |
| `resources` | Recursos ativos, com o horário de abertura **daquele dia** | Tabelas `resources` e `availability_rules` |
| `busy` | Intervalos já reservados (CONFIRMED ou HELD) | Tabela `reservations` |

Campos de cada pedido em `requests`:

| Campo | Obrigatório | Descrição |
|---|---|---|
| `id` | sim | Nome do pedido (único) |
| `resource_type` | sim | `mesa`, `sala`, `vaga`, `padel` ou `personal` |
| `duration_min` | sim, exceto vaga | Duração em minutos |
| `desired_start` | não | Horário preferido (`HH:MM`) |
| `people` | não | Número de pessoas (padrão 1) |
| `favorite_resource_id` | não | Recurso preferido |
| `covers_day` | só na vaga | `true`: a vaga cobre o dia todo |

As horas são sempre **hora local do complexo**, sem fuso.

## Regras implementadas

**Regras rígidas** (nunca podem ser violadas):

| ID | Regra | Onde é verificada |
|---|---|---|
| R1 | Horário de funcionamento | `modelo.py` (domínios) |
| R2 | Duração mínima e máxima por tipo | `modelo.py` (domínios) |
| R3 | Nada no passado, até 30 dias à frente | `modelo.py` (domínios) |
| R4 | Capacidade do recurso | `modelo.py` (domínios) |
| R5 | Recurso livre (sem CONFIRMED ou HELD) | `modelo.py` (domínios) |
| R6 | Usuário sem sobreposição, com 10 min de deslocamento | `restricoes.py` (forward checking) |
| R7 | A vaga cobre da 1ª à última atividade | `restricoes.py` (propagada no forward checking) |
| R8 | No máximo 1 vaga por dia | `restricoes.py` (antes da busca) |
| R9 | 10 min de folga entre reservas do mesmo recurso | `modelo.py` (domínios) |

**Regras flexíveis** (escolhem a melhor solução entre as válidas):

| ID | Regra | Custo |
|---|---|---|
| F1 | Proximidade do horário pedido | 1 ponto por minuto de diferença |
| F2 | Menos tempo ocioso entre atividades | 0,1 ponto por minuto ocioso |
| F3 | Recurso favorito | 30 pontos se não ficar com ele |

Os parâmetros (passo de 15 min, folgas, antecedência, durações e pesos) estão no início de `modelo.py` e `custo.py`.

## Resposta da API

```json
{
  "status": "OK",
  "cost": 127.0,
  "items": [
    { "request_id": "estacionamento", "resource_id": "vaga-02", "resource_name": "Vaga 02", "start": "08:50", "end": "19:40" },
    { "request_id": "trabalho", "resource_id": "mesa-01", "resource_name": "Mesa 01", "start": "09:00", "end": "13:00" }
  ],
  "stats": { "nodes": 92, "solutions": 20, "prunes": 17, "time_ms": 0.9, "limit_reached": false }
}
```

| Situação | Resposta |
|---|---|
| Há solução | `200`, `"status": "OK"` |
| Nenhuma combinação respeita as regras | `200`, `"status": "NO_SOLUTION"` |
| Pedido viola uma regra logo à partida (R2, R3, R8) | `422`, com a regra na mensagem |
| Campo desconhecido ou formato inválido | `422` (validação do Pydantic) |

A busca tem um limite de 200 mil nós, para a API nunca ficar presa. Se o limite for atingido, `limit_reached` vem `true` e a solução devolvida é a melhor encontrada até ali.

## Integração com o SlotUp

Nesta entrega o protótipo corre isolado. Na 3ª entrega, o fluxo previsto é:

```
frontend → booking-service → scheduling-service (este) → booking-service → frontend
```

O booking monta o corpo do pedido a partir do `booking_db` (recursos, horários e reservas). O scheduling devolve a proposta, sem acesso a base de dados. Quando o usuário confirma, o booking cria as reservas e verifica de novo a disponibilidade. O scheduling é interno: não é exposto pelo Nginx.