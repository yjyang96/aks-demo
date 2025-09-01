from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
import redis
import mysql.connector
import json
from datetime import datetime, timedelta, timezone
import os
from messaging_interface import async_log_api_stats
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from threading import Thread
import hashlib
from telemetry import telemetry_manager

app = Flask(__name__)
CORS(app, supports_credentials=True)  # 세션을 위한 credentials 지원
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')  # 세션을 위한 시크릿 키

# OpenTelemetry 설정
telemetry_manager.setup_telemetry(app)

# Flask-Session 설정
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.Redis(
    host=os.getenv('REDIS_HOST', 'my-redis-master'),
    port=6379,
    password=os.getenv('REDIS_PASSWORD'),
    db=1  # 세션용 별도 DB 사용
)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)  # 세션 만료 시간을 1시간으로 설정
app.config['SESSION_COOKIE_SECURE'] = False  # 개발 환경에서는 False, 프로덕션에서는 True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF 보호

# Flask-Session 초기화
Session(app)

# datetime 객체를 JSON 직렬화 가능한 형태로 변환하는 함수
def serialize_datetime(obj):
    if isinstance(obj, datetime):
        # 원래 형식과 동일하게 변환 (예: "Wed, 27 Aug 2025 19:14:30 GMT")
        return obj.strftime("%a, %d %b %Y %H:%M:%S GMT")
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

# ===== 공통 로깅 데코레이터 =====
def log_operation(operation_name, component="api", log_success=True, log_errors=True):
    """
    함수 실행을 자동으로 로깅하는 데코레이터
    
    Args:
        operation_name: 작업 이름 (예: "db_insert", "user_login")
        component: 컴포넌트 이름 (예: "database", "authentication")
        log_success: 성공 시 로깅 여부
        log_errors: 오류 시 로깅 여부
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = telemetry_manager.get_tracer()
            meter = telemetry_manager.get_meter()
            
            # 사용자 정보 추출
            user_id = session.get('user_id', 'anonymous') if 'user_id' in session else 'anonymous'
            
            with tracer.start_as_current_span(f"{operation_name}") as span:
                try:
                    # 공통 span 속성 설정
                    span.set_attribute("user.id", user_id)
                    span.set_attribute("operation.name", operation_name)
                    span.set_attribute("component", component)
                    span.set_attribute("remote.addr", request.remote_addr)
                    
                    # 메트릭 기록
                    telemetry_manager.record_metric(f"{operation_name}_total", 1, {"status": "started"})
                    
                    # 실제 함수 실행
                    result = func(*args, **kwargs)
                    
                    # 성공 로깅
                    if log_success:
                        telemetry_manager.log_info(f"{operation_name} completed successfully", {
                            "action": f"{operation_name}_success",
                            "user_id": user_id,
                            "component": component,
                            "remote_addr": request.remote_addr
                        })
                    
                    # 성공 메트릭
                    telemetry_manager.record_metric(f"{operation_name}_total", 1, {"status": "success"})
                    
                    return result
                    
                except Exception as e:
                    # 오류 span 속성 설정
                    span.set_attribute("error", True)
                    span.set_attribute("error.message", str(e))
                    
                    # 오류 로깅
                    if log_errors:
                        telemetry_manager.log_error(f"{operation_name} failed: {str(e)}", {
                            "action": f"{operation_name}_error",
                            "user_id": user_id,
                            "error": str(e),
                            "component": component,
                            "remote_addr": request.remote_addr
                        })
                    
                    # 오류 메트릭
                    telemetry_manager.record_metric(f"{operation_name}_total", 1, {"status": "error"})
                    
                    raise
                    
        return wrapper
    return decorator

# ===== 보안 관련 로깅 데코레이터 =====
def log_security_event(event_type, log_success=True, log_failures=True):
    """
    보안 관련 이벤트를 로깅하는 데코레이터
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                
                # 성공 로깅 (로그인, 회원가입 성공 등)
                if log_success:
                    username = kwargs.get('username') or (request.json.get('username') if request.json else None)
                    telemetry_manager.log_info(f"{event_type} successful", {
                        "action": f"{event_type}_success",
                        "username": username,
                        "remote_addr": request.remote_addr,
                        "user_agent": request.headers.get('User-Agent', ''),
                        "component": "authentication"
                    })
                
                return result
                
            except Exception as e:
                # 실패 로깅 (잘못된 인증 정보 등)
                if log_failures:
                    username = kwargs.get('username') or (request.json.get('username') if request.json else None)
                    telemetry_manager.log_warn(f"{event_type} failed: {str(e)}", {
                        "action": f"{event_type}_failed",
                        "username": username,
                        "error": str(e),
                        "remote_addr": request.remote_addr,
                        "user_agent": request.headers.get('User-Agent', ''),
                        "component": "authentication"
                    })
                raise
                
        return wrapper
    return decorator

