# SlotUp · Ambiente com Docker

Esta pasta sobe todo o SlotUp com um único comando: o banco de dados, as migrações e os 3 microserviços. Todos os integrantes ficam com o mesmo ambiente: PostgreSQL 17.9, dois bancos (um por microserviço com dados), um usuário por serviço e as tabelas criadas pelo Alembic.

> Para o guia do código e das migrações, veja o [`backend/README.md`](../../backend/README.md).

## Pré-requisitos

- Docker Desktop instalado e **aberto**.
- No Windows, o **Git Bash**, que traz o `openssl` usado pelo `gen-secrets.sh`.
- Conferir no terminal:

```bash
docker --version
docker compose version
```

## Estrutura da pasta

```
infra/docker/
├── docker-compose.yml
├── config/
│   ├── auth.env                      # configuração do auth: endereços, portas, regras (vai para o Git)
│   └── booking.env                   # configuração do booking (vai para o Git)
├── .env.example                      # modelo das senhas (vai para o Git)
├── .env                              # suas senhas reais (NÃO vai para o Git)
├── gen-secrets.sh                    # gera as chaves de desenvolvimento
├── secrets/                          # chaves geradas (NÃO vai para o Git)
├── nginx/default.conf                # Nginx: frontend + failover para as réplicas
├── README.md
└── db/
    └── init/
        └── 01-roles-and-databases.sql   # cria os usuários e os bancos (vazios)
```

As **tabelas** não estão aqui: elas são criadas pelas migrações do Alembic, que ficam em `backend/<serviço>/alembic/`.

## Como subir (primeira vez)

> Rode sempre os comandos `docker compose` de dentro de `infra/docker/`, porque é lá que o Compose procura o `.env`.

```bash
cd infra/docker
cp .env.example .env
```

1. Abra o `.env` e troque todos os `troque-me` por senhas suas. **Use só letras e números**: as senhas vão dentro de uma URL de conexão, e símbolos como `@`, `/`, `:` ou `#` quebram o endereço.
2. Gere os segredos de desenvolvimento (chaves JWT e chave de cifra do 2FA):

```bash
bash gen-secrets.sh
```

3. Construa as imagens e suba tudo:

```bash
docker compose up -d --build
```

4. Confira o estado:

```bash
docker compose ps -a
```

O resultado esperado:

| Contentor | Estado esperado |
|---|---|
| `slotup-db` | `healthy` |
| `slotup-auth-migrate` | `Exited (0)` |
| `slotup-booking-migrate` | `Exited (0)` |
| `slotup-auth-1-1` e `slotup-auth-2-1` | `healthy` |
| `slotup-booking-1-1` e `slotup-booking-2-1` | `healthy` |
| `slotup-scheduling` | `healthy` |
| `slotup-nginx` | `healthy` |

As réplicas não têm `container_name` fixo, por isso o Compose chama-lhes `slotup-<serviço>-1` (projeto, serviço, número). Nos comandos usa-se sempre o nome do **serviço**: `auth-1`, `auth-2`, `booking-1`, `booking-2`.

`Exited (0)` nos contentores de migração **é o normal**: eles rodam as migrações uma vez e terminam. O `0` significa "terminou sem erro".

No Docker Desktop, os contentores aparecem em **Containers**, dentro do grupo `slotup`.

## Ordem de arranque

```
db (healthy)
 ├─► auth-migrate     (alembic upgrade head no auth_db, depois termina)
 │     ├─► auth-1     (servidor 1; só sobe se a migração terminou sem erro)
 │     └─► auth-2     (servidor 2)
 └─► booking-migrate  (alembic upgrade head no booking_db, depois termina)
       ├─► booking-1  (servidor 1)
       └─► booking-2  (servidor 2)

scheduling            (não depende de nada: não tem banco)
nginx                 (porta 8080: serve o frontend e reparte /api pelas réplicas)
```

