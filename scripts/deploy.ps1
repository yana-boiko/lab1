# Створює кластер, якщо його ще немає
if (-not (kind get clusters | Select-String -Quiet "^lab3$")) {
    kind create cluster --config kind/kind-config.yaml
}

# Мітка для вузла, на якому житимуть база і моніторинг
kubectl label node lab3-control-plane role=infra --overwrite

# Збірка образу сервісу і завантаження в кластер
docker build -t lab3-web:1 .
kind load docker-image lab3-web:1 --name lab3

# Secret з паролем із .env і ConfigMap зі схемою
kubectl create secret generic db-secret --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap db-schema --from-file=db/schema.sql --dry-run=client -o yaml | kubectl apply -f -

# Маніфести
kubectl apply -f k8s/