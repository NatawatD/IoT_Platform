"""
Global configuration loaded from environment variables.
"""

import os


class Config:
    """Platform configuration from environment variables with sensible defaults."""

    # ── Broker ───────────────────────────────────────────────────────────────
    BROKER_HOST: str = os.getenv("BROKER_HOST", "0.0.0.0")
    BROKER_PORT: int = int(os.getenv("BROKER_PORT", "1883"))  # Changed to MQTT default per Peem's diagram

    # ── Kafka ────────────────────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_CONSUMER_GROUP: str = os.getenv("KAFKA_CONSUMER_GROUP", "iot-platform")

    # ── MongoDB ──────────────────────────────────────────────────────────────
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://admin:admin12345@localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "iot-platform")
    MONGO_COLLECTION_TELEMETRY: str = os.getenv("MONGO_COLLECTION_TELEMETRY", "telemetry")
    MONGO_TTL_SECONDS: int = int(os.getenv("MONGO_TTL_SECONDS", "2592000"))  # 30 days Default TTL

    # ── Auth (backend API for token verification) ────────────────────────────
    # Peem's backend endpoint — stubbed until confirmed
    AUTH_VERIFY_URL: str = os.getenv(
        "AUTH_VERIFY_URL",
        "http://localhost:8081/api/internal/verify-device"
    )
    AUTH_TIMEOUT: int = int(os.getenv("AUTH_TIMEOUT", "5"))

    # ── Query API ────────────────────────────────────────────────────────────
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8080"))

    # ── Logging ──────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


config = Config()
