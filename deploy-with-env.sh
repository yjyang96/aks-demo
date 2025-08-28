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

# 메시징 시스템 설정 확인
MESSAGING_TYPE=${MESSAGING_TYPE:-kafka}
echo "📡 메시징 시스템: ${MESSAGING_TYPE}"

if [ "${MESSAGING_TYPE}" = "kafka" ]; then
  echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "┃ 2) Kafka 배포 (bitnami/kafka)"
  echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  helm upgrade --install "${KAFKA_SERVERS}" bitnami/kafka \
    --namespace "${K8S_NAMESPACE}" \
    --create-namespace \
    -f "$KAFKA_VALUES_FILE"
elif [ "${MESSAGING_TYPE}" = "eventhub" ]; then
  echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "┃ 2) Azure Event Hubs 연결 확인 (관리형 서비스)"
  echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  
  # Event Hubs Secret이 존재하는지 확인 (Azure Event Hubs는 배포하지 않음)
  if ! kubectl get secret eventhub-secret -n "${K8S_NAMESPACE}" >/dev/null 2>&1; then
    echo "❌ Event Hubs Secret이 없습니다. 먼저 ./setup-eventhub.sh를 실행하세요."
    echo "   Azure Event Hubs는 Azure Portal에서 별도로 생성해야 합니다."
    exit 1
  fi
  
  echo "✅ Event Hubs Secret 확인됨 (Azure Event Hubs 연결 준비 완료)"
else
  echo "❌ 지원하지 않는 메시징 타입: ${MESSAGING_TYPE}"
  echo "   지원되는 타입: kafka, eventhub"
  exit 1
fi

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
  # ACR 이미지 사용 (기존)
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

echo "📡 메시징 시스템 설정:"
echo "  - MESSAGING_TYPE: ${MESSAGING_TYPE}"
echo "  - KAFKA_SERVERS: ${KAFKA_SERVERS}"

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

# Azure 환경에서만 Ingress 적용
if [ "${ENV}" != "rancher" ]; then
  echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "┃ 5) Ingress 리소스 적용 (Azure App Routing 사용)"
  echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  envsubst < k8s/ingress.yaml | kubectl apply -n "${K8S_NAMESPACE}" -f -
else
  echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "┃ 5) Ingress 스킵 (Rancher 환경에서는 Azure App Routing 사용하지 않음)"
  echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

echo "⏳ MariaDB Ready 대기"
kubectl -n "${K8S_NAMESPACE}" wait --for=condition=ready pod -l app.kubernetes.io/instance="${MYSQL_HOST}" --timeout=300s || {
  echo "❌ MariaDB 파드 Ready 대기 실패"; exit 1;
}

echo "🗃️  DB 초기화 실행 (apply-db-init.sh ${ENV})"
bash ./apply-db-init.sh "${ENV}"

echo "📋 리소스 확인"
kubectl get all -n "${K8S_NAMESPACE}" | cat

# Azure 환경에서만 Ingress 접근 정보 표시
if [ "${ENV}" != "rancher" ]; then
  echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "┃ 6) Ingress 접근 정보 (Azure App Routing)"
  echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # LoadBalancer IP 가져오기
  LB_IP=$(kubectl get svc -n app-routing-system nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "로드중...")

  echo "🌐 LoadBalancer IP: ${LB_IP}"
  echo "🔗 접근 URL:"
  echo "   프론트엔드: http://frontend.${K8S_NAMESPACE}.local"
  echo "   백엔드: http://api.${K8S_NAMESPACE}.local"
  echo ""
  echo "📝 hosts 파일에 다음을 추가하세요:"
  echo "   ${LB_IP} frontend.${K8S_NAMESPACE}.local api.${K8S_NAMESPACE}.local"
else
  echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "┃ 6) Rancher 환경 접근 정보"
  echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🔗 Rancher UI에서 서비스에 접근하세요:"
  echo "   - 프론트엔드: frontend-service"
  echo "   - 백엔드: backend-service"
fi

echo "✅ 배포 완료"

# 임시 파일 정리
rm -f "$MARIADB_VALUES_FILE" "$REDIS_VALUES_FILE" "$KAFKA_VALUES_FILE"
