"""
Kafka producer — sends messages from the broker to Kafka topics.

Flow: Device → TCP Broker → Kafka Producer → Kafka Topic
"""

import json
import logging
import time
from typing import Any, Optional

from aiokafka import AIOKafkaProducer

from config import config
from .topics import TOPIC_TELEMETRY, TOPIC_DEVICE_STATUS, TOPIC_COMMANDS

logger = logging.getLogger(__name__)


class KafkaMessageProducer:
    """Async-friendly Kafka producer for the broker using aiokafka."""

    def __init__(self):
        self._producer: Optional[AIOKafkaProducer] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the Kafka producer asynchronously."""
        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
                client_id="iot-broker-producer",
                acks="all"
            )
            await self._producer.start()
            self._initialized = True
            
            logger.info(
                f"Kafka producer connected to {config.KAFKA_BOOTSTRAP_SERVERS}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            self._initialized = False

    async def send_message(
        self, topic: str, payload: Any, device_id: str
    ) -> None:
        """
        Route a published message to the appropriate Kafka topic.
        """
        if not self._initialized or not self._producer:
            logger.warning("Kafka producer not initialized — message dropped")
            return

        # Determine Kafka topic based on MQTT-style topic path
        if topic.endswith("/telemetry"):
            kafka_topic = TOPIC_TELEMETRY
        elif topic.endswith("/status"):
            kafka_topic = TOPIC_DEVICE_STATUS
        elif "commands/response" in topic:
            kafka_topic = TOPIC_DEVICE_STATUS
        else:
            kafka_topic = TOPIC_TELEMETRY  # default fallback

        message = {
            "device_id": device_id,
            "topic": topic,
            "payload": payload,
            "timestamp": int(time.time() * 1000),
        }

        try:
            await self._producer.send_and_wait(
                kafka_topic,
                key=device_id.encode("utf-8"),
                value=json.dumps(message).encode("utf-8")
            )
            logger.debug(f"Kafka message delivered to {kafka_topic}")
        except Exception as e:
            logger.error(f"Kafka produce error: {e}")

    async def send_status(self, device_id: str, status: str) -> None:
        """Send a device status event (online/offline) to Kafka."""
        if not self._initialized or not self._producer:
            return

        message = {
            "device_id": device_id,
            "status": status,
            "timestamp": int(time.time() * 1000),
        }

        try:
            await self._producer.send_and_wait(
                TOPIC_DEVICE_STATUS,
                key=device_id.encode("utf-8"),
                value=json.dumps(message).encode("utf-8")
            )
        except Exception as e:
            logger.error(f"Kafka status produce error: {e}")

    async def close(self) -> None:
        """Close the producer gracefully."""
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer closed")
