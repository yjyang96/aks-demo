# K8s 마이크로서비스 데모

이 프로젝트는 Kubernetes 환경에서 Redis, MariaDB, Kafka를 활용하는 마이크로서비스 데모입니다.

## 주요 기능

### 1. 사용자 관리
- 회원가입: 새로운 사용자 등록
- 로그인/로그아웃: 세션 기반 인증
- Redis를 활용한 세션 관리

### 2. 메시지 관리 (MariaDB)
- 메시지 저장: 사용자가 입력한 메시지를 DB에 저장
- 메시지 조회: 저장된 메시지 목록 표시
- 샘플 데이터 생성: 테스트용 샘플 메시지 생성
- 페이지네이션: 대량의 데이터 효율적 처리

### 3. 검색 기능
- 메시지 검색: 특정 키워드로 메시지 검색
- 전체 메시지 조회: 모든 저장된 메시지 표시
- Redis 캐시를 활용한 검색 성능 최적화

### 4. 로깅 시스템
- Redis 로깅: API 호출 로그 저장 및 조회
- 메시징 시스템 로깅: Kafka 또는 Azure Event Hubs를 통한 API 통계 데이터 수집

## 데이터베이스 구조

### MariaDB
```sql
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    message TEXT,
    created_at DATETIME,
    user_id VARCHAR(255)
);
```

### Redis 데이터 구조
- 세션 저장: `session:{username}`
- API 로그: `api_logs` (List 타입)
- 검색 캐시: `search:{query}`

## API 엔드포인트

### 사용자 관리
- POST /register: 회원가입
- POST /login: 로그인
- POST /logout: 로그아웃

### 메시지 관리
- POST /db/message: 메시지 저장
- GET /db/messages: 전체 메시지 조회
- GET /db/messages/search: 메시지 검색

### 로그 관리
- GET /logs/redis: Redis 로그 조회
- GET /logs/messaging: 메시징 시스템 로그 조회 (Kafka/Event Hubs)

## 환경 변수 설정
```yaml
- MYSQL_HOST: MariaDB 호스트
- MYSQL_USER: MariaDB 사용자
- MYSQL_PASSWORD: MariaDB 비밀번호
- REDIS_HOST: Redis 호스트
- REDIS_PASSWORD: Redis 비밀번호
- MESSAGING_TYPE: 메시징 시스템 타입 (kafka 또는 eventhub)
- KAFKA_SERVERS: Kafka 서버 (MESSAGING_TYPE=kafka일 때)
- KAFKA_USERNAME: Kafka 사용자 (MESSAGING_TYPE=kafka일 때)
- KAFKA_PASSWORD: Kafka 비밀번호 (MESSAGING_TYPE=kafka일 때)
- EVENTHUB_CONNECTION_STRING: Event Hubs 연결 문자열 (MESSAGING_TYPE=eventhub일 때)
- EVENTHUB_NAME: Event Hub 이름 (MESSAGING_TYPE=eventhub일 때)
- EVENTHUB_CONSUMER_GROUP: Consumer Group (MESSAGING_TYPE=eventhub일 때)
- FLASK_SECRET_KEY: Flask 세션 암호화 키
```

## 보안 기능
- 비밀번호 해시화 저장
- 세션 기반 인증
- Redis를 통한 세션 관리
- API 접근 제어

## 성능 최적화
- Redis 캐시를 통한 검색 성능 향상
- 비동기 로깅으로 API 응답 시간 개선
- 페이지네이션을 통한 대용량 데이터 처리

## 모니터링
- API 호출 로그 저장 및 조회
- 사용자 행동 추적
- 시스템 성능 모니터링

## 모니터링 스택 (OpenTelemetry + LGTM)

### LGTM (Logs, Grafana, Tempo, Metrics) 통합
이 프로젝트는 LGTM 스택을 통한 완전한 관찰성(Observability)을 제공합니다:

#### 1. Traces (분산 추적) - Tempo
- **엔드포인트**: `http://collector.lgtm.20.249.154.255.nip.io/v1/traces`
- **수집 데이터**:
  - HTTP 요청/응답 추적
  - 데이터베이스 쿼리 추적
  - Redis 작업 추적
  - Kafka 메시징 추적
  - 사용자 세션 추적
  - API 호출 체인 추적

#### 2. Metrics (메트릭) - Prometheus
- **엔드포인트**: `http://collector.lgtm.20.249.154.255.nip.io/v1/metrics`
- **수집 데이터**:
  - API 호출 횟수 및 응답 시간
  - 데이터베이스 연결 상태
  - Redis 연결 상태
  - 오류율 및 성능 지표
  - 사용자 활동 메트릭

#### 3. Logs (로그) - OpenTelemetry Logs
- **엔드포인트**: `http://collector.lgtm.20.249.154.255.nip.io/v1/logs`
- **수집 데이터**:
  - 애플리케이션 로그
  - 사용자 인증 로그 (로그인/로그아웃/회원가입)
  - 데이터베이스 작업 로그
  - 오류 및 예외 로그
  - API 호출 로그
  - 시스템 이벤트 로그

### 환경 변수 설정
```yaml
# LGTM Telemetry 설정
- TEMPO_ENDPOINT: http://collector.lgtm.20.249.154.255.nip.io/v1/traces
- OTLP_ENDPOINT: http://collector.lgtm.20.249.154.255.nip.io
- BACKEND_SERVICE_NAME: aks-demo-backend
- FRONTEND_SERVICE_NAME: aks-demo-frontend
```

