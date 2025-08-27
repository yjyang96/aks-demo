#!/bin/bash

set -euo pipefail

# 환경 파일 로드: 첫 번째 인자 ENV 사용, 기본값 rancher
ENV=${1:-rancher}
if [ -f "env/.env.${ENV}" ]; then
  export $(grep -v '^#' env/.env.${ENV} | xargs)
  echo "Using environment: ${ENV}"
else
  echo "Environment file not found: env/.env.${ENV}"
  exit 1
fi

# 필수/기본값
K8S_NAMESPACE=${K8S_NAMESPACE:-yejun}
DB_SECRET_NAME=${DB_SECRET_NAME:-yejun-mariadb}
DB_ROOT_KEY=${DB_ROOT_KEY:-mariadb-root-password}
INIT_SQL_PATH=${INIT_SQL_PATH:-db/init.sql}
INIT_SQL_RENDERED=$(mktemp)

if [ ! -f "$INIT_SQL_PATH" ]; then
  echo "❌ INIT SQL 파일을 찾을 수 없습니다: $INIT_SQL_PATH"
  exit 1
fi

echo "📦 네임스페이스: $K8S_NAMESPACE"
echo "🔐 시크릿: $DB_SECRET_NAME (key: $DB_ROOT_KEY)"
echo "📄 적용 파일(템플릿): $INIT_SQL_PATH"

# MariaDB 파드 찾기 (심플 매칭)
MARIADB_POD=$(kubectl -n "$K8S_NAMESPACE" get pods | awk '/mariadb|mysql/ {print $1; exit}')
if [ -z "$MARIADB_POD" ]; then
  echo "❌ MariaDB 파드를 찾지 못했습니다. 네임스페이스를 확인하세요."
  exit 1
fi

echo "🧩 대상 파드: $MARIADB_POD"

# 비밀번호 결정: .env의 DB_PASSWORD 우선, 없으면 Secret에서 루트 비밀번호 조회
if [ -n "${DB_PASSWORD:-}" ]; then
  DB_PASSWORD_EFFECTIVE="$DB_PASSWORD"
  echo "🔑 비밀번호 소스: .env(DB_PASSWORD)"
else
  echo "🔑 비밀번호 소스: Secret($DB_SECRET_NAME/$DB_ROOT_KEY)"
  DB_PASSWORD_EFFECTIVE=$(kubectl get secret --namespace "$K8S_NAMESPACE" "$DB_SECRET_NAME" -o jsonpath="{.data.$DB_ROOT_KEY}" | base64 -d)
  if [ -z "$DB_PASSWORD_EFFECTIVE" ]; then
    echo "❌ 시크릿에서 루트 비밀번호를 읽지 못했습니다."
    exit 1
  fi
fi

# init.sql 템플릿에 환경변수 주입
envsubst < "$INIT_SQL_PATH" > "$INIT_SQL_RENDERED"
echo "📝 렌더링된 SQL: $INIT_SQL_RENDERED"

# 적용 실행 (root 사용자로 접속)
set -o pipefail
cat "$INIT_SQL_RENDERED" | kubectl -n "$K8S_NAMESPACE" exec -i "$MARIADB_POD" -- sh -c "mysql -uroot -p\"$DB_PASSWORD_EFFECTIVE\""

echo "✅ init.sql 적용 완료"
