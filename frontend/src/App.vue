<template>
  <div id="app">
    <h1>K8s 마이크로서비스 데모</h1>
    
    <!-- 로딩 상태 -->
    <div v-if="isLoading" class="loading-container">
      <div class="loading-spinner">
        <p>세션 상태를 확인하는 중...</p>
      </div>
    </div>
    
    <!-- 로그인/회원가입 섹션 -->
    <div class="section" v-else-if="!isLoggedIn">
      <div v-if="!showRegister">
        <h2>로그인</h2>
        <input v-model="username" placeholder="사용자명">
        <input v-model="password" type="password" placeholder="비밀번호">
        <button @click="login">로그인</button>
        <button @click="showRegister = true" class="register-btn">회원가입</button>
      </div>
      <div v-else>
        <h2>회원가입</h2>
        <input v-model="registerUsername" placeholder="사용자명">
        <input v-model="registerPassword" type="password" placeholder="비밀번호">
        <input v-model="confirmPassword" type="password" placeholder="비밀번호 확인">
        <button @click="register">가입하기</button>
        <button @click="showRegister = false">로그인으로 돌아가기</button>
      </div>
    </div>

    <div v-else>
      <div class="user-info">
        <span>안녕하세요, {{ currentUser }}님</span>
        <button @click="logout">로그아웃</button>
      </div>

      <div class="container">
        <div class="section">
          <h2>MariaDB 메시지 관리</h2>
          <input v-model="dbMessage" placeholder="저장할 메시지 입력">
          <button @click="saveToDb">DB에 저장</button>
          <button @click="getFromDb">내 메시지 조회</button>
          <button @click="insertSampleData" class="sample-btn">샘플 데이터 저장</button>
          <div v-if="loading" class="loading-spinner">
            <p>데이터를 불러오는 중...</p>
          </div>
          <div v-if="dbData.length && !loading">
            <h3>내 메시지 (총 {{ totalMessages }}개):</h3>
            <ul>
              <li v-for="item in dbData" :key="item.id">
                {{ item.message }} ({{ formatDate(item.created_at) }}) - {{ item.user_id }}
              </li>
            </ul>
            
            <!-- 페이지네이션 정보 -->
            <div class="pagination-info">
              <p>페이지 {{ currentPage }} / {{ totalPages }} (총 {{ totalMessages }}개 중 {{ dbData.length }}개 표시)</p>
            </div>
            
            <!-- 페이지네이션 버튼 -->
            <div class="pagination">
              <button @click="() => goToFirstPage()" :disabled="currentPage === 1 || loading" class="page-btn">
                처음
              </button>
              <button @click="() => goToPrevPage()" :disabled="currentPage === 1 || loading" class="page-btn">
                이전
              </button>
              
              <!-- 페이지 번호 버튼들 -->
              <div class="page-numbers">
                <button 
                  v-for="page in getVisiblePages()" 
                  :key="page"
                  @click="() => goToPage(page)"
                  :class="['page-number', { active: page === currentPage }]"
                  :disabled="loading"
                >
                  {{ page }}
                </button>
              </div>
              
              <button @click="() => goToNextPage()" :disabled="currentPage === totalPages || loading" class="page-btn">
                다음
              </button>
              <button @click="() => goToLastPage()" :disabled="currentPage === totalPages || loading" class="page-btn">
                마지막
              </button>
            </div>
          </div>
        </div>

        <div class="section">
          <h2>Redis 로그</h2>
          <button @click="getRedisLogs(1)">Redis 로그 조회</button>
          <div v-if="redisLogs.length">
            <h3>API 호출 로그 (총 {{ redisLogsTotal }}개):</h3>
            <ul>
              <li v-for="(log, index) in redisLogs" :key="index">
                [{{ formatDate(log.timestamp) }}] {{ log.action }}: {{ log.details }}
              </li>
            </ul>
            
            <!-- Redis 로그 페이지네이션 -->
            <div class="pagination-info">
              <p>페이지 {{ redisLogsPage }} / {{ redisLogsTotalPages }} ({{ redisLogs.length }}개 표시)</p>
            </div>
            
            <div class="pagination">
              <button @click="() => getRedisLogs(1)" :disabled="redisLogsPage === 1" class="page-btn">처음</button>
              <button @click="() => getRedisLogs(redisLogsPage - 1)" :disabled="redisLogsPage === 1" class="page-btn">이전</button>
              
              <div class="page-numbers">
                <button 
                  v-for="page in getRedisLogsVisiblePages()" 
                  :key="page"
                  @click="() => getRedisLogs(page)"
                  :class="['page-number', { active: page === redisLogsPage }]"
                >
                  {{ page }}
                </button>
              </div>
              
              <button @click="() => getRedisLogs(redisLogsPage + 1)" :disabled="redisLogsPage === redisLogsTotalPages" class="page-btn">다음</button>
              <button @click="() => getRedisLogs(redisLogsTotalPages)" :disabled="redisLogsPage === redisLogsTotalPages" class="page-btn">마지막</button>
            </div>
          </div>
        </div>

        <div class="section">
          <h2>Kafka 로그</h2>
          <button @click="getKafkaLogs(1)" class="kafka-btn">Kafka 로그 조회</button>
          <div v-if="kafkaLogsLoading" class="loading-spinner">
            <p>Kafka 로그를 불러오는 중...</p>
          </div>
          <div v-if="kafkaLogs.length" class="kafka-logs">
            <h3>Kafka API 로그 (총 {{ kafkaLogsTotal }}개):</h3>
            <div class="kafka-log-container">
              <div v-for="(log, index) in kafkaLogs" :key="index" class="kafka-log-item">
                <div class="log-header">
                  <span class="log-timestamp">{{ formatDate(log.timestamp) }}</span>
                  <span class="log-status" :class="getStatusClass(log.status)">{{ log.status }}</span>
                </div>
                <div class="log-details">
                  <div class="log-user"><strong>사용자:</strong> {{ log.user_id }}</div>
                  <div class="log-endpoint"><strong>엔드포인트:</strong> {{ log.method }} {{ log.endpoint }}</div>
                  <div class="log-message"><strong>메시지:</strong> {{ log.message }}</div>
                </div>
              </div>
            </div>
            
            <!-- Kafka 로그 페이지네이션 -->
            <div class="pagination-info">
              <p>페이지 {{ kafkaLogsPage }} / {{ kafkaLogsTotalPages }} ({{ kafkaLogs.length }}개 표시)</p>
            </div>
            
            <div class="pagination">
              <button @click="() => getKafkaLogs(1)" :disabled="kafkaLogsPage === 1" class="page-btn">처음</button>
              <button @click="() => getKafkaLogs(kafkaLogsPage - 1)" :disabled="kafkaLogsPage === 1" class="page-btn">이전</button>
              
              <div class="page-numbers">
                <button 
                  v-for="page in getKafkaLogsVisiblePages()" 
                  :key="page"
                  @click="() => getKafkaLogs(page)"
                  :class="['page-number', { active: page === kafkaLogsPage }]"
                >
                  {{ page }}
                </button>
              </div>
              
              <button @click="() => getKafkaLogs(kafkaLogsPage + 1)" :disabled="kafkaLogsPage === kafkaLogsTotalPages" class="page-btn">다음</button>
              <button @click="() => getKafkaLogs(kafkaLogsTotalPages)" :disabled="kafkaLogsPage === kafkaLogsTotalPages" class="page-btn">마지막</button>
            </div>
          </div>
          <div v-if="kafkaLogsError" class="error-message">
            <p>❌ Kafka 로그 조회 실패: {{ kafkaLogsError }}</p>
          </div>
        </div>

        <div class="section">
          <h2>메시지 검색</h2>
          <div class="search-section">
            <input v-model="searchQuery" placeholder="메시지 검색" @keyup.enter="() => searchMessages(1)">
            <button @click="() => searchMessages(1)">검색</button>
            <button @click="() => getAllMessages(1)" class="view-all-btn">전체 메시지 보기</button>
            <button @click="toggleCacheManager" class="cache-btn">캐시 관리</button>
          </div>
          
          <!-- 캐시 관리 모달 -->
          <div v-if="showCacheManager" class="cache-modal">
            <div class="cache-modal-content">
              <h3>검색 캐시 관리</h3>
              
              <div class="cache-stats">
                <h4>전체 캐시 통계</h4>
                <div v-if="cacheStatsLoading" class="loading-spinner">
                  <p>캐시 통계를 불러오는 중...</p>
                </div>
                <div v-else>
                  <p><strong>캐시된 쿼리 수:</strong> {{ cacheStats.total_cached_queries || 0 }}</p>
                  <p><strong>총 히트 수:</strong> {{ cacheStats.total_hits || 0 }}</p>
                  <p><strong>캐시 만료 시간:</strong> 1분</p>
                  <button @click="loadCacheStats" class="refresh-btn">새로고침</button>
                </div>
              </div>
              
              <div class="cache-list" v-if="!cacheStatsLoading && cacheStats.cache_stats && cacheStats.cache_stats.length > 0">
                <h4>캐시된 쿼리 목록</h4>
                <div v-for="cache in cacheStats.cache_stats" :key="cache.query" class="cache-item">
                  <div class="cache-details">
                    <div class="cache-query"><strong>{{ cache.query }}</strong></div>
                    <div class="cache-info">
                      히트: {{ cache.hit_count }} | 결과: {{ cache.results_count }}개 | 
                      생성: {{ formatDate(cache.timestamp) }}
                    </div>
                  </div>
                  <div class="cache-actions">
                    <button @click="clearCache(cache.query)" class="clear-cache-btn">삭제</button>
                  </div>
                </div>
              </div>
              <div v-else-if="!cacheStatsLoading && (!cacheStats.cache_stats || cacheStats.cache_stats.length === 0)" class="no-cache">
                <p>캐시된 쿼리가 없습니다.</p>
              </div>
              
              <div class="cache-actions-bulk">
                <button @click="clearAllCache" class="clear-all-btn">전체 캐시 삭제</button>
              </div>
              
              <button @click="showCacheManager = false" class="close-btn">닫기</button>
            </div>
          </div>
          
          <div v-if="searchExecuted && (searchResults.length > 0 || searchTotal === 0)" class="search-results">
            <h3>검색 결과 (총 {{ searchTotal }}개):</h3>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>메시지</th>
                  <th>생성 시간</th>
                  <th>사용자</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="result in searchResults" :key="result.id">
                  <td>{{ result.id }}</td>
                  <td>{{ result.message }}</td>
                  <td>{{ formatDate(result.created_at) }}</td>
                  <td>{{ result.user_id || '없음' }}</td>
                </tr>
              </tbody>
            </table>
            
            <!-- 검색 결과가 없을 때 메시지 -->
            <div v-if="searchResults.length === 0 && searchTotal === 0" class="no-results">
              <p>검색 결과가 없습니다.</p>
            </div>
            
            <!-- 검색 결과 페이지네이션 -->
            <div v-if="searchTotal > 0" class="pagination-info">
              <p>페이지 {{ searchPage }} / {{ searchTotalPages }} ({{ searchResults.length }}개 표시)</p>
            </div>
            
            <div v-if="searchTotal > 0" class="pagination">
              <button @click="() => searchMessages(1)" :disabled="searchPage === 1" class="page-btn">처음</button>
              <button @click="() => searchMessages(searchPage - 1)" :disabled="searchPage === 1" class="page-btn">이전</button>
              
              <div class="page-numbers">
                <button 
                  v-for="page in getSearchVisiblePages()" 
                  :key="page"
                  @click="() => searchMessages(page)"
                  :class="['page-number', { active: page === searchPage }]"
                >
                  {{ page }}
                </button>
              </div>
              
              <button @click="() => searchMessages(searchPage + 1)" :disabled="searchPage === searchTotalPages" class="page-btn">다음</button>
              <button @click="() => searchMessages(searchTotalPages)" :disabled="searchPage === searchTotalPages" class="page-btn">마지막</button>
            </div>
          </div>
          
          <div v-if="allMessages.length > 0" class="all-messages">
            <h3>전체 메시지 (총 {{ allMessagesTotal }}개):</h3>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>메시지</th>
                  <th>생성 시간</th>
                  <th>사용자</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="message in allMessages" :key="message.id">
                  <td>{{ message.id }}</td>
                  <td>{{ message.message }}</td>
                  <td>{{ formatDate(message.created_at) }}</td>
                  <td>{{ message.user_id || '없음' }}</td>
                </tr>
              </tbody>
            </table>
            
            <!-- 전체 메시지 페이지네이션 -->
            <div v-if="allMessagesTotal > 0" class="pagination-info">
              <p>페이지 {{ allMessagesPage }} / {{ allMessagesTotalPages }} ({{ allMessages.length }}개 표시)</p>
            </div>
            
            <div v-if="allMessagesTotal > 0" class="pagination">
              <button @click="() => getAllMessages(1)" :disabled="allMessagesPage === 1" class="page-btn">처음</button>
              <button @click="() => getAllMessages(allMessagesPage - 1)" :disabled="allMessagesPage === 1" class="page-btn">이전</button>
              
              <div class="page-numbers">
                <button 
                  v-for="page in getAllMessagesVisiblePages()" 
                  :key="page"
                  @click="() => getAllMessages(page)"
                  :class="['page-number', { active: page === allMessagesPage }]"
                >
                  {{ page }}
                </button>
              </div>
              
              <button @click="() => getAllMessages(allMessagesPage + 1)" :disabled="allMessagesPage === allMessagesTotalPages" class="page-btn">다음</button>
              <button @click="() => getAllMessages(allMessagesTotalPages)" :disabled="allMessagesPage === allMessagesTotalPages" class="page-btn">마지막</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';
