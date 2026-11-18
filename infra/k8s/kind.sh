#!/usr/bin/env bash
# Cluster Kubernetes local do SlotUp com o kind: Servidor 1 e Servidor 2.
#
# Precisa do Docker Desktop a correr (com pelo menos 6 GB de memória), do kind
# (brew install kind) e do kubectl (já vem com o Docker Desktop).
#
#   bash infra/k8s/kind.sh criar        cria o cluster (1 a 2 min) e mostra os nós
#   bash infra/k8s/kind.sh estado       os 3 nós e em que servidor está cada um
#   bash infra/k8s/kind.sh falha 1      o Servidor 1 cai (desliga o contentor desse nó)
#   bash infra/k8s/kind.sh recuperar 1  o Servidor 1 volta
#   bash infra/k8s/kind.sh desligar     desliga o cluster todo (liberta memória do computador)
#   bash infra/k8s/kind.sh ligar        volta a ligar o cluster
#   bash infra/k8s/kind.sh apagar       apaga o cluster
set -euo pipefail
cd "$(dirname "$0")"

CLUSTER=slotup
CONTEXTO="kind-$CLUSTER"   # nome do cluster no kubectl

# Os contentores dos 3 nós (o nome de cada nó no Kubernetes é o nome do contentor)
contentores() {
  docker ps -a --filter "label=io.x-k8s.kind.cluster=$CLUSTER" --format '{{.Names}}' | sort
}

# Contentor do Servidor 1 ou 2, a partir da etiqueta slotup/servidor do nó
no_do_servidor() {
  local n
  n=$(kubectl --context "$CONTEXTO" get nodes -l "slotup/servidor=$1" -o name | sed 's#^node/##')
  [ -n "$n" ] || { echo "Não há nenhum nó com slotup/servidor=$1"; exit 1; }
  echo "$n"
}

estado() {
  kubectl --context "$CONTEXTO" get nodes -L slotup/servidor
}

case "${1:-}" in
  criar)
    kind create cluster --config kind-cluster.yaml --wait 2m
    estado
    ;;
  estado)
    estado
    ;;
  falha)
    no=$(no_do_servidor "${2:?Diga o servidor: falha 1 ou falha 2}")
    docker stop "$no" >/dev/null
    echo "O Servidor $2 ($no) caiu. Daqui a uns 40 s o Kubernetes marca-o NotReady:"
    echo "  kubectl get nodes -w"
    ;;
  recuperar)
    servidor="${2:?Diga o servidor: recuperar 1 ou recuperar 2}"
    # Com o nó em baixo ainda se lê o nome dele no Kubernetes (a API está no nó de controlo)
    no=$(no_do_servidor "$servidor")
    docker start "$no" >/dev/null
    echo "O Servidor $servidor ($no) voltou. À espera que fique Ready..."
    kubectl --context "$CONTEXTO" wait --for=condition=Ready "node/$no" --timeout=120s
    estado
    ;;
  desligar)
    # shellcheck disable=SC2046  # a lista de contentores tem de ser separada em palavras
    docker stop $(contentores) >/dev/null
    echo "Cluster desligado. Para voltar: bash infra/k8s/kind.sh ligar"
    ;;
  ligar)
    # shellcheck disable=SC2046
    docker start $(contentores) >/dev/null
    echo "A arrancar... à espera que os 3 nós fiquem Ready"
    sleep 5   # dá tempo à API do Kubernetes de voltar antes de lhe perguntar
    kubectl --context "$CONTEXTO" wait --for=condition=Ready nodes --all --timeout=180s
    estado
    ;;
  apagar)
    kind delete cluster --name "$CLUSTER"
    ;;
  *)
    sed -n '2,13p' "$0"
    exit 1
    ;;
esac