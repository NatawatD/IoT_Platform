"""
MongoDB writer — consumes telemetry from Kafka and writes to MongoDB.
"""

import logging
from datetime import datetime, timezone

from config import config
from .client import MongoDBManager
from .schema import COLLECTION_TELEMETRY, FIELD_TIMESTAMP, FIELD_DEVICE_ID

logger = logging.getLogger(__name__)


class TelemetryWriter:
    """
    Writes telemetry data points to MongoDB Time Series collection.
    Used as a Kafka consumer handler.
    """

    def __init__(self, mongo_manager: MongoDBManager):
        self._mongo = mongo_manager

    async def handle_telemetry_message(self, message: dict) -> None:
        """
        Handle a telemetry message from Kafka and write to MongoDB.

        Expected message format (from Kafka):
        {
            "device_id": "ESP32_01",
            "topic": "devices/ESP32_01/telemetry",
            "payload": {
                "temperature": 28.5,
                "humidity": 65.2,
                "pm25": 12.3,
                "timestamp": 1711396800000
            },
            "timestamp": 1711396800000
        }
        """
        device_id = message.get("device_id")
        payload = message.get("payload", {})

        if not device_id:
            logger.warning("Telemetry message missing device_id — skipping")
            return

        if not isinstance(payload, dict):
            logger.warning(
                f"Telemetry payload from '{device_id}' is not a dict — skipping"
            )
            return

        try:
            # Set timestamp
            ts_ms = payload.get("timestamp") or message.get("timestamp")
            if ts_ms:
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            else:
                ts = datetime.now(timezone.utc)

            # Clean payload: remove metadata from the root of the sensor data
            sensor_data = {k: v for k, v in payload.items() if k not in ("device_id", "timestamp")}

            if not sensor_data:
                logger.warning(
                    f"No valid fields in telemetry from '{device_id}' — skipping"
                )
                return

            # Construct MongoDB Time Series document
            document = {
                FIELD_TIMESTAMP: ts,
                FIELD_DEVICE_ID: device_id,  # Used as metaField
                **sensor_data
            }

            # Insert async
            await self._mongo.db[COLLECTION_TELEMETRY].insert_one(document)

            logger.debug(f"Wrote telemetry from '{device_id}' to MongoDB")

        except Exception as e:
            logger.error(
                f"Error writing telemetry from '{device_id}' to MongoDB: {e}",
                exc_info=True,
            )