import frontendTelemetry from './telemetry';

// nginx 프록시를 통해 요청하도록 수정
const API_BASE_URL = '/api';

// axios 기본 설정 - 쿠키 자동 전송
axios.defaults.withCredentials = true;

export default {
  name: 'App',
  data() {
    return {
      username: '',
      password: '',
      isLoggedIn: false,
      isLoading: true, // 초기 로딩 상태
      searchQuery: '',
      dbMessage: '',
      dbData: [],
      redisLogs: [],
      sampleMessages: [
        '안녕하세요! 테스트 메시지입니다.',
        'K8s 데모 샘플 데이터입니다.',
        '마이크로서비스 테스트 중입니다.',
        '샘플 메시지 입니다.'
      ],
      limit: 20,
      loading: false,
      // 페이지네이션 정보
      currentPage: 1,
      totalPages: 1,
      totalMessages: 0,
      showRegister: false,
      registerUsername: '',
      registerPassword: '',
      confirmPassword: '',
      currentUser: null,
      searchResults: [],
      searchPage: 1,
      searchTotal: 0,
      searchTotalPages: 1,
      redisLogs: [],
      redisLogsPage: 1,
      redisLogsTotal: 0,
      redisLogsTotalPages: 1,
      kafkaLogs: [],
      kafkaLogsPage: 1,
      kafkaLogsTotal: 0,
      kafkaLogsTotalPages: 1,
      kafkaLogsLoading: false,
      kafkaLogsError: null,
      // 전체 메시지 관련
      allMessages: [],
      allMessagesPage: 1,
      allMessagesTotal: 0,
      allMessagesTotalPages: 1,
      // 검색 상태 추적
      searchExecuted: false,
      // 캐시 관리 관련
      showCacheManager: false,
      cacheStats: {},
      cacheStatsLoading: false
    }
  },
  async mounted() {
    // 페이지 로드 시 세션 상태 확인
    await this.checkSessionStatus();
  },
  methods: {
    // 세션 상태 확인
    async checkSessionStatus() {
      try {
        const response = await axios.get(`${API_BASE_URL}/session/status`);
        if (response.data.logged_in) {
          this.isLoggedIn = true;
          this.currentUser = response.data.username;
        }
      } catch (error) {
        console.log('세션 상태 확인 실패:', error);
        // 세션이 없거나 오류가 발생한 경우 로그인 페이지 표시
      } finally {
        this.isLoading = false;
      }
    },

    // 날짜를 사용자 친화적인 형식으로 변환
    formatDate(dateString) {
      if (!dateString) return '알 수 없음';
      const date = new Date(dateString);
      // UTC 시간을 한국 시간으로 변환
      return date.toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});
    },
    
    // MariaDB에 메시지 저장
    async saveToDb() {
      const startTime = performance.now();
      
      try {
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackUserAction('save_message_to_db', {
          message_length: this.dbMessage.length,
          component: 'db_section'
        });
        frontendTelemetry.recordUserActionMetric('save_message_to_db', {
          message_length: this.dbMessage.length,
          component: 'db_section'
        });
        frontendTelemetry.log('사용자가 메시지를 저장하려고 시도함', 'info', {
          message_length: this.dbMessage.length,
          component: 'db_section'
        });
        
        await axios.post(`${API_BASE_URL}/db/message`, {
          message: this.dbMessage
        });
        
        const duration = performance.now() - startTime;
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackApiCall('POST', `${API_BASE_URL}/db/message`, 200, duration);
        frontendTelemetry.recordApiCallMetric('POST', `${API_BASE_URL}/db/message`, 200, duration);
        frontendTelemetry.recordPerformanceMetric('save_message', duration);
        frontendTelemetry.log('메시지 저장 성공', 'info', {
          duration: duration,
          message_length: this.dbMessage.length
        });
        
        this.dbMessage = '';
        this.getFromDb();
        this.getRedisLogs();
      } catch (error) {
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('POST', `${API_BASE_URL}/db/message`, (error.response && error.response.status) || 500, duration);
        // Trace, Metric, Log 모두 기록 (오류)
        frontendTelemetry.trackError(error, {
          context: 'save_message_to_db',
          message_length: this.dbMessage.length
        });
        frontendTelemetry.recordMetric('save_message_errors_total', 1, {
          context: 'save_message_to_db',
          error_type: error.name || 'Error'
        });
        frontendTelemetry.log('메시지 저장 실패', 'error', {
          error: error.message,
          context: 'save_message_to_db',
          message_length: this.dbMessage.length
        });
        console.error('DB 저장 실패:', error);
      }
    },

    // MariaDB에서 메시지 조회 (페이지네이션 적용)
    async getFromDb() {
      const startTime = performance.now();
      
      try {
        this.loading = true;
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackUserAction('get_messages_from_db', {
          page: this.currentPage,
          limit: this.limit,
          component: 'db_section'
        });
        frontendTelemetry.recordUserActionMetric('get_messages_from_db', {
          page: this.currentPage,
          limit: this.limit,
          component: 'db_section'
        });
        frontendTelemetry.log('사용자가 메시지를 조회하려고 시도함', 'info', {
          page: this.currentPage,
          limit: this.limit,
          component: 'db_section'
        });
        
        const response = await axios.get(`${API_BASE_URL}/db/message?page=${this.currentPage}&limit=${this.limit}`);
        
        const duration = performance.now() - startTime;
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackApiCall('GET', `${API_BASE_URL}/db/message`, 200, duration);
        frontendTelemetry.recordApiCallMetric('GET', `${API_BASE_URL}/db/message`, 200, duration);
        frontendTelemetry.recordPerformanceMetric('get_messages', duration);
        frontendTelemetry.log('메시지 조회 성공', 'info', {
          duration: duration,
          page: this.currentPage,
          limit: this.limit
        });
        
        // 페이지네이션 정보 처리
        if (response.data.messages) {
          // 항상 현재 페이지 데이터로 교체 (중복 방지)
          this.dbData = response.data.messages;
          
          // 페이지네이션 정보 업데이트
          this.totalMessages = response.data.pagination.total;
          this.currentPage = response.data.pagination.current_page;
          this.totalPages = response.data.pagination.total_pages;
        } else {
          // 기존 형식 호환성 유지
          this.dbData = response.data;
        }
      } catch (error) {
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('GET', `${API_BASE_URL}/db/message`, (error.response && error.response.status) || 500, duration);
        // Trace, Metric, Log 모두 기록 (오류)
        frontendTelemetry.trackError(error, {
          context: 'get_messages_from_db',
          page: this.currentPage,
          limit: this.limit
        });
        frontendTelemetry.recordMetric('get_messages_errors_total', 1, {
          context: 'get_messages_from_db',
          error_type: error.name || 'Error'
        });
        frontendTelemetry.log('메시지 조회 실패', 'error', {
          error: error.message,
          context: 'get_messages_from_db',
          page: this.currentPage,
          limit: this.limit
        });
        console.error('DB 조회 실패:', error);
      } finally {
        this.loading = false;
      }
    },

    // 샘플 데이터를 DB에 저장
    async insertSampleData() {
      const startTime = performance.now();
      const randomMessage = this.sampleMessages[Math.floor(Math.random() * this.sampleMessages.length)];
      
      try {
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackUserAction('insert_sample_data', {
          message: randomMessage,
          component: 'db_section'
        });
        frontendTelemetry.recordUserActionMetric('insert_sample_data', {
          message: randomMessage,
          component: 'db_section'
        });
        frontendTelemetry.log('사용자가 샘플 데이터를 저장하려고 시도함', 'info', {
          message: randomMessage,
          component: 'db_section'
        });
        
        await axios.post(`${API_BASE_URL}/db/message`, {
          message: randomMessage
        });
        
        const duration = performance.now() - startTime;
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackApiCall('POST', `${API_BASE_URL}/db/message`, 200, duration);
        frontendTelemetry.recordApiCallMetric('POST', `${API_BASE_URL}/db/message`, 200, duration);
        frontendTelemetry.recordPerformanceMetric('insert_sample_data', duration);
        frontendTelemetry.log('샘플 데이터 저장 성공', 'info', {
          duration: duration,
          message: randomMessage
        });
        
        this.getFromDb();
        this.getRedisLogs();
      } catch (error) {
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('POST', `${API_BASE_URL}/db/message`, (error.response && error.response.status) || 500, duration);
        // Trace, Metric, Log 모두 기록 (오류)
        frontendTelemetry.trackError(error, {
          context: 'insert_sample_data',
          message: randomMessage
        });
        frontendTelemetry.recordMetric('insert_sample_data_errors_total', 1, {
          context: 'insert_sample_data',
          error_type: error.name || 'Error'
        });
        frontendTelemetry.log('샘플 데이터 저장 실패', 'error', {
          error: error.message,
          context: 'insert_sample_data',
          message: randomMessage
        });
        console.error('샘플 데이터 저장 실패:', error);
      }
    },

    // Redis에 저장된 API 호출 로그 조회
    async getRedisLogs(page = 1) {
      const startTime = performance.now();
      
      try {
        this.redisLogsPage = page;
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackUserAction('get_redis_logs', {
          page: page,
          component: 'redis_section'
        });
        frontendTelemetry.recordUserActionMetric('get_redis_logs', {
          page: page,
          component: 'redis_section'
        });
        frontendTelemetry.log('사용자가 Redis 로그를 조회하려고 시도함', 'info', {
          page: page,
          component: 'redis_section'
        });
        
        const response = await axios.get(`${API_BASE_URL}/logs/redis?page=${page}&limit=20`);
        
        const duration = performance.now() - startTime;
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackApiCall('GET', `${API_BASE_URL}/logs/redis`, 200, duration);
        frontendTelemetry.recordApiCallMetric('GET', `${API_BASE_URL}/logs/redis`, 200, duration);
        frontendTelemetry.recordPerformanceMetric('get_redis_logs', duration);
        frontendTelemetry.log('Redis 로그 조회 성공', 'info', {
          duration: duration,
          page: page
        });
        
        if (response.data.logs) {
          this.redisLogs = response.data.logs;
          this.redisLogsTotal = response.data.pagination.total;
          this.redisLogsTotalPages = response.data.pagination.total_pages;
        } else {
          // 기존 형식 호환성 유지
          this.redisLogs = response.data;
        }
      } catch (error) {
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('GET', `${API_BASE_URL}/logs/redis`, (error.response && error.response.status) || 500, duration);
        // Trace, Metric, Log 모두 기록 (오류)
        frontendTelemetry.trackError(error, {
          context: 'get_redis_logs',
          page: page
        });
        frontendTelemetry.recordMetric('get_redis_logs_errors_total', 1, {
          context: 'get_redis_logs',
          error_type: error.name || 'Error'
        });
        frontendTelemetry.log('Redis 로그 조회 실패', 'error', {
          error: error.message,
          context: 'get_redis_logs',
          page: page
        });
        console.error('Redis 로그 조회 실패:', error);
      }
    },

    // Kafka에 저장된 API 호출 로그 조회
    async getKafkaLogs(page = 1) {
      const startTime = performance.now();
      
      try {
        this.kafkaLogsLoading = true;
        this.kafkaLogsError = null;
        this.kafkaLogsPage = page;
        
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackUserAction('get_kafka_logs', {
          page: page,
          component: 'kafka_section'
        });
        frontendTelemetry.recordUserActionMetric('get_kafka_logs', {
          page: page,
          component: 'kafka_section'
        });
        frontendTelemetry.log('사용자가 Kafka 로그를 조회하려고 시도함', 'info', {
          page: page,
          component: 'kafka_section'
        });
        
        const response = await axios.get(`${API_BASE_URL}/logs/messaging?page=${page}&limit=20`);
        
        const duration = performance.now() - startTime;
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackApiCall('GET', `${API_BASE_URL}/logs/messaging`, 200, duration);
        frontendTelemetry.recordApiCallMetric('GET', `${API_BASE_URL}/logs/messaging`, 200, duration);
        frontendTelemetry.recordPerformanceMetric('get_kafka_logs', duration);
        frontendTelemetry.log('Kafka 로그 조회 성공', 'info', {
          duration: duration,
          page: page
        });
        
        if (response.data.logs) {
          this.kafkaLogs = response.data.logs;
          this.kafkaLogsTotal = response.data.pagination.total;
          this.kafkaLogsTotalPages = response.data.pagination.total_pages;
        } else {
          // 기존 형식 호환성 유지
          this.kafkaLogs = response.data;
        }
        console.log('Kafka 로그 조회 성공:', this.kafkaLogs);
      } catch (error) {
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('GET', `${API_BASE_URL}/logs/messaging`, (error.response && error.response.status) || 500, duration);
        // Trace, Metric, Log 모두 기록 (오류)
        frontendTelemetry.trackError(error, {
          context: 'get_kafka_logs',
          page: page
        });
        frontendTelemetry.recordMetric('get_kafka_logs_errors_total', 1, {
          context: 'get_kafka_logs',
          error_type: error.name || 'Error'
        });
        frontendTelemetry.log('Kafka 로그 조회 실패', 'error', {
          error: error.message,
          context: 'get_kafka_logs',
          page: page
        });
        console.error('Kafka 로그 조회 실패:', error);
        this.kafkaLogsError = error.response && error.response.data && error.response.data.message 
          ? error.response.data.message 
          : 'Kafka 로그 조회에 실패했습니다.';
      } finally {
        this.kafkaLogsLoading = false;
      }
    },

    // 상태에 따른 CSS 클래스 반환
    getStatusClass(status) {
      return {
        'status-success': status === 'success',
        'status-error': status === 'error'
      };
    },

    // 사용자 로그인 처리
    async login() {
      const startTime = performance.now();
      
      try {
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackUserAction('login_attempt', {
          username: this.username,
          component: 'login_section'
        });
        frontendTelemetry.recordUserActionMetric('login_attempt', {
          username: this.username,
          component: 'login_section'
        });
        frontendTelemetry.log('사용자 로그인 시도', 'info', {
          username: this.username,
          component: 'login_section'
        });
        
        const response = await axios.post(`${API_BASE_URL}/login`, {
          username: this.username,
          password: this.password
        });
        
        const duration = performance.now() - startTime;
        // Trace, Metric, Log 모두 기록
        frontendTelemetry.trackApiCall('POST', `${API_BASE_URL}/login`, 200, duration);
        frontendTelemetry.recordApiCallMetric('POST', `${API_BASE_URL}/login`, 200, duration);
        frontendTelemetry.recordPerformanceMetric('login', duration);
        frontendTelemetry.log('로그인 API 호출 성공', 'info', {
          duration: duration,
          username: this.username
        });
        
        if (response.data.status === 'success') {
          frontendTelemetry.trackUserAction('login_success', {
            username: this.username
          });
          
          // Trace, Metric, Log 모두 기록
          frontendTelemetry.recordUserActionMetric('login_success', {
            username: this.username
          });
          frontendTelemetry.log('사용자 로그인 성공', 'info', {
            username: this.username
          });
          
          this.isLoggedIn = true;
          this.currentUser = this.username;
          this.username = '';
          this.password = '';
          
          // 로그인 후 세션 정보 업데이트
          await this.checkSessionStatus();
        } else {
                  // Trace, Metric, Log 모두 기록 (로그인 실패)
        frontendTelemetry.trackError(new Error(response.data.message || '로그인 실패'), {
          context: 'login_failed',
          username: this.username
        });
        frontendTelemetry.recordMetric('login_failures_total', 1, {
          context: 'login_failed',
          username: this.username
        });
        frontendTelemetry.log('로그인 실패', 'warn', {
          context: 'login_failed',
          username: this.username,
          reason: response.data.message || '로그인 실패'
        });
          alert(response.data.message || '로그인에 실패했습니다.');
        }
      } catch (error) {
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('POST', `${API_BASE_URL}/login`, (error.response && error.response.status) || 500, duration);
        // Trace, Metric, Log 모두 기록 (로그인 오류)
        frontendTelemetry.trackError(error, {
          context: 'login_error',
          username: this.username
        });
        frontendTelemetry.recordMetric('login_errors_total', 1, {
          context: 'login_error',
          error_type: error.name || 'Error'
        });
        frontendTelemetry.log('로그인 오류 발생', 'error', {
          error: error.message,
          context: 'login_error',
          username: this.username
        });
        console.error('로그인 실패:', error);
        alert(error.response && error.response.data 
          ? error.response.data.message 
          : '로그인에 실패했습니다.');
      }
    },
    
    // 로그아웃 처리
    async logout() {
      const startTime = performance.now();
      
      try {
        frontendTelemetry.trackUserAction('logout_attempt', {
          username: this.currentUser,
          component: 'user_section'
        });
        
        await axios.post(`${API_BASE_URL}/logout`, {}, {
          headers: {
            'Content-Type': 'application/json'
          }
        });
        
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('POST', `${API_BASE_URL}/logout`, 200, duration);
        
        frontendTelemetry.trackUserAction('logout_success', {
          username: this.currentUser
        });
        
        this.isLoggedIn = false;
        this.username = '';
        this.password = '';
        this.currentUser = null;

        
        // 로그아웃 후 모든 데이터 초기화
        this.dbData = [];
        this.redisLogs = [];
        this.kafkaLogs = [];
        this.searchResults = [];
        this.allMessages = [];
        this.currentPage = 1;
        this.totalPages = 1;
        this.totalMessages = 0;
        this.searchPage = 1;
        this.searchTotal = 0;
        this.searchTotalPages = 1;
        this.redisLogsPage = 1;
        this.redisLogsTotal = 0;
        this.redisLogsTotalPages = 1;
        this.kafkaLogsPage = 1;
        this.kafkaLogsTotal = 0;
        this.kafkaLogsTotalPages = 1;
        this.allMessagesPage = 1;
        this.allMessagesTotal = 0;
        this.allMessagesTotalPages = 1;
        this.searchQuery = '';
        this.searchExecuted = false;
        this.showCacheManager = false;
        this.cacheStats = {};
        this.loading = false;
        this.kafkaLogsLoading = false;
        this.kafkaLogsError = null;
      } catch (error) {
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('POST', `${API_BASE_URL}/logout`, (error.response && error.response.status) || 500, duration);
        frontendTelemetry.trackError(error, {
          context: 'logout_error',
          username: this.currentUser
        });
        console.error('로그아웃 실패:', error);
      }
    },

    // 메시지 검색 기능
    async searchMessages(page = 1) {
      const startTime = performance.now();
      
      try {
        this.loading = true;
        this.searchPage = page;
        this.searchExecuted = true; // 검색 실행됨을 표시
        
        frontendTelemetry.trackUserAction('search_messages', {
          query: this.searchQuery,
          page: page,
          component: 'search_section'
        });
        
        // 검색 시 전체 메시지 완전히 숨기기
        this.allMessages = [];
        this.allMessagesPage = 1;
        this.allMessagesTotal = 0;
        this.allMessagesTotalPages = 1;
        
        const response = await axios.get(`${API_BASE_URL}/db/messages/search`, {
          params: { 
            q: this.searchQuery,
            page: page,
            limit: 20
          }
        });
        
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('GET', `${API_BASE_URL}/db/messages/search`, 200, duration);
        
        if (response.data.results) {
          this.searchResults = response.data.results;
          this.searchTotal = response.data.pagination.total;
          this.searchTotalPages = response.data.pagination.total_pages;
        } else {
          // 기존 형식 호환성 유지
          this.searchResults = response.data;
          this.searchTotal = response.data.length;
          this.searchTotalPages = 1;
        }
      } catch (error) {
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('GET', `${API_BASE_URL}/db/messages/search`, (error.response && error.response.status) || 500, duration);
        frontendTelemetry.trackError(error, {
          context: 'search_messages',
          query: this.searchQuery,
          page: page
        });
        console.error('검색 실패:', error);
        alert('검색에 실패했습니다.');
      } finally {
        this.loading = false;
      }
    },

    // 캐시 관리 모달 토글
    async toggleCacheManager() {
      this.showCacheManager = !this.showCacheManager;
      if (this.showCacheManager) {
        // 모달이 열릴 때 캐시 통계 로드
        await this.loadCacheStats();
      }
    },

    // 캐시 통계 로드
    async loadCacheStats() {
      try {
        this.cacheStatsLoading = true;
        const response = await axios.get(`${API_BASE_URL}/cache/search/stats`);
        this.cacheStats = response.data;
      } catch (error) {
        console.error('캐시 통계 로드 실패:', error);
        alert('캐시 통계를 불러오는데 실패했습니다.');
      } finally {
        this.cacheStatsLoading = false;
      }
    },

    // 특정 캐시 삭제
    async clearCache(query) {
      if (!confirm(`쿼리 '${query}'의 캐시를 삭제하시겠습니까?`)) {
        return;
      }
      
      try {
        const response = await axios.post(`${API_BASE_URL}/cache/search/clear`, {
          query: query
        });
        alert(response.data.message);
        // 통계 즉시 새로고침
        await this.loadCacheStats();
      } catch (error) {
        console.error('캐시 삭제 실패:', error);
        alert('캐시 삭제에 실패했습니다.');
      }
    },

    // 모든 캐시 삭제
    async clearAllCache() {
      if (!confirm('전체 검색 캐시를 삭제하시겠습니까?')) {
        return;
      }
      
      try {
        const response = await axios.post(`${API_BASE_URL}/cache/search/clear`, {});
        alert(response.data.message);
        // 통계 즉시 새로고침
        await this.loadCacheStats();
      } catch (error) {
        console.error('캐시 삭제 실패:', error);
        alert('캐시 삭제에 실패했습니다.');
      }
    },

    // 전체 메시지 조회
    async getAllMessages(page = 1) {
      const startTime = performance.now();
      
      try {
        this.loading = true;
        this.allMessagesPage = page;
        
        frontendTelemetry.trackUserAction('get_all_messages', {
          page: page,
          component: 'search_section'
        });
        
        // 전체 메시지 조회 시 검색 결과 완전히 숨기기
        this.searchResults = [];
        this.searchPage = 1;
        this.searchTotal = 0;
        this.searchTotalPages = 1;
        this.searchQuery = ''; // 검색어도 초기화
        this.searchExecuted = false; // 검색 실행 상태 초기화
        
        const response = await axios.get(`${API_BASE_URL}/db/messages?page=${page}&limit=20`);
        
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('GET', `${API_BASE_URL}/db/messages`, 200, duration);
        
        if (response.data.messages) {
          this.allMessages = response.data.messages;
          this.allMessagesTotal = response.data.pagination.total;
          this.allMessagesTotalPages = response.data.pagination.total_pages;
        } else {
          // 기존 형식 호환성 유지
          this.allMessages = response.data;
          this.allMessagesTotal = response.data.length;
          this.allMessagesTotalPages = 1;
        }
      } catch (error) {
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('GET', `${API_BASE_URL}/db/messages`, (error.response && error.response.status) || 500, duration);
        frontendTelemetry.trackError(error, {
          context: 'get_all_messages',
          page: page
        });
        console.error('전체 메시지 로드 실패:', error);
      } finally {
        this.loading = false;
      }
    },

    // 특정 페이지로 이동
    async goToPage(page) {
      if (page >= 1 && page <= this.totalPages && page !== this.currentPage) {
        this.currentPage = page;
        await this.getFromDb();
      }
    },

    // 이전 페이지로 이동
    async goToPrevPage() {
      if (this.currentPage > 1) {
        this.currentPage--;
        await this.getFromDb();
      }
    },

    // 다음 페이지로 이동
    async goToNextPage() {
      if (this.currentPage < this.totalPages) {
        this.currentPage++;
        await this.getFromDb();
      }
    },

    // 첫 페이지로 이동
    async goToFirstPage() {
      if (this.currentPage !== 1) {
        this.currentPage = 1;
        await this.getFromDb();
      }
    },

    // 마지막 페이지로 이동
    async goToLastPage() {
      if (this.currentPage !== this.totalPages) {
        this.currentPage = this.totalPages;
        await this.getFromDb();
      }
    },

    // 표시할 페이지 번호들 계산
    getVisiblePages() {
      const pages = [];
      const maxVisible = 5; // 최대 5개 페이지 번호 표시
      
      if (this.totalPages <= maxVisible) {
        // 전체 페이지가 5개 이하면 모두 표시
        for (let i = 1; i <= this.totalPages; i++) {
          pages.push(i);
        }
      } else {
        // 현재 페이지 기준으로 앞뒤 2개씩 표시
        let start = Math.max(1, this.currentPage - 2);
        let end = Math.min(this.totalPages, this.currentPage + 2);
        
        // 시작과 끝 조정
        if (end - start < 4) {
          if (start === 1) {
            end = Math.min(this.totalPages, start + 4);
          } else {
            start = Math.max(1, end - 4);
          }
        }
        
        for (let i = start; i <= end; i++) {
          pages.push(i);
        }
      }
      
      return pages;
    },

    // Redis 로그 페이지네이션용 페이지 번호들 계산
    getRedisLogsVisiblePages() {
      const pages = [];
      const maxVisible = 5;
      
      if (this.redisLogsTotalPages <= maxVisible) {
        for (let i = 1; i <= this.redisLogsTotalPages; i++) {
          pages.push(i);
        }
      } else {
        let start = Math.max(1, this.redisLogsPage - 2);
        let end = Math.min(this.redisLogsTotalPages, this.redisLogsPage + 2);
        
        if (end - start < 4) {
          if (start === 1) {
            end = Math.min(this.redisLogsTotalPages, start + 4);
          } else {
            start = Math.max(1, end - 4);
          }
        }
        
        for (let i = start; i <= end; i++) {
          pages.push(i);
        }
      }
      
      return pages;
    },

    // Kafka 로그 페이지네이션용 페이지 번호들 계산
    getKafkaLogsVisiblePages() {
      const pages = [];
      const maxVisible = 5;
      
      if (this.kafkaLogsTotalPages <= maxVisible) {
        for (let i = 1; i <= this.kafkaLogsTotalPages; i++) {
          pages.push(i);
        }
      } else {
        let start = Math.max(1, this.kafkaLogsPage - 2);
        let end = Math.min(this.kafkaLogsTotalPages, this.kafkaLogsPage + 2);
        
        if (end - start < 4) {
          if (start === 1) {
            end = Math.min(this.kafkaLogsTotalPages, start + 4);
          } else {
            start = Math.max(1, end - 4);
          }
        }
        
        for (let i = start; i <= end; i++) {
          pages.push(i);
        }
      }
      
      return pages;
    },

    // 검색 결과 페이지네이션용 페이지 번호들 계산
    getSearchVisiblePages() {
      const pages = [];
      const maxVisible = 5;
      
      if (this.searchTotalPages <= maxVisible) {
        for (let i = 1; i <= this.searchTotalPages; i++) {
          pages.push(i);
        }
      } else {
        let start = Math.max(1, this.searchPage - 2);
        let end = Math.min(this.searchTotalPages, this.searchPage + 2);
        
        if (end - start < 4) {
          if (start === 1) {
            end = Math.min(this.searchTotalPages, start + 4);
          } else {
            start = Math.max(1, end - 4);
          }
        }
        
        for (let i = start; i <= end; i++) {
          pages.push(i);
        }
      }
      
      return pages;
    },

    // 전체 메시지 페이지네이션용 페이지 번호들 계산
    getAllMessagesVisiblePages() {
      const pages = [];
      const maxVisible = 5;
      
      if (this.allMessagesTotalPages <= maxVisible) {
        for (let i = 1; i <= this.allMessagesTotalPages; i++) {
          pages.push(i);
        }
      } else {
        let start = Math.max(1, this.allMessagesPage - 2);
        let end = Math.min(this.allMessagesTotalPages, this.allMessagesPage + 2);
        
        if (end - start < 4) {
          if (start === 1) {
            end = Math.min(this.allMessagesTotalPages, start + 4);
          } else {
            start = Math.max(1, end - 4);
          }
        }
        
        for (let i = start; i <= end; i++) {
          pages.push(i);
        }
      }
      
      return pages;
    },

    // 회원가입 처리
    async register() {
      if (this.registerPassword !== this.confirmPassword) {
        frontendTelemetry.trackError(new Error('비밀번호 불일치'), {
          context: 'register_validation',
          username: this.registerUsername
        });
        alert('비밀번호가 일치하지 않습니다');
        return;
      }
      
      const startTime = performance.now();
      
      try {
        frontendTelemetry.trackUserAction('register_attempt', {
          username: this.registerUsername,
          component: 'register_section'
        });
        
        const response = await axios.post(`${API_BASE_URL}/register`, {
          username: this.registerUsername,
          password: this.registerPassword
        });
        
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('POST', `${API_BASE_URL}/register`, 200, duration);
        
        if (response.data.status === 'success') {
          frontendTelemetry.trackUserAction('register_success', {
            username: this.registerUsername
          });
          
          alert('회원가입이 완료되었습니다. 로그인해주세요.');
          this.showRegister = false;
          this.registerUsername = '';
          this.registerPassword = '';
          this.confirmPassword = '';
        }
      } catch (error) {
        const duration = performance.now() - startTime;
        frontendTelemetry.trackApiCall('POST', `${API_BASE_URL}/register`, (error.response && error.response.status) || 500, duration);
        frontendTelemetry.trackError(error, {
          context: 'register_error',
          username: this.registerUsername
        });
        console.error('회원가입 실패:', error);
        alert(error.response && error.response.data && error.response.data.message 
          ? error.response.data.message 
          : '회원가입에 실패했습니다.');
      }
    }
  }
}
</script>

