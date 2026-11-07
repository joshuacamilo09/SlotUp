# SlotUp

Plataforma de reservas para um complexo empresarial (coworking, estacionamento e desporto), com autenticação de dois fatores, fila de espera e alocação por CSP. Três microserviços em Python (FastAPI), PostgreSQL, Docker e Kubernetes.

## O que mudou na branch `dev-sprint3-feature/fila-de-espera`

As duas últimas tarefas da Sprint 3 do backend: a **fila de espera** ligada ao cancelamento e os **testes dos fluxos de reserva**. Tudo no `booking-service`, **sem migração nova**: as tabelas `waitlist_entries`, o estado `HELD` e os emails `WAITLIST_JOINED`/`WAITLIST_OFFERED` já existiam desde a migração `0002`.

### Como funciona a fila

1. **Entrar na fila.** Alguém quer um horário ocupado e entra na fila (`WAITING`). As regras de horário são as mesmas de uma reserva.
2. **Oferta.** Quando o horário fica livre (cancelamento, recusa ou oferta expirada), o primeiro da fila recebe uma **oferta**: uma reserva `HELD` guardada só para ele durante **15 minutos** (`OFFERED`). Ninguém mais consegue reservar esse horário, porque a constraint `reservations_no_overlap` também conta `HELD`.
3. **Resposta.**
   - **Aceita:** a reserva passa a `CONFIRMED`.
   - **Recusa ou não responde a tempo:** a reserva passa a `CANCELLED` e o horário vai para o seguinte da fila.

### Rotas novas (prefixo `/api/reservas/fila`)

| Método e rota | Quem | Para quê |
|---|---|---|
| `POST /` | usuário | entra na fila de um horário ocupado `{resource_id, start_at, end_at}` → `201`. Horário livre, horário já reservado pelo próprio, ou já está na fila → `409` |
| `GET /minhas` | usuário | os pedidos do próprio, com a `position` na fila (1 = o próximo) e, se houver oferta, o `reservation_id` e o `hold_expires_at` |
| `POST /{id}/aceitar` | dono do pedido | aceita a oferta → `200` com a reserva `CONFIRMED`. Sem oferta ou fora de prazo → `409` |
| `POST /{id}/sair` | dono do pedido | sai da fila. Se já tinha oferta, é uma recusa e o horário passa ao seguinte |

### Regras e decisões

- **Ordem de chegada:** a fila é por `created_at`. Só disputam um horário os pedidos que se sobrepõem a ele.
- **Horários parciais:** um horário libertado grande (10h–12h) pode servir dois pedidos pequenos (10h–11h e 11h–12h). Um pedido maior do que o horário libertado continua à espera.
- **Cancelar a reserva de uma oferta** (`POST /api/reservas/reservas/{id}/cancelar`) é o mesmo que recusá-la.
- **Concorrência entre réplicas:** a fila é lida com `SELECT ... FOR UPDATE SKIP LOCKED`, por isso duas réplicas nunca fazem duas ofertas para o mesmo pedido. Cada oferta é um `INSERT HELD` dentro de um `SAVEPOINT`: se o horário ainda estiver ocupado, só essa tentativa é desfeita e passa-se ao pedido seguinte.
- **Ordem dos bloqueios:** primeiro a reserva, depois o pedido, sempre na mesma ordem (cancelar, aceitar, sair, expirar). Assim duas transações nunca ficam à espera uma da outra (deadlock).
- **Pedido de outra pessoa:** `404`, como nas reservas.
- **A validação do horário foi partilhada:** passou para a função `check_slot()` em `routers/reservations.py`, usada ao criar reserva e ao entrar na fila. O comportamento do `POST /reservas` não mudou.

### Expirar ofertas: `python -m app.expire_holds`

O job fecha as ofertas fora de prazo e passa o horário ao seguinte. Também marca como `EXPIRED` os pedidos cujo horário já começou. Corre uma vez e sai.

