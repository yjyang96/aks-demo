from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
import redis
import mysql.connector
import json
from datetime import datetime, timedelta
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

# 세션 활동 시간 업데이트 미들웨어
@app.before_request
def update_session_activity():
    """요청마다 세션 활동 시간을 업데이트합니다."""
    if 'user_id' in session:
        # Flask-Session이 자동으로 세션을 Redis에 저장하므로
        # 단순히 last_activity만 업데이트
        session['last_activity'] = datetime.now().isoformat()
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
            'timestamp': datetime.now().isoformat(),
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
def save_to_db():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("save_message_to_db") as span:
        try:
            user_id = session['user_id']
            span.set_attribute("user.id", user_id)
            span.set_attribute("db.operation", "insert")
            
            # 메트릭 기록
            telemetry_manager.record_metric("db_operations_total", 1, {"operation": "insert", "status": "success"})
            
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
            
            # OpenTelemetry 로깅 추가
            telemetry_manager.log_info(f"Database message saved successfully by user {user_id}", {
                "action": "db_insert",
                "user_id": user_id,
                "message_length": len(data['message']),
                "component": "database"
            })
            
            async_log_api_stats('/db/message', 'POST', 'success', user_id)
            return jsonify({"status": "success"})
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("db_operations_total", 1, {"operation": "insert", "status": "error"})
            
            # OpenTelemetry 오류 로깅
            telemetry_manager.log_error(f"Database insert failed for user {user_id}: {str(e)}", {
                "action": "db_insert_error",
                "user_id": user_id,
                "error": str(e),
                "component": "database"
            })
            
            async_log_api_stats('/db/message', 'POST', 'error', user_id)
            log_to_redis('db_insert_error', str(e))
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/db/message', methods=['GET'])
@login_required
def get_from_db():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("get_messages_from_db") as span:
        try:
            user_id = session['user_id']
            span.set_attribute("user.id", user_id)
            span.set_attribute("db.operation", "select")
            
            # 메트릭 기록
            telemetry_manager.record_metric("db_operations_total", 1, {"operation": "select", "status": "success"})
            
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
            
            # LGTM 로깅 추가
            telemetry_manager.log_info(f"User messages retrieved by user {user_id}", {
                "action": "get_user_messages",
                "user_id": user_id,
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "component": "database"
            })
            
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
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("db_operations_total", 1, {"operation": "select", "status": "error"})
            
            if 'user_id' in session:
                async_log_api_stats('/db/messages', 'GET', 'error', session['user_id'])
            
            # LGTM 오류 로깅
            telemetry_manager.log_error(f"Get user messages failed for user {user_id}: {str(e)}", {
                "action": "get_user_messages_error",
                "user_id": user_id,
                "error": str(e),
                "component": "database"
            })
            return jsonify({"status": "error", "message": str(e)}), 500

# Redis 로그 조회
@app.route('/logs/redis', methods=['GET'])
@login_required
def get_redis_logs():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("get_redis_logs") as span:
        try:
            user_id = session['user_id']
            
            span.set_attribute("user.id", user_id)
            span.set_attribute("logs.operation", "get_redis")
            span.set_attribute("remote.addr", request.remote_addr)
            
            # 메트릭 기록
            telemetry_manager.record_metric("logs_operations_total", 1, {"operation": "get_redis", "status": "success"})
            
            # 페이지네이션 파라미터 처리
            page = request.args.get('page', 1, type=int)
            limit = request.args.get('limit', 20, type=int)
            
            span.set_attribute("pagination.page", page)
            span.set_attribute("pagination.limit", limit)
            
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
            
            span.set_attribute("logs.result_count", len(paginated_logs))
            span.set_attribute("logs.total_count", total_count)
            
            # LGTM 로깅 추가
            telemetry_manager.log_info(f"Redis logs retrieved by user {user_id}", {
                "action": "get_redis_logs",
                "user_id": user_id,
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "component": "logs"
            })
            
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
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("logs_operations_total", 1, {"operation": "get_redis", "status": "error"})
            
            # LGTM 오류 로깅
            telemetry_manager.log_error(f"Get Redis logs failed for user {user_id}: {str(e)}", {
                "action": "get_redis_logs_error",
                "user_id": user_id,
                "error": str(e),
                "component": "logs"
            })
            return jsonify({"status": "error", "message": str(e)}), 500