### 모니터링 기능
- **실시간 추적**: 모든 API 호출의 전체 라이프사이클 추적
- **성능 모니터링**: 응답 시간, 처리량, 오류율 실시간 모니터링
- **로그 분석**: 구조화된 로그를 통한 문제 진단 및 분석
- **사용자 행동 분석**: 로그인 패턴, API 사용 패턴 분석
- **시스템 건강도**: 데이터베이스, Redis, Kafka 연결 상태 모니터링

이 프로젝트는 OpenTelemetry와 LGTM 스택을 사용하여 종합적인 모니터링을 지원합니다.

### LGTM 스택이란?
- **L**oki: 로그 수집 및 저장
- **G**rafana: 시각화 및 대시보드  
- **T**empo: 분산 추적 (Jaeger 대체)
- **M**imir: 메트릭 저장 및 쿼리

### LGTM vs Jaeger 비교
| 기능 | Jaeger | LGTM (Tempo) |
|------|--------|--------------|
| **UI** | 자체 UI 제공 | Grafana 통합 |
| **로그 연관성** | 제한적 | Loki와 완벽 통합 |
| **메트릭 연관성** | 제한적 | Prometheus/Mimir와 완벽 통합 |
| **확장성** | 중간 | 높음 |
| **설정 복잡도** | 낮음 | 중간 |
| **통합성** | 독립적 | 완전 통합 |

### 백엔드 OpenTelemetry 설정

1. **의존성 설치**
```bash
pip install -r backend/requirements.txt
```

2. **환경 변수 설정**
```bash
# OpenTelemetry 설정 (LGTM 스택)
ENVIRONMENT=development
OTLP_ENDPOINT=http://tempo.${K8S_NAMESPACE}.svc.cluster.local:4317
TEMPO_ENDPOINT=http://tempo.${K8S_NAMESPACE}.svc.cluster.local:4317

# Jaeger 설정 (선택적, 기존 호환성)
# JAEGER_HOST=localhost
# JAEGER_PORT=14268
```

3. **자동 계측**
- Flask HTTP 요청/응답 추적
- MySQL 데이터베이스 쿼리 추적
- Redis 작업 추적
- Kafka 메시지 전송 추적

### 프론트엔드 OpenTelemetry 설정

1. **의존성 설치**
```bash
cd frontend
npm install
```

2. **환경 변수 설정**
```bash
# .env 파일에 추가
VUE_APP_TEMPO_ENDPOINT=http://tempo.${K8S_NAMESPACE}.svc.cluster.local:4317/v1/traces
VUE_APP_OTLP_ENDPOINT=http://tempo.${K8S_NAMESPACE}.svc.cluster.local:4317/v1/traces
```

3. **자동 계측**
- 페이지 로딩 시간 추적
- 사용자 인터랙션 추적
- API 호출 추적
- Vue 컴포넌트 생명주기 추적

### LGTM 스택 설치 및 설정

1. **LGTM 스택 설치**
```bash
./setup-lgtm.sh
```

2. **Grafana 접근**
```bash
kubectl port-forward -n <namespace> svc/grafana 3000:3000
```
브라우저에서 http://localhost:3000 접속
또는 외부 URL: http://grafana.20.249.154.255.nip.io
로그인: admin / New1234!

### Jaeger 설치 (선택사항)

기존 Jaeger를 사용하려면:
```bash
./setup-jaeger.sh
```

### 수집되는 추적 데이터

#### 백엔드
- HTTP 요청/응답 (Flask 자동 계측)
- 데이터베이스 쿼리 (MySQL 자동 계측)
- Redis 작업 (Redis 자동 계측)
- Kafka 메시지 전송 (Kafka 자동 계측)
- 커스텀 비즈니스 로직 추적

#### 프론트엔드
- 페이지 로딩 (Document Load 자동 계측)
- 사용자 클릭/입력 (User Interaction 자동 계측)
- API 호출 (Fetch 자동 계측)
- Vue 컴포넌트 생명주기
- 커스텀 사용자 액션 추적

### 메트릭 수집

다음 메트릭들이 자동으로 수집됩니다:
- `db_operations_total`: 데이터베이스 작업 수
- `kafka_messages_sent_total`: Kafka 메시지 전송 수
- `http_requests_total`: HTTP 요청 수
- `http_request_duration_seconds`: HTTP 요청 지속 시간

### 로그-트레이스-메트릭 상관관계

LGTM 스택을 사용하면 다음 상관관계를 확인할 수 있습니다:
- **로그 → 트레이스**: Loki에서 로그를 찾고 관련 트레이스로 이동
- **트레이스 → 메트릭**: Tempo에서 트레이스를 찾고 관련 메트릭으로 이동  
- **메트릭 → 로그**: Prometheus에서 메트릭을 찾고 관련 로그로 이동

### 커스텀 추적 추가

#### 백엔드에서 커스텀 Span 생성
```python
from telemetry import telemetry_manager

tracer = telemetry_manager.get_tracer()
with tracer.start_as_current_span("custom_operation") as span:
    span.set_attribute("custom.attribute", "value")
    # 비즈니스 로직 실행
```

#### 프론트엔드에서 커스텀 Span 생성
```javascript
import frontendTelemetry from './telemetry'

const span = frontendTelemetry.createSpan('custom_action', {
    'action.type': 'button_click',
    'action.target': 'submit_button'
})
// 비즈니스 로직 실행
span.end()
``` 