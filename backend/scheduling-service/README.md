# SlotUp · scheduling-service (CSP)

O "cérebro" do **Planear o meu dia**. Recebe do booking um dia, as atividades que o usuário quer fazer, os recursos e a ocupação, e devolve o melhor plano: que recurso e a que horas para cada atividade, sem sobreposições e só com recursos livres. Quando não há plano, explica porquê.

O problema é modelado como um **CSP** (problema de satisfação de restrições) com custo, ou seja, um problema de otimização com restrições:

- **Variáveis:** as atividades do pedido.
- **Domínio de cada atividade:** os pares (recurso, início), numa grade de 15 em 15 min, nos recursos do tipo pedido.
- **Restrições rígidas:** as 11 regras da [seção 5](#5-regras). Decidem se uma combinação é **válida**.
- **Custo:** F1, F2 e F3 da [seção 6](#6-custo). Decide qual das válidas é a **melhor**.

O serviço **não tem banco de dados** e nunca grava nada. É **interno**: não tem porta no host nem rota no Nginx, e só o booking fala com ele, em `http://scheduling:8003`.

## 1. Rodar

| Para quê | Como |
|---|---|
| Com o resto do sistema | `docker compose up -d --build` em `infra/docker` (o booking encontra-o pelo nome `scheduling`) |
| Swagger (`/docs`) | Fora do Docker, com o `.venv` ativo: `uvicorn app.main:app --port 8013` e abrir `http://localhost:8013/docs`. Tem 3 exemplos prontos no "Try it out": plano, sugestões e sem solução |
| Testes | `pytest -q` (não precisa de banco nem do booking) |
| Demo no terminal | `python demo.py`: resolve o `dados/cenario_basico.json` passo a passo (domínios, 1.ª solução, solução ótima e custo) |
| Benchmark | `pip install -r requirements-dev.txt`, depois `python benchmark.py` (~2 min) e `python graficos.py`. Ver a [seção 8](#8-benchmark) |

## 2. Estrutura

```
scheduling-service/
├── app/
│   ├── main.py            # a aplicação FastAPI
│   ├── schemas.py         # o contrato (Pydantic): entrada, saída, limites de tamanho
│   ├── exemplos.py        # exemplos de pedidos para o Swagger
│   ├── routers/plan.py    # POST /api/scheduling/plan (modos plan e suggest)
│   └── csp/
│       ├── modelo.py      # Problema, Pedido, Valor; monta os domínios (consistência de nó)
│       ├── regras.py      # as regras rígidas, uma classe por regra, e as ligadas em cada modo
│       ├── restricoes.py  # ponte entre o solver e as regras (o solver não conhece as regras)
│       ├── custo.py       # F1, F2 e F3; ordenação dos domínios pelo custo
│       ├── solver.py      # backtracking + forward checking + MRV + branch and bound, com limites
│       └── diagnostico.py # quando não há plano: o motivo e a regra de cada recurso
├── dados/cenario_basico.json   # cenário de exemplo (usado na demo e nos testes)
├── tests/test_solver.py        # uma regra por teste, sem solução, limites, API, força bruta
├── demo.py
├── benchmark.py, graficos.py   # comparação BT × FC × MRV
└── resultados/                 # CSV, tabela (benchmark.md) e gráficos do benchmark
```

## 3. Contrato: entrada

`POST /api/scheduling/plan`. As horas vêm sempre em **hora local do complexo** (`HH:MM`; o booking também pode mandar `HH:MM:SS`), no dia indicado em `day`. Quem converte de UTC é o booking.

```json
{
  "mode": "plan",
  "day": "2026-12-10",
  "now": "2026-12-09T09:00",
  "activities": [
    { "id": "trabalho", "resource_type": "mesa", "people": 1, "duration_min": 240,
      "preferred_start": "08:00", "preferred_end": "13:00" },
    { "id": "reuniao", "resource_type": "sala", "people": 6, "duration_min": 60, "preferred_start": "14:00" },
    { "id": "estacionamento", "resource_type": "vaga_carro", "people": 1, "covers_day": true }
  ],
  "resources": [
    { "id": "sala-grande", "name": "Sala Grande", "resource_type": "sala", "capacity": 8,
      "schedule": [ { "weekday": 3, "open_time": "08:00", "close_time": "20:00" } ],
      "min_duration_min": 15, "max_duration_min": 240, "buffer_min": 10 }
  ],
  "busy": [ { "resource_id": "sala-grande", "start": "14:00", "end": "15:00" } ]
}
```

| Campo | Obrigatório | Descrição |
|---|---|---|
| `mode` | sim | `plan` (planear o dia) ou `suggest` (sugerir horários para **uma** atividade) |
| `day` | sim | Dia a planear (`AAAA-MM-DD`) |
| `now` | sim | Agora, em hora local **sem fuso**. No dia de hoje, nada começa antes disto |
| `max_alternatives` | não | Só no `suggest`: quantas sugestões devolver (1 a 10, padrão 3) |
| `activities` | sim | As atividades (1 a 10) |
| `resources` | sim | Recursos **ativos** dos tipos pedidos (até 300) |
| `busy` | sim | Ocupação do dia: reservas **CONFIRMED e HELD** (até 3000). A fila de espera não conta |

### Atividade

| Campo | Obrigatório | Descrição |
|---|---|---|
| `id` | sim | Nome único da atividade no pedido; volta no `activity_id` da resposta |
| `resource_type` | sim | Tipo de recurso, igual ao do booking: `mesa`, `sala`, `quadra`, `personal`, `vaga_carro`, `vaga_mota` |
| `people` | sim | Número de pessoas (≥ 1). O recurso precisa de `capacity` maior ou igual |
| `duration_min` | sim, exceto vaga | Duração em minutos, múltiplo de 15 |
| `preferred_start` | sim, exceto vaga | Início da janela preferida |
| `preferred_end` | não | Fim da janela preferida (ex.: manhã = 08:00 a 13:00). Sem ele, a janela é `preferred_start` + duração (uma hora específica) |
| `covers_day` | só nas vagas | A vaga cobre da 1.ª à última atividade, com 10 min de folga de cada lado, arredondado para fora na grade de 15 min (08:50 → 08:45) |
| `favorite_resource_id` | não | Recurso preferido. O booking preenche com o recurso deste tipo que o usuário mais reservou nos últimos 90 dias |

### Recurso

| Campo | Descrição |
|---|---|
| `id`, `name`, `resource_type`, `capacity` | Iguais ao recurso no booking |
| `schedule` | Horário **semanal**, igual ao do booking: `weekday` (0 = segunda ... 6 = domingo), `open_time`, `close_time`. O scheduling escolhe as janelas do dia pedido; lista vazia = sempre fechado |
| `min_duration_min`, `max_duration_min` | Duração mínima e máxima de uma reserva (múltiplos de 15, até 1440) |
| `buffer_min` | Intervalo obrigatório entre reservas seguidas do recurso (0 a 60 min) |

### Pedidos inválidos (422)

- Campo em falta, formato errado ou **campo desconhecido**.
- `mode = suggest` sem **exatamente 1 atividade** ou com `covers_day`.
- Mais de 1 atividade com `covers_day` (`UMA_VAGA_POR_DIA`).
- Só estacionamento, sem nenhuma atividade com horário: a vaga não teria o que cobrir.
- Acima dos limites de tamanho. A mensagem diz o máximo e quanto veio: `No máximo 10 itens em 'activities' por pedido (recebidos: 11)`.

## 4. Contrato: saída

A resposta é **sempre 200** quando o pedido é válido, mesmo sem solução. Os campos que não se aplicam vêm como `null`.

### Plano (`mode = plan`)

```json
{
  "status": "OK",
  "mode": "plan",
  "plan": {
    "cost": 75.5,
    "items": [
      { "activity_id": "trabalho", "resource_id": "mesa-01", "resource_name": "Mesa 01", "start": "08:30", "end": "12:30" },
      { "activity_id": "reuniao", "resource_id": "sala-grande", "resource_name": "Sala Grande", "start": "12:45", "end": "13:45" }
    ]
  },
  "alternatives": null,
  "failure": null,
  "stats": { "nodes": 19, "solutions": 8, "prunes": 6, "time_ms": 0.32, "limit_reached": false, "limit": null }
}
```

Os itens vêm por ordem de início. A vaga (`covers_day`) vem com o intervalo que tem de ficar reservada.

### Sugestões (`mode = suggest`)

`alternatives` traz até `max_alternatives` opções, da melhor para a pior, cada uma com 1 item. `plan` é a primeira delas.

```json
{
  "status": "OK",
  "mode": "suggest",
  "plan": { "cost": 75.0, "items": [ { "activity_id": "reuniao", "resource_id": "sala-grande", "resource_name": "Sala Grande", "start": "12:45", "end": "13:45" } ] },
  "alternatives": [
    { "cost": 75.0, "items": [ { "activity_id": "reuniao", "resource_id": "sala-grande", "resource_name": "Sala Grande", "start": "12:45", "end": "13:45" } ] },
    { "cost": 75.0, "items": [ { "activity_id": "reuniao", "resource_id": "sala-grande", "resource_name": "Sala Grande", "start": "15:15", "end": "16:15" } ] },
    { "cost": 90.0, "items": [ { "activity_id": "reuniao", "resource_id": "sala-grande", "resource_name": "Sala Grande", "start": "12:30", "end": "13:30" } ] }
  ],
  "failure": null,
  "stats": { "nodes": 36, "solutions": 3, "prunes": 0, "time_ms": 0.04, "limit_reached": false, "limit": null }
}
```

### Sem solução

```json
{
  "status": "NO_SOLUTION",
  "mode": "plan",
  "plan": null,
  "alternatives": null,
  "failure": {
    "code": "NO_CAPACITY",
    "activity_id": "reuniao",
    "rule_id": "CAPACIDADE",
    "message": "Capacidade: nenhum recurso do tipo 'sala' comporta 12 pessoas.",
    "reasons": [
      { "rule_id": "CAPACIDADE", "resource_id": "sala-pequena", "message": "Sala Pequena: só tem lugar para 4 (pedido: 12 pessoas)." },
      { "rule_id": "CAPACIDADE", "resource_id": "sala-grande", "message": "Sala Grande: só tem lugar para 8 (pedido: 12 pessoas)." }
    ]
  },
  "stats": { "nodes": 0, "solutions": 0, "prunes": 0, "time_ms": 0.0, "limit_reached": false, "limit": null }
}
```

| `failure.code` | Quando acontece | `activity_id` | `reasons` |
|---|---|---|---|
| `NO_RESOURCE` | Não há nenhum recurso ativo do tipo pedido | a atividade | vazio |
| `NO_CAPACITY` | Há recursos do tipo, mas nenhum comporta as pessoas | a atividade | um por recurso |
| `NO_FREE_SLOT` | Nenhum recurso tem um horário que passe em todas as regras unárias | a atividade | um por recurso |
| `CONFLICT` | Cada atividade tem opções, mas não cabem todas no mesmo dia | `null` | vazio |
| `PARKING_NOT_COVERED` | O resto cabe, mas nenhuma vaga fica livre do início ao fim do dia planeado | `null` | vazio |
| `LIMIT_REACHED` | A busca chegou ao limite (tempo ou nós) sem achar nenhum plano | `null` | vazio |

- `message` e cada `reasons[].message` já vêm em texto para a tela.
- `rule_id` é a regra **decisiva**: a última regra unária, na ordem da tabela da seção 5, que eliminou alguma opção. É por ela que a tela escolhe as sugestões ("reduzir pessoas", "outro dia"...).
- Em `reasons`, cada recurso do tipo pedido traz a **sua** regra decisiva. Assim o usuário vê, por exemplo, "Sala Pequena: só tem lugar para 4" e "Sala Grande: não tem nenhum horário livre com esta duração nesse dia".
- Um dia no passado ou a mais de 30 dias dá `NO_FREE_SLOT` com `rule_id` `SEM_PASSADO` ou `ANTECEDENCIA`.

## 5. Regras

As rígidas são **plugáveis**: uma classe por regra em `app/csp/regras.py`, cada uma com o seu `id`, nome e mensagem. Para ligar ou desligar uma regra num modo, basta tirar ou pôr o id em `ATIVAS_POR_MODO`. O booking **não** escolhe as regras.

| `rule_id` | Regra | Tipo | Modos |
|---|---|---|---|
| `CAPACIDADE` | O recurso comporta as pessoas | unária | plan, suggest |
| `DURACAO` | Duração mínima e máxima **do recurso** | unária | plan, suggest |
| `MULTIPLO_15` | Início e duração múltiplos de 15 min | unária | plan, suggest |
| `HORARIO_ABERTURA` | Cabe inteira numa janela de abertura do dia | unária | plan, suggest |
| `SEM_PASSADO` | Nada no passado | unária | plan, suggest |
| `ANTECEDENCIA` | Até 30 dias à frente | unária | plan, suggest |
| `RECURSO_LIVRE` | Sem reservas CONFIRMED ou HELD no horário | unária | plan, suggest |
| `INTERVALO_RECURSO` | Respeita o `buffer_min` antes e depois das reservas do recurso | unária | plan, suggest |
| `UMA_VAGA_POR_DIA` | No máximo 1 vaga por dia | pedido | plan |
| `SEM_SOBREPOSICAO` | Atividades sem sobreposição, com 10 min de deslocamento | binária | plan |
| `VAGA_COBRE_O_DIA` | A vaga fica livre da 1.ª à última atividade | global | plan |

- **Unária:** olha uma atividade e um valor. É aplicada **antes** da busca, ao montar os domínios (consistência de nó).
- **Pedido:** olha o pedido inteiro, antes da busca. Se falhar, a resposta é 422.
- **Binária:** olha duas atividades. Entra no forward checking.
- **Global:** olha todas as atividades. Entra no forward checking da vaga.

## 6. Custo

Entre os planos válidos, ganha o de **menor custo**:

| | O que mede | Peso |
|---|---|---|
| **F1** | Minutos que a atividade fica **fora da janela preferida** | 1 por minuto |
| **F2** | Tempo **ocioso** entre atividades seguidas (os 10 min de deslocamento não contam) | 0,1 por minuto |
| **F3** | Não ficar com o **recurso favorito** | 30 |

Com estes pesos, mudar 30 min de hora custa o mesmo que trocar de recurso: o CSP prefere primeiro um horário perto no recurso favorito.

## 7. Busca e limites

- **Backtracking** com **forward checking** (FC), que inclui a propagação da vaga, e **MRV** (escolhe primeiro a atividade com menos opções).
- **Branch and bound:** os domínios vêm ordenados pelo custo, e um ramo é cortado quando o custo dele, somado ao mínimo das atividades que faltam, já não ganha do melhor plano encontrado. O teste `test_solver_igual_a_forca_bruta` compara com a força bruta em 20 cenários e confirma que o resultado é **sempre o ótimo**.
- **Determinístico:** a mesma entrada dá sempre o mesmo plano, porque os empates são resolvidos pela hora e pelo id do recurso.
- **Limites:** a busca para aos **2 s** ou aos **200 mil nós**, o que vier primeiro. Os 2 s ficam abaixo dos 3 s que o booking espera.
  - Se já achou um plano, devolve-o com `stats.limit_reached = true` e `stats.limit` (`time` ou `nodes`). A busca é *anytime*: o plano é válido, só pode não ser o ótimo.
  - Se não achou nenhum, devolve `LIMIT_REACHED` dizendo qual dos limites parou a busca.
- **Suggest:** com uma atividade não há combinações a procurar. As sugestões são o domínio dela, já filtrado pelas regras unárias e ordenado pelo custo.

## 8. Benchmark

O `benchmark.py` compara a busca simples (BT) com as heurísticas (FC, MRV e as duas juntas) nos mesmos 20 cenários aleatórios por tamanho, com sementes fixas. Os resultados ficam em `resultados/`: `benchmark.csv`, `benchmark.md` (as tabelas do relatório) e os gráficos `benchmark_nos.png` e `benchmark_tempo.png`.

Em resumo:
- **O forward checking é o que mais pesa.** Para provar que não há solução, FC precisa de cerca de 10 nós. O BT passa de 100 mil a partir de 5 atividades.
- **O MRV sozinho quase não muda nada**, porque sem FC os domínios não encolhem durante a busca.
- **Juntos são os melhores nos pedidos grandes.** Com 8 atividades, FC+MRV usa cerca de 40× menos nós do que o BT.
- **Folga em relação ao limite.** O pior tempo médio da busca completa fica perto de 100 ms, longe dos 2 s.

## 9. Responsabilidades

| Booking | Scheduling |
|---|---|
| Validar o token e o usuário | Validar o formato do pedido e os limites de tamanho |
| Ler recursos, horários e reservas do `booking_db`; escolher o favorito | Montar os domínios e aplicar as regras |
| Converter as horas de UTC para hora local | Devolver o plano, as sugestões ou o motivo da falha |
| Timeout de 3 s; plano B (503 no planear, 409 sem sugestões) se o scheduling falhar | Parar a busca nos limites |
| Confirmar o plano: criar as reservas numa transação, e o banco verifica de novo | Nunca grava nada: não tem banco de dados |