# 세션 활동 시간 업데이트 미들웨어
@app.before_request
def update_session_activity():
    """요청마다 세션 활동 시간을 업데이트합니다."""
    if 'user_id' in session:
        # Flask-Session이 자동으로 세션을 Redis에 저장하므로
        # 단순히 last_activity만 업데이트
        session['last_activity'] = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        session.modified = True  # 세션 변경사항을 Redis에 저장
        
        # 세션 활동 업데이트 로깅 (너무 자주 로깅되지 않도록 간헐적으로)
        import random
        if random.random() < 0.01:  # 1% 확률로만 로깅
            telemetry_manager.log_info(f"Session activity updated for user {session['user_id']}", {
                "action": "session_activity_update",
                "username": session['user_id'],
                "remote_addr": request.remote_addr,
                "component": "session"
            })

# # 스레드 풀 생성
# thread_pool = ThreadPoolExecutor(max_workers=5)

# MariaDB 연결 함수
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'my-mariadb'),
            user=os.getenv('MYSQL_USER', 'testuser'),
            password=os.getenv('MYSQL_PASSWORD'),
            database="yejun-db",
            connect_timeout=30
        )
        
        # 데이터베이스 연결 성공 로깅
        telemetry_manager.log_info("Database connection established", {
            "action": "db_connect",
            "host": os.getenv('MYSQL_HOST', 'my-mariadb'),
            "database": "yejun-db",
            "component": "database"
        })
        
        return connection
    except Exception as e:
        # 데이터베이스 연결 실패 로깅
        telemetry_manager.log_error(f"Database connection failed: {str(e)}", {
            "action": "db_connect_error",
            "host": os.getenv('MYSQL_HOST', 'my-mariadb'),
            "database": "yejun-db",
            "error": str(e),
            "component": "database"
        })
        raise

# Redis 연결 함수
def get_redis_connection():
    try:
        connection = redis.Redis(
            host=os.getenv('REDIS_HOST', 'my-redis-master'),
            port=6379,
            password=os.getenv('REDIS_PASSWORD'),
            decode_responses=True,
            db=0
        )
        
        # Redis 연결 성공 로깅
        telemetry_manager.log_info("Redis connection established", {
            "action": "redis_connect",
            "host": os.getenv('REDIS_HOST', 'my-redis-master'),
            "port": 6379,
            "component": "redis"
        })
        
        return connection
    except Exception as e:
        # Redis 연결 실패 로깅
        telemetry_manager.log_error(f"Redis connection failed: {str(e)}", {
            "action": "redis_connect_error",
            "host": os.getenv('REDIS_HOST', 'my-redis-master'),
            "port": 6379,
            "error": str(e),
            "component": "redis"
        })
        raise

# 메시징 시스템 설정
def get_messaging_system():
    """환경 변수에 따라 메시징 시스템을 반환합니다."""
    try:
        from messaging_interface import MessagingFactory
        messaging = MessagingFactory.create_messaging()
        
        # 메시징 시스템 초기화 성공 로깅
        telemetry_manager.log_info("Messaging system initialized successfully", {
            "action": "messaging_init",
            "messaging_type": os.getenv('MESSAGING_TYPE', 'kafka'),
            "component": "messaging"
        })
        
        return messaging
    except Exception as e:
        # 메시징 시스템 초기화 실패 로깅
        telemetry_manager.log_error(f"Messaging system initialization failed: {str(e)}", {
            "action": "messaging_init_error",
            "messaging_type": os.getenv('MESSAGING_TYPE', 'kafka'),
            "error": str(e),
            "component": "messaging"
        })
        print(f"❌ 메시징 시스템 초기화 오류: {str(e)}")
        return None

