"""
MongoDB async client wrapper using Motor.
Sets up Time Series collections and TTL auto-expiry.
"""

import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import CollectionInvalid

from config import config
from .schema import COLLECTION_TELEMETRY, FIELD_TIMESTAMP, FIELD_DEVICE_ID

logger = logging.getLogger(__name__)


class MongoDBManager:
    """Manages async MongoDB connection and collection initialization."""

    def __init__(self):
        self._client: Optional[AsyncIOMotorClient] = None
        self._db = None

    async def initialize(self) -> None:
        """Connect to MongoDB and ensure Time Series collections exist."""
        try:
            # Connect
            self._client = AsyncIOMotorClient(
                config.MONGO_URI,
                serverSelectionTimeoutMS=5000
            )
            # Verify connection
            await self._client.admin.command('ping')
            self._db = self._client[config.MONGO_DB]
            
            logger.info(f"MongoDB connected: {config.MONGO_URI} (db: {config.MONGO_DB})")

            # Initialize collections
            await self._ensure_timeseries_collections()

        except Exception as e:
            logger.error(f"Failed to initialize MongoDB: {e}")
            raise

    async def _ensure_timeseries_collections(self) -> None:
        """
        Create a MongoDB Time Series collection for telemetry if it doesn't exist.
        Native support for efficient time-series storage and TTL expiration.
        """
        existing_collections = await self._db.list_collection_names()

        if COLLECTION_TELEMETRY not in existing_collections:
            logger.info(f"Creating Time Series collection: {COLLECTION_TELEMETRY}")
            try:
                # Create native time-series collection
                await self._db.create_collection(
                    COLLECTION_TELEMETRY,
                    timeseries={
                        "timeField": FIELD_TIMESTAMP,
                        "metaField": FIELD_DEVICE_ID,
                        "granularity": "seconds"
                    },
                    expireAfterSeconds=config.MONGO_TTL_SECONDS
                )
                logger.info(
                    f"Time Series collection '{COLLECTION_TELEMETRY}' created with "
                    f"TTL {config.MONGO_TTL_SECONDS}s"
                )
            except CollectionInvalid as e:
                logger.warning(f"Could not create Time Series collection: {e}")
        else:
            logger.debug(f"Collection '{COLLECTION_TELEMETRY}' already exists.")

            # Ensure TTL index is set (in case collection was created manually without TTL)
            # On MongoDB 5.0+ time-series collections, we can run collMod to update expireAfterSeconds
            try:
                await self._db.command({
                    "collMod": COLLECTION_TELEMETRY,
                    "expireAfterSeconds": config.MONGO_TTL_SECONDS
                })
                logger.debug(f"Ensured TTL is {config.MONGO_TTL_SECONDS}s for '{COLLECTION_TELEMETRY}'")
            except Exception as e:
                logger.warning(f"Failed to update TTL for '{COLLECTION_TELEMETRY}': {e}")

    @property
    def db(self):
        """Get the AsyncIOMotorDatabase instance."""
        if self._db is None:
            raise RuntimeError("MongoDB not initialized")
        return self._db

    def close(self) -> None:
        """Close the connection."""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed")
