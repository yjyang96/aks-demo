import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { Resource } from '@opentelemetry/resources';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { DocumentLoadInstrumentation } from '@opentelemetry/instrumentation-document-load';
import { UserInteractionInstrumentation } from '@opentelemetry/instrumentation-user-interaction';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';
import { metrics } from '@opentelemetry/api';

class FrontendTelemetry {
    constructor() {
        this.provider = null;
        this.tracer = null;
        this.meter = null;
        this.isInitialized = false;
    }

    init() {
        if (this.isInitialized) {
            console.warn('OpenTelemetry가 이미 초기화되었습니다.');
            return;
        }

        try {
            // 리소스 설정
            const resource = new Resource({
                [SemanticResourceAttributes.SERVICE_NAME]: 'yejun-frontend',
                [SemanticResourceAttributes.SERVICE_VERSION]: '1.0.0',
                [SemanticResourceAttributes.DEPLOYMENT_ENVIRONMENT]: 'development'
            });

            // Tracer Provider 설정
            this.provider = new WebTracerProvider({
                resource: resource
            });

            // OTLP Exporter 설정 (LGTM Tempo)
            const otlpExporter = new OTLPTraceExporter({
                url: 'http://collector.lgtm.20.249.154.255.nip.io/v1/traces',
                headers: {}
            });

            // Span Processor 설정
            this.provider.addSpanProcessor(new BatchSpanProcessor(otlpExporter));

            // Tracer 설정 - 서비스 이름과 일치시킴
            this.tracer = this.provider.getTracer('yejun-frontend');
            
            // Meter 설정 (Metrics용)
            this.meter = metrics.getMeter('yejun-frontend');

            // 자동 계측 설정
            registerInstrumentations({
                instrumentations: [
                    new DocumentLoadInstrumentation(),
                    new UserInteractionInstrumentation(),
                    new FetchInstrumentation({
                        // API 호출에 대한 커스텀 속성 추가
                        applyCustomAttributesOnSpan: (span, request) => {
                            // 백엔드 API 호출인 경우 특별한 속성 추가
                            if (request.url.includes('/api/') || request.url.includes('localhost:5000')) {
                                span.setAttribute('app.type', 'api_call');
                                span.setAttribute('app.component', 'frontend');
                            }
                        }
                    })
                ]
            });

            this.isInitialized = true;
            console.log('✅ Frontend OpenTelemetry가 초기화되었습니다.');
            console.log('🔗 Trace Endpoint: http://collector.lgtm.20.249.154.255.nip.io/v1/traces');
            console.log('📊 Metrics Endpoint: http://collector.lgtm.20.249.154.255.nip.io/v1/metrics');
            console.log('📝 Logs Endpoint: http://collector.lgtm.20.249.154.255.nip.io/v1/logs');
            console.log('🏷️ Service Name: yejun-frontend');
            
            // 테스트용 메트릭 전송
            setTimeout(() => {
                this.recordMetric('yejun_frontend_test_metric_total', 1, { test: 'initialization' });
            }, 1000);

        } catch (error) {
            console.error('❌ Frontend OpenTelemetry 초기화 오류:', error);
        }
    }

    getTracer() {
        if (!this.isInitialized) {
            console.warn('OpenTelemetry가 초기화되지 않았습니다. init()을 먼저 호출하세요.');
            return null;
        }
        return this.tracer;
    }

    getMeter() {
        if (!this.isInitialized) {
            console.warn('OpenTelemetry가 초기화되지 않았습니다. init()을 먼저 호출하세요.');
            return null;
        }
        return this.meter;
    }

    createSpan(name, attributes = {}) {
        const tracer = this.getTracer();
        if (!tracer) return null;

        return tracer.startSpan(name, {
            attributes: {
                'app.component': 'frontend',
                ...attributes
            }
        });
    }

    // Vue 컴포넌트 생명주기 추적
    trackComponentLifecycle(componentName, lifecycle) {
        const span = this.createSpan(`vue.${lifecycle}`, {
            'vue.component': componentName,
            'vue.lifecycle': lifecycle
        });

        if (span) {
            span.end();
        }
    }