1. Na **primeira criação** do volume, o PostgreSQL roda o `01-roles-and-databases.sql`, que cria os usuários e os bancos vazios.
2. Os contentores `*-migrate` usam a mesma imagem do serviço e rodam `alembic upgrade head`, que cria ou atualiza as tabelas.
3. Só então o auth e o booking arrancam. Se uma migração falhar, o serviço correspondente **não sobe**, o que é melhor do que subir com o banco pela metade.

Os `*-migrate` são o equivalente a um `Job` do Kubernetes. Com várias réplicas, só um processo migra o banco, em vez de todas as réplicas ao mesmo tempo.

## Configuração e segredos

A configuração e os segredos estão separados. A configuração vai para o Git; os segredos nunca vão.

| O quê | Exemplos | No Docker Compose | No Kubernetes | No Git? |
|---|---|---|---|---|
| **Configuração** | `DB_HOST`, `DB_PORT`, `SCHEDULING_URL`, `JWT_ISSUER`, minutos de bloqueio | `config/auth.env`, `config/booking.env` | ConfigMaps `auth-config` e `booking-config` (`infra/k8s/configmaps.yaml`) | sim |
| **Senhas** | `AUTH_DB_PASSWORD`, `ADMIN_PASSWORD` | `.env` (modelo: `.env.example`) | Secrets `auth-secrets` e `booking-secrets` | **não** |
| **Chaves** | chave privada e pública do JWT, chave de cifra do 2FA | ficheiros em `secrets/` (`bash gen-secrets.sh`) | Secrets `jwt-private-key`, `jwt-public-key` e `totp-encryption-key` | **não** |

- **A mesma chave do JWT nos dois servidores.** `auth-1` e `auth-2` montam o **mesmo** ficheiro `secrets/jwt_private.pem`, e todas as réplicas montam o mesmo `jwt_public.pem`. Por isso um token criado no servidor 1 é aceite no servidor 2 e no booking. No Kubernetes, é um único Secret montado em todos os pods.
- **Cada serviço só recebe o que precisa.** O booking só tem a chave **pública** (valida tokens, não os cria) e a sua própria senha da base de dados.
- **Mudar uma regra** (ex.: `LOCK_MINUTES`): edite `config/auth.env` e faça `docker compose up -d`. O Compose recria as réplicas com o valor novo. Não é preciso mexer no código nem reconstruir a imagem.
- **No Kubernetes:** `kubectl apply -f infra/k8s/namespace.yaml -f infra/k8s/configmaps.yaml` e depois `bash infra/k8s/create-secrets.sh`. O script cria os Secrets a partir **deste** `.env` e **desta** pasta `secrets/`, por isso nenhum segredo é escrito num ficheiro YAML. Para ver o que seria criado sem mexer no cluster: `DRY_RUN=1 bash infra/k8s/create-secrets.sh`.

## Réplicas e balanceamento

O auth e o booking correm em **duas réplicas** cada, todas ligadas ao **mesmo PostgreSQL**:

```
                         ┌─► Servidor 1: auth-1 + booking-1 ─┐
browser ─► nginx :8080 ──┤                                    ├─► db (PostgreSQL)
                         └─► Servidor 2: auth-2 + booking-2 ─┘
```

