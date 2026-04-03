"""
Telemetry Worker
Kafka consumer that writes telemetry data to MongoDB with TTL auto-expiry
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class TelemetryWorker:
    """Consumes from Kafka iot.telemetry and writes to MongoDB"""
    
    def __init__(
        self, 
        kafka_bootstrap: str = "kafka:9092",
        mongodb_uri: str = "mongodb://localhost:27017",
        retention_days: int = 30
    ):
        self.kafka_bootstrap = kafka_bootstrap
        self.mongodb_uri = mongodb_uri
        self.retention_days = retention_days
        self.kafka_consumer = None
        self.mongodb_client = None
    
    async def initialize(self):
        """Initialize Kafka consumer and MongoDB connection"""
        try:
            from aiokafka import AIOKafkaConsumer
            from motor.motor_asyncio import AsyncIOMotorClient
            
            # Initialize Kafka consumer
            self.kafka_consumer = AIOKafkaConsumer(
                'iot.telemetry',
                bootstrap_servers=self.kafka_bootstrap,
                group_id='telemetry-worker',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='earliest',
                enable_auto_commit=True
            )
            await self.kafka_consumer.start()
            logger.info(f"Kafka consumer connected to {self.kafka_bootstrap}")
            
            # Initialize MongoDB connection
            self.mongodb_client = AsyncIOMotorClient(self.mongodb_uri)
            db = self.mongodb_client.iot_platform
            
            # Create TTL index on telemetry collection
            telemetry_col = db.telemetry
            await telemetry_col.create_index(
                "expires_at",
                expireAfterSeconds=0
            )
            
            # Create query index
            await telemetry_col.create_index([
                ("group_id", 1),
                ("device_id", 1),
                ("sensor_type", 1),
                ("timestamp", -1)
            ])
            
            logger.info("MongoDB indexes created")
        
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            raise
    
    async def start(self):
        """Start consuming and writing telemetry"""
        await self.initialize()
        
        try:
            async for message in self.kafka_consumer:
                await self.process_telemetry(message.value)
        
        except Exception as e:
            logger.error(f"Consumer error: {e}")
        finally:
            await self.kafka_consumer.stop()
            if self.mongodb_client:
                self.mongodb_client.close()
    
    async def process_telemetry(self, telemetry_msg: dict):
        """Process and store telemetry message"""
        try:
            db = self.mongodb_client.iot_platform
            telemetry_col = db.telemetry
            device_state_col = db.device_state
            
            group_id = telemetry_msg.get('group_id')
            device_id = telemetry_msg.get('device_id')
            topic = telemetry_msg.get('topic')
            data = telemetry_msg.get('data')
            timestamp = telemetry_msg.get('timestamp', datetime.utcnow().isoformat())
            
            # Parse timestamp
            if isinstance(timestamp, str):
                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                ts = datetime.utcnow()
            
            # Extract sensor type from topic
            topic_parts = topic.split('/')
            sensor_type = topic_parts[-1] if len(topic_parts) > 0 else "unknown"
            
            # Try to parse data as JSON
            try:
                value = json.loads(data) if isinstance(data, str) else data
            except:
                value = data
            
            # Create telemetry document with TTL
            expires_at = ts + timedelta(days=self.retention_days)
            
            telemetry_doc = {
                "group_id": group_id,
                "device_id": device_id,
                "sensor_type": sensor_type,
                "value": value,
                "timestamp": ts,
                "expires_at": expires_at,
                "created_at": datetime.utcnow()
            }
            
            # Insert into telemetry collection
            await telemetry_col.insert_one(telemetry_doc)
            logger.info(f"Stored telemetry: {group_id}/{device_id}/{sensor_type}")
            
            # Update device_state
            device_state_id = f"{group_id}:{device_id}"
            
            update_doc = {
                "$set": {
                    f"{sensor_type}": value,
                    "last_updated": ts,
                    "group_id": group_id,
                    "device_id": device_id
                }
            }
            
            await device_state_col.update_one(
                {"_id": device_state_id},
                update_doc,
                upsert=True
            )
            
            logger.info(f"Updated device state: {device_state_id}")
        
        except Exception as e:
            logger.error(f"Error processing telemetry: {e}")


async def main():
    """Main entry point"""
    kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    retention_days = int(os.getenv("TELEMETRY_RETENTION_DAYS", 30))
    
    worker = TelemetryWorker(
        kafka_bootstrap=kafka_bootstrap,
        mongodb_uri=mongodb_uri,
        retention_days=retention_days
    )
    
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
