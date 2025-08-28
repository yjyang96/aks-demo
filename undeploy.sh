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

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 1) Helm 릴리스 삭제 (MariaDB / Kafka / Redis)"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
helm uninstall "${MYSQL_HOST}" -n "${K8S_NAMESPACE}" || true
helm uninstall "${KAFKA_SERVERS}" -n "${K8S_NAMESPACE}" || true
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
envsubst < k8s/ingress.yaml | kubectl delete -n "${K8S_NAMESPACE}" -f - --ignore-not-found=true
set -e

echo "📋 네임스페이스 내 잔여 리소스 확인"
kubectl get all -n "${K8S_NAMESPACE}" | cat

echo "✅ 언디플로이 완료"