# 회원가입 엔드포인트
@app.route('/register', methods=['POST'])
def register():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("user_registration") as span:
        try:
            data = request.json
            username = data.get('username')
            password = data.get('password')
            
            span.set_attribute("user.username", username)
            span.set_attribute("auth.operation", "register")
            span.set_attribute("remote.addr", request.remote_addr)
            
            # 메트릭 기록
            telemetry_manager.record_metric("auth_operations_total", 1, {"operation": "register", "status": "success"})
            
            if not username or not password:
                span.set_attribute("error", True)
                span.set_attribute("error.message", "Missing credentials")
                telemetry_manager.record_metric("auth_operations_total", 1, {"operation": "register", "status": "error"})
                
                telemetry_manager.log_warn("Registration attempt with missing credentials", {
                    "action": "register_attempt",
                    "status": "missing_credentials",
                    "remote_addr": request.remote_addr,
                    "component": "authentication"
                })
                return jsonify({"status": "error", "message": "사용자명과 비밀번호는 필수입니다"}), 400
                
            # 비밀번호 해시화
            hashed_password = generate_password_hash(password)
            
            db = get_db_connection()
            cursor = db.cursor()
            
            # 사용자명 중복 체크
            cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                span.set_attribute("error", True)
                span.set_attribute("error.message", "Duplicate username")
                telemetry_manager.record_metric("auth_operations_total", 1, {"operation": "register", "status": "error"})
                
                telemetry_manager.log_warn(f"Registration attempt with duplicate username: {username}", {
                    "action": "register_attempt",
                    "status": "duplicate_username",
                    "username": username,
                    "remote_addr": request.remote_addr,
                    "component": "authentication"
                })
                return jsonify({"status": "error", "message": "이미 존재하는 사용자명입니다"}), 400
            
            # 사용자 정보 저장
            sql = "INSERT INTO users (username, password) VALUES (%s, %s)"
            cursor.execute(sql, (username, hashed_password))
            db.commit()
            cursor.close()
            db.close()
            
            # 성공 로그
            telemetry_manager.log_info(f"User {username} registered successfully", {
                "action": "register_success",
                "username": username,
                "remote_addr": request.remote_addr,
                "component": "authentication"
            })
            
            return jsonify({"status": "success", "message": "회원가입이 완료되었습니다"})
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("auth_operations_total", 1, {"operation": "register", "status": "error"})
            
            telemetry_manager.log_error(f"Registration error: {str(e)}", {
                "action": "register_error",
                "error": str(e),
                "remote_addr": request.remote_addr,
                "component": "authentication"
            })
            return jsonify({"status": "error", "message": str(e)}), 500

# 로그인 엔드포인트
@app.route('/login', methods=['POST'])
def login():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("user_login") as span:
        try:
            data = request.json
            username = data.get('username')
            password = data.get('password')
            
            span.set_attribute("user.username", username)
            span.set_attribute("auth.operation", "login")
            span.set_attribute("remote.addr", request.remote_addr)
            
            # 메트릭 기록
            telemetry_manager.record_metric("auth_operations_total", 1, {"operation": "login", "status": "success"})
            
            if not username or not password:
                span.set_attribute("error", True)
                span.set_attribute("error.message", "Missing credentials")
                telemetry_manager.record_metric("auth_operations_total", 1, {"operation": "login", "status": "error"})
                
                telemetry_manager.log_warn("Login attempt with missing credentials", {
                    "action": "login_attempt",
                    "status": "missing_credentials",
                    "remote_addr": request.remote_addr,
                    "component": "authentication"
                })
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
                session['login_time'] = datetime.now().isoformat()
                session['last_activity'] = datetime.now().isoformat()
                session['user_agent'] = request.headers.get('User-Agent', '')
                session['remote_addr'] = request.remote_addr or 'unknown'
                session['browser_id'] = hashlib.md5(f"{request.headers.get('User-Agent', '')}:{request.remote_addr or 'unknown'}".encode()).hexdigest()[:12]
                
                # Flask-Session이 자동으로 Redis에 저장
                session.modified = True
                
                # 성공 로그
                telemetry_manager.log_info(f"User {username} logged in successfully", {
                    "action": "login_success",
                    "username": username,
                    "remote_addr": request.remote_addr,
                    "user_agent": request.headers.get('User-Agent', ''),
                    "component": "authentication"
                })
                
                return jsonify({
                    "status": "success", 
                    "message": "로그인 성공",
                    "username": username
                })
            
            # 실패 로그
            span.set_attribute("error", True)
            span.set_attribute("error.message", "Invalid credentials")
            telemetry_manager.record_metric("auth_operations_total", 1, {"operation": "login", "status": "error"})
            
            telemetry_manager.log_warn(f"Failed login attempt for user {username}", {
                "action": "login_failed",
                "username": username,
                "remote_addr": request.remote_addr,
                "user_agent": request.headers.get('User-Agent', ''),
                "component": "authentication"
            })
            
            return jsonify({"status": "error", "message": "잘못된 인증 정보"}), 401
            
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("auth_operations_total", 1, {"operation": "login", "status": "error"})
            
            error_msg = f"Login error: {str(e)}"
            telemetry_manager.log_error(error_msg, {
                "action": "login_error",
                "error": str(e),
                "remote_addr": request.remote_addr,
                "component": "authentication"
            })
            print(error_msg)  # 서버 로그에 에러 출력
            return jsonify({"status": "error", "message": "로그인 처리 중 오류가 발생했습니다"}), 500

