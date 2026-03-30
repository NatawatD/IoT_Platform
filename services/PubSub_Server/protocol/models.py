"""
Pydantic models for each message type's JSON payload.

⚠️ LIBRARY DESIGN: These models define the payload contract. The Arduino C++
library must produce/consume JSON matching these schemas.
"""

from pydantic import BaseModel, Field
from typing import Any, Optional


# ── CONNECT (0x01) ──────────────────────────────────────────────────────────

class ConnectPayload(BaseModel):
    """Sent by device to authenticate with the broker."""
    device_id: str = Field(..., description="Device identifier (e.g., 'ESP32_01')")
    token: str = Field(..., description="Authentication token provided by the backend")
    secret: str = Field(..., description="Device secret for 3-part auth")
    client_version: Optional[str] = Field(
        default="1.0",
        description="Protocol tracking version"
    )


# ── CONNACK (0x02) ──────────────────────────────────────────────────────────

class ConnackPayload(BaseModel):
    """Sent by broker in response to CONNECT."""
    status: str = Field(..., description="'ok' or 'error'")
    reason: Optional[str] = Field(
        default=None,
        description="Error reason, e.g. 'invalid_token' (only when status='error')"
    )


# ── PUBLISH (0x03) ──────────────────────────────────────────────────────────

class PublishPayload(BaseModel):
    """Publish a message to a topic. Used in both directions."""
    topic: str = Field(..., description="Topic path, e.g. 'devices/ESP32_01/telemetry'")
    payload: Any = Field(..., description="Message payload (any JSON value)")


# ── PUBACK (0x04) ───────────────────────────────────────────────────────────

class PubAckPayload(BaseModel):
    """Acknowledgement of a published message."""
    topic: str = Field(..., description="Topic that was published to")
    status: str = Field(default="ok", description="'ok' or 'error'")


# ── SUBSCRIBE (0x05) ────────────────────────────────────────────────────────

class SubscribePayload(BaseModel):
    """Subscribe to a topic pattern (supports '#' wildcard)."""
    topic: str = Field(
        ...,
        description="Topic pattern, e.g. 'devices/ESP32_01/commands/#'"
    )


# ── SUBACK (0x06) ──────────────────────────────────────────────────────────

class SubAckPayload(BaseModel):
    """Acknowledgement of a subscription."""
    topic: str = Field(..., description="Topic pattern that was subscribed to")
    status: str = Field(default="ok", description="'ok' or 'error'")


# ── UNSUBSCRIBE (0x07) ──────────────────────────────────────────────────────

class UnsubscribePayload(BaseModel):
    """Unsubscribe from a topic."""
    topic: str = Field(..., description="Topic to unsubscribe from")


# ── UNSUBACK (0x08) ─────────────────────────────────────────────────────────

class UnsubAckPayload(BaseModel):
    """Acknowledgement of an unsubscription."""
    topic: str = Field(..., description="Topic that was unsubscribed from")
    status: str = Field(default="ok", description="'ok' or 'error'")


# ── Telemetry payload (convenience model for broker/consumer use) ───────────

class TelemetryData(BaseModel):
    """
    Default sensor fields for weather station telemetry.
    Based on ET WEATHER PM2.5/H/T sensor. Subject to change per Wilfred.
    """
    device_id: str
    temperature: Optional[float] = Field(default=None, description="°C")
    humidity: Optional[float] = Field(default=None, description="%")
    pm25: Optional[float] = Field(default=None, description="µg/m³")
    timestamp: Optional[int] = Field(
        default=None,
        description="Unix epoch milliseconds (device or server receive time)"
    )