# 로깅 함수
def log_to_redis(action, details):
    try:
        redis_client = get_redis_connection()
        log_entry = {
            'timestamp': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            'action': action,
            'details': details
        }
        redis_client.lpush('api_logs', json.dumps(log_entry))
        redis_client.ltrim('api_logs', 0, 99)  # 최근 100개 로그만 유지
        redis_client.close()
        
        # OpenTelemetry 로그 전송
        telemetry_manager.log_info(f"Redis log: {action} - {details}", {
            "action": action,
            "component": "redis_logging"
        })
    except Exception as e:
        print(f"Redis logging error: {str(e)}")
        # OpenTelemetry 오류 로그 전송
        telemetry_manager.log_error(f"Redis logging error: {str(e)}", {
            "action": "redis_logging_error",
            "error": str(e)
        })

# API 통계 로깅은 messaging_interface에서 처리됩니다.

# 로그인 데코레이터
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"status": "error", "message": "로그인이 필요합니다"}), 401
        return f(*args, **kwargs)
    return decorated_function

# MariaDB 엔드포인트
@app.route('/db/message', methods=['POST'])
@login_required
@log_operation("save_message_to_db", "database")
def save_to_db():
    user_id = session['user_id']
    
    db = get_db_connection()
    data = request.json
    cursor = db.cursor()
    sql = "INSERT INTO messages (message, created_at, user_id) VALUES (%s, %s, %s)"
    cursor.execute(sql, (data['message'], datetime.now(), user_id))
    db.commit()
    cursor.close()
    db.close()
    
    # 로깅
    log_to_redis('db_insert', f"Message saved: {data['message'][:30]}... by {user_id}")
    
    async_log_api_stats('/db/message', 'POST', 'success', user_id)
    return jsonify({"status": "success"})

@app.route('/db/message', methods=['GET'])
@login_required
@log_operation("get_messages_from_db", "database")
def get_from_db():
    user_id = session['user_id']
    
    # 페이지네이션 파라미터 처리
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # 파라미터 유효성 검사
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20
    
    # offset 계산
    offset = (page - 1) * limit
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # 전체 메시지 수 조회
    cursor.execute("SELECT COUNT(*) as total FROM messages WHERE user_id = %s", (user_id,))
    total_count = cursor.fetchone()['total']
    
    # 페이지네이션된 메시지 조회
    cursor.execute("SELECT * FROM messages WHERE user_id = %s ORDER BY id DESC LIMIT %s OFFSET %s", 
                  (user_id, limit, offset))
    messages = cursor.fetchall()
    cursor.close()
    db.close()
    
    # 비동기 로깅으로 변경
    async_log_api_stats('/db/messages', 'GET', 'success', user_id)
    
    # 페이지네이션 정보와 함께 반환
    return jsonify({
        "messages": messages,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total_count,
            "has_more": offset + limit < total_count,
            "current_page": (offset // limit) + 1,
            "total_pages": (total_count + limit - 1) // limit
        }
    })

# Redis 로그 조회
@app.route('/logs/redis', methods=['GET'])
@login_required
@log_operation("get_redis_logs", "logs")
def get_redis_logs():
    user_id = session['user_id']
    
    # 페이지네이션 파라미터 처리
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # 파라미터 유효성 검사
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20
    
    redis_client = get_redis_connection()
    all_logs = redis_client.lrange('api_logs', 0, -1)
    redis_client.close()
    
    # JSON 파싱
    logs = [json.loads(log) for log in all_logs]
    
    # 전체 로그 수
    total_count = len(logs)
    
    # 페이지네이션 적용
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_logs = logs[start_idx:end_idx]
    
    return jsonify({
        "logs": paginated_logs,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total_count,
            "current_page": page,
            "total_pages": (total_count + limit - 1) // limit
        }
    })

