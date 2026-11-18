#!/usr/bin/env bash
# Gera o certificado HTTPS de DESENVOLVIMENTO do SlotUp no kind, em infra/docker/secrets/
# (fora do Git, junto das outras chaves):
#   tls.crt   certificado para localhost e slotup.localhost
#   tls.key   chave privada do certificado
# Depois, o create-secrets.sh põe-nos no Secret slotup-tls, que o Nginx do frontend usa.
#
# Com o mkcert (brew install mkcert; no Windows: winget install FiloSottile.mkcert), o
# navegador confia no certificado e mostra o cadeado sem avisos. Sem o mkcert, o
# certificado é feito com o openssl e o navegador mostra um aviso (é só aceitar).
#
# Num servidor a sério, com um domínio, o certificado viria do Let's Encrypt (cert-manager).
set -euo pipefail
cd "$(dirname "$0")"

DIR=../docker/secrets
NOMES="localhost slotup.localhost 127.0.0.1"

if [ -f "$DIR/tls.crt" ]; then
  echo "Já existe $DIR/tls.crt. Apague-o (e o tls.key) se quiser gerar outro."
  exit 0
fi
mkdir -p "$DIR"

if command -v mkcert >/dev/null; then
  # Só da primeira vez: instala a autoridade do mkcert no computador (pede a senha)
  mkcert -install
  # shellcheck disable=SC2086  # NOMES tem de ser separado em palavras
  mkcert -cert-file "$DIR/tls.crt" -key-file "$DIR/tls.key" $NOMES
else
  echo "mkcert não encontrado: a gerar um certificado autoassinado (o navegador vai avisar)."
  openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout "$DIR/tls.key" -out "$DIR/tls.crt" -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:slotup.localhost,IP:127.0.0.1" 2>/dev/null
fi
echo "Certificado criado em $DIR/tls.crt"