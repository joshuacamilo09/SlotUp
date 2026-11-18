#!/usr/bin/env bash
# Cria (ou atualiza) os Secrets do SlotUp no Kubernetes, a partir dos MESMOS segredos
# que o Docker Compose usa:
#   infra/docker/.env       senhas da base de dados e do administrador
#   infra/docker/secrets/   chaves do JWT e chave de cifra do 2FA (bash gen-secrets.sh)
# Assim os segredos nunca são escritos num YAML e nunca vão para o Git.
#
# Uso (com o kubectl ligado ao cluster):  bash infra/k8s/create-secrets.sh
# Ver o que seria criado, sem mexer no cluster:  DRY_RUN=1 bash infra/k8s/create-secrets.sh
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE=../docker/.env
SECRETS=../docker/secrets
NS=slotup

[ -f "$ENV_FILE" ] || { echo "Falta $ENV_FILE (cp ../docker/.env.example ../docker/.env)"; exit 1; }
[ -f "$SECRETS/jwt_private.pem" ] || { echo "Faltam as chaves: bash ../docker/gen-secrets.sh"; exit 1; }

# Lê uma variável do .env sem executar o ficheiro (tira aspas e o \r do Windows)
valor() {
  grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d '\r' | sed -E 's/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/'
}

# Confirma logo no início que nenhuma senha falta (um Secret com a senha vazia
# só daria erro mais tarde, no arranque dos serviços)
for v in AUTH_DB_PASSWORD BOOKING_DB_PASSWORD ADMIN_EMAIL ADMIN_PASSWORD; do
  [ -n "$(valor "$v")" ] || { echo "Defina $v no $ENV_FILE"; exit 1; }
done

# "create --dry-run=client -o yaml | apply" cria o Secret, ou atualiza-o se já existir
aplicar() {
  if [ "${DRY_RUN:-}" = "1" ]; then cat; echo "---"; else kubectl apply -f -; fi
}

if [ "${DRY_RUN:-}" != "1" ]; then
  kubectl apply -f namespace.yaml
fi

# Os SEED_* são para os dados de exemplo (python -m app.seed), como no Docker Compose
kubectl create secret generic auth-secrets -n "$NS" --dry-run=client -o yaml \
  --from-literal=DB_PASSWORD="$(valor AUTH_DB_PASSWORD)" \
  --from-literal=ADMIN_NAME="$(valor ADMIN_NAME)" \
  --from-literal=ADMIN_EMAIL="$(valor ADMIN_EMAIL)" \
  --from-literal=ADMIN_PASSWORD="$(valor ADMIN_PASSWORD)" \
  --from-literal=SEED_ENABLED="$(valor SEED_ENABLED)" \
  --from-literal=SEED_TOTP_SECRET="$(valor SEED_TOTP_SECRET)" \
  --from-literal=SEED_USER_PASSWORD="$(valor SEED_USER_PASSWORD)" | aplicar

kubectl create secret generic booking-secrets -n "$NS" --dry-run=client -o yaml \
  --from-literal=DB_PASSWORD="$(valor BOOKING_DB_PASSWORD)" \
  --from-literal=SEED_ENABLED="$(valor SEED_ENABLED)" | aplicar

# Login no servidor de email, só para o worker. Vazio com o Mailpit.
kubectl create secret generic smtp-secrets -n "$NS" --dry-run=client -o yaml \
  --from-literal=SMTP_USER="$(valor SMTP_USER)" \
  --from-literal=SMTP_PASSWORD="$(valor SMTP_PASSWORD)" | aplicar

# Utilizadores do PostgreSQL (postgres.yaml): o CloudNativePG cria-os com estas senhas,
# as mesmas que os serviços usam. O formato (basic-auth: username e password) é o
# que o CloudNativePG pede. A etiqueta cnpg.io/reload faz o operador mudar a senha
# no banco se o Secret mudar.
for u in auth booking; do
  var=$(echo "$u" | tr '[:lower:]' '[:upper:]')_DB_PASSWORD
  kubectl create secret generic "$u-db-credentials" -n "$NS" --dry-run=client -o yaml \
    --type=kubernetes.io/basic-auth \
    --from-literal=username="${u}_user" \
    --from-literal=password="$(valor "$var")" |
    kubectl label --local -f - cnpg.io/reload=true -o yaml | aplicar
done

# Chaves em Secrets separados, para cada serviço montar SÓ o que precisa:
#   jwt-private-key      só o auth (é quem assina os tokens)
#   jwt-public-key       auth e booking (validam os tokens). Um único Secret para todas as
#                        réplicas: a mesma chave do JWT no servidor 1 e no servidor 2
#   totp-encryption-key  só o auth
# O nome de cada ficheiro é o mesmo do Docker (/run/secrets/<nome>), por isso o código não muda.
kubectl create secret generic jwt-private-key -n "$NS" --dry-run=client -o yaml \
  --from-file=jwt_private_key="$SECRETS/jwt_private.pem" | aplicar
kubectl create secret generic jwt-public-key -n "$NS" --dry-run=client -o yaml \
  --from-file=jwt_public_key="$SECRETS/jwt_public.pem" | aplicar
kubectl create secret generic totp-encryption-key -n "$NS" --dry-run=client -o yaml \
  --from-file=totp_encryption_key="$SECRETS/totp_encryption_key" | aplicar

if [ "${DRY_RUN:-}" != "1" ]; then
  echo "Secrets criados no namespace $NS."
fi