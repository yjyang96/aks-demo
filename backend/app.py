from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
import redis
import mysql.connector
import json
from datetime import datetime, timedelta
import os
from kafka import KafkaProducer, KafkaConsumer
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from threading import Thread
import hashlib

app = Flask(__name__)
CORS(app, supports_credentials=True)  # 세션을 위한 credentials 지원
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')  # 세션을 위한 시크릿 키

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

# # 스레드 풀 생성
# thread_pool = ThreadPoolExecutor(max_workers=5)

# MariaDB 연결 함수
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'my-mariadb'),
        user=os.getenv('MYSQL_USER', 'testuser'),
        password=os.getenv('MYSQL_PASSWORD'),
        database="yejun-db",
        connect_timeout=30
    )

# Redis 연결 함수
def get_redis_connection():
    return redis.Redis(
        host=os.getenv('REDIS_HOST', 'my-redis-master'),
        port=6379,
        password=os.getenv('REDIS_PASSWORD'),
        decode_responses=True,
        db=0
    )

# Kafka Producer 설정
def get_kafka_producer():
    kafka_servers = os.getenv('KAFKA_SERVERS', 'my-kafka')
    kafka_servers += ':9092'
    kafka_username = os.getenv('KAFKA_USERNAME', 'user1')
    kafka_password = os.getenv('KAFKA_PASSWORD', '')

    if kafka_password:
        return KafkaProducer(
            bootstrap_servers=kafka_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            security_protocol='SASL_PLAINTEXT',
            sasl_mechanism='PLAIN',
            sasl_plain_username=kafka_username,
            sasl_plain_password=kafka_password
        )
    else:
        return KafkaProducer(
            bootstrap_servers=kafka_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            security_protocol='PLAINTEXT'
        )

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
    except Exception as e:
        print(f"Redis logging error: {str(e)}")

