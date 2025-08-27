#!/bin/bash

# .env 파일 로드
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo ".env 파일을 로드했습니다."
else
    echo ".env 파일이 없습니다. env.example을 복사해서 .env 파일을 만드세요."
    exit 1
fi

# Kubernetes 시크릿에서 비밀번호 가져오기
export DB_PASSWORD=$(kubectl get secret --namespace ${K8S_NAMESPACE} ${DB_SECRET_NAME} -o jsonpath="{.data.mariadb-root-password}" | base64 -d)

# 환경 변수 확인
echo "환경 변수 확인:"
echo "ACR_LOGIN_SERVER: $ACR_LOGIN_SERVER"
echo "ACR_REPO_NAME_BACKEND: $ACR_REPO_NAME_BACKEND"
echo "K8S_NAMESPACE: $K8S_NAMESPACE"
echo "DB_SECRET_NAME: $DB_SECRET_NAME"
echo "DB_PASSWORD: [HIDDEN]"

# Kubernetes에 배포
envsubst < k8s/backend-secret.yaml | kubectl apply -f -
envsubst < k8s/backend-deployment.yaml | kubectl apply -f -
envsubst < k8s/frontend-deployment.yaml | kubectl apply -f -

echo "📋 Pod 확인 중..."
kubectl get pods -n ${K8S_NAMESPACE}

echo "배포 완료!"
