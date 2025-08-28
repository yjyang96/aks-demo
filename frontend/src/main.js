import Vue from 'vue'
import App from './App.vue'
import frontendTelemetry from './telemetry'

Vue.config.productionTip = false

// OpenTelemetry 초기화
frontendTelemetry.init()

// Vue 전역 믹스인으로 컴포넌트 생명주기 추적
Vue.mixin({
  mounted() {
    frontendTelemetry.trackComponentLifecycle(this.$options.name || 'Unknown', 'mounted')
  },
  beforeDestroy() {
    frontendTelemetry.trackComponentLifecycle(this.$options.name || 'Unknown', 'beforeDestroy')
  }
})

new Vue({
  render: h => h(App)
}).$mount('#app') 