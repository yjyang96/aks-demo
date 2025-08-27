#!/bin/bash

echo "🚀 배포 삭제를 시작합니다..."

# .env 파일 로드
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo ".env 파일을 로드했습니다."
else
    echo ".env 파일이 없습니다. env.example을 복사해서 .env 파일을 만드세요."
    exit 1
fi

echo "📦 Kubernetes 리소스 삭제 중..."

# Deployment 삭제
echo "🗑️  Deployment 삭제 중..."
kubectl delete deployment backend -n ${K8S_NAMESPACE} --ignore-not-found=true
kubectl delete deployment frontend -n ${K8S_NAMESPACE} --ignore-not-found=true

# Service 삭제
echo "🗑️  Service 삭제 중..."
kubectl delete service backend-service -n ${K8S_NAMESPACE} --ignore-not-found=true
kubectl delete service frontend-service -n ${K8S_NAMESPACE} --ignore-not-found=true

# Secret 삭제 (선택사항 - 주석 해제하면 삭제됨)
echo "🗑️  Secret 삭제 중..."
kubectl delete secret backend-secrets -n ${K8S_NAMESPACE} --ignore-not-found=true

# ConfigMap 삭제
# echo "🗑️  ConfigMap 삭제 중..."
# kubectl delete configmap app-config -n ${K8S_NAMESPACE} --ignore-not-found=true

# Pod 확인
echo "📋 남은 Pod 확인 중..."
kubectl get pods -n ${K8S_NAMESPACE}

echo "✅ 배포 삭제 완료!"