    // 사용자 액션 추적
    trackUserAction(action, details = {}) {
        console.log('📊 Tracking user action:', action, details);
        const span = this.createSpan('user.action', {
            'user.action': action,
            'user.details': JSON.stringify(details)
        });

        if (span) {
            console.log('✅ User action span created:', span.name);
            span.end();
        } else {
            console.warn('❌ Failed to create user action span');
        }
    }

    // API 호출 추적
    trackApiCall(method, url, status, duration) {
        const span = this.createSpan('api.call', {
            'http.method': method,
            'http.url': url,
            'http.status_code': status,
            'http.duration_ms': duration
        });

        if (span) {
            span.end();
        }
    }

    // 오류 추적
    trackError(error, context = {}) {
        const span = this.createSpan('error', {
            'error.type': error.name || 'Error',
            'error.message': error.message,
            'error.stack': error.stack,
            'error.context': JSON.stringify(context)
        });

        if (span) {
            span.setStatus({ code: 2 }); // ERROR
            span.end();
        }
    }

    // 메트릭 기록 (별도 endpoint로 전송)
    async recordMetric(name, value, attributes = {}) {
        try {
            console.log('📊 Recording metric:', name, value, attributes);
            
            const metricType = this.getMetricType(name);
            const metricData = {
                resourceMetrics: [{
                    resource: {
                        attributes: [
                            { key: "service.name", value: { stringValue: "yejun-frontend" } },
                            { key: "service.version", value: { stringValue: "1.0.0" } },
                            { key: "deployment.environment", value: { stringValue: "development" } }
                        ]
                    },
                    scopeMetrics: [{
                        scope: { name: "yejun-frontend", version: "1.0.0" },
                        metrics: [{
                            name: name,
                            description: `Metric for ${name}`,
                            unit: this.getMetricUnit(name),
                            [metricType]: {
                                dataPoints: [{
                                    timeUnixNano: (Date.now() * 1000000).toString(),
                                    value: metricType === 'gauge' ? { asDouble: value } : { asInt: Math.floor(value) },
                                    attributes: Object.keys(attributes).map(function(key) {
                                        return {
                                            key: key,
                                            value: { stringValue: String(attributes[key]) }
                                        };
                                    })
                                }],
                                isMonotonic: metricType === 'counter',
                                aggregationTemporality: 2  // CUMULATIVE
                            }
                        }]
                    }]
                }]
            };

            // 디버깅: 전송할 데이터 로그
            console.log('📤 Sending metric data:', JSON.stringify(metricData, null, 2));
            
            // /v1/metrics endpoint로 전송
            const response = await fetch('http://collector.lgtm.20.249.154.255.nip.io/v1/metrics', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(metricData)
            });
            
            if (response.ok) {
                const responseText = await response.text();
                console.log('✅ Metric sent to /v1/metrics:', name, value, metricType);
                console.log('📥 Response:', responseText);
            } else {
                const responseText = await response.text();
                console.warn('⚠️ Metric sent but response not ok:', response.status, response.statusText);
                console.warn('📥 Error response:', responseText);
            }
        } catch (error) {
            console.warn('❌ Failed to record metric:', error);
        }
    }

    // 메트릭 타입 판별
    getMetricType(name) {
        if (name.includes('_total') || name.includes('_count') || name.includes('_errors_total') || name.includes('_failures_total')) {
            return 'counter';
        } else {
            return 'gauge';
        }
    }

    // 메트릭 단위 판별
    getMetricUnit(name) {
        if (name.includes('_duration') || name.includes('_time')) {
            return 'ms';
        } else if (name.includes('_total') || name.includes('_count')) {
            return '1';
        } else {
            return '1';
        }
    }

    // 로그 기록 (별도 endpoint로 전송)
    async log(message, level = 'info', attributes = {}) {
        try {
            console.log('📝 Logging:', level, message, attributes);
            
            // 브라우저 콘솔에 로그 출력
            const logEntry = {
                timestamp: new Date().toISOString(),
                level: level,
                message: message,
                service: 'yejun-frontend',
                attributes: attributes
            };
            
            // 로그 레벨에 따른 콘솔 출력
            switch (level.toLowerCase()) {
                case 'error':
                    console.error('🔴 [ERROR]', logEntry);
                    break;
                case 'warn':
                    console.warn('🟡 [WARN]', logEntry);
                    break;
                case 'debug':
                    console.debug('🔵 [DEBUG]', logEntry);
                    break;
                default:
                    console.info('🟢 [INFO]', logEntry);
            }
            
            const logData = {
                resourceLogs: [{
                    resource: {
                        attributes: [
                            { key: "service.name", value: { stringValue: "yejun-frontend" } },
                            { key: "service.version", value: { stringValue: "1.0.0" } }
                        ]
                    },
                    scopeLogs: [{
                        scope: { name: "yejun-frontend" },
                        logRecords: [{
                            timeUnixNano: (Date.now() * 1000000).toString(),
                            severityText: level.toUpperCase(),
                            severityNumber: this.getSeverityNumber(level),
                            body: { stringValue: message },
                            attributes: Object.keys(attributes).map(function(key) {
                                return {
                                    key: key,
                                    value: { stringValue: String(attributes[key]) }
                                };
                            })
                        }]
                    }]
                }]
            };

            // /v1/logs endpoint로 전송
            await fetch('http://collector.lgtm.20.249.154.255.nip.io/v1/logs', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(logData)
            });
            
            console.log('✅ Log sent to /v1/logs:', level, message);
        } catch (error) {
            console.warn('❌ Failed to log:', error);
        }
    }

    // 로그 심각도 번호 반환
    getSeverityNumber(level) {
        switch (level.toLowerCase()) {
            case 'trace': return 1;
            case 'debug': return 5;
            case 'info': return 9;
            case 'warn': return 13;
            case 'error': return 17;
            case 'fatal': return 21;
            default: return 9;
        }
    }

    // 성능 메트릭 기록
    async recordPerformanceMetric(name, duration, attributes = {}) {
        await this.recordHistogramMetric(`yejun_frontend_${name}_duration_ms`, duration, attributes);
        await this.recordMetric(`yejun_frontend_${name}_total`, 1, attributes);
    }

    // Histogram 메트릭 기록 (별도 처리)
    async recordHistogramMetric(name, value, attributes = {}) {
        try {
            console.log('📊 Recording histogram metric:', name, value, attributes);
            
            const metricData = {
                resourceMetrics: [{
                    resource: {
                        attributes: [
                            { key: "service.name", value: { stringValue: "yejun-frontend" } },
                            { key: "service.version", value: { stringValue: "1.0.0" } },
                            { key: "deployment.environment", value: { stringValue: "development" } }
                        ]
                    },
                    scopeMetrics: [{
                        scope: { name: "yejun-frontend", version: "1.0.0" },
                        metrics: [{
                            name: name,
                            description: `Histogram for ${name}`,
                            unit: 'ms',
                            histogram: {
                                dataPoints: [{
                                    timeUnixNano: (Date.now() * 1000000).toString(),
                                    count: 1,
                                    sum: value,
                                    min: value,
                                    max: value,
                                    bucketCounts: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1], // 간단한 버킷
                                    bounds: [0, 10, 50, 100, 200, 500, 1000, 2000, 5000, 10000],
                                    attributes: Object.keys(attributes).map(function(key) {
                                        return {
                                            key: key,
                                            value: { stringValue: String(attributes[key]) }
                                        };
                                    })
                                }]
                            }
                        }]
                    }]
                }]
            };

            const response = await fetch('http://collector.lgtm.20.249.154.255.nip.io/v1/metrics', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(metricData)
            });
            
            if (response.ok) {
                console.log('✅ Histogram metric sent:', name, value);
            } else {
                console.warn('⚠️ Histogram metric sent but response not ok:', response.status);
            }
        } catch (error) {
            console.warn('❌ Failed to record histogram metric:', error);
        }
    }

    // 사용자 액션 메트릭
    async recordUserActionMetric(action, attributes = {}) {
        const metricAttributes = Object.assign({ action: action }, attributes);
        await this.recordMetric('yejun_frontend_user_actions_total', 1, metricAttributes);
    }

    // API 호출 메트릭
    async recordApiCallMetric(method, url, status, duration, attributes = {}) {
        const metricAttributes = Object.assign({ 
            method: method, 
            url: url, 
            status: status 
        }, attributes);
        
        await this.recordMetric('yejun_frontend_api_calls_total', 1, metricAttributes);
        await this.recordHistogramMetric('yejun_frontend_api_call_duration_ms', duration, metricAttributes);
    }
}

// 전역 인스턴스 생성
const frontendTelemetry = new FrontendTelemetry();

export default frontendTelemetry;
