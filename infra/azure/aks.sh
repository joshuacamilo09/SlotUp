#!/usr/bin/env bash
# Cluster AKS do SlotUp no Azure: 2 nós, um para o Servidor 1 e outro para o Servidor 2.
#
# Precisa do Azure CLI (brew install azure-cli) e de ter feito "az login".
#
#   bash infra/azure/aks.sh verificar   antes de criar: conta, regiões permitidas, quota e tamanho de VM
#   bash infra/azure/aks.sh criar       cria o grupo e o cluster (demora 5 a 10 min) e liga o kubectl
#   bash infra/azure/aks.sh estado      o cluster está ligado ou desligado? e os nós?
#   bash infra/azure/aks.sh desligar    desliga os nós: deixa de gastar crédito nas VMs
#   bash infra/azure/aks.sh ligar       volta a ligar (demora uns minutos)
#   bash infra/azure/aks.sh apagar      apaga TUDO (grupo, cluster, discos)
#
# Os valores por omissão podem ser trocados na linha de comandos, por exemplo:
#   REGIAO=germanywestcentral bash infra/azure/aks.sh criar
set -euo pipefail

GRUPO="${GRUPO:-slotup-rg}"
CLUSTER="${CLUSTER:-slotup-aks}"
REGIAO="${REGIAO:-westeurope}"
VM="${VM:-Standard_B2s}"          # 2 vCPU e 4 GB por nó: o mais barato que aguenta o SlotUp
NOS=2                             # Servidor 1 e Servidor 2

verificar() {
  echo "== Conta e subscrição"
  az account show --query "{subscricao:name, id:id, utilizador:user.name}" -o table

  echo; echo "== Fornecedores que o AKS precisa (registar só na primeira vez)"
  for ns in Microsoft.ContainerService Microsoft.Compute Microsoft.Network; do
    printf '%-30s %s\n' "$ns" "$(az provider show -n "$ns" --query registrationState -o tsv)"
    az provider register -n "$ns" >/dev/null
  done

  echo; echo "== Regiões permitidas pelas políticas da subscrição (vazio = sem restrição)"
  az policy assignment list \
    --query "[?parameters.listOfAllowedLocations].parameters.listOfAllowedLocations.value" -o tsv | tr '\t' '\n' | sort -u

  echo; echo "== Quota de vCPU em $REGIAO (precisamos de $((NOS * 2)) para $NOS x $VM)"
  az vm list-usage --location "$REGIAO" \
    --query "[?contains(name.value, 'cores') || contains(name.value, 'BS')].{quota:localName, usado:currentValue, limite:limit}" -o table

  echo; echo "== $VM está disponível em $REGIAO? (coluna Restrictions vazia = sim)"
  az vm list-skus --location "$REGIAO" --size "$VM" --all --resource-type virtualMachines -o table
}

criar() {
  az group create --name "$GRUPO" --location "$REGIAO" -o table
  # --tier free: o plano de controlo não paga; só se pagam as 2 VMs (e só quando ligadas)
  az aks create \
    --resource-group "$GRUPO" \
    --name "$CLUSTER" \
    --location "$REGIAO" \
    --tier free \
    --node-count "$NOS" \
    --node-vm-size "$VM" \
    --nodepool-name servidores \
    --generate-ssh-keys \
    -o table
  az aks get-credentials --resource-group "$GRUPO" --name "$CLUSTER" --overwrite-existing

  # Etiqueta cada nó com o servidor que representa. Mais tarde, os Deployments usam
  # isto para pôr uma réplica de cada serviço em cada servidor.
  # (sem mapfile nem arrays: o bash do macOS é a versão 3.2)
  nos=$(kubectl get nodes -o name | sort)
  kubectl label --overwrite "$(echo "$nos" | sed -n 1p)" slotup/servidor=1
  kubectl label --overwrite "$(echo "$nos" | sed -n 2p)" slotup/servidor=2
  kubectl get nodes -L slotup/servidor -o wide
}

estado() {
  az aks show --resource-group "$GRUPO" --name "$CLUSTER" \
    --query "{cluster:name, estado:powerState.code, regiao:location, versao:kubernetesVersion}" -o table
  kubectl get nodes -L slotup/servidor 2>/dev/null || echo "(nós desligados ou kubectl sem acesso)"
}

case "${1:-}" in
  verificar) verificar ;;
  criar)     criar ;;
  estado)    estado ;;
  desligar)  az aks stop  --resource-group "$GRUPO" --name "$CLUSTER" && echo "Desligado: as VMs deixaram de gastar crédito." ;;
  ligar)     az aks start --resource-group "$GRUPO" --name "$CLUSTER" && estado ;;
  apagar)    az group delete --name "$GRUPO" --yes --no-wait && echo "A apagar o grupo $GRUPO (corre em fundo)." ;;
  *)         sed -n '2,15p' "$0"; exit 1 ;;
esac