- **No Kubernetes (Sprint 4):** fica num **CronJob** a correr a cada minuto. Pode correr em várias réplicas ao mesmo tempo, graças ao `SKIP LOCKED`.
- **Em desenvolvimento**, para correr à mão:

  ```bash
  docker compose exec booking python -m app.expire_holds
  ```
- **Mesmo sem o job,** aceitar uma oferta fora de prazo dá `409` e passa o horário ao seguinte.

### Testes dos fluxos de reserva

O ficheiro `tests/test_reservation_flows.py` conta 4 histórias completas, passo a passo:

1. **Reservar, conflitar, cancelar e outra pessoa reservar.** Confirma a disponibilidade, as "minhas reservas" de cada um e os emails.
2. **Permissões, usuário comum contra administrador:** ver, cancelar, listar e criar recursos.
3. **Fila de espera completa:** conflito, entrar na fila, oferta, recusa, oferta ao seguinte e aceitação.
4. **Oferta sem resposta:** expira e passa ao seguinte.

### Testes desta branch

- `pytest` do booking-service: **160 testes OK**. São 139 anteriores, mais 17 da fila (`test_waitlist.py`) e 4 fluxos (`test_reservation_flows.py`).
- **A limpeza da fixture `category`** (em `test_reservations.py`) passou a apagar também os pedidos da fila e os seus emails. Sem isso, as chaves estrangeiras impediam de apagar as reservas e os recursos de teste.

## O que mudou na branch `dev-sprint3-feature/gerir-reservas`

Mais três tarefas da Sprint 3 do backend: **minhas reservas**, **cancelar reserva** e **todas as reservas (admin)**. Tudo no `booking-service`, **sem migração nova**.

### Rotas novas (prefixo `/api/reservas/reservas`)

| Método e rota | Quem | Para quê |
|---|---|---|
| `GET /minhas` | usuário | as reservas de quem pede. `?periodo=futuras\|passadas\|todas` (padrão `todas`), `?status=`, `?limit=` (até 200) e `?offset=` |
| `GET /` | ADMIN | todas as reservas, com o `user_id`. Filtros: `periodo`, `status`, `resource_id`, `user_email`, `limit` e `offset` |
| `GET /{id}` | dono ou ADMIN | uma reserva |
| `POST /{id}/cancelar` | dono ou ADMIN | cancela a reserva → `200`, e o horário volta a ficar livre |

### Regras

- **Futura = ainda não acabou.** Uma reserva a decorrer conta como futura. As futuras vêm da mais próxima para a mais distante; as passadas e a lista completa, da mais recente para a mais antiga.
- **Paginação:** o total vai no cabeçalho `X-Total-Count`, para o frontend saber quantas páginas há.
- **As respostas trazem `resource_name`, `category_name`, `updated_at` e `cancelled_at`.** O frontend já não precisa de pedir o recurso à parte. O `POST /` (criar reserva) também passou a devolver estes campos.
- **A reserva de outra pessoa dá `404`, e não `403`**, tanto ao ver como ao cancelar. Assim ninguém consegue descobrir que ids de reservas existem (ataque IDOR).
- **Quem pode cancelar:**
  - o dono, só **antes** de a reserva começar;
  - o ADMIN, qualquer reserva, até ela **acabar**.
  
  Reserva já cancelada, ou já terminada, dá `409`.
- **O horário fica livre sem código extra:** a constraint `reservations_no_overlap` só conta `HELD` e `CONFIRMED`, por isso uma reserva `CANCELLED` deixa de ocupar o horário.
- **Email (outbox):** na mesma transação, grava um pedido `RESERVATION_CANCELLED` na tabela `notifications`, sempre para o **dono** da reserva, mesmo quando quem cancela é o admin. O `payload` diz quem cancelou (`"cancelled_by": "USER"` ou `"ADMIN"`).
- **Dois cancelamentos ao mesmo tempo** (por exemplo, o dono e o admin): a rota bloqueia a linha da reserva (`SELECT ... FOR UPDATE`) até ao commit. O segundo pedido espera, vê a reserva já `CANCELLED` e recebe `409`. Só sai um email. Há um teste que força esta corrida com 8 pedidos: 1 recebe `200` e 7 recebem `409`.
- **Corrigido:** a mensagem do `409` ao criar reserva dizia "resrevado".

