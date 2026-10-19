ATT: Por erro meu parece que tudo foi alterado, mas nesta branch dedicada ao sprint1 dobackend, as alteracoes foram apenas feitas na pasta backend e infra. O resto está igual como está na branch main

# Sprint 1: o que foi feito

**Base de partida:** a base de dados que o grupo já tinha (3 serviços, `HELD` nas reservas, tabela `notifications`). Em cima disso, o Sprint 1 ficou assim:

## 1. Os 3 serviços do backend (Python + FastAPI)

**auth-service (porta 8001)**

- Registo e login em **dois passos**: password e depois o código de 6 dígitos da app Authenticator (Google ou Microsoft).
- O 2FA é obrigatório. Na primeira vez o utilizador configura-o com um QR code e confirma com o primeiro código.
- Papéis **ADMIN** e **USER**. O admin pode listar utilizadores, mudar papéis e repor o 2FA de quem perdeu o telemóvel.
- O administrador inicial é criado no arranque, a partir do `.env`.

**booking-service (porta 8002):** nesta fase só valida o token que o auth emite e tem os health checks. As reservas, os recursos e a fila de espera ficam para os Sprints 2 e 3.

**scheduling-service (porta 8003):** só o esqueleto, com health checks. O algoritmo CSP ainda não existe.

Os 3 serviços têm `/health/live`, `/health/ready` (testa a base de dados) e `/whoami` (devolve o nome da instância, para provar o balanceamento na demo).

## 2. Segurança (material para o relatório da UC de Segurança)

- **Passwords:** guardadas com Argon2id.
- **Tokens:** JWT **RS256**. Só o auth tem a chave privada, e o booking só valida com a pública. Um serviço comprometido não consegue forjar tokens.
- **Códigos 2FA:** não podem ser reutilizados. O último passo usado fica guardado, e a verificação é atómica na base de dados, por isso funciona com várias réplicas.
- **Segredo do 2FA:** cifrado com AES-256-GCM antes de ir para a base de dados.
- **Força bruta:** 5 falhas seguidas, de password ou de código, bloqueiam a conta 15 minutos. O contador vive na base de dados e não em memória.
- **Falha da base de dados:** quando cai, os serviços respondem **503** em vez de 500 e recuperam sozinhos quando ela volta, sem reiniciar.

## 3. Infraestrutura

- **Dockerfiles:** um por serviço, sem correr como root.
- **docker-compose:** passou a subir a base de dados e os 3 serviços.
- **Segredos:** o script `bash gen-secrets.sh` gera as chaves de desenvolvimento, fora do Git.
- **Ficheiros de apoio:** `.env.example` e `.gitignore` atualizados, e o guia completo em `backend/README.md`.

## 4. Testes

- **Automáticos:** 42 testes contra um PostgreSQL real, com cada serviço a correr como processo próprio.
- **Ponta a ponta:** o fluxo completo entre os 3 serviços (registo, 2FA, token aceite no booking e papéis) foi testado com sucesso, e também a queda e o regresso da base de dados.
- **Ainda por testar:** o `docker compose up --build`, que foi validado só ao nível da configuração. Quem pegar primeiro nisto deve subir tudo e confirmar que os 4 contentores ficam *healthy*.

## Como correr (na pasta `infra/docker`)

```bash
cp .env.example .env        # trocar os "troque-me"
bash gen-secrets.sh         # no Windows, no Git Bash
docker compose up -d --build
python ../../backend/scripts/e2e_smoke.py   # pip install httpx pyotp
```

## Decisões que o grupo tem de tomar

1. **Rota do booking:** usei `/api/booking`, mas o diagrama diz `/api/reservas`. Temos de alinhar uma das duas.
2. **Notificações:** a tabela `notifications` guarda pedidos pendentes, mas falta o processo que os envia (com Mailpit em desenvolvimento). Não está no ClickUp.
3. **Tarefas em falta no ClickUp:** fila de espera, CronJob de expiração dos `HELD`, algoritmos do CSP, GitHub Actions e limite de pedidos no Nginx.

---

# Plano de branches

1. **`dev-sprint1`:** tudo o que está acima.
2. **`dev-sprint2`:** nasce da `dev-sprint1` já testada e certa, e leva as tarefas do Sprint 2 (categorias, recursos e listagem).
3. **`dev-sprint3`:** nasce da `dev-sprint2` já testada, com as tarefas do Sprint 3.
4. **Assim sucessivamente.** Cada branch contém sempre os sprints anteriores já validados mais o atual.
5. **No fim:** juntam-se ao `main` por Pull Request, com revisão de pelo menos um colega, como combinámos.

**Dois cuidados para este plano funcionar:**

- Antes de cada Pull Request, trazer o `main` para a branch (`git merge origin/main`), para apanhar os conflitos cedo, por exemplo se alguém mexer na base de dados.
- Convém que o `main` tenha algo a funcionar nas entregas de 15/11 e 20/12. Por isso, sugiro fazer Pull Request de cada sprint para o `main` assim que estiver testado, em vez de esperar pelo fim. A `dev-sprint(N+1)` nasce então do `main` atualizado.

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
