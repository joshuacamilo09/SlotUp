# Contrato de dados · booking ⇄ scheduling

Formato do JSON que o **booking-service** envia ao **scheduling-service** (CSP) e do que recebe de volta. Definido antes do código para os dois serviços serem desenvolvidos em paralelo.

- **Rota:** `POST /api/scheduling/plan` (só na rede interna; o Nginx não tem rota para ela)
- **Quem chama:** só o booking, depois de validar o token do usuário
- **Horas:** sempre `HH:MM` em **hora local do complexo**, no dia indicado em `day`. O booking converte de UTC antes de enviar.

## 1. Entrada

```json
{
  "mode": "plan",
  "day": "2026-12-10",
  "now": "2026-12-09T15:30",
  "activities": [
    { "id": "estacionamento", "resource_type": "vaga_carro", "covers_day": true, "people": 1 },
    { "id": "trabalho", "resource_type": "mesa", "duration_min": 240, "preferred_start": "09:00", "people": 1, "favorite_resource_id": "4e2a..." },
    { "id": "reuniao", "resource_type": "sala", "duration_min": 60, "preferred_start": "14:00", "people": 6 }
  ],
  "resources": [
    {
      "id": "9b1c...",
      "name": "Sala Grande",
      "resource_type": "sala",
      "capacity": 8,
      "opening": [ { "open_time": "08:00", "close_time": "20:00" } ],
      "params": { "min_duration_min": 15, "max_duration_min": 240, "buffer_min": 10 }
    }
  ],
  "busy": [
    { "resource_id": "9b1c...", "start": "14:00", "end": "15:00" }
  ]
}
```

| Campo | Obrigatório | Descrição |
|---|---|---|
| `mode` | sim | `plan` (planear o dia) ou `suggest` (sugerir horários para uma atividade) |
| `day` | sim | Dia a planear (`AAAA-MM-DD`) |
| `now` | sim | Data e hora atuais do complexo. No dia de hoje, nada começa antes disto |
| `max_alternatives` | não | Só no modo `suggest`: quantas sugestões devolver (1 a 10, padrão 3) |
| `activities` | sim | Atividades pedidas (as variáveis do CSP), de 1 a 10 |
| `resources` | sim | Recursos **ativos** dos tipos pedidos, com o horário de abertura **daquele dia** |
| `busy` | sim | Intervalos ocupados por reservas **CONFIRMED e HELD**. A fila de espera (pessoas à espera) é ignorada |

### Atividade

| Campo | Obrigatório | Descrição |
|---|---|---|
| `id` | sim | Nome único da atividade no pedido |
| `resource_type` | sim | Tipo de recurso, igual ao do booking: `mesa`, `sala`, `quadra`, `personal`, `vaga_carro`, `vaga_mota` |
| `people` | sim | Número de pessoas (≥ 1). O recurso precisa ter `capacity` maior ou igual |
| `duration_min` | sim, exceto vaga | Duração em minutos, múltiplo de 15 |
| `preferred_start` | sim, exceto vaga | Horário preferido (`HH:MM`) |
| `covers_day` | só nas vagas | `true` em `vaga_carro` e `vaga_mota`: a vaga cobre da primeira à última atividade, mais 10 min de cada lado |
| `favorite_resource_id` | não | Recurso preferido do usuário para esta atividade. Preenchido pelo booking a partir do histórico de reservas (o recurso deste tipo mais reservado). Não ficar com ele custa 30 pontos (F3) |

### Recurso

| Campo | Obrigatório | Descrição |
|---|---|---|
| `id`, `name`, `resource_type`, `capacity` | sim | Iguais ao recurso no booking |
| `opening` | sim | Janelas de abertura do dia (pode ter mais de uma) |
| `params` | não | Parâmetros do recurso. O que faltar usa o padrão do tipo no scheduling |

| Parâmetro | Regra | Padrão |
|---|---|---|
| `min_duration_min` / `max_duration_min` | R2 | Sala 15–240; mesa 15–720; quadra 60–90; personal 60–60 |
| `buffer_min` | R9 | 10 |

### Regras de validação (respondem 422)

- `mode = suggest` exige **exatamente 1 atividade**, sem `covers_day`.
- No máximo **1 atividade** com `covers_day` (R8).
- `day` não pode ser anterior à data de `now`, nem estar a mais de 30 dias (R3).
- Campos desconhecidos são recusados.

## 2. Saída

A resposta é sempre `200` quando o pedido é válido, mesmo sem solução. Os campos que não se aplicam vêm como `null`.

### Plano encontrado (`mode = plan`)

```json
{
  "status": "OK",
  "mode": "plan",
  "plan": {
    "cost": 105.0,
    "items": [
      { "activity_id": "estacionamento", "resource_id": "...", "resource_name": "Vaga 02", "start": "08:50", "end": "16:25" },
      { "activity_id": "trabalho", "resource_id": "...", "resource_name": "Mesa 01", "start": "09:00", "end": "13:00" },
      { "activity_id": "reuniao", "resource_id": "9b1c...", "resource_name": "Sala Grande", "start": "15:15", "end": "16:15" }
    ]
  },
  "alternatives": null,
  "failure": null,
  "stats": { "nodes": 61, "solutions": 9, "prunes": 12, "time_ms": 0.6, "limit_reached": false }
}
```

### Sugestões (`mode = suggest`)

```json
{
  "status": "OK",
  "mode": "suggest",
  "plan": null,
  "alternatives": [
    { "cost": 75.0, "items": [ { "activity_id": "reuniao", "resource_id": "9b1c...", "resource_name": "Sala Grande", "start": "15:15", "end": "16:15" } ] },
    { "cost": 90.0, "items": [ { "activity_id": "reuniao", "resource_id": "9b1c...", "resource_name": "Sala Grande", "start": "12:30", "end": "13:30" } ] }
  ],
  "failure": null,
  "stats": { "...": "..." }
}
```

As sugestões vêm ordenadas do menor para o maior custo.

### Sem solução

```json
{
  "status": "NO_SOLUTION",
  "mode": "plan",
  "plan": null,
  "alternatives": null,
  "failure": { "code": "NO_CAPACITY", "activity_id": "reuniao", "message": "Nenhuma sala comporta 9 pessoas." },
  "stats": { "...": "..." }
}
```

| `failure.code` | Quando acontece |
|---|---|
| `NO_RESOURCE` | Não há nenhum recurso ativo do tipo pedido |
| `NO_CAPACITY` | Há recursos do tipo, mas nenhum comporta as pessoas (R4) |
| `NO_FREE_SLOT` | Há recursos com capacidade, mas nenhum horário livre que caiba (R1, R2, R5, R9) |
| `CONFLICT` | Cada atividade tem opções, mas não cabem todas no mesmo dia (R6) |
| `PARKING_NOT_COVERED` | Nenhuma vaga cobre o dia inteiro (R7) |
| `LIMIT_REACHED` | A busca atingiu o limite de nós sem encontrar solução |

`activity_id` indica a atividade que causou a falha, quando há uma só; é `null` em `CONFLICT`, `PARKING_NOT_COVERED` e `LIMIT_REACHED`.

## 3. Responsabilidades

| Booking | Scheduling |
|---|---|
| Validar o token e o usuário | Validar o formato do pedido |
| Ler recursos, horários e reservas do booking_db | Montar domínios e aplicar as regras R1 a R9 |
| Converter as horas de UTC para hora local | Devolver o plano, as sugestões ou o motivo da falha |
| Ao confirmar: criar as reservas e verificar de novo a disponibilidade | Nunca grava nada: não tem base de dados |