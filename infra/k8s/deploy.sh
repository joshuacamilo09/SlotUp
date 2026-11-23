#!/usr/bin/env bash
# Sobe o SlotUp inteiro no cluster kind, pela ordem certa:
#   1. operador do PostgreSQL (CloudNativePG)
#   2. namespace, configuração (ConfigMaps) e segredos (Secrets)
#   3. PostgreSQL com primário e réplica, e os bancos auth_db e booking_db
#   4. migrações (Alembic), uma vez, ANTES dos serviços
#   5. serviços: auth, booking (+ worker), scheduling, frontend e mailpit
#
# Antes, uma vez:  bash infra/k8s/kind.sh criar
#                  bash infra/docker/gen-secrets.sh    (chaves do JWT e do 2FA)
#                  bash infra/k8s/gen-cert.sh          (certificado HTTPS)
#                  infra/docker/.env preenchido         (cp .env.example .env)
#
# Uso:  bash infra/k8s/deploy.sh      (pode correr-se outra vez: atualiza o que mudou)
set -euo pipefail
cd "$(dirname "$0")"

CONTEXTO=kind-slotup
NS=slotup
CNPG_VERSAO=1.30.2
CNPG_URL="https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.30/releases/cnpg-$CNPG_VERSAO.yaml"
SERVICOS="auth booking booking-worker scheduling frontend mailpit"

# Todos os kubectl deste script (e do create-secrets.sh) falam com o cluster do kind
kubectl config use-context "$CONTEXTO" >/dev/null

echo "== 1/5 Operador do PostgreSQL (CloudNativePG $CNPG_VERSAO)"
# --server-side: os CRDs do CloudNativePG são grandes demais para o apply normal
kubectl apply --server-side -f "$CNPG_URL" >/dev/null
# O operador é quem faz o failover do PostgreSQL. Fica no nó de controlo, que nunca
# cai nos testes de falha: se ficasse num dos servidores, e esse servidor caísse junto
# com o primário, não sobrava ninguém para promover a réplica (aconteceu no teste).
kubectl -n cnpg-system patch deployment cnpg-controller-manager --type merge -p \
  '{"spec":{"template":{"spec":{"nodeSelector":{"node-role.kubernetes.io/control-plane":""},"tolerations":[{"key":"node-role.kubernetes.io/control-plane","operator":"Exists","effect":"NoSchedule"}]}}}}' >/dev/null
kubectl rollout status deployment/cnpg-controller-manager -n cnpg-system --timeout=180s

echo "== 2/5 Namespace, configuração e segredos"
kubectl apply -f namespace.yaml -f configmaps.yaml
bash create-secrets.sh

echo "== 3/5 PostgreSQL: primário e réplica (da primeira vez demora uns minutos)"
kubectl apply -f postgres.yaml
kubectl wait --for=condition=Ready cluster/slotup-db -n "$NS" --timeout=600s
kubectl wait --for=jsonpath='{.status.applied}'=true database/auth-db database/booking-db -n "$NS" --timeout=120s

echo "== 4/5 Migrações (Alembic), antes dos serviços"
# Um Job não se pode alterar depois de criado: apaga-se o anterior e cria-se outra vez.
# O alembic só aplica as migrações que faltam, por isso correr de novo não estraga nada.
kubectl delete job auth-migrate booking-migrate -n "$NS" --ignore-not-found >/dev/null
kubectl apply -f migrations.yaml
for job in auth-migrate booking-migrate; do
  if ! kubectl wait --for=condition=complete "job/$job" -n "$NS" --timeout=300s; then
    echo "A migração $job falhou. Últimas linhas do log:"
    kubectl logs "job/$job" -n "$NS" --tail=20 || true
    exit 1
  fi
done

echo "== 5/5 Serviços"
# Já existiam? Então reinicia-os no fim: com a mesma tag (dev-sprint7), o Kubernetes não
# sabe que há imagens novas no ghcr.io, nem que a configuração do Nginx mudou
ja_existiam=$(kubectl get deployment auth -n "$NS" -o name 2>/dev/null || true)

# O Service do scheduling passou a headless (Sprint 8). O clusterIP de um Service não se
# pode mudar: se ainda for o antigo, com IP, apaga-se e é criado de novo logo a seguir.
if [ "$(kubectl get service scheduling -n "$NS" -o jsonpath='{.spec.clusterIP}' 2>/dev/null)" != "None" ]; then
  kubectl delete service scheduling -n "$NS" --ignore-not-found >/dev/null
fi
kubectl apply -f mailpit.yaml -f scheduling.yaml -f auth.yaml -f booking.yaml -f frontend.yaml
if [ -n "$ja_existiam" ]; then
  for d in $SERVICOS; do kubectl rollout restart "deployment/$d" -n "$NS" >/dev/null; done
fi
for d in $SERVICOS; do
  kubectl rollout status "deployment/$d" -n "$NS" --timeout=300s
done

echo
kubectl get pods -n "$NS" -o wide
echo
echo "SlotUp no ar: https://localhost:8443"
echo "Emails (Mailpit): kubectl -n $NS port-forward svc/mailpit 8026:8025  e abrir http://localhost:8026"