<style>
.container {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}

.section {
  margin-bottom: 30px;
  padding: 20px;
  border: 1px solid #ddd;
  border-radius: 5px;
}

input {
  margin-right: 10px;
  padding: 5px;
  width: 300px;
}

button {
  margin-right: 10px;
  padding: 5px 10px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 3px;
  cursor: pointer;
}

button:hover {
  background-color: #0056b3;
}

.sample-btn {
  background-color: #28a745;
}

.sample-btn:hover {
  background-color: #218838;
}

ul {
  list-style-type: none;
  padding: 0;
}

li {
  margin: 5px 0;
  padding: 5px;
  border-bottom: 1px solid #eee;
}

.pagination {
  text-align: center;
  margin-top: 10px;
}

.pagination button {
  padding: 5px 10px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 3px;
  cursor: pointer;
}

.pagination button:hover {
  background-color: #0056b3;
}

.pagination button:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

.pagination-info {
  margin: 10px 0;
  padding: 10px;
  background-color: #f8f9fa;
  border-radius: 5px;
  text-align: center;
  font-size: 14px;
  color: #6c757d;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 5px;
  margin: 15px 0;
}

.page-btn {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 8px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.page-btn:hover:not(:disabled) {
  background-color: #0056b3;
}

.page-numbers {
  display: flex;
  gap: 3px;
}

.page-number {
  background-color: #f8f9fa;
  color: #495057;
  border: 1px solid #dee2e6;
  padding: 8px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  min-width: 40px;
}

.page-number:hover:not(:disabled) {
  background-color: #e9ecef;
}

.page-number.active {
  background-color: #007bff;
  color: white;
  border-color: #007bff;
}

.page-number.active:hover {
  background-color: #0056b3;
}

.no-results {
  text-align: center;
  padding: 20px;
  color: #6c757d;
  font-style: italic;
}

.loading-spinner {
  text-align: center;
  margin-top: 20px;
  font-size: 16px;
  color: #555;
}

.user-info {
  text-align: right;
  padding: 10px;
  margin-bottom: 20px;
}

.search-section {
  margin: 10px 0;
}

.search-section input {
  width: 200px;
  margin-right: 10px;
}

.register-btn {
  background-color: #6c757d;
}

.register-btn:hover {
  background-color: #5a6268;
}

.search-results {
  margin-top: 20px;
}

.search-results table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 10px;
}