### Para o frontend

- **Próximas reservas da página inicial:** `GET /api/reservas/reservas/minhas?periodo=futuras&limit=3`.
- **Página "As minhas reservas":** `?periodo=futuras` e `?periodo=passadas`, um em cada separador.
- **Botão "Cancelar":** `POST /api/reservas/reservas/{id}/cancelar`. Com `409`, mostrar a mensagem do campo `detail`.

### Ainda por fazer

- **Fila de espera:** quando uma reserva é cancelada, o horário deveria ser oferecido ao primeiro da fila (`HELD`). Fica para quando a fila de espera existir.

### Testes desta branch

- `pytest` do booking-service: **139 testes OK** (120 anteriores + 19 novos).

# ATUALIZACAO ANTIGA ABAIXO (NAO E NECESSARIO LEREM SE JA LERAM)

## O que mudou na branch `dev-sprint3`

Primeiras tarefas da Sprint 3 do backend: **dados de exemplo**, **consultar disponibilidade**, **criar reserva**, **evitar reservas duplicadas** e o **teste de concorrência**. Tudo no `booking-service`, menos o seed dos usuários, que fica no `auth-service`.

### Decisões desta sprint

- **Aulas de yoga saem por agora.** A regra de "vários lugares no mesmo horário" fica para a 3.ª entrega, se o grupo mantiver as aulas. **Todos os recursos são exclusivos**: uma reserva ocupa o recurso inteiro.
- A reserva nasce **`CONFIRMED`**. O estado `HELD` fica para a fila de espera.
- O pedido de email é gravado na tabela `notifications` **na mesma transação** da reserva (padrão outbox).
- **Regras de horário:** a reserva cabe inteira num intervalo de abertura do recurso, não começa no passado nem a mais de **30 dias**, e usa horas múltiplas de **15 minutos** (mínimo 15 min).
- O mesmo usuário **pode** ter reservas simultâneas em recursos diferentes. As regras por usuário (ex.: 1 vaga de estacionamento por dia) ficam para o CSP, na 3.ª entrega.
- **Horas sem fuso** (`2026-11-09T10:00`) valem como hora local do complexo (`Europe/Lisbon`).

### Dados de exemplo (seed)

```bash
docker compose exec auth python -m app.seed      # admin do .env + ana@slotup.pt, com 2FA já ativo
docker compose exec booking python -m app.seed   # apaga reservas, fila, notificações e recursos; recria 13 recursos
```

- **Usuários:** o admin do `.env` e `ana@slotup.pt` (senha `SEED_USER_PASSWORD`), os dois com o 2FA ativo e o mesmo segredo `SEED_TOTP_SECRET`. Adicione o segredo **uma vez** no Authenticator ("Inserir chave de configuração"). Ele continua valendo depois de um `down -v`.
- **Recursos (13):** 3 mesas e 3 salas (Coworking); 1 quadra de padel e 2 personal trainers (Desporto); 2 vagas de carro (uma elétrica) e 2 de moto (Estacionamento).
- **Ids fixos:** cada recurso tem sempre o mesmo id (`uuid5` a partir do nome), por isso scripts de demo podem usar ids conhecidos.
- **Idempotente:** pode rodar quantas vezes quiser, sem duplicar nada. **Só roda com `SEED_ENABLED=true`**, que nunca deve existir fora do desenvolvimento.

### Consultar disponibilidade

`GET /api/reservas/recursos/{id}/disponibilidade?day=AAAA-MM-DD` devolve três listas para o dia: `opening` (quando o recurso abre), `busy` (o que já está reservado) e `free` (o que está livre).

