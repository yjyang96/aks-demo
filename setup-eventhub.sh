#!/bin/bash

# Azure Event Hubs 설정 스크립트
# 이 스크립트는 Azure Event Hubs를 설정하고 Kubernetes Secret을 생성합니다.

set -e

echo "🚀 Azure Event Hubs 설정을 시작합니다..."

# 환경 변수 파일 확인
if [ ! -f "env/.env.local" ]; then
    echo "❌ env/.env.local 파일이 없습니다. 먼저 환경 변수를 설정해주세요."
    exit 1
fi

# 환경 변수 로드
source env/.env.local

# 필수 환경 변수 확인
if [ -z "$EVENTHUB_CONNECTION_STRING" ] || [ -z "$EVENTHUB_NAME" ]; then
    echo "❌ EVENTHUB_CONNECTION_STRING 또는 EVENTHUB_NAME이 설정되지 않았습니다."
    echo "env/.env.local 파일에서 Event Hubs 설정을 확인해주세요."
    exit 1
fi

echo "📋 Event Hubs 설정 정보:"
echo "  - Event Hub Name: $EVENTHUB_NAME"
echo "  - Consumer Group: ${EVENTHUB_CONSUMER_GROUP:-$Default}"

# Event Hubs Secret 생성
echo "🔐 Event Hubs Secret을 생성합니다..."

# base64로 인코딩
CONNECTION_STRING_B64=$(echo -n "$EVENTHUB_CONNECTION_STRING" | base64)
EVENTHUB_NAME_B64=$(echo -n "$EVENTHUB_NAME" | base64)
CONSUMER_GROUP_B64=$(echo -n "${EVENTHUB_CONSUMER_GROUP:-$Default}" | base64)

# Secret 매니페스트 생성
cat > k8s/eventhub-secret.yaml << EOF
apiVersion: v1
kind: Secret
metadata:
  name: eventhub-secret
  namespace: ${K8S_NAMESPACE:-default}
type: Opaque
data:
  connection-string: ${CONNECTION_STRING_B64}
  eventhub-name: ${EVENTHUB_NAME_B64}
  consumer-group: ${CONSUMER_GROUP_B64}
EOF

echo "✅ Event Hubs Secret 매니페스트가 생성되었습니다: k8s/eventhub-secret.yaml"

# Kubernetes에 Secret 적용
echo "🔧 Kubernetes에 Event Hubs Secret을 적용합니다..."
kubectl apply -f k8s/eventhub-secret.yaml

echo "✅ Event Hubs 설정이 완료되었습니다!"
echo ""
echo "📝 다음 단계:"
echo "  1. env/.env.local에서 MESSAGING_TYPE=eventhub로 설정하세요."
echo "  2. ./deploy-with-env.sh로 배포를 시작하세요."
echo ""
echo "🚀 배포를 시작하려면: ./deploy-with-env.sh"