# 세션 상태 확인 엔드포인트
@app.route('/session/status', methods=['GET'])
def session_status():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("session_status_check") as span:
        try:
            span.set_attribute("session.operation", "status_check")
            span.set_attribute("remote.addr", request.remote_addr)
            
            # 메트릭 기록
            telemetry_manager.record_metric("session_operations_total", 1, {"operation": "status_check", "status": "success"})
            
            if 'user_id' in session:
                username = session['user_id']
                span.set_attribute("user.username", username)
                
                telemetry_manager.log_info(f"Session status checked for user {username}", {
                    "action": "session_status_check",
                    "username": username,
                    "remote_addr": request.remote_addr,
                    "component": "session"
                })
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
                telemetry_manager.log_info("Session status checked - not logged in", {
                    "action": "session_status_check",
                    "remote_addr": request.remote_addr,
                    "component": "session"
                })
                return jsonify({
                    "status": "success",
                    "logged_in": False,
                    "username": None
                })
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("session_operations_total", 1, {"operation": "status_check", "status": "error"})
            
            telemetry_manager.log_error(f"Session status check error: {str(e)}", {
                "action": "session_status_error",
                "error": str(e),
                "remote_addr": request.remote_addr,
                "component": "session"
            })
            return jsonify({"status": "error", "message": str(e)}), 500

# 로그아웃 엔드포인트
@app.route('/logout', methods=['POST'])
def logout():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("user_logout") as span:
        try:
            username = session.get('user_id', 'unknown')
            
            span.set_attribute("user.username", username)
            span.set_attribute("auth.operation", "logout")
            span.set_attribute("remote.addr", request.remote_addr)
            
            # 메트릭 기록
            telemetry_manager.record_metric("auth_operations_total", 1, {"operation": "logout", "status": "success"})
            
            # Flask-Session이 자동으로 세션을 삭제
            session.clear()
            session.permanent = False
            
            # 로그아웃 로그
            telemetry_manager.log_info(f"User {username} logged out successfully", {
                "action": "logout_success",
                "username": username,
                "remote_addr": request.remote_addr,
                "component": "authentication"
            })
            
            return jsonify({"status": "success", "message": "로그아웃 성공"})
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("auth_operations_total", 1, {"operation": "logout", "status": "error"})
            
            telemetry_manager.log_error(f"Logout error: {str(e)}", {
                "action": "logout_error",
                "error": str(e),
                "remote_addr": request.remote_addr,
                "component": "authentication"
            })
            return jsonify({"status": "error", "message": str(e)}), 500



