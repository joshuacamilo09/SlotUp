# SlotUp

Plataforma de reservas para um complexo empresarial (coworking, estacionamento e desporto), com autenticação de dois fatores, fila de espera e alocação por CSP. Três microserviços em Python (FastAPI), PostgreSQL, Docker e Kubernetes.

## O que mudou na branch `dev-sprint2-feature/recursos`

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