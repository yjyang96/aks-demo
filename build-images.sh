#!/bin/bash

set -euo pipefail

# 사용법: ./build-images.sh [BUILD_TYPE] [ENV] [PLATFORM]
# - BUILD_TYPE: 빌드할 이미지 타입 (기본값: a)
#   · b: 백엔드만 빌드
#   · f: 프론트엔드만 빌드  
#   · a: 전체 빌드 (백엔드 + 프론트엔드)
# - ENV: env/.env.${ENV} 로드 (기본값: rancher)
#   · rancher: 로컬 도커에만 빌드/태깅
#   · azure: 로컬 도커에 빌드 후 ACR에 태그/푸시까지 수행
# - PLATFORM: docker 빌드 플랫폼 (예: linux/amd64, linux/arm64). 미지정 시 현재 머신 기준 자동 결정

BUILD_TYPE=${1:-a}
ENV_NAME=${2:-rancher}
IMAGE_TAG="latest"  # 태그는 latest로 고정

# 빌드 타입 검증
case "${BUILD_TYPE}" in
  b|f|a)
    ;;
  *)
    echo "❌ 잘못된 빌드 타입입니다: ${BUILD_TYPE}"
    echo "사용법: ./build-images.sh [BUILD_TYPE] [ENV] [PLATFORM]"
    echo "  BUILD_TYPE: b(백엔드), f(프론트엔드), a(전체)"
    echo "  ENV: rancher, azure"
    echo "  PLATFORM: linux/amd64, linux/arm64"
    exit 1
    ;;
esac

# 플랫폼 자동 결정 (3번째 인자 우선)
HOST_ARCH="$(uname -m)"
case "${HOST_ARCH}" in
  arm64|aarch64)
    DEFAULT_PLATFORM="linux/arm64";;
  x86_64|amd64)
    DEFAULT_PLATFORM="linux/amd64";;
  *)
    DEFAULT_PLATFORM="linux/amd64";;
esac

BUILD_PLATFORM=${3:-${DEFAULT_PLATFORM}}

# Azure 환경은 기본 플랫폼을 amd64로 강제 (인자 미지정 시)
if [ "${ENV_NAME}" = "azure" ] && [ -z "${3:-}" ]; then
  BUILD_PLATFORM="linux/amd64"
  echo "ℹ️ Azure 환경 감지: 기본 빌드 플랫폼을 linux/amd64 로 설정합니다."
fi

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "${ROOT_DIR}/env/.env.${ENV_NAME}" ]; then
    export $(grep -v '^#' "${ROOT_DIR}/env/.env.${ENV_NAME}" | xargs)
    echo "Building for environment: ${ENV_NAME}"
else
    echo "Environment file not found: ${ROOT_DIR}/env/.env.${ENV_NAME}"
    exit 1
fi

# Rancher 환경에서는 레지스트리 프리픽스 없이 이름만 사용
BACKEND_IMAGE_NAME="${ACR_REPO_NAME_BACKEND}:${IMAGE_TAG}"
FRONTEND_IMAGE_NAME="${ACR_REPO_NAME_FRONTEND}:${IMAGE_TAG}"

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 빌드 설정"
echo "┃ • 타입: ${BUILD_TYPE} (b:백엔드, f:프론트엔드, a:전체)"
echo "┃ • 환경: ${ENV_NAME}"
echo "┃ • 플랫폼: ${BUILD_PLATFORM}"
echo "┃ • 태그: ${IMAGE_TAG}"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 백엔드 빌드
if [ "${BUILD_TYPE}" = "b" ] || [ "${BUILD_TYPE}" = "a" ]; then
  echo ""
  echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "┃ 1) Backend 이미지 빌드 → ${BACKEND_IMAGE_NAME} (${BUILD_PLATFORM})"
  echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  docker build \
    --platform "${BUILD_PLATFORM}" \
    --no-cache \
    -t "${BACKEND_IMAGE_NAME}" \
    -f "${ROOT_DIR}/backend/Dockerfile" \
    "${ROOT_DIR}/backend"
  echo "✅ 백엔드 빌드 완료"
fi

# 프론트엔드 빌드
if [ "${BUILD_TYPE}" = "f" ] || [ "${BUILD_TYPE}" = "a" ]; then
  echo ""
  echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "┃ 2) Frontend 이미지 빌드 → ${FRONTEND_IMAGE_NAME} (${BUILD_PLATFORM})"
  echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  docker build \
    --platform "${BUILD_PLATFORM}" \
    --no-cache \
    -t "${FRONTEND_IMAGE_NAME}" \
    -f "${ROOT_DIR}/frontend/Dockerfile" \
    "${ROOT_DIR}/frontend"
  echo "✅ 프론트엔드 빌드 완료"
