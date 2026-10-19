# SlotUp · Migrações do banco com Alembic

Este guia explica como criar e atualizar as tabelas do SlotUp com o **Alembic**. O Docker (`infra/docker`) cria os bancos **vazios**; o Alembic cria e evolui as **tabelas** dentro deles.

> **Em uma frase:** cada serviço com banco tem a sua pasta `alembic/`, e o comando `alembic upgrade head` deixa o banco igual ao que o código espera.

## Para que serve

- Cria todas as tabelas do zero com um comando, igual para todo o grupo.
- Guarda o **histórico** das mudanças, uma migração por arquivo.
- Permite alterar uma tabela **sem apagar os dados** (o `down -v` só é necessário para recomeçar do zero).
- Permite voltar atrás (`alembic downgrade -1`).
- Vai servir também no Kubernetes, onde um Job rodará `alembic upgrade head` contra o PostgreSQL do cluster.

## Quem tem Alembic

| Serviço            | Banco        | Variável da URL         | Tem Alembic? |
|--------------------|--------------|-------------------------|--------------|
| auth-service       | `auth_db`    | `AUTH_DATABASE_URL`     | Sim          |
| booking-service    | `booking_db` | `BOOKING_DATABASE_URL`  | Sim          |
| scheduling-service | (sem banco)  | —                       | Não precisa  |

Cada serviço usa o seu próprio usuário e o seu próprio banco, e tem a sua própria tabela `alembic_version`. As migrações de um serviço nunca tocam o banco do outro.

## Migrações existentes

| Serviço         | Migração | O que faz                                                          |
|-----------------|----------|--------------------------------------------------------------------|
| auth-service    | `0001`   | tabela `users` (2FA, tentativas de login, bloqueio)                |
| booking-service | `0001`   | extensão `btree_gist`, `categories`, `resources`, `availability_rules` |
| booking-service | `0002`   | `reservations` (com constraint anti-sobreposição) e `waitlist_entries` |
| booking-service | `0003`   | `notifications` (outbox de e-mails)                                |
| booking-service | `0004`   | as 3 categorias iniciais (Coworking, Estacionamento, Desporto)     |

## Estrutura

```
backend/
├── ALEMBIC.md                 # este guia
├── auth-service/
│   ├── alembic.ini            # configuração do comando alembic
│   ├── alembic/
│   │   ├── env.py             # como conectar ao banco (lê AUTH_DATABASE_URL)
│   │   ├── script.py.mako     # molde das novas migrações (precisa ir para o Git)
│   │   └── versions/          # as migrações: 0001_create_users.py, ...
│   ├── requirements.txt
│   ├── .env.example           # modelo da URL (vai para o Git)
│   └── .env                   # sua URL real (NÃO vai para o Git)
└── booking-service/           # mesma estrutura, com BOOKING_DATABASE_URL
```

## Primeira vez (por serviço)

**Pré-requisitos:** Docker Desktop aberto, banco no ar (`docker compose up -d db`, dentro de `infra/docker`) e Python 3.12 ou superior.

```bash
cd backend/auth-service
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # abra o .env e coloque a senha do AUTH_DB_PASSWORD
alembic upgrade head
alembic current                    # deve mostrar a última versão (head)
```

Repita em `backend/booking-service` (com `BOOKING_DATABASE_URL` e a senha do `BOOKING_DB_PASSWORD`).

O `.env` de cada serviço é **diferente** do `.env` de `infra/docker`. Este guarda só a URL de conexão do Alembic:

```
AUTH_DATABASE_URL=postgresql+psycopg://auth_user:SUA_SENHA@localhost:5436/auth_db
```

Use a porta que está em `ports` no `docker-compose.yml` (hoje `5436`). Use senhas só com letras e números: símbolos como `$` e `@` quebram o `.env` e a URL.

## Comandos do dia a dia (dentro do serviço, com o `.venv` ativo)

| O que fazer                      | Comando                                              |
|----------------------------------|------------------------------------------------------|
| Aplicar tudo o que falta         | `alembic upgrade head`                               |
| Ver a versão atual do banco      | `alembic current`                                    |
| Ver o histórico                  | `alembic history`                                    |
| Desfazer a última migração       | `alembic downgrade -1`                               |
| Desfazer tudo                    | `alembic downgrade base`                             |
| Ver o SQL sem executar           | `alembic upgrade head --sql`                         |
| Criar uma nova migração (vazia)  | `alembic revision -m "descrição" --rev-id 0005`      |

Para recomeçar do zero (apaga **todos** os dados locais):

```bash
cd infra/docker
docker compose down -v && docker compose up -d db
# depois, em cada serviço: alembic upgrade head
```

5. Teste a ida e a volta: `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head`.

Escrevemos as migrações **à mão**, sem autogenerate, porque o banco usa recursos do PostgreSQL que o autogenerate trata mal (constraint de exclusão, índices parciais, índice sobre `lower(email)`).

## Regras para trabalhar em equipe

1. **Nunca edite uma migração que já foi para o `main`.** Para corrigir algo, crie uma nova.
2. Antes de criar uma migração, faça `git pull` para não repetir o número de outra pessoa.
3. Se duas pessoas criarem o mesmo número em branches diferentes, quem entrar depois no `main` renumera (`revision` e `down_revision`) antes do merge.
4. Quem puxar migrações novas só roda `alembic upgrade head`. Não precisa recriar o banco.
5. Sem `.env`, `.venv/` ou `__pycache__/` no Git (o `.gitignore` já cobre).
6. O `script.py.mako` **vai** para o Git: sem ele ninguém consegue criar migrações.

## Problemas comuns

| Sintoma | Causa provável e solução |
|---|---|
| `password authentication failed` | A URL do `.env` do serviço tem outra senha ou outra porta. Compare com o `infra/docker/.env` e o `ports` do compose. Evite `$` e `@` na senha. |
| `Defina AUTH_DATABASE_URL` | Faltou o `.env` do serviço (`cp .env.example .env`) ou você está fora da pasta do serviço. |
| `already exists` no `upgrade` | O banco tem tabelas de antes do Alembic (dos antigos `02-auth.sql` e `03-booking.sql`). Recrie com `docker compose down -v`. |
| `Can't locate revision identified by '...'` | O `revision` dentro de um arquivo não bate com o `down_revision` do seguinte. O nome do arquivo não importa, o texto dentro sim. Confira com `alembic history`. |
| `syntax error at or near ...` | Erro de digitação no SQL da migração (aspa ou parêntese faltando). O Alembic desfaz a transação inteira, então o banco continua limpo: corrija e rode de novo. |
| `alembic: command not found` | O `.venv` não está ativo: `source .venv/bin/activate` dentro do serviço. |
| `connection refused` | O banco não está no ar: `docker compose up -d db` em `infra/docker`. |
| Variável do terminal ignora o `.env` | O `load_dotenv()` não sobrescreve variáveis já exportadas. Rode `unset AUTH_DATABASE_URL` (ou `BOOKING_DATABASE_URL`). |
