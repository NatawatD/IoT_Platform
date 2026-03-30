"""
Frame encoding/decoding for the custom binary protocol.

⚠️ LIBRARY DESIGN: Core frame logic — the Arduino C++ library implements
the same encode/decode in C++.

Frame layout:
    Byte 0: message type (MessageType enum)
    Byte 1: flags (0x00 reserved)
    Byte 2: payload length high byte (big-endian)
    Byte 3: payload length low byte (big-endian)
    Byte 4+: JSON payload (UTF-8) or empty for PING/PONG/DISCONNECT
"""

import json
import struct
from typing import Any

from .constants import (
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    DEFAULT_FLAGS,
    NO_PAYLOAD_TYPES,
    MessageType,
)


class ProtocolError(Exception):
    """Raised when a frame violates the binary protocol."""
    pass


def encode_frame(msg_type: MessageType, payload: dict | None = None, flags: int = DEFAULT_FLAGS) -> bytes:
    """
    Encode a message into a binary frame.

    Args:
        msg_type: The message type code.
        payload: JSON-serializable dict (or None for no-payload types).
        flags: Flags byte (default 0x00).

    Returns:
        bytes: The complete binary frame (header + payload).

    Raises:
        ProtocolError: If payload exceeds MAX_PAYLOAD_SIZE or type mismatch.
    """
    if msg_type in NO_PAYLOAD_TYPES:
        # No-payload messages: 4-byte header only
        return struct.pack("!BBH", int(msg_type), flags, 0)

    if payload is None:
        payload = {}

    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    if len(payload_bytes) > MAX_PAYLOAD_SIZE:
        raise ProtocolError(
            f"Payload size {len(payload_bytes)} exceeds maximum {MAX_PAYLOAD_SIZE}"
        )

    header = struct.pack("!BBH", int(msg_type), flags, len(payload_bytes))
    return header + payload_bytes


def decode_header(data: bytes) -> tuple[MessageType, int, int]:
    """
    Decode the 4-byte frame header.

    Args:
        data: At least 4 bytes of raw data.

    Returns:
        Tuple of (message_type, flags, payload_length).

    Raises:
        ProtocolError: If data is too short or message type is unknown.
    """
    if len(data) < HEADER_SIZE:
        raise ProtocolError(
            f"Header too short: got {len(data)} bytes, need {HEADER_SIZE}"
        )

    type_byte, flags, payload_length = struct.unpack("!BBH", data[:HEADER_SIZE])

    try:
        msg_type = MessageType(type_byte)
    except ValueError:
        raise ProtocolError(f"Unknown message type: 0x{type_byte:02X}")

    return msg_type, flags, payload_length


def decode_frame(data: bytes) -> tuple[MessageType, int, dict | None]:
    """
    Decode a complete binary frame (header + payload).

    Args:
        data: Complete frame bytes (header + payload).

    Returns:
        Tuple of (message_type, flags, payload_dict_or_None).

    Raises:
        ProtocolError: If frame is malformed.
    """
    msg_type, flags, payload_length = decode_header(data)

    if msg_type in NO_PAYLOAD_TYPES:
        if payload_length != 0:
            raise ProtocolError(
                f"{msg_type.name} must have payload length 0, got {payload_length}"
            )
        return msg_type, flags, None

    if len(data) < HEADER_SIZE + payload_length:
        raise ProtocolError(
            f"Frame too short: expected {HEADER_SIZE + payload_length} bytes, "
            f"got {len(data)}"
        )

    payload_bytes = data[HEADER_SIZE : HEADER_SIZE + payload_length]

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ProtocolError(f"Invalid JSON payload: {e}")

    return msg_type, flags, payload


async def read_frame(reader) -> tuple[MessageType, int, dict | None]:
    """
    Read a complete frame from an asyncio StreamReader.

    Args:
        reader: asyncio.StreamReader instance.

    Returns:
        Tuple of (message_type, flags, payload_dict_or_None).

    Raises:
        ProtocolError: If frame is malformed.
        ConnectionError: If connection is closed mid-read.
    """
    # Read 4-byte header
    header_data = await reader.readexactly(HEADER_SIZE)
    msg_type, flags, payload_length = decode_header(header_data)

    # Validate no-payload types
    if msg_type in NO_PAYLOAD_TYPES:
        if payload_length != 0:
            raise ProtocolError(
                f"{msg_type.name} must have payload length 0, got {payload_length}"
            )
        return msg_type, flags, None

    # Read payload
    if payload_length == 0:
        return msg_type, flags, {}

    payload_data = await reader.readexactly(payload_length)

    try:
        payload = json.loads(payload_data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ProtocolError(f"Invalid JSON payload: {e}")

    return msg_type, flags, payload
