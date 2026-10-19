# SlotUp

Plataforma de reservas para um complexo empresarial (coworking, estacionamento e desporto), com autenticação de dois fatores, fila de espera e alocação por CSP. Três microserviços em Python (FastAPI), PostgreSQL, Docker e Kubernetes.

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