# API 통계 로깅을 비동기로 처리하는 함수
def async_log_api_stats(endpoint, method, status, user_id):
    def _log():
        try:
            producer = get_kafka_producer()
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'endpoint': endpoint,
                'method': method,
                'status': status,
                'user_id': user_id,
                'message': f"{user_id}가 {method} {endpoint} 호출 ({status})"
            }

            future = producer.send('api-logs', log_data)
            record_metadata = future.get(timeout=10)  # 10초 타임아웃
            print(f"✅ Kafka message sent successfully: topic={record_metadata.topic}, partition={record_metadata.partition}, offset={record_metadata.offset}")
            producer.flush()
            producer.close()
        except Exception as e:
            print(f"❌ Kafka logging error: {str(e)}")
    
    # 새로운 스레드에서 로깅 실행
    Thread(target=_log).start()
    
    #  # 스레드 풀을 사용하여 작업 실행
    # thread_pool.submit(_log)

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
    try:
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
    except Exception as e:
        async_log_api_stats('/db/message', 'POST', 'error', user_id)
        log_to_redis('db_insert_error', str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/db/message', methods=['GET'])
@login_required
def get_from_db():
    try:
        user_id = session['user_id']
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        # 자기 메시지만 조회하도록 WHERE 조건 추가
        cursor.execute("SELECT * FROM messages WHERE user_id = %s ORDER BY id DESC", (user_id,))
        messages = cursor.fetchall()
        cursor.close()
        db.close()
        
        # 비동기 로깅으로 변경
        async_log_api_stats('/db/messages', 'GET', 'success', user_id)
        
        return jsonify(messages)
    except Exception as e:
        if 'user_id' in session:
            async_log_api_stats('/db/messages', 'GET', 'error', session['user_id'])
        return jsonify({"status": "error", "message": str(e)}), 500

# Redis 로그 조회
@app.route('/logs/redis', methods=['GET'])
def get_redis_logs():
    try:
        redis_client = get_redis_connection()
        logs = redis_client.lrange('api_logs', 0, -1)
        redis_client.close()
        return jsonify([json.loads(log) for log in logs])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 회원가입 엔드포인트
@app.route('/register', methods=['POST'])
def register():
    try:
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
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 로그인 엔드포인트
@app.route('/login', methods=['POST'])
def login():
    try:
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
            session['login_time'] = datetime.now().isoformat()
            session['last_activity'] = datetime.now().isoformat()
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
        
    except Exception as e:
        print(f"Login error: {str(e)}")  # 서버 로그에 에러 출력
        return jsonify({"status": "error", "message": "로그인 처리 중 오류가 발생했습니다"}), 500

# 세션 상태 확인 엔드포인트
@app.route('/session/status', methods=['GET'])
def session_status():
    try:
        if 'user_id' in session:
            return jsonify({
                "status": "success",
                "logged_in": True,
                "username": session['user_id'],
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
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 로그아웃 엔드포인트
@app.route('/logout', methods=['POST'])
def logout():
    try:
        # Flask-Session이 자동으로 세션을 삭제
        session.clear()
        session.permanent = False
        
        return jsonify({"status": "success", "message": "로그아웃 성공"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



# 전체 메시지 조회 (모든 사용자의 메시지)
@app.route('/db/messages', methods=['GET'])
@login_required
def get_all_messages():
    try:
        user_id = session['user_id']
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM messages ORDER BY id DESC")
        messages = cursor.fetchall()
        cursor.close()
        db.close()
        
        # 비동기 로깅으로 변경
        async_log_api_stats('/db/messages/all', 'GET', 'success', user_id)
        
        return jsonify(messages)
    except Exception as e:
        if 'user_id' in session:
            async_log_api_stats('/db/messages/all', 'GET', 'error', session['user_id'])
        return jsonify({"status": "error", "message": str(e)}), 500

# 메시지 검색 (DB에서 검색 + Redis 캐시)
@app.route('/db/messages/search', methods=['GET'])
@login_required
def search_messages():
    try:
        query = request.args.get('q', '').strip()
        user_id = session['user_id']
        
        if not query:
            return jsonify([])
        
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
                async_log_api_stats('/db/messages/search', 'GET', 'cache_hit', user_id)
                return jsonify(cache_info['results'])
            
            redis_client.close()
        except Exception as redis_error:
            print(f"Redis cache error: {str(redis_error)}")
        
        # 캐시 미스 - DB에서 검색
        print(f"Cache MISS for query: {query}")
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        sql = "SELECT * FROM messages WHERE message LIKE %s ORDER BY id DESC"
        cursor.execute(sql, (f"%{query}%",))
        results = cursor.fetchall()
        cursor.close()
        db.close()
        
        # 검색 결과를 캐시에 저장
        try:
            redis_client = get_redis_connection()
            cache_data = {
                "query": query,
                "results": results,
                "timestamp": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(minutes=1)).isoformat(),
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
        
        return jsonify(results)
    except Exception as e:
        if 'user_id' in session:
            async_log_api_stats('/db/messages/search', 'GET', 'error', session['user_id'])
        return jsonify({"status": "error", "message": str(e)}), 500

# Kafka 로그 조회 엔드포인트
@app.route('/logs/kafka', methods=['GET'])
@login_required
def get_kafka_logs():
    try:
        kafka_servers = os.getenv('KAFKA_SERVERS', 'my-kafka')
        kafka_servers += ':9092'
        kafka_username = os.getenv('KAFKA_USERNAME', 'user1')
        kafka_password = os.getenv('KAFKA_PASSWORD', '')

        if kafka_password:
            consumer = KafkaConsumer(
                'api-logs',
                bootstrap_servers=kafka_servers,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                security_protocol='SASL_PLAINTEXT',
                sasl_mechanism='PLAIN',
                sasl_plain_username=kafka_username,
                sasl_plain_password=kafka_password,
                # group_id='api-logs-viewer',
                auto_offset_reset='earliest',
                consumer_timeout_ms=5000
            )
        else:
            consumer = KafkaConsumer(
                'api-logs',
                bootstrap_servers=kafka_servers,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                security_protocol='PLAINTEXT',
                # group_id='api-logs-viewer',
                auto_offset_reset='earliest',
                consumer_timeout_ms=5000
            )
        
        logs = []
        try:
            for message in consumer:
                logs.append({
                    'timestamp': message.value['timestamp'],
                    'endpoint': message.value['endpoint'],
                    'method': message.value['method'],
                    'status': message.value['status'],
                    'user_id': message.value['user_id'],
                    'message': message.value['message']
                })
                if len(logs) >= 100:
                    break
        finally:
            consumer.close()
        
        # 시간 역순으로 정렬
        logs.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(logs)
    except Exception as e:
        print(f"Kafka log retrieval error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# 검색 캐시 통계 조회
@app.route('/cache/search/stats', methods=['GET'])
@login_required
def get_search_cache_stats():
    try:
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
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 검색 캐시 삭제
@app.route('/cache/search/clear', methods=['POST'])
@login_required
def clear_search_cache():
    try:
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
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 