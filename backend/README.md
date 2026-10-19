# SlotUp · Backend

Três microserviços em Python (FastAPI). Cada um tem a sua pasta, o seu `Dockerfile`, os seus testes e, quando tem banco, as suas migrações do Alembic.

| Serviço | Porta | Banco | Prefixo das rotas | Faz |
|---|---|---|---|---|
| `auth-service` | 8001 | `auth_db` | `/api/auth` | cadastro, login em dois passos (senha + código TOTP), papéis, emissão de JWT |
| `booking-service` | 8002 | `booking_db` | `/api/reservas` | recursos, reservas, fila de espera, notificações e worker (nesta fase só valida o token) |
| `scheduling-service` | 8003 | nenhum | — | algoritmo CSP (nesta fase só o esqueleto). Interno: só o booking fala com ele |

> Para subir o ambiente, conectar ao banco e resolver erros do Docker, veja o [`infra/docker/README.md`](../infra/docker/README.md).

## Estrutura

```
backend/
├── auth-service/
│   ├── app/
│   │   ├── main.py            # arranque, admin inicial, erro 503 quando o banco cai
│   │   ├── config.py          # variáveis de ambiente
│   │   ├── database.py        # conexão com o banco (com pool_pre_ping)
│   │   ├── models.py          # mapeia a tabela users (o schema vem da migração)
│   │   ├── schemas.py         # formato dos pedidos e respostas
│   │   ├── security.py        # Argon2, JWT RS256, TOTP, cifra AES-GCM
│   │   ├── dependencies.py    # "quem é o usuário?" e "é admin?"
│   │   └── routers/           # health.py, auth.py, users.py
│   ├── alembic/
│   │   ├── env.py             # como conectar ao banco (lê AUTH_DATABASE_URL)
│   │   ├── script.py.mako     # molde das novas migrações (precisa ir para o Git)
│   │   └── versions/          # as migrações: 0001_create_users.py, ...
│   ├── alembic.ini            # configuração do comando alembic
│   ├── tests/                 # pytest (contra o PostgreSQL real)
│   ├── Dockerfile
│   ├── requirements.txt       # o que vai para a imagem
│   ├── requirements-dev.txt   # + pytest
│   └── .env.example           # modelo da URL do Alembic para rodar sem Docker
├── booking-service/           # mesma estrutura; security.py só valida tokens; usa BOOKING_DATABASE_URL
├── scheduling-service/        # mesma estrutura, sem banco e sem Alembic
└── scripts/e2e_smoke.py       # teste de ponta a ponta entre os 3 serviços
```

## 1. Rodar tudo

O caminho normal é o Docker. Em `infra/docker`:

```bash
docker compose up -d --build
docker compose ps -a          # *-migrate "Exited (0)", os outros "healthy"
```

As migrações rodam **sozinhas**: os contentores `auth-migrate` e `booking-migrate` executam `alembic upgrade head` antes de os serviços subirem.

Documentação interativa de cada API (Swagger): `http://localhost:8001/docs`, `:8002/docs` e `:8003/docs`.

Teste de ponta a ponta:

```bash
source ~/.venvs/slotup-e2e/bin/activate    # ambiente com httpx e pyotp (ver README da raiz)
python ../../backend/scripts/e2e_smoke.py  # deve terminar com "Tudo certo."
```

## 2. Como funciona o login

O 2FA é obrigatório. O login tem dois passos, e só o segundo devolve um token de acesso.

```
POST /api/auth/register  {name, email, password}          → cria o usuário (papel USER)

POST /api/auth/login     {email, password}                → { status, pre_auth_token }
        │
        ├─ status = MFA_SETUP_REQUIRED  (1.ª vez, ainda sem 2FA)
        │     POST /api/auth/2fa/setup   (Bearer pre_auth_token) → { secret, otpauth_uri }
        │           o frontend desenha o QR code com o otpauth_uri
        │     POST /api/auth/2fa/enable  {code}  (Bearer pre_auth_token) → { access_token }
        │
        └─ status = MFA_REQUIRED        (já tem 2FA)
              POST /api/auth/2fa/verify  {code}  (Bearer pre_auth_token) → { access_token }

Daí em diante:  Authorization: Bearer <access_token>   em todos os serviços
```

### Rotas do `auth-service` (prefixo `/api/auth`)

| Método e rota | Quem | Para quê |
|---|---|---|
| `POST /register` | público | criar conta |
| `POST /login` | público | passo 1 |
| `POST /2fa/setup`, `/2fa/enable` | token `pre_auth` | configurar o 2FA |
| `POST /2fa/verify` | token `pre_auth` | passo 2 |
| `GET /me` | usuário | dados do próprio |
| `GET /users` | ADMIN | listar usuários |
| `PATCH /users/{id}/role` | ADMIN | mudar papel (não o próprio) |
| `POST /users/{id}/2fa/reset` | ADMIN | quem perdeu o celular volta a configurar o 2FA |

### Rotas do `booking-service` (prefixo `/api/reservas`)

