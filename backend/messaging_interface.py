import os
import json
from abc import ABC, abstractmethod
from datetime import datetime
from threading import Thread
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MessagingInterface(ABC):
    """메시징 시스템을 위한 추상 인터페이스"""
    
    @abstractmethod
    def send_message(self, topic, message):
        """메시지를 전송합니다."""
        pass
    
    @abstractmethod
    def get_messages(self, topic, limit=1000):
        """메시지를 조회합니다."""
        pass
    
    @abstractmethod
    def close(self):
        """연결을 종료합니다."""
        pass

class KafkaMessaging(MessagingInterface):
    """Kafka 메시징 구현"""
    
    def __init__(self):
        try:
            from kafka import KafkaProducer, KafkaConsumer
            self.KafkaProducer = KafkaProducer
            self.KafkaConsumer = KafkaConsumer
        except ImportError:
            raise ImportError("kafka-python 패키지가 설치되지 않았습니다.")
        
        self.kafka_servers = os.getenv('KAFKA_SERVERS', 'my-kafka')
        self.kafka_servers += ':9092'
        self.kafka_username = os.getenv('KAFKA_USERNAME', 'user1')
        self.kafka_password = os.getenv('KAFKA_PASSWORD', '')
        
        logger.info(f"Kafka 설정: {self.kafka_servers}")
    
    def get_producer(self):
        """Kafka Producer를 생성합니다."""
        if self.kafka_password:
            return self.KafkaProducer(
                bootstrap_servers=self.kafka_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                security_protocol='SASL_PLAINTEXT',
                sasl_mechanism='PLAIN',
                sasl_plain_username=self.kafka_username,
                sasl_plain_password=self.kafka_password
            )
        else:
            return self.KafkaProducer(
                bootstrap_servers=self.kafka_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                security_protocol='PLAINTEXT'
            )
    
    def get_consumer(self, topic):
        """Kafka Consumer를 생성합니다."""
        if self.kafka_password:
            return self.KafkaConsumer(
                topic,
                bootstrap_servers=self.kafka_servers,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                security_protocol='SASL_PLAINTEXT',
                sasl_mechanism='PLAIN',
                sasl_plain_username=self.kafka_username,
                sasl_plain_password=self.kafka_password,
                auto_offset_reset='earliest',
                consumer_timeout_ms=5000
            )
        else:
            return self.KafkaConsumer(
                topic,
                bootstrap_servers=self.kafka_servers,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                security_protocol='PLAINTEXT',
                auto_offset_reset='earliest',
                consumer_timeout_ms=5000
            )
    
    def send_message(self, topic, message):
        """Kafka에 메시지를 전송합니다."""
        try:
            producer = self.get_producer()
            future = producer.send(topic, message)
            record_metadata = future.get(timeout=10)
            logger.info(f"✅ Kafka message sent: topic={record_metadata.topic}, partition={record_metadata.partition}, offset={record_metadata.offset}")
            producer.flush()
            producer.close()
            return True
        except Exception as e:
            logger.error(f"❌ Kafka send error: {str(e)}")
            return False
    
    def get_messages(self, topic, limit=1000):
        """Kafka에서 메시지를 조회합니다."""
        try:
            consumer = self.get_consumer(topic)
            messages = []
            
            for message in consumer:
                messages.append({
                    'timestamp': message.value['timestamp'],
                    'endpoint': message.value['endpoint'],
                    'method': message.value['method'],
                    'status': message.value['status'],
                    'user_id': message.value['user_id'],
                    'message': message.value['message']
                })
                if len(messages) >= limit:
                    break
            
            consumer.close()
            return messages
        except Exception as e:
            logger.error(f"❌ Kafka receive error: {str(e)}")
            return []
    
    def close(self):
        """연결을 종료합니다."""
        pass

