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
            <h3>내 메시지:</h3>
            <ul>
              <li v-for="item in dbData" :key="item.id">
                {{ item.message }} ({{ formatDate(item.created_at) }}) - {{ item.user_id }}
              </li>
            </ul>
          </div>
        </div>

        <div class="section">
          <h2>Redis 로그</h2>
          <button @click="getRedisLogs">로그 조회</button>
          <div v-if="redisLogs.length">
            <h3>API 호출 로그:</h3>
            <ul>
              <li v-for="(log, index) in redisLogs" :key="index">
                [{{ formatDate(log.timestamp) }}] {{ log.action }}: {{ log.details }}
              </li>
            </ul>
          </div>
        </div>

        <div class="section">
          <h2>Kafka 로그</h2>
          <button @click="getKafkaLogs" class="kafka-btn">Kafka 로그 조회</button>
          <div v-if="kafkaLogsLoading" class="loading-spinner">
            <p>Kafka 로그를 불러오는 중...</p>
          </div>
          <div v-if="kafkaLogs.length" class="kafka-logs">
            <h3>Kafka API 로그:</h3>
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
          </div>
          <div v-if="kafkaLogsError" class="error-message">
            <p>❌ Kafka 로그 조회 실패: {{ kafkaLogsError }}</p>
          </div>
        </div>

        <div class="section">
          <h2>메시지 검색</h2>
          <div class="search-section">
            <input v-model="searchQuery" placeholder="메시지 검색">
            <button @click="searchMessages">검색</button>
            <button @click="getAllMessages" class="view-all-btn">전체 메시지 보기</button>
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
          
          <div v-if="searchResults.length > 0" class="search-results">
            <h3>검색 결과:</h3>
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
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

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
      offset: 0,
      limit: 20,
      loading: false,
      hasMore: true,
      showRegister: false,
      registerUsername: '',
      registerPassword: '',
      confirmPassword: '',
      currentUser: null,
      searchResults: [],
      kafkaLogs: [],
      kafkaLogsLoading: false,
      kafkaLogsError: null,
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
      return date.toLocaleString();
    },
    
    // MariaDB에 메시지 저장
    async saveToDb() {
      try {
        await axios.post(`${API_BASE_URL}/db/message`, {
          message: this.dbMessage
        });
        this.dbMessage = '';
        this.getFromDb();
        this.getRedisLogs();
      } catch (error) {
        console.error('DB 저장 실패:', error);
      }
    },

    // MariaDB에서 메시지 조회 (페이지네이션 적용)
    async getFromDb() {
      try {
        this.loading = true;
        const response = await axios.get(`${API_BASE_URL}/db/message?offset=${this.offset}&limit=${this.limit}`);
        this.dbData = response.data;
        this.hasMore = response.data.length === this.limit;
      } catch (error) {
        console.error('DB 조회 실패:', error);
      } finally {
        this.loading = false;
      }
    },

    // 샘플 데이터를 DB에 저장
    async insertSampleData() {
      const randomMessage = this.sampleMessages[Math.floor(Math.random() * this.sampleMessages.length)];
      try {
        await axios.post(`${API_BASE_URL}/db/message`, {
          message: randomMessage
        });
        this.getFromDb();
        this.getRedisLogs();
      } catch (error) {
        console.error('샘플 데이터 저장 실패:', error);
      }
    },

    // Redis에 저장된 API 호출 로그 조회
    async getRedisLogs() {
      try {
        const response = await axios.get(`${API_BASE_URL}/logs/redis`);
        this.redisLogs = response.data;
      } catch (error) {
        console.error('Redis 로그 조회 실패:', error);
      }
    },

    // Kafka에 저장된 API 호출 로그 조회
    async getKafkaLogs() {
      try {
        this.kafkaLogsLoading = true;
        this.kafkaLogsError = null;
        const response = await axios.get(`${API_BASE_URL}/logs/kafka`);
        this.kafkaLogs = response.data;
        console.log('Kafka 로그 조회 성공:', this.kafkaLogs);
      } catch (error) {
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
      try {
        const response = await axios.post(`${API_BASE_URL}/login`, {
          username: this.username,
          password: this.password
        });
        
        if (response.data.status === 'success') {
          this.isLoggedIn = true;
          this.currentUser = this.username;
          this.username = '';
          this.password = '';
          
          // 로그인 후 세션 정보 업데이트
          await this.checkSessionStatus();
        } else {
          alert(response.data.message || '로그인에 실패했습니다.');
        }
      } catch (error) {
        console.error('로그인 실패:', error);
        alert(error.response && error.response.data 
          ? error.response.data.message 
          : '로그인에 실패했습니다.');
      }
    },
    
    // 로그아웃 처리
    async logout() {
      try {
        await axios.post(`${API_BASE_URL}/logout`);
        this.isLoggedIn = false;
        this.username = '';
        this.password = '';
        this.currentUser = null;
      } catch (error) {
        console.error('로그아웃 실패:', error);
      }
    },

    // 메시지 검색 기능
    async searchMessages() {
      try {
        this.loading = true;
        const response = await axios.get(`${API_BASE_URL}/db/messages/search`, {
          params: { q: this.searchQuery }
        });
        this.searchResults = response.data;
      } catch (error) {
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
    async getAllMessages() {
      try {
        this.loading = true;
        const response = await axios.get(`${API_BASE_URL}/db/messages`);
        this.searchResults = response.data;
      } catch (error) {
        console.error('전체 메시지 로드 실패:', error);
      } finally {
        this.loading = false;
      }
    },

    // 페이지네이션을 위한 추가 데이터 로드
    async loadMore() {
      this.offset += this.limit;
      await this.getFromDb();
    },

    // 회원가입 처리
    async register() {
      if (this.registerPassword !== this.confirmPassword) {
        alert('비밀번호가 일치하지 않습니다');
        return;
      }
      
      try {
        const response = await axios.post(`${API_BASE_URL}/register`, {
          username: this.registerUsername,
          password: this.registerPassword
        });
        
        if (response.data.status === 'success') {
          alert('회원가입이 완료되었습니다. 로그인해주세요.');
          this.showRegister = false;
          this.registerUsername = '';
          this.registerPassword = '';
          this.confirmPassword = '';
        }
      } catch (error) {
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