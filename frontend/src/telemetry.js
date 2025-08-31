import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { Resource } from '@opentelemetry/resources';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { DocumentLoadInstrumentation } from '@opentelemetry/instrumentation-document-load';
import { UserInteractionInstrumentation } from '@opentelemetry/instrumentation-user-interaction';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';

class FrontendTelemetry {
    constructor() {
        this.provider = null;
        this.tracer = null;
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
            console.log('🏷️ Service Name: yejun-frontend');

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
}

// 전역 인스턴스 생성
const frontendTelemetry = new FrontendTelemetry();

export default frontendTelemetry;