- **Mesma imagem:** `auth-migrate`, `auth-1` e `auth-2` usam a imagem `slotup-auth:dev` (o mesmo para o booking). No `docker-compose.yml`, a configuração comum está escrita uma vez nos blocos `x-auth-service` e `x-booking-service`.
- **O que muda entre réplicas:** só o `INSTANCE_NAME` e a porta no seu computador.
- **Failover:** o servidor 1 (`auth-1`, `booking-1`) recebe todos os pedidos e o servidor 2 (`auth-2`, `booking-2`) fica de reserva (`backup`). Se o servidor 1 falhar, o Nginx refaz o pedido no servidor 2, sem erro para o utilizador. Detalhes em [Failover](#failover).
- **Porque funciona:** os serviços não guardam estado na memória. A sessão é o JWT, os bloqueios e os códigos TOTP usados estão no banco, e as reservas são protegidas pelas constraints do PostgreSQL. Qualquer réplica pode atender qualquer pedido.

| Serviço | No seu computador | Pelo Nginx |
|---|---|---|
| `auth-1` | `http://localhost:8001` | `http://localhost:8080/api/auth/...` |
| `auth-2` | `http://localhost:8011` | (o Nginx escolhe) |
| `booking-1` | `http://localhost:8002` | `http://localhost:8080/api/reservas/...` |
| `booking-2` | `http://localhost:8012` | (o Nginx escolhe) |

Ver que réplica responde:

```bash
for i in 1 2 3 4; do curl -s http://localhost:8080/api/auth/whoami; echo; done
```

Responde sempre `"instance":"auth-1"`, até o servidor 1 falhar. O mesmo com `/api/reservas/whoami`. Todas as respostas trazem também o cabeçalho `X-Served-By` (no browser: DevTools, separador Rede).

## Failover

Configurado em `nginx/default.conf`:

| O quê | Valor | Para quê |
|---|---|---|
| `server auth-1 ... max_fails=1 fail_timeout=10s` | servidor 1, principal | à primeira falha fica 10 s de fora; depois o Nginx volta a experimentá-lo |
| `server auth-2 ... backup` | servidor 2, reserva | só recebe pedidos quando o 1 falha |
| `proxy_connect_timeout 1s` | 1 s | réplica que não aceita a ligação |
| `proxy_read_timeout 5s` | 5 s | réplica ligada mas pendurada |
| `proxy_next_upstream error timeout http_502 http_503 http_504` | | quando refazer o pedido no servidor 2 |
| `proxy_next_upstream_tries 2` | 2 | servidor 1 e servidor 2, no máximo |

O que acontece em cada falha:

| Falha no servidor 1 | O que o utilizador vê |
|---|---|
| Parado ou a reiniciar (`docker compose stop auth-1`) | nada: o pedido vai para o servidor 2 (`200`). O primeiro pode demorar até 1 s (`proxy_connect_timeout`). |
| Pendurado (`docker compose pause auth-1`), pedido `GET` | espera 5 s e recebe a resposta do servidor 2 |
| Pendurado, pedido `POST` (login, reserva) | `504` uma vez. O POST não é repetido porque já chegou ao servidor 1: repeti-lo podia fazer a mesma reserva ou gastar o mesmo código 2FA duas vezes. Os pedidos seguintes já vão para o servidor 2. |
| Servidores 1 e 2 em baixo | `503` com `{"detail": "Serviço temporariamente indisponível..."}`, que o frontend mostra |

Ver o failover:

```bash
docker compose stop auth-1
for i in 1 2 3; do curl -s http://localhost:8080/api/auth/whoami; echo; done
docker compose logs --tail 3 nginx
docker compose start auth-1
```

Com o `auth-1` parado, responde o `auth-2`. O log do Nginx mostra o caminho de cada pedido. Num failover aparecem os dois servidores: `upstream=172.18.0.5:8001, 172.18.0.6:8001 upstream_status=502, 200` (ou `504, 200`, se o servidor 1 não respondeu a tempo). Uns segundos depois do `stop`, o nome `auth-1` sai do DNS do Docker e o log já só mostra o servidor 2. Depois do `start`, o `auth-1` volta a responder em cerca de 10 s.

## Bancos, usuários e serviços

| Microserviço | Banco | Usuário | Conteúdo |
|---|---|---|---|
| auth-service | `auth_db` | `auth_user` | usuários, 2FA, tentativas de login e bloqueio |
| booking-service | `booking_db` | `booking_user` | categorias, recursos, horários de funcionamento, reservas, fila de espera e notificações |
| scheduling-service | (nenhum) | (nenhum) | sem banco: recebe os dados no pedido e devolve a alocação (CSP) |

Regras do desenho:

- Cada serviço usa **apenas** o seu usuário e o seu banco. O acesso cruzado é bloqueado pelo PostgreSQL.
- Não existe chave estrangeira entre bancos. No `booking_db`, o `user_id` e o `user_email` vêm do token JWT emitido pelo auth-service: o booking não consulta o auth a cada pedido.
- Reservas sobrepostas no mesmo recurso são recusadas pelo próprio banco, com uma constraint de exclusão que usa a extensão `btree_gist`.
- Cada banco tem a sua tabela `alembic_version`, onde o Alembic anota até que migração aquele banco já foi atualizado.

## Como conectar

O banco fica na porta **5436** do seu computador, para não colidir com um PostgreSQL local na 5432. A porta só aceita conexões da sua própria máquina (`127.0.0.1`).

```bash
psql "host=localhost port=5436 dbname=auth_db user=auth_user" -W
```

Sem instalar o `psql`, pelo contentor:

```bash
docker compose exec db psql -U postgres -d booking_db -c "\dt"   # lista as tabelas
docker compose exec db psql -U postgres -d booking_db -c "\dx"   # lista as extensões
```

Em clientes visuais (DBeaver, pgAdmin): host `localhost`, porta `5436`, banco e usuário do serviço, senha do `.env`.

## Comandos do dia a dia

| O que fazer | Comando |
|---|---|
| Ver o estado (inclusive os que já terminaram) | `docker compose ps -a` |
| Ver os logs de um contentor | `docker compose logs -f db` (ou `auth-1`, `booking-2`, `auth-migrate`…) |
| Parar (mantém os dados) | `docker compose down` |
| Ligar de novo | `docker compose up -d` |
| Reconstruir depois de mudar código ou migrações | `docker compose up -d --build` |
| Reconstruir só um serviço | `docker compose up -d --build auth-1 auth-2` (ou `booking-1 booking-2`, `scheduling`) |
| Abrir o psql dentro do contentor | `docker compose exec db psql -U postgres` |
| **Recriar do zero (apaga os dados)** | `docker compose down -v && docker compose up -d --build` |

**Puxou migrações novas do Git?** Basta `docker compose up -d --build`. Os `*-migrate` rodam de novo e aplicam só o que falta, sem apagar dados.

## Problemas comuns

| Sintoma | Causa provável e solução |
|---|---|
| `Cannot connect to the Docker daemon` | O Docker Desktop está fechado. Abra o aplicativo e tente de novo. |
| `port is already allocated` (5436) | Outro programa usa a porta. Pare-o ou troque no compose para `"127.0.0.1:5437:5432"`. |
| `secrets ... no such file or directory` | Faltou gerar as chaves: `bash gen-secrets.sh`. |
| `dependency failed to start: container slotup-db is unhealthy` | O script de `db/init` falhou na criação do volume. Veja `docker compose logs db`, corrija e recrie com `docker compose down -v`. |
| `slotup-auth-migrate` ou `slotup-booking-migrate` com `Exited (1)` | A migração falhou. Veja `docker compose logs auth-migrate` (ou `booking-migrate`). As causas mais comuns são as três linhas abaixo. |
| `already exists` no log da migração | O volume foi criado por uma versão antiga do projeto, com as tabelas dos scripts SQL. Recrie com `docker compose down -v`. |
| `password authentication failed` | As senhas são gravadas na **primeira** criação do volume. Se mudou o `.env` depois, recrie com `down -v`. Confira também se a senha tem só letras e números. |
| `Role "..." does not exist` | O `01-roles-and-databases.sql` não rodou. Veja `docker compose logs db` e recrie com `down -v`. |
| Auth ou booking `unhealthy` | Veja `docker compose logs auth-1` (ou `auth-2`, `booking-1`, `booking-2`). Se o `/health/ready` responde `503`, o serviço está vivo mas não alcança o banco. |
| Nginx: `invalid parameter "resolve"` | A imagem do Nginx é anterior à 1.27.3. Confirme `image: nginx:1.27.5-alpine` no compose e corra `docker compose pull nginx`. |
| `port is already allocated` (8011 ou 8012) | Outro programa usa a porta da réplica 2. Troque o número da esquerda no compose (ex.: `"127.0.0.1:8021:8001"`). |
| `permission denied for database` | Você está usando o usuário de outro serviço. É o comportamento esperado (isolamento). |