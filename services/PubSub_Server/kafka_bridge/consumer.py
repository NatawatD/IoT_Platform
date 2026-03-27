"""
Kafka consumer — consumes messages from Kafka topics and processes them.

Flow: Kafka Topic → Kafka Consumer → TCP Broker → Device
      Kafka Topic → Kafka Consumer → MongoDB Writer
"""

import asyncio
import json
import logging
from typing import Callable, Awaitable, List

from aiokafka import AIOKafkaConsumer

from config import config

logger = logging.getLogger(__name__)


class KafkaTopicConsumer:
    """
    Subscribes to Kafka topics and dispatches to handler callbacks.
    Uses aiokafka natively with asyncio.
    """

    def __init__(
        self,
        topics: List[str],
        group_id: str,
        handler_callback: Callable[[dict], Awaitable[None]],
    ):
        self.topics = topics
        self.group_id = group_id
        self.handler_callback = handler_callback
        self._consumer = None
        self._running = False
        self._consume_task = None

    def start(self):
        """Start the background consumer task."""
        if self._running:
            return

        self._running = True
        self._consume_task = asyncio.create_task(self._consume_loop())
        logger.info(
            f"Kafka consumer ({self.group_id}) started listening to {self.topics}"
        )

    async def _consume_loop(self):
        """Async loop to read messages using aiokafka."""
        try:
            self._consumer = AIOKafkaConsumer(
                *self.topics,
                bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
                group_id=self.group_id,
                auto_offset_reset="latest"
            )
            
            # Start consumer
            await self._consumer.start()

            while self._running:
                # Wait for next message
                msg = await self._consumer.getone()
                if msg and msg.value:
                    try:
                        payload = json.loads(msg.value.decode("utf-8"))
                        # Pass to the async handler
                        await self.handler_callback(payload)
                    except json.JSONDecodeError:
                        logger.error(
                            f"Kafka decode error on topic {msg.topic}: {msg.value}"
                        )
                    except Exception as e:
                        logger.error(f"Kafka handler error: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Kafka consumer connection error: {e}")
        finally:
            self._running = False
            if self._consumer:
                await self._consumer.stop()
            logger.info(f"Kafka consumer ({self.group_id}) stopped")

    async def stop(self):
        """Gracefully stop the consumer."""
        self._running = False
        if self._consume_task:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass
