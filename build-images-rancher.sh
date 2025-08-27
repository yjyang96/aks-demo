#!/bin/bash

set -euo pipefail

# 사용법: ./build-images-rancher.sh [ENV] [TAG] [PLATFORM]
# - ENV: env/.env.${ENV} 로드 (기본값: rancher)
# - TAG: 이미지 태그 (기본값: latest)
# - PLATFORM: docker 빌드 플랫폼 (예: linux/amd64, linux/arm64). 미지정 시 현재 머신 기준 자동 결정

ENV_NAME=${1:-rancher}
IMAGE_TAG=${2:-latest}

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

# 기존 이미지 강제 삭제 (선택적)
# echo "🧹 기존 이미지 정리 중..."
# docker rmi "${BACKEND_IMAGE_NAME}" 2>/dev/null || true
# docker rmi "${FRONTEND_IMAGE_NAME}" 2>/dev/null || true

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 1) Backend 이미지 빌드 → ${BACKEND_IMAGE_NAME} (${BUILD_PLATFORM})"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker build \
  --platform "${BUILD_PLATFORM}" \
  --no-cache \
  -t "${BACKEND_IMAGE_NAME}" \
  -f "${ROOT_DIR}/backend/Dockerfile" \
  "${ROOT_DIR}/backend"

echo "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "┃ 2) Frontend 이미지 빌드 → ${FRONTEND_IMAGE_NAME} (${BUILD_PLATFORM})"
echo "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker build \
  --platform "${BUILD_PLATFORM}" \
  --no-cache \
  -t "${FRONTEND_IMAGE_NAME}" \
  -f "${ROOT_DIR}/frontend/Dockerfile" \
  "${ROOT_DIR}/frontend"

echo "✅ 로컬 Docker에 이미지가 생성되었습니다. (platform=${BUILD_PLATFORM})"
echo "ℹ️ 배포 스크립트에서 ENV=rancher 를 사용하면 위 이름으로 바로 참조됩니다."


