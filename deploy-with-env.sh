#!/bin/bash

set -euo pipefail

# 환경 변수로 환경 설정 (기본값: rancher)
ENV=${1:-rancher}
# 두 번째 인자: CLEAN_INSTALL=true 시 기존 릴리스 제거 후 재설치
CLEAN_INSTALL=${2:-false}

# 환경별 .env 파일 로드
if [ -f "env/.env.${ENV}" ]; then
    export $(grep -v '^#' env/.env.${ENV} | xargs)
    echo "Deploying to environment: ${ENV}"
else
    echo "Environment file not found: env/.env.${ENV}"
    exit 1
fi

# 네임스페이스 생성(없으면)
kubectl get ns "${K8S_NAMESPACE}" >/dev/null 2>&1 || kubectl create namespace "${K8S_NAMESPACE}"

# Bitnami Helm 리포지토리 준비
helm repo add bitnami https://charts.bitnami.com/bitnami >/dev/null 2>&1 || true
helm repo update >/dev/null 2>&1 || true

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 0) 기존 릴리스 정리 옵션: CLEAN_INSTALL=${CLEAN_INSTALL}"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "${CLEAN_INSTALL}" = "true" ]; then
  helm uninstall "${MYSQL_HOST}" -n "${K8S_NAMESPACE}" || true
  helm uninstall "${KAFKA_SERVERS}" -n "${K8S_NAMESPACE}" || true
  helm uninstall "${REDIS_HOST}" -n "${K8S_NAMESPACE}" || true
fi

echo "🧩 values 템플릿 렌더링"
MARIADB_VALUES_FILE=$(mktemp)
REDIS_VALUES_FILE=$(mktemp)
KAFKA_VALUES_FILE=$(mktemp)
envsubst < k8s/mariadb-values.yaml > "$MARIADB_VALUES_FILE"
envsubst < k8s/redis-values.yaml > "$REDIS_VALUES_FILE"
envsubst < k8s/kafka-values.yaml > "$KAFKA_VALUES_FILE"

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 1) MariaDB 배포 (bitnami/mariadb)"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
helm upgrade --install "${MYSQL_HOST}" bitnami/mariadb \
  --namespace "${K8S_NAMESPACE}" \
  --create-namespace \
  -f "$MARIADB_VALUES_FILE"

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 2) Kafka 배포 (bitnami/kafka)"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

helm upgrade --install "${KAFKA_SERVERS}" bitnami/kafka \
  --namespace "${K8S_NAMESPACE}" \
  --create-namespace \
  -f "$KAFKA_VALUES_FILE"

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 3) Redis 배포 (bitnami/redis)"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

helm upgrade --install "${REDIS_HOST}" bitnami/redis \
  --namespace "${K8S_NAMESPACE}" \
  --create-namespace \
  -f "$REDIS_VALUES_FILE"

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 4) Backend/Frontend 시크릿 및 디플로이먼트 적용"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "${ENV}" = "rancher" ]; then
  export BACKEND_IMAGE="${ACR_REPO_NAME_BACKEND}:latest"
  export FRONTEND_IMAGE="${ACR_REPO_NAME_FRONTEND}:latest"
  # Rancher 로컬 이미지 사용 시 imagePullSecrets 불필요할 수 있음
else
  export BACKEND_IMAGE="${ACR_LOGIN_SERVER}/${ACR_REPO_NAME_BACKEND}:latest"
  export FRONTEND_IMAGE="${ACR_LOGIN_SERVER}/${ACR_REPO_NAME_FRONTEND}:latest"
fi

envsubst < k8s/backend-secret.yaml | kubectl apply -n "${K8S_NAMESPACE}" -f -
envsubst < k8s/backend-deployment.yaml | kubectl apply -n "${K8S_NAMESPACE}" -f -
envsubst < k8s/frontend-deployment.yaml | kubectl apply -n "${K8S_NAMESPACE}" -f -

echo "⏳ MariaDB Ready 대기"
kubectl -n "${K8S_NAMESPACE}" wait --for=condition=ready pod -l app.kubernetes.io/instance="${MYSQL_HOST}" --timeout=300s || {
  echo "❌ MariaDB 파드 Ready 대기 실패"; exit 1;
}

echo "🗃️  DB 초기화 실행 (apply-db-init.sh ${ENV})"
bash ./apply-db-init.sh "${ENV}"

echo "📋 리소스 확인"
kubectl get all -n "${K8S_NAMESPACE}" | cat

echo "✅ 배포 완료"

# 임시 파일 정리
rm -f "$MARIADB_VALUES_FILE" "$REDIS_VALUES_FILE" "$KAFKA_VALUES_FILE"