- O ocupado são as reservas `HELD` e `CONFIRMED`, os mesmos estados que o banco bloqueia. Então, um horário que aparece livre é um horário que o banco aceita.
- O ocupado mostra **só o horário**, nunca quem reservou. As horas que já passaram nunca aparecem como livres.
- O fuso vem de `LOCAL_TIMEZONE` (padrão `Europe/Lisbon`). O horário de funcionamento está em hora local, e o banco guarda as reservas em UTC. Entrou o pacote `tzdata` no `requirements.txt`, para o contentor conhecer os fusos.

### Criar reserva

`POST /api/reservas/reservas` com `{resource_id, start_at, end_at}` → `201`. Horário já ocupado → `409`.

- **O id e o email vêm do token (JWT)**, nunca do corpo do pedido. Campos extra, como `user_id` ou `status`, dão `422`.
- O recurso e a categoria têm de estar ativos (`404` caso contrário, até para o ADMIN).
- **Sem migração nova:** as tabelas `reservations` e `notifications` já existiam (migrações `0002` e `0003`). O `models.py` ganhou os modelos `Reservation` e `Notification`.

### Evitar reservas duplicadas

**Quem decide é o PostgreSQL**, e não o código. Por isso, o resultado é o mesmo com uma ou com várias réplicas do booking.

| Peça | Onde |
|---|---|
| Extensão `btree_gist` | migração `0001` do booking |
| Constraint de exclusão `reservations_no_overlap` (mesmo recurso + intervalos sobrepostos, para `HELD` e `CONFIRMED`) | migração `0002` |
| `CHECK` nos valores de `status`, para nenhum valor escapar da constraint | migração `0006` |
| A rota faz o `INSERT` direto, **sem `SELECT` antes**, e trata a violação como `409` | `app/routers/reservations.py` |

### Teste de concorrência (demo)

O script `backend/scripts/demo_concorrencia.py` faz login real, com 2FA, com a Ana e o admin, escolhe o primeiro horário livre da **Sala de Reunião B** e dispara vários pedidos **ao mesmo tempo**. O resultado tem de ser sempre **um `201` e o resto `409`**.

```bash
source ~/.venvs/slotup-e2e/bin/activate
set -a; source .env; set +a                                  # em infra/docker
DEMO_REQUESTS=2 python ../../backend/scripts/demo_concorrencia.py   # duas pessoas, um vencedor
python ../../backend/scripts/demo_concorrencia.py                   # 10 pedidos, continua só um
```

Depois do Nginx, é só apontar para ele: `BOOKING_URL=http://localhost:8080 python ...`.

### Como atualizar

1. **Acrescente ao seu `infra/docker/.env`** as linhas novas do `.env.example` (`SEED_ENABLED`, `SEED_TOTP_SECRET`, `SEED_USER_PASSWORD`). Gere o segredo com:
   `docker compose exec auth python -c "import pyotp; print(pyotp.random_base32())"`
2. Reconstrua e semeie, em `infra/docker`:

```bash
docker compose up -d --build
docker compose exec auth python -m app.seed
docker compose exec booking python -m app.seed
```

3. Para rodar os testes na sua máquina, reinstale as dependências do booking (entrou o `tzdata`): `pip install -r requirements-dev.txt`.

### Testes desta branch

- `pytest` do booking-service: **120 testes OK** (84 anteriores + 15 de disponibilidade + 21 de reservas), inclusive 8 pedidos simultâneos com só um vencedor.
- `pytest` do auth-service: **30 testes OK**.
- Demo de concorrência: 1 de 2 e 1 de 10 pedidos aceitos.

### Pendências e decisões em aberto

- **Aulas com vários lugares:** 3.ª entrega, se o grupo mantiver as aulas.
- **Reservas futuras** quando o admin muda o horário ou desativa um recurso: cancelar e notificar, ou impedir a mudança (continua em aberto desde a Sprint 2).
- **`HELD` expirado** continua a ocupar o horário até existir o job que o expira.
- **Estacionamento à noite:** as vagas fecham às 23:59 e as horas são múltiplas de 15 min, por isso a última reserva acaba às 23:45, e nenhuma reserva atravessa a meia-noite.
- **Worker de email (SMTP):** os pedidos ficam `PENDING` na tabela `notifications` até o worker existir.