class EventHubMessaging(MessagingInterface):
    """Azure Event Hubs 메시징 구현"""
    
    def __init__(self):
        try:
            from azure.eventhub import EventHubProducerClient, EventHubConsumerClient
            self.EventHubProducerClient = EventHubProducerClient
            self.EventHubConsumerClient = EventHubConsumerClient
        except ImportError:
            raise ImportError("azure-eventhub 패키지가 설치되지 않았습니다.")
        
        self.connection_str = os.getenv('EVENTHUB_CONNECTION_STRING', '')
        self.eventhub_name = os.getenv('EVENTHUB_NAME', 'api-logs')
        self.consumer_group = os.getenv('EVENTHUB_CONSUMER_GROUP', '$Default')
        
        if not self.connection_str:
            logger.warning("EVENTHUB_CONNECTION_STRING 환경 변수가 설정되지 않았습니다. Event Hubs 기능이 제한됩니다.")
            # 연결 문자열이 없어도 초기화는 허용하되, 실제 사용 시 오류 발생
        
        logger.info(f"Event Hubs 설정: {self.eventhub_name}")
    
    def get_producer(self):
        """Event Hubs Producer를 생성합니다."""
        return self.EventHubProducerClient.from_connection_string(
            conn_str=self.connection_str,
            eventhub_name=self.eventhub_name
        )
    
    def get_consumer(self, topic):
        """Event Hubs Consumer를 생성합니다."""
        return self.EventHubConsumerClient.from_connection_string(
            conn_str=self.connection_str,
            consumer_group=self.consumer_group,
            eventhub_name=self.eventhub_name
        )
    
    def send_message(self, topic, message):
        """Event Hubs에 메시지를 전송합니다."""
        if not self.connection_str:
            logger.error("❌ Event Hubs 연결 문자열이 설정되지 않았습니다.")
            return False
            
        try:
            producer = self.get_producer()
            event_data_batch = producer.create_batch()
            event_data_batch.add(json.dumps(message))
            producer.send_batch(event_data_batch)
            logger.info(f"✅ Event Hubs message sent successfully")
            producer.close()
            return True
        except Exception as e:
            logger.error(f"❌ Event Hubs send error: {str(e)}")
            return False
    
    def get_messages(self, topic, limit=1000):
        """Event Hubs에서 메시지를 조회합니다."""
        if not self.connection_str:
            logger.error("❌ Event Hubs 연결 문자열이 설정되지 않았습니다.")
            return []
            
        try:
            consumer = self.get_consumer(topic)
            messages = []
            
            def on_event(partition_context, event):
                try:
                    log_data = json.loads(event.body_as_str())
                    messages.append({
                        'timestamp': log_data['timestamp'],
                        'endpoint': log_data['endpoint'],
                        'method': log_data['method'],
                        'status': log_data['status'],
                        'user_id': log_data['user_id'],
                        'message': log_data['message']
                    })
                except Exception as e:
                    logger.error(f"Event parsing error: {str(e)}")
            
            consumer.receive(
                on_event=on_event,
                track_last_enqueued_event_properties=True,
                starting_position="-1",
                max_wait_time=5
            )
            consumer.close()
            
            return messages[:limit]
        except Exception as e:
            logger.error(f"❌ Event Hubs receive error: {str(e)}")
            return []
    
    def close(self):
        """연결을 종료합니다."""
        pass

class MessagingFactory:
    """메시징 시스템 팩토리"""
    
    @staticmethod
    def create_messaging():
        """환경 변수에 따라 적절한 메시징 시스템을 생성합니다."""
        messaging_type = os.getenv('MESSAGING_TYPE', 'kafka').lower()
        
        if messaging_type == 'eventhub':
            logger.info("Event Hubs 메시징 시스템을 사용합니다.")
            return EventHubMessaging()
        elif messaging_type == 'kafka':
            logger.info("Kafka 메시징 시스템을 사용합니다.")
            return KafkaMessaging()
        else:
            raise ValueError(f"지원하지 않는 메시징 타입: {messaging_type}")

# 비동기 로깅 함수
def async_log_api_stats(endpoint, method, status, user_id):
    """API 통계를 비동기로 로깅합니다."""
    def _log():
        try:
            messaging = MessagingFactory.create_messaging()
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'endpoint': endpoint,
                'method': method,
                'status': status,
                'user_id': user_id,
                'message': f"{user_id}가 {method} {endpoint} 호출 ({status})"
            }
            
            success = messaging.send_message('api-logs', log_data)
            if success:
                logger.info(f"✅ API 로그 전송 성공: {endpoint}")
            else:
                logger.error(f"❌ API 로그 전송 실패: {endpoint}")
            
            messaging.close()
        except Exception as e:
            logger.error(f"❌ 로깅 오류: {str(e)}")
    
    # 새로운 스레드에서 로깅 실행
    Thread(target=_log).start()
