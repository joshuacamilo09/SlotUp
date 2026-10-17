# SlotUp · Backend

Três microserviços em Python (FastAPI). Cada um tem a sua pasta, o seu `Dockerfile` e os seus testes.

| Serviço | Porta | Base de dados | Faz |
|---|---|---|---|
| `auth-service` | 8001 | `auth_db` | registo, login em dois passos (password + código TOTP), papéis, emissão de JWT |
| `booking-service` | 8002 | `booking_db` | categorias, recursos, reservas, fila de espera (nesta fase só valida o token) |
| `scheduling-service` | 8003 | nenhuma | algoritmo CSP (nesta fase só o esqueleto). Interno: só o booking lhe fala |

```
backend/
├── auth-service/
│   ├── app/
│   │   ├── main.py            # arranque, admin inicial, erro 503 quando a BD cai
│   │   ├── config.py          # variáveis de ambiente
│   │   ├── database.py        # ligação à BD (com pool_pre_ping)
│   │   ├── models.py          # tabela users
│   │   ├── schemas.py         # formato dos pedidos e respostas
│   │   ├── security.py        # Argon2, JWT RS256, TOTP, cifra AES-GCM
│   │   ├── dependencies.py    # "quem é o utilizador?" e "é admin?"
│   │   └── routers/           # health.py, auth.py, users.py
│   ├── tests/                 # pytest (contra o PostgreSQL real)
│   ├── Dockerfile
│   ├── requirements.txt       # o que vai para a imagem
│   └── requirements-dev.txt   # + pytest
├── booking-service/           # mesma estrutura; security.py só valida tokens
├── scheduling-service/        # mesma estrutura; sem base de dados
└── scripts/e2e_smoke.py       # teste de fumo entre os 3 serviços
```

## 1. Pôr tudo a correr (primeira vez)

Pré-requisitos: Docker Desktop **aberto** e, no Windows, o **Git Bash** (traz o `openssl`).

```bash
cd infra/docker

# 1) senhas da BD e administrador inicial
cp .env.example .env          # abra o .env e troque os "troque-me"

# 2) chaves de desenvolvimento (JWT RS256 + chave de cifra do 2FA) → pasta secrets/ (fora do Git)
bash gen-secrets.sh

# 3) construir e subir a BD + os 3 serviços
docker compose up -d --build
docker compose ps             # esperar que tudo fique "healthy"
```

Se a BD já existia de antes, os scripts em `db/init` não voltam a correr: use `docker compose down -v` (**apaga os dados**) e suba de novo.

Verificar:

```bash
curl http://localhost:8001/whoami      # auth
curl http://localhost:8002/whoami      # booking
curl http://localhost:8003/whoami      # scheduling
```

A documentação interativa de cada API (Swagger) está em `http://localhost:8001/docs`, `:8002/docs` e `:8003/docs`.

Teste de ponta a ponta (percorre o fluxo real entre os três serviços):

```bash
pip install httpx pyotp
python backend/scripts/e2e_smoke.py
```

## 2. Como funciona o login

O 2FA é obrigatório. O login tem dois passos e só o segundo devolve um token de acesso.

```
POST /api/auth/register  {name, email, password}          → cria o utilizador (papel USER)

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

Endpoints do `auth-service` (prefixo `/api/auth`):

| Método e rota | Quem | Para quê |
|---|---|---|
| `POST /register` | público | criar conta |
| `POST /login` | público | passo 1 |
| `POST /2fa/setup`, `/2fa/enable` | token `pre_auth` | configurar o 2FA |
| `POST /2fa/verify` | token `pre_auth` | passo 2 |
| `GET /me` | utilizador | dados do próprio |
| `GET /users` | ADMIN | listar utilizadores |
| `PATCH /users/{id}/role` | ADMIN | mudar papel (não o próprio) |
| `POST /users/{id}/2fa/reset` | ADMIN | quem perdeu o telemóvel volta a configurar o 2FA |

O **administrador inicial** é criado no arranque a partir de `ADMIN_EMAIL` e `ADMIN_PASSWORD` do `.env`. Também tem de configurar o 2FA no primeiro login. Para lhe dar o papel a outros: `PATCH /users/{id}/role`.

## 3. Decisões de segurança (para o relatório da UC de Segurança)

| Tema | O que fizemos | Onde |
|---|---|---|
| Passwords | Argon2id; mínimo 10 caracteres; tempo de resposta igual quando o email não existe | `security.py` |
| Tokens | JWT **RS256**: só o auth tem a chave privada, os outros serviços só validam com a pública. Um serviço comprometido não consegue forjar tokens | `security.py`, `booking-service/app/security.py` |
| Tipos de token | `pre_auth` (2FA incompleto, 5 min) e `access` (30 min) não se confundem; o algoritmo é fixo em RS256 | `dependencies.py` |
| 2FA | TOTP (RFC 6238), compatível com Google/Microsoft Authenticator; aceita ±30 s de relógio | `security.py` |
| Reutilização de códigos | guarda-se o último *time-step* usado; o `UPDATE` condicional é atómico, por isso funciona com várias réplicas | `routers/auth.py` |
| Segredo do 2FA | cifrado com AES-256-GCM antes de ir para a BD, ligado ao id do utilizador | `security.py` |
| Força bruta | 5 falhas (password ou código) bloqueiam a conta 15 min; contador atómico na BD, não em memória | `routers/auth.py` |
| Isolamento | cada serviço só acede à sua BD (utilizadores e permissões separados) | `infra/docker/db/init` |

## 4. Limitações conhecidas (assumidas)

- **Sem refresh token nem logout:** o token de acesso vale 30 min e não pode ser revogado antes.
- **Papéis no token:** se um admin mudar o papel de alguém, o token antigo mantém o papel antigo até expirar. O booking não pergunta ao auth.
- **Sem limite por IP:** o bloqueio é por conta. O limite por IP vai no Nginx/Ingress (Sprint 4).
- **O schema vem dos scripts SQL** (`db/init`), não de migrações. O Alembic entra antes do Kubernetes.
- **Chaves de desenvolvimento:** `gen-secrets.sh` gera chaves com permissões abertas só para o desenvolvimento. No Kubernetes passam a ser `Secret`.

## 5. Trabalhar no código (sem Docker para os serviços)

Para correr os testes só precisa da BD no Docker:

```bash
cd infra/docker && docker compose up -d db
```

Depois, em cada serviço (exemplo com o auth), em **bash**:

```bash
cd backend/auth-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
AUTH_DB_PASSWORD=<a-do-seu-.env> pytest -q
```

Em **PowerShell**:

```powershell
cd backend\auth-service
py -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:AUTH_DB_PASSWORD = "<a-do-seu-.env>"; pytest -q
```

No booking-service a variável é `BOOKING_DB_PASSWORD`; o scheduling-service não precisa de nenhuma.
Os testes geram as próprias chaves RSA, por isso **não** precisam da pasta `secrets/`.

Depois de mudar código de um serviço: `docker compose up -d --build auth` (ou `booking`, `scheduling`).