## O que mudou na branch `dev-sprint2-feature/recursos`

## INFORMAÇÃO ABAIXO
*NOTA: ANTIGO (branches `dev-sprint2-feature/recursos`, `dev-sprint2-feature/categorias` e `merge-alembic`; se já leram, não precisam ler de novo)*
Segunda tarefa da Sprint 2 do backend: **Recursos** (mesa, sala, vaga, quadra de padel…), dentro do `booking-service`, com o horário de funcionamento de cada recurso.

### Rotas (prefixo `/api/reservas/recursos`)

| Método e rota | Quem | Para quê |
|---|---|---|
| `GET /` | usuário | lista os recursos ativos de categorias ativas, por categoria e nome. `?category_id=` filtra por categoria; `?include_inactive=true` inclui os desativados (só ADMIN) |
| `GET /{id}` | usuário | um recurso, com a categoria e o horário |
| `POST /` | ADMIN | cria `{category_id, name, resource_type, description?, capacity?, attributes?, schedule?}` → `201` |
| `PATCH /{id}` | ADMIN | altera só os campos enviados (inclusive mudar de categoria e `is_active`). O horário **não** muda aqui |
| `PUT /{id}/horarios` | ADMIN | substitui o horário inteiro: `{"rules": [...]}` |
| `DELETE /{id}` | ADMIN | apaga ou desativa (ver abaixo) |

### Regras

- **Nome único dentro da mesma categoria:** o mesmo nome em outra categoria é permitido. Quem garante é a restrição única do PostgreSQL, como nas categorias. Há um teste com 8 pedidos simultâneos: só um recebe `201`.
- **Normalização:** os espaços à volta do nome são removidos e o `resource_type` é guardado em minúsculas (`" SALA "` → `"sala"`).
- **Categoria:** se não existir, a resposta é `422`. Se estiver desativada, `409`.
- **Recurso desativado, ou de categoria desativada:** para o usuário comum, é como se não existisse (`404` e fora da lista). O ADMIN continua a vê-lo.
- **`DELETE`:** se o recurso **não** tem reservas nem entradas na fila de espera, é apagado de vez (`"action": "deleted"`). Se tem, é só desativado (`"action": "deactivated"`), para não quebrar o histórico.
- **`attributes`:** campo livre em JSON para extras, como `{"tem_projetor": true}`, com no máximo 4000 caracteres.

### Horário de funcionamento (tabela `availability_rules`)

- **Dia da semana na convenção do Python: `0` = segunda-feira … `6` = domingo.** Atenção: no PostgreSQL, o `EXTRACT(DOW ...)` usa `0` = domingo. Quem validar reservas contra o horário tem de usar a convenção do Python.
- **Sem horário no `POST`:** o recurso abre **todos os dias, das 08:00 às 20:00**. Com `"schedule": []`, o recurso fica sem horário, ou seja, fechado.
- **Pode haver vários intervalos no mesmo dia** (ex.: 09:00–13:00 e 14:00–18:00), mas sem sobreposição. O máximo é de 35 intervalos.
- **As horas são sem fuso horário** (`"09:00"`, e não `"09:00Z"`): é a hora local do complexo.

### Banco de dados

- **Sem migração nova.** As tabelas `resources` e `availability_rules` já existiam desde a migração `0001`. O `models.py` passou a mapeá-las, e as colunas foram conferidas contra a migração.
- **Arquivos novos ou alterados no booking:** `app/routers/resources.py`, `app/models.py` (`Resource` e `AvailabilityRule`), `app/schemas.py`, `app/main.py` e `tests/test_resources.py`.
- **No auth-service**, os arquivos `main.py`, `models.py` e `schemas.py` aparecem no histórico desta branch só porque perderam a quebra de linha no fim do arquivo. Não há mudança de código.

### Como atualizar

Em `infra/docker`:

```bash
git branch --show-current     # confirme que está na branch certa
docker compose up -d --build  # reconstrói as imagens com o código desta branch
```