# 회원가입 엔드포인트
@app.route('/register', methods=['POST'])
@log_security_event("user_registration")
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"status": "error", "message": "사용자명과 비밀번호는 필수입니다"}), 400
        
    # 비밀번호 해시화
    hashed_password = generate_password_hash(password)
    
    db = get_db_connection()
    cursor = db.cursor()
    
    # 사용자명 중복 체크
    cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
    if cursor.fetchone():
        return jsonify({"status": "error", "message": "이미 존재하는 사용자명입니다"}), 400
    
    # 사용자 정보 저장
    sql = "INSERT INTO users (username, password) VALUES (%s, %s)"
    cursor.execute(sql, (username, hashed_password))
    db.commit()
    cursor.close()
    db.close()
    
    return jsonify({"status": "success", "message": "회원가입이 완료되었습니다"})

# 로그인 엔드포인트
@app.route('/login', methods=['POST'])
@log_security_event("user_login")
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"status": "error", "message": "사용자명과 비밀번호는 필수입니다"}), 400
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    db.close()
    
    if user and check_password_hash(user['password'], password):
        # 세션을 영구적으로 설정
        session.permanent = True
        session['user_id'] = username
        session['login_time'] = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        session['last_activity'] = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        session['user_agent'] = request.headers.get('User-Agent', '')
        session['remote_addr'] = request.remote_addr or 'unknown'
        session['browser_id'] = hashlib.md5(f"{request.headers.get('User-Agent', '')}:{request.remote_addr or 'unknown'}".encode()).hexdigest()[:12]
        
        # Flask-Session이 자동으로 Redis에 저장
        session.modified = True
        
        return jsonify({
            "status": "success", 
            "message": "로그인 성공",
            "username": username
        })
    
    return jsonify({"status": "error", "message": "잘못된 인증 정보"}), 401

# 세션 상태 확인 엔드포인트
@app.route('/session/status', methods=['GET'])
@log_operation("session_status_check", "session", log_success=False)  # 성공 로깅 비활성화
def session_status():
    if 'user_id' in session:
        username = session['user_id']
        return jsonify({
            "status": "success",
            "logged_in": True,
            "username": username,
            "session_permanent": session.permanent,
            "browser_id": session.get('browser_id'),
            "user_agent": session.get('user_agent'),
            "login_time": session.get('login_time'),
            "last_activity": session.get('last_activity')
        })
    else:
        return jsonify({
            "status": "success",
            "logged_in": False,
            "username": None
        })

# 로그아웃 엔드포인트
@app.route('/logout', methods=['POST'])
@log_security_event("user_logout")
def logout():
    username = session.get('user_id', 'unknown')
    
    # Flask-Session이 자동으로 세션을 삭제
    session.clear()
    session.permanent = False
    
    return jsonify({"status": "success", "message": "로그아웃 성공"})

# 전체 메시지 조회 (모든 사용자의 메시지)
@app.route('/db/messages', methods=['GET'])
@login_required
@log_operation("get_all_messages", "database")
def get_all_messages():
    user_id = session['user_id']
    
    # 페이지네이션 파라미터 처리
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # 파라미터 유효성 검사
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20
    
    # offset 계산
    offset = (page - 1) * limit
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # 전체 메시지 수 조회
    cursor.execute("SELECT COUNT(*) as total FROM messages")
    total_count = cursor.fetchone()['total']
    
    # 페이지네이션된 메시지 조회
    cursor.execute("SELECT * FROM messages ORDER BY id DESC LIMIT %s OFFSET %s", (limit, offset))
    messages = cursor.fetchall()
    cursor.close()
    db.close()
    
    # 비동기 로깅으로 변경
    async_log_api_stats('/db/messages/all', 'GET', 'success', user_id)
    
    return jsonify({
        "messages": messages,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total_count,
            "current_page": page,
            "total_pages": (total_count + limit - 1) // limit
        }
    })

