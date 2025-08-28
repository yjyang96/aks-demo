# CI/CD 파이프라인 가이드

## 개요
이 프로젝트는 Docker Hub를 사용한 CI/CD 파이프라인을 구축합니다.
GitHub Actions에서 Docker 이미지를 빌드하고 Docker Hub에 푸시한 후, 로컬에서 배포합니다.

## GitHub Secrets 설정

### Docker Hub 관련
- `DOCKER_HUB_USERNAME`: Docker Hub 사용자명
- `DOCKER_HUB_ACCESS_TOKEN`: Docker Hub 액세스 토큰

## 워크플로우 설명

### 1. 트리거 조건
- **rancher 브랜치 push**: 이미지 빌드 및 푸시
- Pull Request에서는 실행되지 않음

### 2. 이미지 태그
- `latest`: 최신 버전
- `{sha}`: 커밋 해시

### 3. 멀티 아키텍처 지원
- `linux/amd64`: Intel/AMD 64비트 프로세서
- `linux/arm64`: ARM 64비트 프로세서 (Apple Silicon, ARM 서버)
- 맥북 M1/M2에서도 최적화된 성능

### 4. 캐시 최적화
- GitHub Actions 캐시 사용 (`cache-from`, `cache-to`)
- `docker/build-push-action` 내장 캐시 기능 활용
- Docker layer 캐싱으로 빌드 속도 향상

### 5. 배포 방식
- Docker Hub에 이미지 푸시 완료 후
- 로컬에서 `deploy-with-env.sh` 스크립트로 배포

## 사용법

### 1. Secrets 설정
GitHub 저장소 Settings > Secrets and variables > Actions에서 위의 secrets를 설정

### 2. Docker Hub 액세스 토큰 생성
1. Docker Hub 로그인
2. Account Settings > Security > New Access Token
3. 토큰 생성 후 GitHub Secrets에 등록

### 3. 로컬 배포
rancher 브랜치에 푸시 후 GitHub Actions에서 빌드 완료 시:
```bash
# 환경 변수 설정
export BACKEND_IMAGE="your-dockerhub-username/aks-demo-backend:commit-sha"
export FRONTEND_IMAGE="your-dockerhub-username/aks-demo-frontend:commit-sha"

# 배포 실행
./deploy-with-env.sh
```

## 워크플로우 파일
- `ci.yml`: ACR용 (기존)
- `ci-dockerhub.yml`: Docker Hub용 (rancher 브랜치 push 전용, 멀티 아키텍처 지원)