**Sempre reconstrua as imagens depois de trocar de branch.** Os contentores rodam o código da última imagem construída, e não o da pasta. O `pytest` usa o código da pasta, por isso pode passar enquanto o Swagger ainda mostra a versão antiga.

### Testes desta branch

- `pytest` do booking-service: **84 testes OK** (36 anteriores + 48 de recursos).
- `pytest` do auth-service: **30 testes OK**.
- Testes manuais no Swagger: criar, nome repetido, visão de usuário × admin, desativar e reativar, trocar o horário e apagar.

### Para decidir na Sprint 3

- O que acontece com as **reservas futuras** quando o admin muda o horário ou desativa um recurso: cancelar e notificar por email, ou impedir a mudança.
- Trocar no `resources.py` a constante `HTTP_422_UNPROCESSABLE_ENTITY` pela nova `HTTP_422_UNPROCESSABLE_CONTENT`. É só o nome que mudou: o código devolvido continua sendo `422`.

## INFORMAÇÃO ABAIXO
*NOTA: ANTIGO (branches `dev-sprint2` (categorias) e `merge-alembic`; se já leram, não precisam ler de novo)*
## O que mudou na branch `dev-sprint2-feature/categorias`

Primeira tarefa da Sprint 2 do backend: **Categorias**, dentro do `booking-service`. Também foram corrigidos dois erros encontrados na revisão das migrações.

### Categorias (novo)

- **Rotas** (prefixo `/api/reservas`):
  - `GET /categorias`: qualquer usuário com login. Mostra só as categorias ativas, ordenadas por nome.
  - `GET /categorias/{id}`: uma categoria. Se estiver desativada, só o ADMIN a vê.
  - `POST /categorias`: só ADMIN. Cria `{name, description}`.
  - `PATCH /categorias/{id}`: só ADMIN. Altera só os campos enviados (`name`, `description`, `is_active`).
- **Não há `DELETE`.** Os recursos apontam para a categoria, e as reservas antigas apontam para os recursos. Apagar quebraria o histórico. Para tirar uma categoria do catálogo, o admin usa `PATCH {"is_active": false}`. Ela pode ser reativada depois.
- **Nome único sem diferenciar maiúsculas:** "Coworking" e "coworking" contam como a mesma categoria (resposta `409`). Os espaços à volta do nome são removidos.
- **Quem garante o nome único é o PostgreSQL, e não o código.** Com duas réplicas do booking, dois admins podiam criar o mesmo nome ao mesmo tempo: os dois fariam um `SELECT`, não encontrariam nada e os dois gravariam. Com um índice único no banco, só o primeiro `INSERT` passa. Há um teste com 8 pedidos simultâneos: 1 recebe `201` e 7 recebem `409`.
- **Arquivos novos:** `app/models.py` (tabela `categories`), `app/schemas.py` (formato dos pedidos e respostas), `app/routers/categories.py` (as rotas) e `tests/test_categories.py`.

### Migrações novas e corrigidas (booking)

- `0005`: troca o nome único de `categories` por um índice sobre `lower(name)` e adiciona a coluna `updated_at`.
- `0006`: adiciona um `CHECK` aos valores de `status` das reservas (`HELD`, `CONFIRMED`, `CANCELLED`).
  - **Por que era importante:** a proteção contra reservas sobrepostas só vale para `status IN ('HELD', 'CONFIRMED')`. Sem o `CHECK`, um valor mal escrito como `'confirmed'` (minúsculas) escapava da proteção e permitia duas reservas no mesmo horário. Os scripts SQL antigos tinham esse `CHECK`, mas ele se perdeu na passagem para o Alembic.
- `0004` (corrigida): o `downgrade` tinha `'Desposto'` em vez de `'Desporto'`, por isso a categoria Desporto não era apagada ao desfazer a migração. A `0004` ainda não está no `main`, por isso foi corrigida no próprio arquivo.

### Como atualizar

Em `infra/docker`:

```bash
docker compose up -d --build
```