.search-results th,
.search-results td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid #eee;
}

.search-results th {
  background-color: #f8f9fa;
  font-weight: bold;
}

.search-results tr:hover {
  background-color: #f5f5f5;
}

.view-all-btn {
  background-color: #6c757d;
}

.view-all-btn:hover {
  background-color: #5a6268;
}

.kafka-btn {
  background-color: #17a2b8;
}

.kafka-btn:hover {
  background-color: #138496;
}

.kafka-logs {
  margin-top: 20px;
}

.kafka-log-container {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #ddd;
  border-radius: 5px;
  padding: 10px;
}

.kafka-log-item {
  margin-bottom: 15px;
  padding: 10px;
  border: 1px solid #eee;
  border-radius: 5px;
  background-color: #f8f9fa;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  padding-bottom: 5px;
  border-bottom: 1px solid #dee2e6;
}

.log-timestamp {
  font-size: 0.9em;
  color: #6c757d;
}

.log-status {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.8em;
  font-weight: bold;
}

.status-success {
  background-color: #d4edda;
  color: #155724;
}

.status-error {
  background-color: #f8d7da;
  color: #721c24;
}

.log-details {
  font-size: 0.9em;
}

.log-details > div {
  margin-bottom: 3px;
}

.log-user {
  color: #495057;
}

