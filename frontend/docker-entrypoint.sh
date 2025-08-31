#!/bin/bash

# 환경 변수를 nginx 설정 템플릿에 적용
envsubst '${BACKEND_SERVICE_NAME}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

# nginx 설정 테스트
nginx -t

# 원래 명령어 실행
exec "$@"