# 메시지 검색 (DB에서 검색 + Redis 캐시)
@app.route('/db/messages/search', methods=['GET'])
@login_required
@log_operation("search_messages", "search")
def search_messages():
    query = request.args.get('q', '').strip()
    user_id = session['user_id']
    
    # 페이지네이션 파라미터 처리
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # 파라미터 유효성 검사
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20
    
    if not query:
        return jsonify({
            "results": [],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": 0,
                "current_page": page,
                "total_pages": 0
            }
        })
    
    # 캐시 키 생성 (쿼리 해시만 사용)
    query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
    cache_key = f"search:{query_hash}"
    
    # Redis에서 캐시 확인
    try:
        redis_client = get_redis_connection()
        cached_data = redis_client.get(cache_key)
        
        if cached_data:
            cache_info = json.loads(cached_data)
            # 캐시 히트 카운트 증가
            cache_info['hit_count'] += 1
            redis_client.set(cache_key, json.dumps(cache_info, default=serialize_datetime))
            redis_client.expire(cache_key, 60)  # 1분 만료
            redis_client.close()
            
            print(f"Cache HIT for query: {query} (hits: {cache_info['hit_count']})")
            
            # 비동기 로깅으로 변경
            async_log_api_stats('/db/messages/search', 'GET', 'cache_hit', user_id)
            
            # 캐시된 결과에 페이지네이션 적용
            all_results = cache_info['results']
            total_count = len(all_results)
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            paginated_results = all_results[start_idx:end_idx]
            
            return jsonify({
                "results": paginated_results,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total_count,
                    "current_page": page,
                    "total_pages": (total_count + limit - 1) // limit
                }
            })
        
        redis_client.close()
    except Exception as redis_error:
        print(f"Redis cache error: {str(redis_error)}")
    
    # 캐시 미스 - DB에서 검색
    print(f"Cache MISS for query: {query}")
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # 전체 검색 결과 수 조회
    count_sql = "SELECT COUNT(*) as total FROM messages WHERE message LIKE %s"
    cursor.execute(count_sql, (f"%{query}%",))
    total_count = cursor.fetchone()['total']
    
    # 페이지네이션된 검색 결과 조회
    sql = "SELECT * FROM messages WHERE message LIKE %s ORDER BY id DESC LIMIT %s OFFSET %s"
    offset = (page - 1) * limit
    cursor.execute(sql, (f"%{query}%", limit, offset))
    results = cursor.fetchall()
    cursor.close()
    db.close()
    
    # 검색 결과를 캐시에 저장 (전체 결과)
    try:
        # 전체 결과를 다시 조회하여 캐시에 저장
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM messages WHERE message LIKE %s ORDER BY id DESC", (f"%{query}%",))
        all_results = cursor.fetchall()
        cursor.close()
        db.close()
        
        redis_client = get_redis_connection()
        cache_data = {
            "query": query,
            "results": all_results,
            "timestamp": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=1)).replace(tzinfo=timezone.utc).isoformat(),
            "hit_count": 1
        }
        redis_client.set(cache_key, json.dumps(cache_data, default=serialize_datetime))
        redis_client.expire(cache_key, 60)  # 1분 만료
        redis_client.close()
        print(f"Cache STORED for query: {query}")
    except Exception as redis_error:
        print(f"Redis cache store error: {str(redis_error)}")
    
    # 검색 이력을 Kafka에 저장
    async_log_api_stats('/db/messages/search', 'GET', 'success', user_id)
    
    return jsonify({
        "results": results,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total_count,
            "current_page": page,
            "total_pages": (total_count + limit - 1) // limit
        }
    })

# 메시징 시스템 로그 조회 엔드포인트
@app.route('/logs/messaging', methods=['GET'])
@login_required
@log_operation("get_messaging_logs", "messaging")
def get_messaging_logs():
    user_id = session['user_id']
    
    # 페이지네이션 파라미터 처리
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # 파라미터 유효성 검사
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20
    
    # 메시징 시스템에서 로그 조회
    messaging = get_messaging_system()
    if messaging is None:
        return jsonify({"status": "error", "message": "메시징 시스템을 초기화할 수 없습니다"}), 500
        
    all_logs = messaging.get_messages('api-logs', limit=1000)
    messaging.close()
    
    # 시간 역순으로 정렬
    all_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # 전체 로그 수
    total_count = len(all_logs)
    
    # 페이지네이션 적용
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_logs = all_logs[start_idx:end_idx]
    
    return jsonify({
        "logs": paginated_logs,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total_count,
            "current_page": page,
            "total_pages": (total_count + limit - 1) // limit
        }
    })