.log-endpoint {
  color: #6c757d;
}

.log-message {
  color: #495057;
  font-style: italic;
}

.error-message {
  margin-top: 10px;
  padding: 10px;
  background-color: #f8d7da;
  border: 1px solid #f5c6cb;
  border-radius: 5px;
  color: #721c24;
}

/* 캐시 관리 버튼 */
.cache-btn {
  background-color: #ffc107;
  color: #212529;
}

.cache-btn:hover {
  background-color: #e0a800;
}

/* 캐시 관리 모달 */
.cache-modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.cache-modal-content {
  background-color: white;
  padding: 30px;
  border-radius: 10px;
  max-width: 700px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
}

.cache-modal h3 {
  margin-top: 0;
  margin-bottom: 20px;
  color: #333;
}

.cache-stats {
  background-color: #f8f9fa;
  padding: 15px;
  border-radius: 5px;
  margin-bottom: 20px;
}

.cache-stats h4 {
  margin-top: 0;
  margin-bottom: 10px;
  color: #333;
}

.cache-stats p {
  margin: 5px 0;
  font-size: 14px;
}

.refresh-btn {
  background-color: #17a2b8;
  margin-top: 10px;
}

.refresh-btn:hover {
  background-color: #138496;
}

.cache-list h4 {
  margin-bottom: 15px;
  color: #333;
}

.cache-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  border: 1px solid #dee2e6;
  border-radius: 5px;
  margin-bottom: 10px;
  background-color: #fff;
}

.cache-details {
  flex: 1;
}

.cache-query {
  margin-bottom: 5px;
  color: #495057;
}

.cache-info {
  font-size: 12px;
  color: #6c757d;
}

.cache-actions {
  margin-left: 15px;
}

.clear-cache-btn {
  background-color: #dc3545;
  font-size: 12px;
  padding: 5px 10px;
}

.clear-cache-btn:hover {
  background-color: #c82333;
}

.cache-actions-bulk {
  margin-top: 20px;
  text-align: center;
}

.clear-all-btn {
  background-color: #dc3545;
  padding: 10px 20px;
}

.clear-all-btn:hover {
  background-color: #c82333;
}

.no-cache {
  text-align: center;
  padding: 20px;
  color: #6c757d;
  font-style: italic;
}

/* 로딩 컨테이너 */
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  font-size: 18px;
  color: #555;
}


</style> 