# 전체 메시지 조회 (모든 사용자의 메시지)
@app.route('/db/messages', methods=['GET'])
@login_required
def get_all_messages():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("get_all_messages") as span:
        try:
            user_id = session['user_id']
            
            span.set_attribute("user.id", user_id)
            span.set_attribute("db.operation", "select_all")
            span.set_attribute("remote.addr", request.remote_addr)
            
            # 메트릭 기록
            telemetry_manager.record_metric("db_operations_total", 1, {"operation": "select_all", "status": "success"})
            
            # 페이지네이션 파라미터 처리
            page = request.args.get('page', 1, type=int)
            limit = request.args.get('limit', 20, type=int)
            
            span.set_attribute("pagination.page", page)
            span.set_attribute("pagination.limit", limit)
            
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
            
            span.set_attribute("db.result_count", len(messages))
            span.set_attribute("db.total_count", total_count)
            
            # LGTM 로깅 추가
            telemetry_manager.log_info(f"All messages retrieved by user {user_id}", {
                "action": "get_all_messages",
                "user_id": user_id,
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "component": "database"
            })
            
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
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("db_operations_total", 1, {"operation": "select_all", "status": "error"})
            
            if 'user_id' in session:
                async_log_api_stats('/db/messages/all', 'GET', 'error', session['user_id'])
            
            # LGTM 오류 로깅
            telemetry_manager.log_error(f"Get all messages failed for user {user_id}: {str(e)}", {
                "action": "get_all_messages_error",
                "user_id": user_id,
                "error": str(e),
                "component": "database"
            })
            return jsonify({"status": "error", "message": str(e)}), 500

# 메시지 검색 (DB에서 검색 + Redis 캐시)
@app.route('/db/messages/search', methods=['GET'])
@login_required
def search_messages():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("search_messages") as span:
        try:
            query = request.args.get('q', '').strip()
            user_id = session['user_id']
            
            span.set_attribute("user.id", user_id)
            span.set_attribute("search.query", query)
            span.set_attribute("search.operation", "search")
            
            # 메트릭 기록
            telemetry_manager.record_metric("search_operations_total", 1, {"operation": "search", "status": "success"})
            
            # 페이지네이션 파라미터 처리
            page = request.args.get('page', 1, type=int)
            limit = request.args.get('limit', 20, type=int)
            
            # 파라미터 유효성 검사
            if page < 1:
                page = 1
            if limit < 1 or limit > 100:
                limit = 20
            
            if not query:
                telemetry_manager.log_info(f"Empty search query by user {user_id}", {
                    "action": "search_empty_query",
                    "user_id": user_id,
                    "component": "search"
                })
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
                    
                    # LGTM 캐시 히트 로깅
                    telemetry_manager.log_info(f"Search cache hit for query '{query}' by user {user_id}", {
                        "action": "search_cache_hit",
                        "user_id": user_id,
                        "query": query,
                        "hit_count": cache_info['hit_count'],
                        "component": "cache"
                    })
                    
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
                telemetry_manager.log_error(f"Redis cache error during search: {str(redis_error)}", {
                    "action": "search_cache_error",
                    "user_id": user_id,
                    "query": query,
                    "error": str(redis_error),
                    "component": "cache"
                })
            
            # 캐시 미스 - DB에서 검색
            print(f"Cache MISS for query: {query}")
            telemetry_manager.log_info(f"Search cache miss for query '{query}' by user {user_id}", {
                "action": "search_cache_miss",
                "user_id": user_id,
                "query": query,
                "component": "cache"
            })
            
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
                    "timestamp": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(minutes=1)).isoformat(),
                    "hit_count": 1
                }
                redis_client.set(cache_key, json.dumps(cache_data, default=serialize_datetime))
                redis_client.expire(cache_key, 60)  # 1분 만료
                redis_client.close()
                print(f"Cache STORED for query: {query}")
                
                # LGTM 캐시 저장 로깅
                telemetry_manager.log_info(f"Search results cached for query '{query}' by user {user_id}", {
                    "action": "search_cache_store",
                    "user_id": user_id,
                    "query": query,
                    "results_count": len(all_results),
                    "component": "cache"
                })
            except Exception as redis_error:
                print(f"Redis cache store error: {str(redis_error)}")
                telemetry_manager.log_error(f"Redis cache store error: {str(redis_error)}", {
                    "action": "search_cache_store_error",
                    "user_id": user_id,
                    "query": query,
                    "error": str(redis_error),
                    "component": "cache"
                })
            
            # LGTM 검색 성공 로깅
            telemetry_manager.log_info(f"Search completed for query '{query}' by user {user_id}", {
                "action": "search_completed",
                "user_id": user_id,
                "query": query,
                "total_count": total_count,
                "page": page,
                "limit": limit,
                "component": "search"
            })
            
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
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("search_operations_total", 1, {"operation": "search", "status": "error"})
            
            if 'user_id' in session:
                async_log_api_stats('/db/messages/search', 'GET', 'error', session['user_id'])
            
            # LGTM 검색 오류 로깅
            telemetry_manager.log_error(f"Search failed for query '{query}' by user {user_id}: {str(e)}", {
                "action": "search_error",
                "user_id": user_id,
                "query": query,
                "error": str(e),
                "component": "search"
            })
            return jsonify({"status": "error", "message": str(e)}), 500

