# Imagem do frontend para o Kubernetes: o Nginx com os ficheiros do site lá dentro.
# A configuração do Nginx (encaminhar /api para o auth e o booking) não vem na imagem:
# vem do ConfigMap frontend-nginx (infra/k8s/frontend.yaml).
# No Docker Compose não se usa esta imagem: o Nginx monta a pasta frontend/ diretamente.
FROM nginx:1.27.5-alpine

COPY . /usr/share/nginx/html