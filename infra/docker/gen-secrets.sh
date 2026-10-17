#!/usr/bin/env bash
# Gera os segredos de DESENVOLVIMENTO em infra/docker/secrets/ (fora do Git):
#   jwt_private.pem        chave privada RSA: só o auth-service a usa (assina tokens)
#   jwt_public.pem         chave pública: todos os serviços a usam (validam tokens)
#   totp_encryption_key    chave AES-256 (base64): o auth-service cifra os segredos do 2FA
# Em Windows corra no Git Bash (já traz o openssl) ou no WSL.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f secrets/jwt_private.pem ]; then
  echo "A pasta secrets/ já tem chaves. Apague-a se quiser gerar outras (os tokens e os 2FA existentes deixam de funcionar)."
  exit 0
fi

command -v openssl >/dev/null || { echo "openssl não encontrado. Use o Git Bash ou o WSL."; exit 1; }

mkdir -p secrets
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out secrets/jwt_private.pem 2>/dev/null
openssl pkey -in secrets/jwt_private.pem -pubout -out secrets/jwt_public.pem
openssl rand -base64 32 | tr -d '\n' > secrets/totp_encryption_key
# Só em desenvolvimento: o utilizador do container precisa de conseguir ler os ficheiros.
chmod 644 secrets/*
echo "Segredos criados em infra/docker/secrets/"
