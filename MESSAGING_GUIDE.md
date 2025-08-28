# 메시징 시스템 사용 가이드

이 프로젝트는 Kafka와 Azure Event Hubs를 환경 변수로 선택하여 사용할 수 있습니다.

## 메시징 시스템 선택

환경 변수 `MESSAGING_TYPE`을 통해 사용할 메시징 시스템을 선택할 수 있습니다:

- `kafka`: Apache Kafka 사용 (기본값)
- `eventhub`: Azure Event Hubs 사용

## 1. Kafka 사용하기

### 환경 변수 설정
`env/.env.local` 파일에서 다음을 설정하세요:

```bash
# 메시징 시스템 타입
MESSAGING_TYPE=kafka

# Kafka 설정
KAFKA_SERVERS=my-kafka
KAFKA_USERNAME=user1
KAFKA_PASSWORD=your-kafka-password
```

### 배포
```bash
./deploy-with-env.sh rancher
```

## 2. Azure Event Hubs 사용하기

### 사전 준비 (Azure Portal에서 수행)
1. Azure Portal에서 Event Hubs 네임스페이스 생성
2. Event Hub 생성
3. 연결 문자열 및 액세스 키 확인

**참고**: Event Hubs는 Azure 관리형 서비스이므로 Kubernetes에 배포하지 않습니다.

### 환경 변수 설정
`env/.env.local` 파일에서 다음을 설정하세요:

```bash
# 메시징 시스템 타입
MESSAGING_TYPE=eventhub

# Event Hubs 설정
EVENTHUB_CONNECTION_STRING=Endpoint=sb://your-namespace.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=your-key
EVENTHUB_NAME=your-eventhub-name
EVENTHUB_CONSUMER_GROUP=$Default
```

### Event Hubs Secret 설정
```bash
./setup-eventhub.sh
```

### 배포
```bash
./deploy-with-env.sh rancher
```

## 3. API 엔드포인트

### 로그 조회
- **Kafka 사용 시**: `/logs/messaging` (기존 `/logs/kafka`와 동일)
- **Event Hubs 사용 시**: `/logs/messaging` (기존 `/logs/kafka`와 동일)

### 로그 데이터 형식
```json
{
  "timestamp": "2024-01-01T12:00:00",
  "endpoint": "/api/message",
  "method": "POST",
  "status": "success",
  "user_id": "username",
  "message": "사용자가 API를 호출했습니다"
}
```

## 4. 아키텍처

### 메시징 인터페이스
- `MessagingInterface`: 추상 인터페이스
- `KafkaMessaging`: Kafka 구현
- `EventHubMessaging`: Event Hubs 구현
- `MessagingFactory`: 팩토리 패턴으로 적절한 구현 선택

### 비동기 로깅
- 모든 API 호출은 비동기적으로 메시징 시스템에 로깅됩니다
- 메인 API 응답 시간에 영향을 주지 않습니다

## 5. 문제 해결

### Event Hubs 연결 오류
1. 연결 문자열 확인
2. Event Hub 이름 확인
3. 네트워크 연결 확인
4. Azure 서비스 권한 확인

### Kafka 연결 오류
1. Kafka 서버 상태 확인
2. 인증 정보 확인
3. 네트워크 연결 확인

### 로그 확인
```bash
# 백엔드 로그 확인
kubectl logs -f deployment/backend -n your-namespace

# 메시징 시스템 로그 확인
kubectl logs -f deployment/backend -n your-namespace | grep -i "messaging\|kafka\|eventhub"
```

## 6. 성능 고려사항

### Kafka
- 로컬 네트워크에서 빠른 성능
- 자체 관리 필요
- 확장성 우수

### Event Hubs
- Azure 관리형 서비스 (별도 배포 불필요)
- 높은 처리량 지원
- 자동 확장
- Azure 생태계와 통합 우수

## 7. 비용 비교

### Kafka
- 인프라 비용 (서버, 스토리지)
- 운영 비용 (관리, 모니터링)

### Event Hubs
- 사용량 기반 과금
- 처리량 단위당 과금
- 스토리지 비용 별도
- 인프라 관리 비용 없음 (Azure 관리)

## 8. 마이그레이션

### Kafka에서 Event Hubs로
1. `MESSAGING_TYPE=eventhub`로 변경
2. Event Hubs 설정 추가
3. `./setup-eventhub.sh` 실행
4. 재배포

### Event Hubs에서 Kafka로
1. `MESSAGING_TYPE=kafka`로 변경
2. Kafka 설정 확인
3. 재배포