fi

echo ""
echo "✅ 로컬 Docker에 이미지가 생성되었습니다. (platform=${BUILD_PLATFORM})"
echo "ℹ️ 배포 스크립트에서 ENV=rancher 를 사용하면 위 이름으로 바로 참조됩니다."

# Azure(ACR) 푸시 옵션
if [ "${ENV_NAME}" = "azure" ]; then
  echo ""
  echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "┃ 3) Azure ACR 로그인/태깅/푸시"
  echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [ -z "${ACR_LOGIN_SERVER:-}" ]; then
    echo "❌ ACR_LOGIN_SERVER 가 설정되어 있지 않습니다. env/.env.azure 를 확인하세요."
    exit 1
  fi

  # ACR 이름 추출 (ktech4.azurecr.io -> ktech4)
  ACR_NAME="${ACR_LOGIN_SERVER%%.*}"

  echo "🔐 ACR 로그인 시도 (az acr login -n ${ACR_NAME})"
  if command -v az >/dev/null 2>&1; then
    if ! az acr login -n "${ACR_NAME}" >/dev/null 2>&1; then
      echo "⚠️ az acr login 실패. 도커 로그인 시도(${ACR_LOGIN_SERVER})"
      if [ -n "${ACR_USERNAME:-}" ] && [ -n "${ACR_PASSWORD:-}" ]; then
        echo "docker login ${ACR_LOGIN_SERVER} -u "+"ACR_USERNAME"+" -p ******"
        echo "${ACR_PASSWORD}" | docker login "${ACR_LOGIN_SERVER}" -u "${ACR_USERNAME}" --password-stdin
      else
        echo "❌ 도커 로그인 정보(ACR_USERNAME/ACR_PASSWORD)가 없습니다. 로그인에 실패했습니다."
        exit 1
      fi
    else
      echo "✅ az acr login 성공"
    fi
  else
    echo "⚠️ Azure CLI(az)가 없습니다. 도커 로그인 사용 시도"
    if [ -n "${ACR_USERNAME:-}" ] && [ -n "${ACR_PASSWORD:-}" ]; then
      echo "docker login ${ACR_LOGIN_SERVER} -u "+"ACR_USERNAME"+" -p ******"
      echo "${ACR_PASSWORD}" | docker login "${ACR_LOGIN_SERVER}" -u "${ACR_USERNAME}" --password-stdin
    else
      echo "❌ az 또는 ACR_USERNAME/ACR_PASSWORD 중 하나가 필요합니다."
      exit 1
    fi
  fi

  BACKEND_ACR_IMAGE="${ACR_LOGIN_SERVER}/${ACR_REPO_NAME_BACKEND}:${IMAGE_TAG}"
  FRONTEND_ACR_IMAGE="${ACR_LOGIN_SERVER}/${ACR_REPO_NAME_FRONTEND}:${IMAGE_TAG}"

  # 백엔드 푸시
  if [ "${BUILD_TYPE}" = "b" ] || [ "${BUILD_TYPE}" = "a" ]; then
    echo "🏷️  태깅: ${BACKEND_IMAGE_NAME} -> ${BACKEND_ACR_IMAGE}"
    docker tag "${BACKEND_IMAGE_NAME}" "${BACKEND_ACR_IMAGE}"
    echo "📤 푸시: ${BACKEND_ACR_IMAGE}"
    docker push "${BACKEND_ACR_IMAGE}"
  fi

  # 프론트엔드 푸시
  if [ "${BUILD_TYPE}" = "f" ] || [ "${BUILD_TYPE}" = "a" ]; then
    echo "🏷️  태깅: ${FRONTEND_IMAGE_NAME} -> ${FRONTEND_ACR_IMAGE}"
    docker tag "${FRONTEND_IMAGE_NAME}" "${FRONTEND_ACR_IMAGE}"
    echo "📤 푸시: ${FRONTEND_ACR_IMAGE}"
    docker push "${FRONTEND_ACR_IMAGE}"
  fi

  echo "✅ ACR 푸시 완료"
  echo "ℹ️ 배포 시: ./deploy-with-env.sh azure true 로 이미지 풀/배포가 가능합니다."
fi

echo ""
echo "🎉 빌드 완료!"
echo "사용 예시:"
echo "  ./build-images.sh b    # 백엔드만 빌드"
echo "  ./build-images.sh f    # 프론트엔드만 빌드"
echo "  ./build-images.sh a    # 전체 빌드"
echo "  ./build-images.sh b azure    # 백엔드만 Azure ACR에 푸시"
echo "  ./build-images.sh f rancher linux/arm64    # 프론트엔드만 ARM64로 빌드"

