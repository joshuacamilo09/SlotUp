# SlotUp · Infraestrutura com Docker

Esta pasta sobe, com um único comando, a base de dados do SlotUp num container Docker. Todos os integrantes ficam com o mesmo ambiente: PostgreSQL 17.9, três bancos (um por microserviço), um usuário por serviço e as tabelas iniciais.

## Pré-requisitos

- Docker Desktop instalado e **aberto**.
- Conferir no terminal:

```bash(terminal)
docker --version
docker compose version
```

## Estrutura da pasta

```
infra/docker/
├── docker-compose.yml
├── .env.example          # modelo das senhas (vai para o Git)
├── .env                  # suas senhas reais (NÃO vai para o Git)
├── README.md
└── db/
    └── init/
        ├── 01-roles-and-databases.sh   # usuários, bancos e permissões
        ├── 02-auth.sql                 # tabelas do auth_db
        ├── 03-catalog.sql              # tabelas do catalog_db
        └── 04-reservation.sql          # tabelas do reservation_db
```

## Como subir (primeira vez)

A partir da raiz do repositório:
> Rode sempre os comandos `docker compose` de dentro de `infra/docker/`, porque é lá que o Compose procura o `.env`.

```bash(terminal)
cd infra/docker
cp .env.example .env
```

1. Abra o `.env` e troque `troque-me` por senhas suas. O `.env` nunca vai para o Git (já está no `.gitignore`).
2. Suba o banco:

```bash
docker compose up -d
```

3. Confirme que está saudável (`healthy`):

```bash
docker compose ps
docker compose logs -f db     # Ctrl+C para sair do log
```


No Docker Desktop, o container aparece em **Containers**, dentro do grupo `slotup`, com o nome `slotup-db`.

## Bancos, usuários e serviços

| Microserviço        | Banco            | Usuário            | Conteúdo                                         |
|---------------------|------------------|--------------------|--------------------------------------------------|
| auth-service        | `auth_db`        | `auth_user`        | utilizadores, 2FA, tentativas de login           |
| catalog-service     | `catalog_db`     | `catalog_user`     | categorias, recursos, horários de funcionamento  |
| reservation-service | `reservation_db` | `reservation_user` | reservas e fila de espera                        |

Regras do desenho:

- Cada serviço usa **apenas** o seu usuário e o seu banco. O acesso cruzado é bloqueado pelo PostgreSQL.
- Não existe chave estrangeira entre bancos. Em `reservation_db`, `user_id` e `resource_id` são UUIDs que o serviço valida consultando o auth e o catalog.
- Reservas sobrepostas no mesmo recurso são recusadas pelo próprio banco (constraint de exclusão com `btree_gist`).

## Como conectar

O banco fica na porta **5436** do seu computador, para não colidir com um PostgreSQL local na 5432. A porta só aceita conexões da sua máquina (`127.0.0.1`).

```bash
psql "host=localhost port=5436 dbname=auth_db user=auth_user" -W
```

Em clientes visuais (DBeaver, pgAdmin): host `localhost`, porta `5436`, banco e usuário do serviço, senha do `.env`.


## Comandos do dia a dia

| O que fazer                          | Comando                                         |
|--------------------------------------|-------------------------------------------------|
| Ver o estado                         | `docker compose ps`                             |
| Ver os logs                          | `docker compose logs -f db`                     |
| Parar (mantém os dados)              | `docker compose down`                           |
| Ligar de novo                        | `docker compose up -d`                          |
| Abrir o psql dentro do container     | `docker compose exec db psql -U postgres`       |
| **Recriar do zero (apaga os dados)** | `docker compose down -v && docker compose up -d`|

## Problemas comuns

| Sintoma                                          | Causa provável e solução                                                                                         |
|--------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| `Cannot connect to the Docker daemon`            | O Docker Desktop está fechado. Abra o aplicativo e tente de novo.                                                |
| `port is already allocated` (5433)               | Outro programa usa a porta. Pare-o ou troque no compose para `"127.0.0.1:5434:5432"`.                            |
| Os bancos ou as tabelas não existem              | O volume já existia antes dos scripts. Recrie com `docker compose down -v` e `docker compose up -d`.             |
| `password authentication failed`                 | As senhas são gravadas na primeira criação. Se mudou o `.env` depois, recrie com `down -v`.                      |
| `permission denied for database`                 | Você está usando o usuário de outro serviço. É o comportamento esperado.                                         |
| Erro estranho no `.sh` (`\r`) no Windows         | Fim de linha CRLF. O `.gitattributes` da raiz força LF; refaça o checkout do arquivo.                            |
