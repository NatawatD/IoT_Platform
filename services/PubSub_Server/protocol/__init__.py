"""
IoT Platform Protocol Library (Server-Side)
============================================
⚠️ LIBRARY DESIGN DELIVERABLE — All files in this package are part of the
Library Design responsibility. This is the server-side reference implementation
of the custom binary protocol. The Arduino C++ client library (Pubsub_Client/)
mirrors this logic.

Binary Frame Format:
    [type: 1 byte][flags: 1 byte][length_hi: 1 byte][length_lo: 1 byte][payload: N bytes]

Message Types:
    0x01 CONNECT, 0x02 CONNACK, 0x03 PUBLISH, 0x04 PUBACK,
    0x05 SUBSCRIBE, 0x06 SUBACK, 0x07 UNSUBSCRIBE, 0x08 UNSUBACK,
    0x09 PINGREQ, 0x0A PINGRESP, 0x0B DISCONNECT
"""

from .constants import MessageType, HEADER_SIZE, MAX_PAYLOAD_SIZE
from .frames import encode_frame, decode_frame, decode_header
from .models import (
    ConnectPayload,
    ConnackPayload,
    PublishPayload,
    PubAckPayload,
    SubscribePayload,
    SubAckPayload,
    UnsubscribePayload,
    UnsubAckPayload,
)

__all__ = [
    "MessageType",
    "HEADER_SIZE",
    "MAX_PAYLOAD_SIZE",
    "encode_frame",
    "decode_frame",
    "decode_header",
    "ConnectPayload",
    "ConnackPayload",
    "PublishPayload",
    "PubAckPayload",
    "SubscribePayload",
    "SubAckPayload",
    "UnsubscribePayload",
    "UnsubAckPayload",
]
