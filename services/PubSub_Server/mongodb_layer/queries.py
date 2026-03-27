"""
MongoDB queries — helper functions for fetching historical telemetry.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

from .client import MongoDBManager
from .schema import COLLECTION_TELEMETRY, FIELD_TIMESTAMP, FIELD_DEVICE_ID

logger = logging.getLogger(__name__)


async def query_device_telemetry(
    mongo: MongoDBManager,
    device_id: str,
    start_time: Optional[datetime] = None,
    stop_time: Optional[datetime] = None,
    limit: int = 1000,
) -> List[Dict]:
    """
    Query historical telemetry for a device.

    Args:
        mongo: MongoDBManager instance.
        device_id: Device ID to query.
        start_time: Start datetime (utc). Defaults to 1 hour ago.
        stop_time: Stop datetime (utc). Defaults to now.
        limit: Max number of records to return.

    Returns:
        List of dicts representing sensor readings.
    """
    if not start_time:
        start_time = datetime.now(timezone.utc) - timedelta(hours=1)
    if not stop_time:
        stop_time = datetime.now(timezone.utc)

    filter_query = {
        FIELD_DEVICE_ID: device_id,
        FIELD_TIMESTAMP: {"$gte": start_time, "$lte": stop_time}
    }

    try:
        cursor = mongo.db[COLLECTION_TELEMETRY].find(
            filter_query,
            {"_id": 0}  # Exclude Mongo Object IDs from results
        ).sort(FIELD_TIMESTAMP, -1).limit(limit)

        results = []
        async for document in cursor:
            # Convert datetime to ISO string for JSON serialization
            if FIELD_TIMESTAMP in document and isinstance(document[FIELD_TIMESTAMP], datetime):
                document[FIELD_TIMESTAMP] = document[FIELD_TIMESTAMP].isoformat()
            results.append(document)

        return results

    except Exception as e:
        logger.error(f"MongoDB query error for device '{device_id}': {e}")
        raise


async def query_latest_telemetry(
    mongo: MongoDBManager,
    device_id: str,
) -> Optional[Dict]:
    """
    Get the latest telemetry reading for a device.
    """
    filter_query = {
        FIELD_DEVICE_ID: device_id
    }

    try:
        document = await mongo.db[COLLECTION_TELEMETRY].find_one(
            filter_query,
            {"_id": 0},
            sort=[(FIELD_TIMESTAMP, -1)]
        )

        if document:
            if FIELD_TIMESTAMP in document and isinstance(document[FIELD_TIMESTAMP], datetime):
                document[FIELD_TIMESTAMP] = document[FIELD_TIMESTAMP].isoformat()
        
        return document

    except Exception as e:
        logger.error(f"MongoDB latest query error for '{device_id}': {e}")
        raise