# 검색 캐시 통계 조회
@app.route('/cache/search/stats', methods=['GET'])
@login_required
@log_operation("get_cache_stats", "cache", log_success=False)  # 성공 로깅 비활성화
def get_search_cache_stats():
    user_id = session['user_id']
    
    try:
        redis_client = get_redis_connection()
        
        # 모든 검색 캐시 키 조회
        cache_pattern = f"search:*"
        cache_keys = redis_client.keys(cache_pattern)
        
        cache_stats = []
        total_hits = 0
        
        for key in cache_keys:
            try:
                cached_data = redis_client.get(key)
                if cached_data:
                    cache_info = json.loads(cached_data)
                    cache_stats.append({
                        'query': cache_info['query'],
                        'hit_count': cache_info['hit_count'],
                        'timestamp': cache_info['timestamp'],
                        'expires_at': cache_info['expires_at'],
                        'results_count': len(cache_info['results'])
                    })
                    total_hits += cache_info['hit_count']
            except Exception as e:
                print(f"Error parsing cache data for key {key}: {str(e)}")
                continue
        
        redis_client.close()
        
        return jsonify({
            "status": "success",
            "total_cached_queries": len(cache_stats),
            "total_hits": total_hits,
            "cache_stats": cache_stats
        })
        
    except Exception as redis_error:
        print(f"Redis cache stats error: {str(redis_error)}")
        return jsonify({"status": "error", "message": "캐시 통계 조회 중 오류가 발생했습니다"}), 500

# 검색 캐시 삭제
@app.route('/cache/search/clear', methods=['POST'])
@login_required
@log_operation("clear_cache", "cache")
def clear_search_cache():
    user_id = session['user_id']
    data = request.json
    query = data.get('query', '').strip() if data else ''
    
    try:
        redis_client = get_redis_connection()
        
        if query:
            # 특정 쿼리 캐시만 삭제
            query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
            cache_key = f"search:{query_hash}"
            deleted_count = redis_client.delete(cache_key)
            
            message = f"쿼리 '{query}'의 캐시가 삭제되었습니다." if deleted_count > 0 else f"쿼리 '{query}'의 캐시를 찾을 수 없습니다."
        else:
            # 모든 검색 캐시 삭제
            cache_pattern = f"search:*"
            cache_keys = redis_client.keys(cache_pattern)
            deleted_count = 0
            
            for key in cache_keys:
                deleted_count += redis_client.delete(key)
            
            message = f"{deleted_count}개의 검색 캐시가 삭제되었습니다."
        
        redis_client.close()
        
        return jsonify({
            "status": "success",
            "message": message,
            "deleted_count": deleted_count
        })
        
    except Exception as redis_error:
        print(f"Redis cache clear error: {str(redis_error)}")
        return jsonify({"status": "error", "message": "캐시 삭제 중 오류가 발생했습니다"}), 500

if __name__ == '__main__':
    # 애플리케이션 시작 로깅
    telemetry_manager.log_info("AKS Demo Backend application starting", {
        "action": "app_start",
        "component": "application",
        "host": "0.0.0.0",
        "port": 5000
    })
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        # 애플리케이션 종료 로깅
        telemetry_manager.log_info("AKS Demo Backend application shutting down", {
            "action": "app_shutdown",
            "component": "application"
        })
        telemetry_manager.shutdown()
    except Exception as e:
        # 애플리케이션 오류 로깅
        telemetry_manager.log_error(f"Application error: {str(e)}", {
            "action": "app_error",
            "error": str(e),
            "component": "application"
        })
        telemetry_manager.shutdown() 