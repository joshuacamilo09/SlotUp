# Contrato de dados · booking ⇄ scheduling

Formato do JSON que o **booking-service** envia ao **scheduling-service** (CSP) e do que recebe de volta. Definido antes do código para os dois serviços serem desenvolvidos em paralelo.

- **Rota:** `POST /api/scheduling/plan` (só na rede interna; o Nginx não tem rota para ela)
- **Quem chama:** só o booking, depois de validar o token do usuário
- **Horas:** sempre `HH:MM:SS` em **hora local do complexo**, no dia indicado em `day`. O booking converte de UTC antes de enviar.

## 1. Entrada

```json
{
  "id": "9b1c...",
  "name": "Sala de Reunião B",
  "resource_type": "sala",
  "capacity": 8,
  "schedule": [ { "weekday": 3, "open_time": "08:00:00", "close_time": "20:00:00" } ],
  "min_duration_min": 15,
  "max_duration_min": 240,
  "buffer_min": 10
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
| `schedule` | sim | Horário **semanal**, igual ao do booking: `weekday` (0 = segunda ... 6 = domingo), `open_time`, `close_time`. O scheduling escolhe as janelas do dia pedido |
| `min_duration_min`, `max_duration_min` | sim | Duração mínima e máxima de uma reserva, em minutos (múltiplos de 15) |
| `buffer_min` | sim | Intervalo obrigatório entre reservas seguidas do recurso (0 a 60 min) |

### Regras de validação (respondem 422)

- `mode = suggest` exige **exatamente 1 atividade**, sem `covers_day`.
- No máximo **1 atividade** com `covers_day` (R8).
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

"failure": 
{ 
  "code": "NO_CAPACITY", 
  "activity_id": "reuniao", 
  "rule_id": "CAPACIDADE", 
  "message": "Capacidade: nenhum recurso do tipo 'sala' comporta 9 pessoas." 
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

`rule_id` é o id da regra que impediu o plano (`null` em `NO_RESOURCE` e `LIMIT_REACHED`). Um dia no passado ou a mais de 30 dias responde `NO_FREE_SLOT` com `rule_id` `SEM_PASSADO` ou `ANTECEDENCIA`.

### Regras

| `rule_id` | Regra | Tipo | Modos |
|---|---|---|---|
| `CAPACIDADE` | O recurso comporta as pessoas | unária | plan, suggest |
| `DURACAO` | Duração mínima e máxima do recurso | unária | plan, suggest |
| `MULTIPLO_15` | Início e duração múltiplos de 15 min | unária | plan, suggest |
| `HORARIO_ABERTURA` | Dentro de uma janela de abertura | unária | plan, suggest |
| `SEM_PASSADO` | Nada no passado | unária | plan, suggest |
| `ANTECEDENCIA` | Até 30 dias à frente | unária | plan, suggest |
| `RECURSO_LIVRE` | Sem reservas CONFIRMED ou HELD no horário | unária | plan, suggest |
| `INTERVALO_RECURSO` | Folga entre reservas seguidas do recurso | unária | plan, suggest |
| `UMA_VAGA_POR_DIA` | No máximo 1 vaga por dia | pedido | plan |
| `SEM_SOBREPOSICAO` | Atividades sem sobreposição, com 10 min de deslocamento | binária | plan |
| `VAGA_COBRE_O_DIA` | A vaga cobre da 1.ª à última atividade | global | plan |

## 3. Responsabilidades

| Booking | Scheduling |
|---|---|
| Validar o token e o usuário | Validar o formato do pedido |
| Ler recursos, horários e reservas do booking_db | Montar domínios e aplicar as regras R1 a R9 |
| Converter as horas de UTC para hora local | Devolver o plano, as sugestões ou o motivo da falha |
| Ao confirmar: criar as reservas e verificar de novo a disponibilidade | Nunca grava nada: não tem base de dados |