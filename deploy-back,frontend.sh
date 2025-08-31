#!/bin/bash

set -euo pipefail

# 사용법:
# ./deploy-with-env.sh [환경] [DOCKER_HUB] [CLEAN_INSTALL]
# 예시:
#   ./deploy-with-env.sh rancher                    # rancher 환경, Docker Hub 사용
#   ./deploy-with-env.sh rancher false              # rancher 환경, 로컬 이미지 사용
#   ./deploy-with-env.sh rancher true true          # rancher 환경, Docker Hub 사용, 기존 삭제 후 재설치
#   ./deploy-with-env.sh other-env                  # 다른 환경, ACR 사용

# 환경 변수로 환경 설정 (기본값: rancher)
ENV=${1:-rancher}
DOCKER_HUB=${2:-true}
# 세 번째 인자: CLEAN_INSTALL=true 시 기존 릴리스 제거 후 재설치
CLEAN_INSTALL=${3:-false}

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

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 4) Backend/Frontend 시크릿 및 디플로이먼트 적용"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 이미지 풀 정책과 시크릿 설정
if [ "${ENV}" = "rancher" ]; then
  if [ "${DOCKER_HUB}" = "true" ]; then
    # Docker Hub 이미지 사용
    export BACKEND_IMAGE="${DOCKER_HUB_USERNAME}/${ACR_REPO_NAME_BACKEND}:latest"
    export FRONTEND_IMAGE="${DOCKER_HUB_USERNAME}/${ACR_REPO_NAME_FRONTEND}:latest"
    export IMAGE_PULL_POLICY="Always"
    export IMAGE_PULL_SECRETS="[]"
    echo "🐳 Docker Hub 이미지 사용:"
  else
    # Rancher 로컬 이미지 사용
    export BACKEND_IMAGE="${ACR_REPO_NAME_BACKEND}:latest"
    export FRONTEND_IMAGE="${ACR_REPO_NAME_FRONTEND}:latest"
    export IMAGE_PULL_POLICY="Never"
    export IMAGE_PULL_SECRETS="[]"
    echo "🐳 Rancher 로컬 이미지 사용:"
  fi
else
  # ACR 이미지 사용
  export BACKEND_IMAGE="${ACR_LOGIN_SERVER}/${ACR_REPO_NAME_BACKEND}:latest"
  export FRONTEND_IMAGE="${ACR_LOGIN_SERVER}/${ACR_REPO_NAME_FRONTEND}:latest"
  export IMAGE_PULL_POLICY="Always"
  export IMAGE_PULL_SECRETS="- name: acr-registry"
  echo "🏢 ACR 이미지 사용:"
fi

echo "  Backend: ${BACKEND_IMAGE}"
echo "  Frontend: ${FRONTEND_IMAGE}"
echo "  Image Pull Policy: ${IMAGE_PULL_POLICY}"
echo "  Image Pull Secrets: ${IMAGE_PULL_SECRETS:-없음}"

# 메시징 시스템 환경 변수 설정
export MESSAGING_TYPE="${MESSAGING_TYPE:-kafka}"
export KAFKA_SERVERS="${KAFKA_SERVERS:-my-kafka}"

# LGTM Telemetry 환경 변수 설정
export TEMPO_ENDPOINT="${TEMPO_ENDPOINT:-http://collector.lgtm.20.249.154.255.nip.io/v1/traces}"
export OTLP_ENDPOINT="${OTLP_ENDPOINT:-http://collector.lgtm.20.249.154.255.nip.io}"

echo "📡 메시징 시스템 설정:"
echo "  - MESSAGING_TYPE: ${MESSAGING_TYPE}"
echo "  - KAFKA_SERVERS: ${KAFKA_SERVERS}"

echo "📊 LGTM Telemetry 설정:"
echo "  - TEMPO_ENDPOINT: ${TEMPO_ENDPOINT}"
echo "  - OTLP_ENDPOINT: ${OTLP_ENDPOINT}"

envsubst < k8s/backend-secret.yaml | kubectl apply -n "${K8S_NAMESPACE}" -f -

# Event Hubs 환경 변수 설정
if [ "${MESSAGING_TYPE}" = "eventhub" ]; then
  echo "🔐 Event Hubs Secret 적용 (Azure Event Hubs 연결)"
  envsubst < k8s/eventhub-secret.yaml | kubectl apply -n "${K8S_NAMESPACE}" -f -
  
  # Event Hubs 환경 변수를 deployment에서 사용할 수 있도록 설정
  export EVENTHUB_CONNECTION_STRING="${EVENTHUB_CONNECTION_STRING}"
  export EVENTHUB_NAME="${EVENTHUB_NAME}"
  export EVENTHUB_CONSUMER_GROUP="${EVENTHUB_CONSUMER_GROUP:-$Default}"
else
  # Kafka 사용 시 Event Hubs 환경 변수는 빈 값으로 설정
  export EVENTHUB_CONNECTION_STRING=""
  export EVENTHUB_NAME=""
  export EVENTHUB_CONSUMER_GROUP=""
fi

envsubst < k8s/backend-deployment.yaml | kubectl apply -n "${K8S_NAMESPACE}" -f -
envsubst < k8s/frontend-deployment.yaml | kubectl apply -n "${K8S_NAMESPACE}" -f -
