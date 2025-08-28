#!/bin/bash

set -euo pipefail

echo "🚀 언디플로이(삭제)를 시작합니다..."

# 사용법: ./undeploy.sh [ENV]
# - ENV: env/.env.${ENV} 로드 (기본값: rancher)

ENV=${1:-rancher}

# 환경별 .env 파일 로드
if [ -f "env/.env.${ENV}" ]; then
    export $(grep -v '^#' env/.env.${ENV} | xargs)
    echo "Using environment: ${ENV}"
else
    echo "Environment file not found: env/.env.${ENV}"
    exit 1
fi

# 메시징 시스템 설정 확인
MESSAGING_TYPE=${MESSAGING_TYPE:-kafka}
echo "📡 메시징 시스템: ${MESSAGING_TYPE}"

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 1) Helm 릴리스 삭제 (MariaDB / Kafka / Redis)"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
helm uninstall "${MYSQL_HOST}" -n "${K8S_NAMESPACE}" || true

if [ "${MESSAGING_TYPE}" = "kafka" ]; then
  helm uninstall "${KAFKA_SERVERS}" -n "${K8S_NAMESPACE}" || true
fi

helm uninstall "${REDIS_HOST}" -n "${K8S_NAMESPACE}" || true

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 2) 앱 리소스 삭제 (Secret / Deployment / Service)"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 이미지 이름 구성 (deploy-with-env.sh와 동일 로직)
if [ "${ENV}" = "rancher" ]; then
  export BACKEND_IMAGE="${ACR_REPO_NAME_BACKEND}:latest"
  export FRONTEND_IMAGE="${ACR_REPO_NAME_FRONTEND}:latest"
else
  export BACKEND_IMAGE="${ACR_LOGIN_SERVER}/${ACR_REPO_NAME_BACKEND}:latest"
  export FRONTEND_IMAGE="${ACR_LOGIN_SERVER}/${ACR_REPO_NAME_FRONTEND}:latest"
fi

# envsubst로 동일 매니페스트 경로 삭제 (apply의 역동작)
set +e
envsubst < k8s/frontend-deployment.yaml | kubectl delete -n "${K8S_NAMESPACE}" -f - --ignore-not-found=true
envsubst < k8s/backend-deployment.yaml | kubectl delete -n "${K8S_NAMESPACE}" -f - --ignore-not-found=true
envsubst < k8s/backend-secret.yaml | kubectl delete -n "${K8S_NAMESPACE}" -f - --ignore-not-found=true

# Event Hubs Secret 삭제 (Azure Event Hubs 연결 정보)
if [ "${MESSAGING_TYPE}" = "eventhub" ]; then
  envsubst < k8s/eventhub-secret.yaml | kubectl delete -n "${K8S_NAMESPACE}" -f - --ignore-not-found=true
fi

# Azure 환경에서만 Ingress 삭제
if [ "${ENV}" != "rancher" ]; then
  echo "🗑️  Ingress 리소스 삭제 (Azure App Routing)"
  envsubst < k8s/ingress.yaml | kubectl delete -n "${K8S_NAMESPACE}" -f - --ignore-not-found=true
else
  echo "⏭️  Ingress 삭제 스킵 (Rancher 환경)"
fi
set -e

echo "📋 네임스페이스 내 잔여 리소스 확인"
kubectl get all -n "${K8S_NAMESPACE}" | cat

echo "✅ 언디플로이 완료"