# 메시징 시스템 로그 조회 엔드포인트
@app.route('/logs/messaging', methods=['GET'])
@login_required
def get_messaging_logs():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("get_messaging_logs") as span:
        try:
            user_id = session['user_id']
            
            span.set_attribute("user.id", user_id)
            span.set_attribute("logs.operation", "get_messaging")
            span.set_attribute("remote.addr", request.remote_addr)
            
            # 메트릭 기록
            telemetry_manager.record_metric("logs_operations_total", 1, {"operation": "get_messaging", "status": "success"})
            
            # 페이지네이션 파라미터 처리
            page = request.args.get('page', 1, type=int)
            limit = request.args.get('limit', 20, type=int)
            
            span.set_attribute("pagination.page", page)
            span.set_attribute("pagination.limit", limit)
            
            # 파라미터 유효성 검사
            if page < 1:
                page = 1
            if limit < 1 or limit > 100:
                limit = 20
            
            # 메시징 시스템에서 로그 조회
            messaging = get_messaging_system()
            if messaging is None:
                span.set_attribute("error", True)
                span.set_attribute("error.message", "Messaging system initialization failed")
                telemetry_manager.record_metric("logs_operations_total", 1, {"operation": "get_messaging", "status": "error"})
                
                telemetry_manager.log_error("Messaging system initialization failed", {
                    "action": "messaging_init_error",
                    "user_id": user_id,
                    "component": "messaging"
                })
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
            
            span.set_attribute("logs.result_count", len(paginated_logs))
            span.set_attribute("logs.total_count", total_count)
            
            # LGTM 로깅 추가
            telemetry_manager.log_info(f"Messaging logs retrieved by user {user_id}", {
                "action": "get_messaging_logs",
                "user_id": user_id,
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "component": "messaging"
            })
            
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
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("logs_operations_total", 1, {"operation": "get_messaging", "status": "error"})
            
            print(f"Messaging log retrieval error: {str(e)}")
            telemetry_manager.log_error(f"Messaging log retrieval error: {str(e)}", {
                "action": "messaging_log_error",
                "user_id": user_id,
                "error": str(e),
                "component": "messaging"
            })
            return jsonify({"status": "error", "message": str(e)}), 500

# 검색 캐시 통계 조회
@app.route('/cache/search/stats', methods=['GET'])
@login_required
def get_search_cache_stats():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("get_cache_stats") as span:
        try:
            user_id = session['user_id']
            
            span.set_attribute("user.id", user_id)
            span.set_attribute("cache.operation", "get_stats")
            span.set_attribute("remote.addr", request.remote_addr)
            
            # 메트릭 기록
            telemetry_manager.record_metric("cache_operations_total", 1, {"operation": "get_stats", "status": "success"})
            
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
                
                span.set_attribute("cache.total_queries", len(cache_stats))
                span.set_attribute("cache.total_hits", total_hits)
                
                # LGTM 로깅 추가
                telemetry_manager.log_info(f"Search cache stats retrieved by user {user_id}", {
                    "action": "get_cache_stats",
                    "user_id": user_id,
                    "total_cached_queries": len(cache_stats),
                    "total_hits": total_hits,
                    "component": "cache"
                })
                
                return jsonify({
                    "status": "success",
                    "total_cached_queries": len(cache_stats),
                    "total_hits": total_hits,
                    "cache_stats": cache_stats
                })
                
            except Exception as redis_error:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(redis_error))
                telemetry_manager.record_metric("cache_operations_total", 1, {"operation": "get_stats", "status": "error"})
                
                print(f"Redis cache stats error: {str(redis_error)}")
                telemetry_manager.log_error(f"Redis cache stats error: {str(redis_error)}", {
                    "action": "cache_stats_error",
                    "user_id": user_id,
                    "error": str(redis_error),
                    "component": "cache"
                })
                return jsonify({"status": "error", "message": "캐시 통계 조회 중 오류가 발생했습니다"}), 500
                
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("cache_operations_total", 1, {"operation": "get_stats", "status": "error"})
            
            telemetry_manager.log_error(f"Cache stats retrieval error: {str(e)}", {
                "action": "cache_stats_error",
                "user_id": user_id,
                "error": str(e),
                "component": "cache"
            })
            return jsonify({"status": "error", "message": str(e)}), 500