O `booking-migrate` aplica a `0005` e a `0006` sozinho. Não é preciso apagar o banco.

### Testes desta branch

- `pytest` do booking-service: 36 testes OK (11 antigos + 25 das categorias).
- `pytest` do auth-service: 30 testes OK.
- Migrações testadas na ida e na volta: `alembic upgrade head`, `alembic downgrade 0004`, `alembic upgrade head`.


## INFORMACAO ABAIXO
*NOTA: ANTIGO (branch merge-alembic, se já leram, nn precisam ler de novo)*

## O que mudou na branch `merge-alembic`

Esta branch junta a **Sprint 1 do backend** (`dev-sprint1`) com a **migração da base de dados para Alembic** (`alembic_bd`). Ela é a base para a Sprint 2 do backend. Este resumo substitui a leitura dos commits um a um.

### Arquitetura (segue o diagrama de distribuição)

- **3 microserviços:**
  - `auth-service`: cadastro, login com 2FA, papéis e emissão do token JWT.
  - `booking-service`: recursos, reservas, fila de espera, notificações e worker.
  - `scheduling-service`: algoritmo CSP, **sem banco de dados**.
- **2 bancos:** `auth_db` (usuário `auth_user`) e `booking_db` (usuário `booking_user`).
- **Nomes antigos removidos:** `catalog_db`, `reservation_db`, `catalog_user` e `reservation_user` deixaram de existir. O catálogo (categorias e recursos) virou um módulo do booking.
- **Rotas:** o auth fica em `/api/auth` e o booking em `/api/reservas`. A rota antiga `/api/booking` foi trocada para seguir o diagrama.

### Banco de dados: agora com Alembic

- **As tabelas são criadas pelas migrações do Alembic**, e não mais por scripts SQL de arranque.
- O `infra/docker/db/init` tem agora **um único arquivo**, `01-roles-and-databases.sql`, que só cria os usuários e os bancos (vazios).
- **Removidos:** o `01-roles-and-databases.sh` e os `02-auth.sql`, `03-catalog.sql` e `04-reservation.sql`.
- **Por que `.sql` em vez de `.sh`:** no macOS o script bash falhava com `bad interpreter: Permission denied`. O `.sql` lê as senhas com o comando `\getenv` do psql e não depende de permissão de execução, por isso funciona igual em Mac, Windows e Linux.
- **Migrações atuais:**
  - auth `0001`: tabela `users`.
  - booking `0001`: extensão `btree_gist` e o catálogo (`categories`, `resources`, `availability_rules`).
  - booking `0002`: `reservations`, com proteção contra reservas sobrepostas, e `waitlist_entries`.
  - booking `0003`: `notifications`.
  - booking `0004`: as 3 categorias iniciais (Coworking, Estacionamento, Desporto).

### Notificações por email (decisão da reunião de 15/10)

- O email é enviado em **4 eventos**: fazer reserva, cancelar reserva, entrar na fila de espera e abrir vaga na fila de espera.
- **Padrão outbox:** o booking grava o pedido de email na tabela `notifications`, no `booking_db`, na mesma transação da reserva. Um **worker do booking** lê essa tabela e envia por **SMTP**.
- **No diagrama:** entrou a caixa externa "Servidor de email (SMTP)", ligada ao Booking. O texto do Booking passou a "recursos, reservas, fila, notificações, worker".
- **O email do usuário vem do token JWT** e é copiado para as reservas e para a fila (`user_email`). Assim, o booking não precisa consultar o auth: o auth fica fora do caminho crítico.
- **Estado atual:** a tabela já existe (migração `0003`). O worker e o envio ainda não estão implementados.

### Docker Compose

