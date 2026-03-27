"""
IoT Platform — Main Entrypoint
================================
Starts all services:
1. TCP Broker (custom binary protocol)
2. Kafka producer (from broker)
3. Kafka consumer for telemetry → MongoDB
4. Kafka consumer for commands → broker → device
5. FastAPI query API
"""

import asyncio
import logging
import signal
import sys
import threading

import uvicorn

from config import config
from broker.server import BrokerServer
from kafka_bridge.producer import KafkaMessageProducer
from kafka_bridge.consumer import KafkaTopicConsumer
from kafka_bridge.topics import TOPIC_TELEMETRY, TOPIC_COMMANDS
from mongodb_layer.client import MongoDBManager
from mongodb_layer.writer import TelemetryWriter
from api.app import create_app
from protocol.frames import encode_frame
from protocol.constants import MessageType

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


async def route_command_to_device(broker: BrokerServer, message: dict) -> None:
    """
    Handle a command message from Kafka and route it to the target device
    through the broker.

    Expected message format:
    {
        "device_id": "ESP32_01",
        "topic": "devices/ESP32_01/commands/set_interval",
        "payload": {"interval": 5}
    }
    """
    device_id = message.get("device_id")
    topic = message.get("topic")
    payload = message.get("payload")

    if not device_id or not topic:
        logger.warning("Command message missing device_id or topic")
        return

    conn = broker.get_connection(device_id)
    if not conn:
        logger.warning(f"Device '{device_id}' not connected — command dropped")
        return

    try:
        frame = encode_frame(
            MessageType.PUBLISH,
            {"topic": topic, "payload": payload},
        )
        conn.writer.write(frame)
        await conn.writer.drain()
        logger.info(f"Command routed to '{device_id}' on topic '{topic}'")
    except Exception as e:
        logger.error(f"Error routing command to '{device_id}': {e}")


async def main():
    """Main entry point — start all services."""
    logger.info("=" * 60)
    logger.info("  IoT Platform PubSub Server Starting")
    logger.info("=" * 60)

    # ── 1. Initialize MongoDB ─────────────────────────────────────────────
    mongo_manager = MongoDBManager()
    try:
        await mongo_manager.initialize()
    except Exception as e:
        logger.error(f"MongoDB initialization failed: {e}")
        logger.warning("Continuing without MongoDB (telemetry storage disabled)")
        mongo_manager = None

    # ── 2. Initialize Kafka producer ──────────────────────────────────────
    kafka_producer = KafkaMessageProducer()
    try:
        await kafka_producer.initialize()
    except Exception as e:
        logger.error(f"Kafka producer initialization failed: {e}")
        logger.warning("Continuing without Kafka (message routing disabled)")
        kafka_producer = None

    # ── 3. Initialize broker ─────────────────────────────────────────────
    broker = BrokerServer()
    if kafka_producer:
        broker.kafka_producer = kafka_producer

    # ── 4. Start Kafka consumers ─────────────────────────────────────────
    telemetry_consumer = None
    commands_consumer = None

    if mongo_manager and kafka_producer:
        # Telemetry consumer → MongoDB
        writer = TelemetryWriter(mongo_manager)
        telemetry_consumer = KafkaTopicConsumer(
            topics=[TOPIC_TELEMETRY],
            group_id=f"{config.KAFKA_CONSUMER_GROUP}-telemetry",
            handler=writer.handle_telemetry_message,
            name="telemetry-writer",
        )
        telemetry_consumer.start()

    if kafka_producer:
        # Commands consumer → broker → device
        async def command_handler(msg):
            await route_command_to_device(broker, msg)

        commands_consumer = KafkaTopicConsumer(
            topics=[TOPIC_COMMANDS],
            group_id=f"{config.KAFKA_CONSUMER_GROUP}-commands",
            handler=command_handler,
            name="command-router",
        )
        commands_consumer.start()

    # ── 5. Start FastAPI in background thread ────────────────────────────
    app = create_app(mongo_manager)
    api_config = uvicorn.Config(
        app,
        host=config.API_HOST,
        port=config.API_PORT,
        log_level="info",
    )
    api_server = uvicorn.Server(api_config)
    api_thread = threading.Thread(target=api_server.run, daemon=True)
    api_thread.start()
    logger.info(f"📊 Query API running on http://{config.API_HOST}:{config.API_PORT}")

    # ── 6. Start broker (blocks) ─────────────────────────────────────────
    try:
        await broker.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Cleanup
        logger.info("Stopping services...")

        if telemetry_consumer:
            await telemetry_consumer.stop()
        if commands_consumer:
            await commands_consumer.stop()

        await broker.stop()

        if kafka_producer:
            await kafka_producer.close()
        if mongo_manager:
            mongo_manager.close()

        api_server.should_exit = True

        logger.info("All services stopped. Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