| Método e rota | Quem | Para quê |
|---|---|---|
| `GET /me` | usuário | prova que o token foi validado (provisória) |
| `GET /admin/check` | ADMIN | prova que o papel é respeitado (provisória) |

As duas rotas são provisórias (tag `scaffolding` no Swagger). As rotas de categorias, recursos e reservas entram a partir da Sprint 2, com o mesmo prefixo.

O **administrador inicial** é criado no arranque a partir de `ADMIN_EMAIL` e `ADMIN_PASSWORD` do `.env`. Ele também tem de configurar o 2FA no primeiro login. Para dar o papel de admin a outros: `PATCH /users/{id}/role`.

## 3. Decisões de segurança (para o relatório da UC de Segurança)

| Tema | O que fizemos | Onde |
|---|---|---|
| Senhas | Argon2id; mínimo de 10 caracteres; tempo de resposta igual quando o email não existe | `security.py` |
| Tokens | JWT **RS256**: só o auth tem a chave privada, os outros serviços só validam com a pública. Um serviço comprometido não consegue forjar tokens | `security.py`, `booking-service/app/security.py` |
| Tipos de token | `pre_auth` (2FA incompleto, 5 min) e `access` (30 min) não se confundem; o algoritmo é fixo em RS256 | `dependencies.py` |
| 2FA | TOTP (RFC 6238), compatível com Google/Microsoft Authenticator; aceita ±30 s de diferença no relógio | `security.py` |
| Reutilização de códigos | guarda-se o último *time-step* usado; o `UPDATE` condicional é atômico, por isso funciona com várias réplicas | `routers/auth.py` |
| Segredo do 2FA | cifrado com AES-256-GCM antes de ir para o banco, ligado ao id do usuário | `security.py` |
| Força bruta | 5 falhas (senha ou código) bloqueiam a conta por 15 min; o contador é atômico e fica no banco, não na memória | `routers/auth.py` |
| Isolamento | cada serviço só acessa o seu banco (usuários e permissões separados) | `infra/docker/db/init/01-roles-and-databases.sql` |
| Falha do banco | os serviços respondem `503` (e não `500`) e se recuperam sozinhos quando o banco volta, sem reiniciar | `main.py`, `database.py` |

## 4. Limitações conhecidas (assumidas)

- **Sem refresh token nem logout:** o token de acesso vale 30 min e não pode ser revogado antes.
- **Papéis no token:** se um admin mudar o papel de alguém, o token antigo mantém o papel antigo até expirar. O booking não pergunta ao auth.
- **Sem limite por IP:** o bloqueio é por conta. O limite por IP vai no Nginx/Ingress.
- **Chaves de desenvolvimento:** o `gen-secrets.sh` gera chaves com permissões abertas, só para desenvolvimento. No Kubernetes elas passam a ser `Secret`.

## 5. Banco de dados e migrações (Alembic)

O Docker cria os bancos **vazios** (`infra/docker/db/init/01-roles-and-databases.sql`). O **Alembic** cria e evolui as **tabelas** dentro deles.

- Cria todas as tabelas do zero com um comando, igual para todo o grupo.
- Guarda o **histórico** das mudanças, uma migração por arquivo.
- Permite alterar uma tabela **sem apagar os dados**.
- Permite voltar atrás (`alembic downgrade -1`).
- No Kubernetes, um `Job` vai rodar o `alembic upgrade head`, como os contentores `*-migrate` fazem no Docker.

### Quem tem Alembic

| Serviço | Banco | Variável da URL | Tem Alembic? |
|---|---|---|---|
| auth-service | `auth_db` | `AUTH_DATABASE_URL` | Sim |
| booking-service | `booking_db` | `BOOKING_DATABASE_URL` | Sim |
| scheduling-service | (sem banco) | — | Não precisa |

Cada serviço tem a sua própria tabela `alembic_version`. As migrações de um serviço nunca tocam o banco do outro.

### Migrações existentes

| Serviço | Migração | O que faz |
|---|---|---|
| auth-service | `0001` | tabela `users` (2FA, tentativas de login, bloqueio) |
| booking-service | `0001` | extensão `btree_gist`, `categories`, `resources`, `availability_rules` |
| booking-service | `0002` | `reservations` (com constraint contra sobreposição) e `waitlist_entries` |
| booking-service | `0003` | `notifications` (outbox de emails) |
| booking-service | `0004` | as 3 categorias iniciais (Coworking, Estacionamento, Desporto) |

As migrações são escritas **à mão**, sem *autogenerate*, porque o banco usa recursos do PostgreSQL que o autogenerate trata mal: constraint de exclusão, índices parciais e índice sobre `lower(email)`. Por isso o `env.py` tem `target_metadata = None`, e **o `models.py` precisa ser atualizado à mão** sempre que uma migração mudar as colunas.

### Rodar o Alembic sem Docker (para criar e testar migrações)

Pré-requisitos: banco no ar e Python 3.12 ou superior.

```bash
cd infra/docker && docker compose up -d db
```

Depois, em cada serviço:

```bash
cd backend/auth-service
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # coloque a senha do AUTH_DB_PASSWORD na URL
alembic upgrade head
alembic current                    # deve mostrar a última versão (head)
```

O `.env` de cada serviço é **diferente** do `.env` de `infra/docker`. Ele guarda só a URL de conexão do Alembic, apontando para a porta do seu computador:

```
AUTH_DATABASE_URL=postgresql+psycopg://auth_user:SUA_SENHA@localhost:5436/auth_db
```

No booking-service é igual, com `BOOKING_DATABASE_URL`, `booking_user` e `booking_db`.

### Comandos do Alembic (dentro do serviço, com o `.venv` ativo)

| O que fazer | Comando |
|---|---|
| Aplicar tudo o que falta | `alembic upgrade head` |
| Ver a versão atual do banco | `alembic current` |
| Ver o histórico | `alembic history` |
| Desfazer a última migração | `alembic downgrade -1` |
| Desfazer tudo | `alembic downgrade base` |
| Ver o SQL sem executar | `alembic upgrade head --sql` |
| Criar uma nova migração (vazia) | `alembic revision -m "descrição" --rev-id 0005` |

### Criar uma nova migração

1. Faça `git pull` para não repetir o número de outra pessoa.
2. Crie o arquivo: `alembic revision -m "descrição" --rev-id 0005`.
3. Escreva à mão o `upgrade()` (o que criar ou mudar) e o `downgrade()` (como desfazer).
4. Se a migração mudar colunas da tabela, atualize o `models.py` do serviço.
5. Teste a ida e a volta: `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head`.
6. Confirme no Docker: `docker compose up -d --build` em `infra/docker`. O `*-migrate` deve terminar com `Exited (0)`.

### Regras para trabalhar em equipe

1. **Nunca edite uma migração que já foi para o `main`.** Para corrigir algo, crie uma nova.
2. Se duas pessoas criarem o mesmo número em branches diferentes, quem entrar depois no `main` renumera (`revision` e `down_revision`) antes do merge.
3. Quem puxar migrações novas só precisa de `docker compose up -d --build`. Não é necessário recriar o banco.
4. O `script.py.mako` **vai** para o Git: sem ele, ninguém consegue criar migrações.
5. Nada de `.env`, `.venv/` ou `__pycache__/` no Git (o `.gitignore` já cobre).

### Problemas comuns do Alembic

| Sintoma | Causa provável e solução |
|---|---|
| `password authentication failed` | A URL do `.env` do serviço tem outra senha ou outra porta. Compare com o `infra/docker/.env` e com o `ports` do compose. Use só letras e números na senha. |
| `Defina AUTH_DATABASE_URL` | Faltou o `.env` do serviço (`cp .env.example .env`) ou você está fora da pasta do serviço. |
| `already exists` no `upgrade` | O banco tem tabelas de antes do Alembic, criadas pelos antigos scripts SQL. Recrie com `docker compose down -v`. |
| `Can't locate revision identified by '...'` | O `revision` de um arquivo não bate com o `down_revision` do seguinte. O nome do arquivo não importa, o texto dentro dele sim. Confira com `alembic history`. |
| `syntax error at or near ...` | Erro de digitação no SQL da migração. O Alembic desfaz a transação inteira, então o banco continua limpo: corrija e rode de novo. |
| `alembic: command not found` | O `.venv` não está ativo: `source .venv/bin/activate` dentro do serviço. |
| `connection refused` | O banco não está no ar: `docker compose up -d db` em `infra/docker`. |
| Variável do terminal ignora o `.env` | O `load_dotenv()` não sobrescreve variáveis já exportadas. Rode `unset AUTH_DATABASE_URL` (ou `BOOKING_DATABASE_URL`). |

## 6. Testes automáticos (pytest)

Os testes rodam **contra o banco real** do Docker, que precisa estar no ar **com as migrações aplicadas**. Em `infra/docker`:

```bash
docker compose up -d db auth-migrate booking-migrate
```

Depois, em cada serviço, em **bash** (exemplo com o booking):

```bash
cd backend/booking-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
set -a; source ../../infra/docker/.env; set +a   # carrega as senhas sem digitá-las
pytest -q
```

O `set -a` faz com que as variáveis lidas do `.env` fiquem visíveis para o `pytest`, e o `set +a` desliga esse modo no fim.

Em **PowerShell**:

```powershell
cd backend\booking-service
py -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:BOOKING_DB_PASSWORD = "<a-do-seu-.env>"; pytest -q
```

No auth-service, a variável é `AUTH_DB_PASSWORD`. O scheduling-service não precisa de nenhuma. Os testes geram as próprias chaves RSA, por isso **não** precisam da pasta `secrets/`.

> As imagens Docker usam Python 3.12. Se um teste passar na sua máquina e falhar no Docker, verifique a versão do Python do seu `.venv` (`python --version`).