# 검색 캐시 삭제
@app.route('/cache/search/clear', methods=['POST'])
@login_required
def clear_search_cache():
    tracer = telemetry_manager.get_tracer()
    meter = telemetry_manager.get_meter()
    
    with tracer.start_as_current_span("clear_cache") as span:
        try:
            user_id = session['user_id']
            data = request.json
            query = data.get('query', '').strip() if data else ''
            
            span.set_attribute("user.id", user_id)
            span.set_attribute("cache.operation", "clear")
            span.set_attribute("cache.query", query)
            span.set_attribute("remote.addr", request.remote_addr)
            
            # 메트릭 기록
            telemetry_manager.record_metric("cache_operations_total", 1, {"operation": "clear", "status": "success"})
            
            try:
                redis_client = get_redis_connection()
                
                if query:
                    # 특정 쿼리 캐시만 삭제
                    query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
                    cache_key = f"search:{query_hash}"
                    deleted_count = redis_client.delete(cache_key)
                    
                    message = f"쿼리 '{query}'의 캐시가 삭제되었습니다." if deleted_count > 0 else f"쿼리 '{query}'의 캐시를 찾을 수 없습니다."
                    
                    span.set_attribute("cache.deleted_count", deleted_count)
                    span.set_attribute("cache.clear_type", "specific")
                    
                    # LGTM 로깅 추가
                    telemetry_manager.log_info(f"Specific search cache cleared by user {user_id}", {
                        "action": "clear_specific_cache",
                        "user_id": user_id,
                        "query": query,
                        "deleted_count": deleted_count,
                        "component": "cache"
                    })
                else:
                    # 모든 검색 캐시 삭제
                    cache_pattern = f"search:*"
                    cache_keys = redis_client.keys(cache_pattern)
                    deleted_count = 0
                    
                    for key in cache_keys:
                        deleted_count += redis_client.delete(key)
                    
                    message = f"{deleted_count}개의 검색 캐시가 삭제되었습니다."
                    
                    span.set_attribute("cache.deleted_count", deleted_count)
                    span.set_attribute("cache.clear_type", "all")
                    
                    # LGTM 로깅 추가
                    telemetry_manager.log_info(f"All search cache cleared by user {user_id}", {
                        "action": "clear_all_cache",
                        "user_id": user_id,
                        "deleted_count": deleted_count,
                        "component": "cache"
                    })
                
                redis_client.close()
                
                return jsonify({
                    "status": "success",
                    "message": message,
                    "deleted_count": deleted_count
                })
                
            except Exception as redis_error:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(redis_error))
                telemetry_manager.record_metric("cache_operations_total", 1, {"operation": "clear", "status": "error"})
                
                print(f"Redis cache clear error: {str(redis_error)}")
                telemetry_manager.log_error(f"Redis cache clear error: {str(redis_error)}", {
                    "action": "cache_clear_error",
                    "user_id": user_id,
                    "query": query,
                    "error": str(redis_error),
                    "component": "cache"
                })
                return jsonify({"status": "error", "message": "캐시 삭제 중 오류가 발생했습니다"}), 500
                
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            telemetry_manager.record_metric("cache_operations_total", 1, {"operation": "clear", "status": "error"})
            
            telemetry_manager.log_error(f"Cache clear error: {str(e)}", {
                "action": "cache_clear_error",
                "user_id": user_id,
                "error": str(e),
                "component": "cache"
            })
            return jsonify({"status": "error", "message": str(e)}), 500

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