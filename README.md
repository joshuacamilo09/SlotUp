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