- Entraram dois contentores de uso único, `auth-migrate` e `booking-migrate`. Eles rodam `alembic upgrade head` e terminam. O auth e o booking **só sobem depois de as migrações terminarem sem erro**.
- Esses contentores são o equivalente a um `Job` do Kubernetes. Com várias réplicas, só um processo migra o banco, e não todas as réplicas ao mesmo tempo.
- Os `Dockerfile` do auth e do booking passaram a copiar a pasta `alembic/` e o `alembic.ini` para a imagem.
- **Senhas do `.env`: só letras e números.** Agora elas vão dentro de uma URL de conexão, e símbolos como `@`, `/`, `:` ou `#` quebram o endereço.

### Segurança do repositório

- O `.gitignore` não protegia a pasta `infra/docker/secrets/`, que guarda a **chave privada do JWT**. Agora protege, e também ignora `*.pem`, `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.DS_Store` e `._*`.
- **Antes de cada commit, confira o `git status`. Adicione os arquivos um por um e evite `git add .`.**

### Testes desta branch

- `e2e_smoke.py`: 15 de 15 OK. Cobre os serviços vivos, o registro, o login com 2FA, o token aceito no booking e os papéis.
- `pytest` do booking-service: 11 testes OK, contra o banco criado pelo Alembic.

## Início rápido

Pré-requisitos: Docker Desktop **aberto**, Python 3.12 ou superior e, no Windows, o Git Bash.

> **Já usou uma versão anterior do projeto?** Apague o banco antigo antes de subir. Ele foi criado com os scripts antigos e não é compatível com o Alembic:
> `cd infra/docker && docker compose down -v` (**apaga os dados locais**)

```bash
cd infra/docker

# 1) Senhas e administrador inicial: troque todos os "troque-me" (só letras e números)
cp .env.example .env

# 2) Chaves de desenvolvimento: JWT RS256 e chave de cifra do 2FA, na pasta secrets/ (fora do Git)
bash gen-secrets.sh

# 3) Construir e subir: banco, migrações e os 3 serviços
docker compose up -d --build

# 4) Conferir: os *-migrate devem estar "Exited (0)" e os outros 4 "healthy"
docker compose ps -a
```

Teste de ponta a ponta, que percorre o fluxo real entre os 3 serviços:

```bash
python3 -m venv ~/.venvs/slotup-e2e
source ~/.venvs/slotup-e2e/bin/activate      # Windows: ~/.venvs/slotup-e2e/Scripts/activate
pip install httpx pyotp
python ../../backend/scripts/e2e_smoke.py    # deve terminar com "Tudo certo."
```

Documentação interativa de cada API (Swagger): `http://localhost:8001/docs` (auth), `:8002/docs` (booking) e `:8003/docs` (scheduling).

## Estrutura do repositório

```
SlotUp/
├── backend/
│   ├── auth-service/          # cadastro, login com 2FA, papéis, JWT (+ alembic/)
│   ├── booking-service/       # recursos, reservas, fila, notificações (+ alembic/)
│   ├── scheduling-service/    # algoritmo CSP, sem banco
│   ├── scripts/e2e_smoke.py   # teste de ponta a ponta entre os 3 serviços
│   └── README.md              # guia do backend e do Alembic
├── frontend/
├── documentacao/
├── infra/
│   ├── docker/                # docker-compose, .env.example, db/init, gen-secrets.sh
│   │   └── README.md          # guia do ambiente Docker
│   └── k8s/                   # manifestos do Kubernetes
├── tests/
│   ├── fault-injection/       # testes de falhas
│   └── load/                  # testes de carga
└── README.md                  # este arquivo
```
## Onde ver mais detalhes

| Quero saber… | Leia |
|---|---|
| Como subir, parar e resetar o ambiente, conectar ao banco, resolver erros do Docker | [`infra/docker/README.md`](infra/docker/README.md) |
| Rotas, fluxo de login, decisões de segurança, testes, criar e rodar migrações do Alembic | [`backend/README.md`](backend/README.md) |

## Fluxo de branches

1. **`merge-alembic`:** Sprint 1 do backend + Alembic, já testada. É a base atual.
2. **`dev-sprint2`:** nasce da `merge-alembic` e leva as tarefas da Sprint 2 (categorias, recursos e listagem).
3. **Cada sprint seguinte** nasce da anterior, já testada.