"""
Protocol constants — message type codes and frame parameters.

⚠️ LIBRARY DESIGN: This file defines the wire-format constants shared between
the Python broker and the Arduino C++ client library.
"""

from enum import IntEnum


class MessageType(IntEnum):
    """
    Binary message type codes (byte 0 of every frame).
    Codes 0x01 and 0x03 were specified by Peem; the rest are proposed
    and pending Peem's confirmation.
    """

    CONNECT = 0x01       # Device → Broker: authentication request
    CONNACK = 0x02       # Broker → Device: authentication response
    PUBLISH = 0x03       # Bidirectional: publish to a topic
    PUBACK = 0x04        # Receiver → Sender: publish acknowledgement
    SUBSCRIBE = 0x05     # Device → Broker: subscribe to topic pattern
    SUBACK = 0x06        # Broker → Device: subscribe acknowledgement
    UNSUBSCRIBE = 0x07   # Device → Broker: unsubscribe from topic
    UNSUBACK = 0x08      # Broker → Device: unsubscribe acknowledgement
    PINGREQ = 0x09       # Device → Broker: keepalive ping (no payload)
    PINGRESP = 0x0A      # Broker → Device: keepalive pong (no payload)
    DISCONNECT = 0x0B    # Device → Broker: graceful disconnect (no payload)


# Frame header is always exactly 4 bytes
HEADER_SIZE = 4

# Maximum payload size: bytes 2-3 are uint16 big-endian → max 65535 bytes
MAX_PAYLOAD_SIZE = 0xFFFF

# Message types that carry no payload (payload length must be 0)
NO_PAYLOAD_TYPES = frozenset({
    MessageType.PINGREQ,
    MessageType.PINGRESP,
    MessageType.DISCONNECT,
})

# Default flags byte (reserved for future QoS)
DEFAULT_FLAGS = 0x00

# Default keepalive interval in seconds
DEFAULT_KEEPALIVE = 60

# Default broker port
DEFAULT_BROKER_PORT = 1883
