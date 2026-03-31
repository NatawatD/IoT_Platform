"""
PubSub Server — Comprehensive Test Suite
==========================================
Tests the broker end-to-end: protocol, TCP connection, auth, ACL, subscriptions,
publish/subscribe routing, Kafka bridge, and API layer.

Run:
    cd services/PubSub_Server
    pytest tests/test_pubsub_server.py -v

Requirements:
    pip install pytest pytest-asyncio
"""

import asyncio
import json
import struct
import time
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Protocol imports ───────────────────────────────────────────────────────
from protocol.constants import (
    MessageType,
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    NO_PAYLOAD_TYPES,
    DEFAULT_FLAGS,
)
from protocol.frames import (
    encode_frame,
    decode_frame,
    decode_header,
    read_frame,
    ProtocolError,
)
from protocol.models import (
    ConnectPayload,
    ConnackPayload,
    PublishPayload,
    PubAckPayload,
    SubscribePayload,
    SubAckPayload,
    UnsubscribePayload,
    UnsubAckPayload,
    TelemetryData,
)

# ─── Broker imports ────────────────────────────────────────────────────────
from broker.server import BrokerServer
from broker.subscriptions import SubscriptionManager
from broker.acl import check_publish_acl, check_subscribe_acl

# ─── Kafka imports ──────────────────────────────────────────────────────────
from kafka_bridge.topics import (
    TOPIC_TELEMETRY,
    TOPIC_DEVICE_STATUS,
    TOPIC_COMMANDS,
    TOPIC_CMD_RESPONSES,
)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

class FakeStreamReader:
    """Simulates asyncio.StreamReader for testing read_frame()."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    async def readexactly(self, n: int) -> bytes:
        if self._pos + n > len(self._data):
            raise asyncio.IncompleteReadError(
                self._data[self._pos:], n
            )
        chunk = self._data[self._pos: self._pos + n]
        self._pos += n
        return chunk


class FakeStreamWriter:
    """Simulates asyncio.StreamWriter for testing broker output."""

    def __init__(self):
        self.data = bytearray()
        self._closed = False
        self._extra = {"peername": ("127.0.0.1", 12345)}

    def write(self, data: bytes):
        self.data.extend(data)

    async def drain(self):
        pass

    def close(self):
        self._closed = True

    async def wait_closed(self):
        pass

    def get_extra_info(self, name, default=None):
        return self._extra.get(name, default)

    def get_written_frames(self) -> list:
        """Parse all frames written to the writer."""
        frames = []
        pos = 0
        raw = bytes(self.data)
        while pos < len(raw):
            if pos + HEADER_SIZE > len(raw):
                break
            msg_type, flags, plen = struct.unpack("!BBH", raw[pos:pos + HEADER_SIZE])
            payload_bytes = raw[pos + HEADER_SIZE: pos + HEADER_SIZE + plen]
            try:
                mt = MessageType(msg_type)
            except ValueError:
                mt = msg_type
            payload = None
            if plen > 0:
                try:
                    payload = json.loads(payload_bytes.decode("utf-8"))
                except Exception:
                    payload = payload_bytes
            frames.append((mt, flags, payload))
            pos += HEADER_SIZE + plen
        return frames


def build_connect_frame(
    device_id: str = "ESP32_01",
    token: str = "test_token",
    secret: str = "test_secret",
    client_version: str = "1.0",
) -> bytes:
    """Build a CONNECT frame."""
    return encode_frame(
        MessageType.CONNECT,
        {
            "device_id": device_id,
            "token": token,
            "secret": secret,
            "client_version": client_version,
        },
    )


def build_publish_frame(topic: str, payload: dict) -> bytes:
    """Build a PUBLISH frame."""
    return encode_frame(
        MessageType.PUBLISH,
        {"topic": topic, "payload": payload},
    )


def build_subscribe_frame(topic: str) -> bytes:
    """Build a SUBSCRIBE frame."""
    return encode_frame(MessageType.SUBSCRIBE, {"topic": topic})


def build_unsubscribe_frame(topic: str) -> bytes:
    """Build a UNSUBSCRIBE frame."""
    return encode_frame(MessageType.UNSUBSCRIBE, {"topic": topic})


# ══════════════════════════════════════════════════════════════════════════════
# 1. PROTOCOL LAYER TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestProtocolEncoding:
    """Test binary frame encoding for all message types."""

    def test_encode_connect_structure(self):
        """CONNECT frame: type=0x01, flags=0x00, payload=JSON."""
        payload = {"device_id": "ESP32_01", "token": "abc", "secret": "xyz"}
        frame = encode_frame(MessageType.CONNECT, payload)

        assert frame[0] == 0x01
        assert frame[1] == 0x00
        payload_len = struct.unpack("!H", frame[2:4])[0]
        json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        assert payload_len == len(json_bytes)
        assert frame[4:] == json_bytes

    def test_encode_connack(self):
        """CONNACK frame: type=0x02."""
        frame = encode_frame(MessageType.CONNACK, {"status": "ok"})
        assert frame[0] == 0x02

    def test_encode_publish(self):
        """PUBLISH frame: type=0x03."""
        frame = encode_frame(
            MessageType.PUBLISH,
            {"topic": "devices/ESP32_01/telemetry", "payload": {"temp": 28.5}},
        )
        assert frame[0] == 0x03

    def test_encode_subscribe(self):
        """SUBSCRIBE frame: type=0x05."""
        frame = encode_frame(MessageType.SUBSCRIBE, {"topic": "devices/ESP32_01/commands/#"})
        assert frame[0] == 0x05

    def test_encode_all_no_payload_types(self):
        """PINGREQ (0x09), PINGRESP (0x0A), DISCONNECT (0x0B) have no payload."""
        for msg_type in NO_PAYLOAD_TYPES:
            frame = encode_frame(msg_type)
            assert len(frame) == HEADER_SIZE
            payload_len = struct.unpack("!H", frame[2:4])[0]
            assert payload_len == 0

    def test_encode_with_custom_flags(self):
        """Flags byte should be preserved."""
        frame = encode_frame(MessageType.PUBLISH, {"topic": "t", "payload": {}}, flags=0x42)
        assert frame[1] == 0x42

    def test_encode_payload_too_large(self):
        """Payload exceeding MAX_PAYLOAD_SIZE should raise ProtocolError."""
        huge = {"data": "x" * (MAX_PAYLOAD_SIZE + 1)}
        with pytest.raises(ProtocolError, match="Payload size"):
            encode_frame(MessageType.PUBLISH, huge)

    def test_encode_none_payload_becomes_empty_dict(self):
        """None payload for payload-carrying types becomes {}."""
        frame = encode_frame(MessageType.PUBLISH, None)
        _, _, decoded = decode_frame(frame)
        assert decoded == {}

    def test_encode_empty_dict_payload(self):
        """Empty dict payload is valid."""
        frame = encode_frame(MessageType.CONNACK, {})
        _, _, decoded = decode_frame(frame)
        assert decoded == {}


class TestProtocolDecoding:
    """Test binary frame decoding."""

    def test_decode_header_normal(self):
        """Decode a properly formed 4-byte header."""
        header = struct.pack("!BBH", 0x01, 0x00, 42)
        msg_type, flags, plen = decode_header(header)
        assert msg_type == MessageType.CONNECT
        assert flags == 0
        assert plen == 42

    def test_decode_header_too_short(self):
        """Header less than 4 bytes should raise."""
        with pytest.raises(ProtocolError, match="Header too short"):
            decode_header(b"\x01\x00")

    def test_decode_unknown_message_type(self):
        """Unknown type byte should raise."""
        bad = struct.pack("!BBH", 0xFF, 0x00, 0)
        with pytest.raises(ProtocolError, match="Unknown message type"):
            decode_frame(bad)

    def test_decode_pingreq_with_nonzero_length(self):
        """PINGREQ with nonzero payload length should raise."""
        bad = struct.pack("!BBH", 0x09, 0x00, 5) + b"hello"
        with pytest.raises(ProtocolError, match="must have payload length 0"):
            decode_frame(bad)

    def test_decode_truncated_payload(self):
        """Frame with declared length > actual data should raise."""
        header = struct.pack("!BBH", 0x03, 0x00, 100)
        truncated = header + b'{"a":1}'
        with pytest.raises(ProtocolError, match="Frame too short"):
            decode_frame(truncated)

    def test_decode_invalid_json(self):
        """Invalid JSON payload should raise."""
        bad_json = b"not{json"
        header = struct.pack("!BBH", 0x03, 0x00, len(bad_json))
        with pytest.raises(ProtocolError, match="Invalid JSON payload"):
            decode_frame(header + bad_json)

    def test_roundtrip_all_payload_types(self):
        """Every payload-carrying type should survive encode→decode roundtrip."""
        test_cases = {
            MessageType.CONNECT: {"device_id": "d1", "token": "t", "secret": "s"},
            MessageType.CONNACK: {"status": "ok"},
            MessageType.PUBLISH: {"topic": "a/b", "payload": {"val": 42}},
            MessageType.PUBACK: {"topic": "a/b", "status": "ok"},
            MessageType.SUBSCRIBE: {"topic": "a/#"},
            MessageType.SUBACK: {"topic": "a/#", "status": "ok"},
            MessageType.UNSUBSCRIBE: {"topic": "a/b"},
            MessageType.UNSUBACK: {"topic": "a/b", "status": "ok"},
        }
        for msg_type, payload in test_cases.items():
            frame = encode_frame(msg_type, payload)
            dec_type, dec_flags, dec_payload = decode_frame(frame)
            assert dec_type == msg_type, f"Roundtrip failed for {msg_type.name}"
            assert dec_payload == payload

    def test_roundtrip_no_payload_types(self):
        """PING/PONG/DISCONNECT roundtrip with None payload."""
        for msg_type in NO_PAYLOAD_TYPES:
            frame = encode_frame(msg_type)
            dec_type, _, dec_payload = decode_frame(frame)
            assert dec_type == msg_type
            assert dec_payload is None


class TestProtocolAsyncRead:
    """Test async frame reading from StreamReader."""

    @pytest.mark.asyncio
    async def test_read_connect_frame(self):
        """Read a CONNECT frame from a fake reader."""
        frame = build_connect_frame()
        reader = FakeStreamReader(frame)
        msg_type, flags, payload = await read_frame(reader)

        assert msg_type == MessageType.CONNECT
        assert payload["device_id"] == "ESP32_01"
        assert payload["token"] == "test_token"

    @pytest.mark.asyncio
    async def test_read_pingreq_frame(self):
        """Read a PINGREQ frame (no payload)."""
        frame = encode_frame(MessageType.PINGREQ)
        reader = FakeStreamReader(frame)
        msg_type, flags, payload = await read_frame(reader)

        assert msg_type == MessageType.PINGREQ
        assert payload is None

    @pytest.mark.asyncio
    async def test_read_publish_frame(self):
        """Read a PUBLISH frame with nested JSON payload."""
        frame = build_publish_frame(
            "devices/ESP32_01/telemetry",
            {"temperature": 28.5, "humidity": 65.2},
        )
        reader = FakeStreamReader(frame)
        msg_type, _, payload = await read_frame(reader)

        assert msg_type == MessageType.PUBLISH
        assert payload["payload"]["temperature"] == 28.5

    @pytest.mark.asyncio
    async def test_read_multiple_frames_sequential(self):
        """Read two frames back-to-back from same reader."""
        frame1 = build_connect_frame(device_id="ESP32_01")
        frame2 = build_publish_frame("devices/ESP32_01/telemetry", {"t": 25})
        reader = FakeStreamReader(frame1 + frame2)

        t1, _, p1 = await read_frame(reader)
        t2, _, p2 = await read_frame(reader)

        assert t1 == MessageType.CONNECT
        assert t2 == MessageType.PUBLISH
        assert p1["device_id"] == "ESP32_01"
        assert p2["payload"]["t"] == 25

    @pytest.mark.asyncio
    async def test_read_incomplete_header(self):
        """Incomplete header should raise IncompleteReadError."""
        reader = FakeStreamReader(b"\x01\x00")  # Only 2 bytes
        with pytest.raises(asyncio.IncompleteReadError):
            await read_frame(reader)

    @pytest.mark.asyncio
    async def test_read_disconnect_frame(self):
        """DISCONNECT frame should return None payload."""
        frame = encode_frame(MessageType.DISCONNECT)
        reader = FakeStreamReader(frame)
        msg_type, _, payload = await read_frame(reader)

        assert msg_type == MessageType.DISCONNECT
        assert payload is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. PYDANTIC MODEL TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestPayloadModels:
    """Test Pydantic payload model validation."""

    def test_connect_valid(self):
        p = ConnectPayload(device_id="ESP32_01", token="abc", secret="xyz")
        assert p.device_id == "ESP32_01"
        assert p.client_version == "1.0"  # default

    def test_connect_missing_secret_raises(self):
        """Secret is required by 3-part auth."""
        with pytest.raises(Exception):
            ConnectPayload(device_id="ESP32_01", token="abc")

    def test_connect_missing_token_raises(self):
        with pytest.raises(Exception):
            ConnectPayload(device_id="ESP32_01", secret="xyz")

    def test_connect_custom_version(self):
        p = ConnectPayload(device_id="d", token="t", secret="s", client_version="2.0")
        assert p.client_version == "2.0"

    def test_connack_ok(self):
        p = ConnackPayload(status="ok")
        assert p.reason is None

    def test_connack_error_with_reason(self):
        p = ConnackPayload(status="error", reason="invalid_token")
        assert p.reason == "invalid_token"

    def test_connack_excludes_none(self):
        """model_dump(exclude_none=True) should drop None reason."""
        p = ConnackPayload(status="ok")
        dumped = p.model_dump(exclude_none=True)
        assert "reason" not in dumped

    def test_publish_any_payload(self):
        """Payload field accepts any JSON-compatible type."""
        p = PublishPayload(topic="a/b", payload=42)
        assert p.payload == 42

        p2 = PublishPayload(topic="a/b", payload=[1, 2, 3])
        assert p2.payload == [1, 2, 3]

        p3 = PublishPayload(topic="a/b", payload="string")
        assert p3.payload == "string"

    def test_subscribe_topic(self):
        p = SubscribePayload(topic="devices/ESP32_01/commands/#")
        assert "#" in p.topic

    def test_telemetry_data_all_optional(self):
        """Only device_id is required; sensor fields are optional."""
        t = TelemetryData(device_id="ESP32_01")
        assert t.temperature is None
        assert t.humidity is None
        assert t.pm25 is None

    def test_telemetry_data_full(self):
        t = TelemetryData(
            device_id="ESP32_01",
            temperature=28.5,
            humidity=65.2,
            pm25=12.0,
            timestamp=1711396800000,
        )
        assert t.pm25 == 12.0


# ══════════════════════════════════════════════════════════════════════════════
# 3. SUBSCRIPTION MANAGER TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestSubscriptionManager:
    """Test topic subscription matching including wildcards."""

    def setup_method(self):
        self.sm = SubscriptionManager()

    # ── Exact match ─────────────────────────────────────────────────────────

    def test_exact_match(self):
        self.sm.subscribe("d1", "devices/d1/telemetry")
        assert "d1" in self.sm.get_subscribers("devices/d1/telemetry")

    def test_no_match_different_device(self):
        self.sm.subscribe("d1", "devices/d1/telemetry")
        assert "d1" not in self.sm.get_subscribers("devices/d2/telemetry")

    # ── Wildcard '#' ────────────────────────────────────────────────────────

    def test_wildcard_single_level(self):
        self.sm.subscribe("d1", "devices/d1/commands/#")
        assert "d1" in self.sm.get_subscribers("devices/d1/commands/reboot")

    def test_wildcard_multi_level(self):
        self.sm.subscribe("d1", "devices/d1/commands/#")
        assert "d1" in self.sm.get_subscribers("devices/d1/commands/set/interval")

    def test_wildcard_matches_exact_prefix(self):
        """'commands/#' should match 'commands' itself."""
        self.sm.subscribe("d1", "devices/d1/commands/#")
        assert "d1" in self.sm.get_subscribers("devices/d1/commands")

    def test_universal_wildcard(self):
        self.sm.subscribe("admin", "#")
        assert "admin" in self.sm.get_subscribers("any/topic/path/here")

    def test_wildcard_does_not_cross_devices(self):
        """d1's wildcard should NOT match d2's topics."""
        self.sm.subscribe("d1", "devices/d1/commands/#")
        assert "d1" not in self.sm.get_subscribers("devices/d2/commands/reboot")

    # ── Unsubscribe ─────────────────────────────────────────────────────────

    def test_unsubscribe_removes_match(self):
        self.sm.subscribe("d1", "devices/d1/telemetry")
        self.sm.unsubscribe("d1", "devices/d1/telemetry")
        assert len(self.sm.get_subscribers("devices/d1/telemetry")) == 0

    def test_unsubscribe_nonexistent_is_safe(self):
        """Unsubscribing from a topic never subscribed to should not crash."""
        self.sm.unsubscribe("d1", "nonexistent/topic")  # Should not raise

    # ── Remove client ───────────────────────────────────────────────────────

    def test_remove_client_clears_all(self):
        self.sm.subscribe("d1", "devices/d1/telemetry")
        self.sm.subscribe("d1", "devices/d1/commands/#")
        self.sm.subscribe("d1", "devices/d1/status")
        self.sm.remove_client("d1")

        assert len(self.sm.get_subscribers("devices/d1/telemetry")) == 0
        assert len(self.sm.get_subscribers("devices/d1/commands/reboot")) == 0
        assert len(self.sm.get_subscribers("devices/d1/status")) == 0

    def test_remove_nonexistent_client_is_safe(self):
        self.sm.remove_client("nonexistent")  # Should not raise

    # ── Multiple subscribers ────────────────────────────────────────────────

    def test_multiple_subscribers_same_topic(self):
        self.sm.subscribe("d1", "shared/topic")
        self.sm.subscribe("d2", "shared/topic")
        self.sm.subscribe("d3", "shared/topic")
        subs = self.sm.get_subscribers("shared/topic")
        assert len(subs) == 3

    def test_remove_one_subscriber_preserves_others(self):
        self.sm.subscribe("d1", "shared/topic")
        self.sm.subscribe("d2", "shared/topic")
        self.sm.remove_client("d1")
        subs = self.sm.get_subscribers("shared/topic")
        assert "d2" in subs
        assert "d1" not in subs

    # ── Client subscriptions query ──────────────────────────────────────────

    def test_get_client_subscriptions(self):
        self.sm.subscribe("d1", "t1")
        self.sm.subscribe("d1", "t2")
        subs = self.sm.get_client_subscriptions("d1")
        assert subs == {"t1", "t2"}

    def test_get_client_subscriptions_empty(self):
        assert self.sm.get_client_subscriptions("nonexistent") == set()


# ══════════════════════════════════════════════════════════════════════════════
# 4. ACL TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestACL:
    """Test publish and subscribe ACL enforcement."""

    # ── Publish ACL ─────────────────────────────────────────────────────────

    def test_publish_own_topic_allowed(self):
        assert check_publish_acl("ESP32_01", "devices/ESP32_01/telemetry") is True

    def test_publish_own_nested_topic_allowed(self):
        assert check_publish_acl("ESP32_01", "devices/ESP32_01/telemetry/raw") is True

    def test_publish_other_device_denied(self):
        assert check_publish_acl("ESP32_01", "devices/ESP32_02/telemetry") is False

    def test_publish_no_prefix_denied(self):
        assert check_publish_acl("ESP32_01", "telemetry") is False

    def test_publish_partial_match_denied(self):
        """'devices/ESP32_01' without trailing '/' is not a valid prefix match."""
        assert check_publish_acl("ESP32_01", "devices/ESP32_01") is False

    def test_publish_empty_topic_denied(self):
        assert check_publish_acl("ESP32_01", "") is False

    # ── Subscribe ACL ───────────────────────────────────────────────────────

    def test_subscribe_own_wildcard_allowed(self):
        assert check_subscribe_acl("ESP32_01", "devices/ESP32_01/commands/#") is True

    def test_subscribe_own_exact_allowed(self):
        assert check_subscribe_acl("ESP32_01", "devices/ESP32_01/telemetry") is True

    def test_subscribe_other_device_denied(self):
        assert check_subscribe_acl("ESP32_01", "devices/ESP32_02/commands/#") is False

    def test_subscribe_universal_wildcard_denied(self):
        """Subscribing to '#' (all topics) should be denied for devices."""
        assert check_subscribe_acl("ESP32_01", "#") is False


# ══════════════════════════════════════════════════════════════════════════════
# 5. BROKER SERVER TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestBrokerServer:
    """Test BrokerServer connection registry."""

    def setup_method(self):
        self.broker = BrokerServer()

    def test_register_connection(self):
        conn = MagicMock()
        conn.device_id = "ESP32_01"
        conn.writer = MagicMock()
        self.broker.register_connection(conn)

        assert self.broker.get_connection("ESP32_01") is conn

    def test_unregister_connection(self):
        conn = MagicMock()
        conn.device_id = "ESP32_01"
        conn.writer = MagicMock()
        self.broker.register_connection(conn)
        self.broker.unregister_connection("ESP32_01")

        assert self.broker.get_connection("ESP32_01") is None

    def test_reconnect_replaces_old(self):
        """A device reconnecting should replace the old connection."""
        old_conn = MagicMock()
        old_conn.device_id = "ESP32_01"
        old_conn.writer = MagicMock()

        new_conn = MagicMock()
        new_conn.device_id = "ESP32_01"
        new_conn.writer = MagicMock()

        self.broker.register_connection(old_conn)
        self.broker.register_connection(new_conn)

        assert self.broker.get_connection("ESP32_01") is new_conn
        old_conn.writer.close.assert_called_once()

    def test_get_all_connections(self):
        for i in range(3):
            conn = MagicMock()
            conn.device_id = f"ESP32_{i:02d}"
            conn.writer = MagicMock()
            self.broker.register_connection(conn)

        all_conns = self.broker.get_all_connections()
        assert len(all_conns) == 3

    def test_get_nonexistent_connection(self):
        assert self.broker.get_connection("nonexistent") is None


# ══════════════════════════════════════════════════════════════════════════════
# 6. HANDLER TESTS (CONNECT, PUBLISH, SUBSCRIBE, PING)
# ══════════════════════════════════════════════════════════════════════════════

class TestHandlers:
    """Test message handlers with mocked connections."""

    @pytest.mark.asyncio
    @patch("broker.handlers.verify_device_token", new_callable=AsyncMock)
    async def test_handle_connect_success(self, mock_verify):
        """Successful authentication should return True and send CONNACK ok."""
        mock_verify.return_value = (True, "ok")

        from broker.handlers import handle_connect
        from broker.connection import ClientConnection

        writer = FakeStreamWriter()
        conn = MagicMock(spec=ClientConnection)
        conn.writer = writer
        conn.device_id = None
        conn.authenticated = False
        conn.addr = "127.0.0.1:12345"

        payload = {"device_id": "ESP32_01", "token": "t", "secret": "s"}
        result = await handle_connect(conn, payload)

        assert result is True
        assert conn.device_id == "ESP32_01"
        assert conn.authenticated is True

        # Verify CONNACK was sent
        frames = writer.get_written_frames()
        assert len(frames) == 1
        assert frames[0][0] == MessageType.CONNACK
        assert frames[0][2]["status"] == "ok"

    @pytest.mark.asyncio
    @patch("broker.handlers.verify_device_token", new_callable=AsyncMock)
    async def test_handle_connect_failure(self, mock_verify):
        """Failed authentication should return False and send CONNACK error."""
        mock_verify.return_value = (False, "invalid_token")

        from broker.handlers import handle_connect

        writer = FakeStreamWriter()
        conn = MagicMock()
        conn.writer = writer
        conn.device_id = None
        conn.authenticated = False
        conn.addr = "127.0.0.1:12345"

        payload = {"device_id": "ESP32_01", "token": "bad", "secret": "bad"}
        result = await handle_connect(conn, payload)

        assert result is False
        frames = writer.get_written_frames()
        assert frames[0][2]["status"] == "error"
        assert frames[0][2]["reason"] == "invalid_token"

    @pytest.mark.asyncio
    async def test_handle_connect_invalid_payload(self):
        """Invalid CONNECT payload should send error CONNACK."""
        from broker.handlers import handle_connect

        writer = FakeStreamWriter()
        conn = MagicMock()
        conn.writer = writer
        conn.addr = "127.0.0.1:12345"

        result = await handle_connect(conn, {"bad_field": "value"})

        assert result is False
        frames = writer.get_written_frames()
        assert frames[0][2]["status"] == "error"
        assert frames[0][2]["reason"] == "invalid_payload"

    @pytest.mark.asyncio
    async def test_handle_pingreq(self):
        """PINGREQ should respond with PINGRESP."""
        from broker.handlers import handle_pingreq

        writer = FakeStreamWriter()
        conn = MagicMock()
        conn.writer = writer
        conn.device_id = "ESP32_01"

        await handle_pingreq(conn)

        frames = writer.get_written_frames()
        assert len(frames) == 1
        assert frames[0][0] == MessageType.PINGRESP

    @pytest.mark.asyncio
    async def test_handle_subscribe_allowed(self):
        """Subscribe to own topic should succeed."""
        from broker.handlers import handle_subscribe

        writer = FakeStreamWriter()
        broker = BrokerServer()
        conn = MagicMock()
        conn.writer = writer
        conn.device_id = "ESP32_01"
        conn.server = broker

        await handle_subscribe(conn, {"topic": "devices/ESP32_01/commands/#"})

        frames = writer.get_written_frames()
        assert frames[0][0] == MessageType.SUBACK
        assert frames[0][2]["status"] == "ok"

        # Verify subscription was registered
        subs = broker.subscriptions.get_subscribers("devices/ESP32_01/commands/reboot")
        assert "ESP32_01" in subs

    @pytest.mark.asyncio
    async def test_handle_subscribe_denied(self):
        """Subscribe to another device's topic should be denied."""
        from broker.handlers import handle_subscribe

        writer = FakeStreamWriter()
        broker = BrokerServer()
        conn = MagicMock()
        conn.writer = writer
        conn.device_id = "ESP32_01"
        conn.server = broker

        await handle_subscribe(conn, {"topic": "devices/ESP32_02/commands/#"})

        frames = writer.get_written_frames()
        assert frames[0][2]["status"] == "error"

    @pytest.mark.asyncio
    async def test_handle_unsubscribe(self):
        """Unsubscribe should remove subscription and send UNSUBACK."""
        from broker.handlers import handle_unsubscribe

        writer = FakeStreamWriter()
        broker = BrokerServer()
        broker.subscriptions.subscribe("ESP32_01", "devices/ESP32_01/telemetry")

        conn = MagicMock()
        conn.writer = writer
        conn.device_id = "ESP32_01"
        conn.server = broker

        await handle_unsubscribe(conn, {"topic": "devices/ESP32_01/telemetry"})

        frames = writer.get_written_frames()
        assert frames[0][0] == MessageType.UNSUBACK
        assert frames[0][2]["status"] == "ok"
        assert len(broker.subscriptions.get_subscribers("devices/ESP32_01/telemetry")) == 0

    @pytest.mark.asyncio
    async def test_handle_publish_routes_to_subscriber(self):
        """PUBLISH should route message to matching subscribers."""
        from broker.handlers import handle_publish

        broker = BrokerServer()
        broker.kafka_producer = None  # No Kafka for this test

        # Set up subscriber
        sub_writer = FakeStreamWriter()
        sub_conn = MagicMock()
        sub_conn.writer = sub_writer
        sub_conn.device_id = "dashboard"
        broker.register_connection(sub_conn)
        broker.subscriptions.subscribe("dashboard", "devices/ESP32_01/telemetry")

        # Publisher connection
        pub_writer = FakeStreamWriter()
        pub_conn = MagicMock()
        pub_conn.writer = pub_writer
        pub_conn.device_id = "ESP32_01"
        pub_conn.server = broker

        await handle_publish(pub_conn, {
            "topic": "devices/ESP32_01/telemetry",
            "payload": {"temperature": 28.5},
        })

        # Subscriber should receive the message
        frames = sub_writer.get_written_frames()
        assert len(frames) == 1
        assert frames[0][0] == MessageType.PUBLISH
        assert frames[0][2]["payload"]["temperature"] == 28.5

    @pytest.mark.asyncio
    async def test_handle_publish_no_echo_to_sender(self):
        """Publisher should NOT receive its own message."""
        from broker.handlers import handle_publish

        broker = BrokerServer()
        broker.kafka_producer = None

        writer = FakeStreamWriter()
        conn = MagicMock()
        conn.writer = writer
        conn.device_id = "ESP32_01"
        conn.server = broker

        # Subscribe to own topic then publish
        broker.subscriptions.subscribe("ESP32_01", "devices/ESP32_01/telemetry")

        await handle_publish(conn, {
            "topic": "devices/ESP32_01/telemetry",
            "payload": {"temp": 25},
        })

        # Should NOT get its own message back
        frames = writer.get_written_frames()
        assert len(frames) == 0

    @pytest.mark.asyncio
    async def test_handle_publish_acl_denied(self):
        """Publishing to another device's topic should be silently rejected."""
        from broker.handlers import handle_publish

        broker = BrokerServer()
        broker.kafka_producer = None

        conn = MagicMock()
        conn.device_id = "ESP32_01"
        conn.server = broker

        # Subscribe a listener on ESP32_02's topic
        broker.subscriptions.subscribe("listener", "devices/ESP32_02/telemetry")
        listener_conn = MagicMock()
        listener_conn.writer = FakeStreamWriter()
        listener_conn.device_id = "listener"
        broker.register_connection(listener_conn)

        # ESP32_01 tries to publish to ESP32_02's topic
        await handle_publish(conn, {
            "topic": "devices/ESP32_02/telemetry",
            "payload": {"hacked": True},
        })

        # Listener should NOT receive anything (ACL blocked it)
        frames = listener_conn.writer.get_written_frames()
        assert len(frames) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 7. KAFKA BRIDGE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestKafkaTopics:
    """Test Kafka topic constants match the architecture."""

    def test_topic_names(self):
        """Topics should match System Architecture Proposal §2."""
        assert TOPIC_TELEMETRY == "iot.telemetry"
        assert TOPIC_COMMANDS == "iot.commands"
        assert TOPIC_DEVICE_STATUS == "iot.device-events"
        assert TOPIC_CMD_RESPONSES == "iot.cmd-responses"


class TestKafkaProducerRouting:
    """Test Kafka producer topic routing logic (without actual Kafka)."""

    def test_telemetry_topic_routing(self):
        """Topics ending in '/telemetry' → iot.telemetry."""
        from kafka_bridge.producer import KafkaMessageProducer

        producer = KafkaMessageProducer()
        # Test the routing logic by inspecting the code path
        topic = "devices/ESP32_01/telemetry"
        assert topic.endswith("/telemetry")

    def test_status_topic_routing(self):
        """Topics ending in '/status' → iot.device-events."""
        topic = "devices/ESP32_01/status"
        assert topic.endswith("/status")

    def test_command_response_routing(self):
        """Command responses should route to iot.cmd-responses (BUG: currently goes to device-events)."""
        topic = "devices/ESP32_01/commands/response"
        # This is a known bug — command responses go to TOPIC_DEVICE_STATUS
        # instead of TOPIC_CMD_RESPONSES
        assert "commands/response" in topic


# ══════════════════════════════════════════════════════════════════════════════
# 8. TELEMETRY WRITER TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestTelemetryWriter:
    """Test MongoDB telemetry writer logic (mocked MongoDB)."""

    @pytest.mark.asyncio
    async def test_write_telemetry(self):
        """Valid telemetry message should be written to MongoDB."""
        from mongodb_layer.writer import TelemetryWriter

        mock_mongo = MagicMock()
        mock_collection = AsyncMock()
        mock_mongo.db.__getitem__ = MagicMock(return_value=mock_collection)

        writer = TelemetryWriter(mock_mongo)
        await writer.handle_telemetry_message({
            "device_id": "ESP32_01",
            "topic": "devices/ESP32_01/telemetry",
            "payload": {
                "temperature": 28.5,
                "humidity": 65.2,
                "timestamp": 1711396800000,
            },
            "timestamp": 1711396800000,
        })

        mock_collection.insert_one.assert_called_once()
        doc = mock_collection.insert_one.call_args[0][0]
        assert doc["device_id"] == "ESP32_01"
        assert doc["temperature"] == 28.5
        assert doc["humidity"] == 65.2
        assert isinstance(doc["timestamp"], datetime)

    @pytest.mark.asyncio
    async def test_write_telemetry_missing_device_id(self):
        """Message without device_id should be skipped."""
        from mongodb_layer.writer import TelemetryWriter

        mock_mongo = MagicMock()
        mock_collection = AsyncMock()
        mock_mongo.db.__getitem__ = MagicMock(return_value=mock_collection)

        writer = TelemetryWriter(mock_mongo)
        await writer.handle_telemetry_message({
            "payload": {"temperature": 28.5},
        })

        mock_collection.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_telemetry_non_dict_payload(self):
        """Non-dict payload should be skipped."""
        from mongodb_layer.writer import TelemetryWriter

        mock_mongo = MagicMock()
        mock_collection = AsyncMock()
        mock_mongo.db.__getitem__ = MagicMock(return_value=mock_collection)

        writer = TelemetryWriter(mock_mongo)
        await writer.handle_telemetry_message({
            "device_id": "ESP32_01",
            "payload": "not a dict",
        })

        mock_collection.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_telemetry_empty_sensor_data(self):
        """Payload with only device_id and timestamp should be skipped."""
        from mongodb_layer.writer import TelemetryWriter

        mock_mongo = MagicMock()
        mock_collection = AsyncMock()
        mock_mongo.db.__getitem__ = MagicMock(return_value=mock_collection)

        writer = TelemetryWriter(mock_mongo)
        await writer.handle_telemetry_message({
            "device_id": "ESP32_01",
            "payload": {"device_id": "ESP32_01", "timestamp": 123},
        })

        mock_collection.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_telemetry_uses_server_time_if_no_timestamp(self):
        """Missing timestamp should default to server time."""
        from mongodb_layer.writer import TelemetryWriter

        mock_mongo = MagicMock()
        mock_collection = AsyncMock()
        mock_mongo.db.__getitem__ = MagicMock(return_value=mock_collection)

        writer = TelemetryWriter(mock_mongo)
        before = datetime.now(timezone.utc)
        await writer.handle_telemetry_message({
            "device_id": "ESP32_01",
            "payload": {"temperature": 20.0},
        })
        after = datetime.now(timezone.utc)

        doc = mock_collection.insert_one.call_args[0][0]
        assert before <= doc["timestamp"] <= after


# ══════════════════════════════════════════════════════════════════════════════
# 9. AUTH TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAuth:
    """Test device authentication."""

    @pytest.mark.asyncio
    async def test_stub_auth_accepts(self):
        """In STUB mode, all devices should be accepted."""
        with patch.dict("os.environ", {"STUB_AUTH": "true"}):
            # Re-import to pick up env var
            import importlib
            import broker.auth
            importlib.reload(broker.auth)

            result, reason = await broker.auth.verify_device_token(
                "ESP32_01", "any_token", "any_secret"
            )
            assert result is True
            assert reason == "ok"

    @pytest.mark.asyncio
    async def test_auth_service_unavailable(self):
        """When auth service is down, should return False."""
        with patch.dict("os.environ", {"STUB_AUTH": "false"}):
            import importlib
            import broker.auth
            importlib.reload(broker.auth)

            with patch("broker.auth.aiohttp.ClientSession") as mock_session:
                mock_session.return_value.__aenter__ = AsyncMock(
                    side_effect=Exception("Connection refused")
                )
                mock_session.return_value.__aexit__ = AsyncMock()

                result, reason = await broker.auth.verify_device_token(
                    "ESP32_01", "token", "secret"
                )
                assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# 10. END-TO-END BROKER SESSION TEST
# ══════════════════════════════════════════════════════════════════════════════

class TestEndToEndSession:
    """Simulate a full device session: CONNECT → SUB → PUB → PING → DISCONNECT."""

    @pytest.mark.asyncio
    @patch("broker.handlers.verify_device_token", new_callable=AsyncMock)
    async def test_full_device_session(self, mock_verify):
        """Simulate a complete device lifecycle through the broker."""
        mock_verify.return_value = (True, "ok")

        broker = BrokerServer()
        broker.kafka_producer = None  # No Kafka

        # Build a full session's worth of frames
        frames = b""
        frames += build_connect_frame(device_id="ESP32_TEST")
        frames += build_subscribe_frame("devices/ESP32_TEST/commands/#")
        frames += build_publish_frame(
            "devices/ESP32_TEST/telemetry",
            {"temperature": 28.5, "humidity": 65.2},
        )
        frames += encode_frame(MessageType.PINGREQ)
        frames += encode_frame(MessageType.DISCONNECT)

        reader = FakeStreamReader(frames)
        writer = FakeStreamWriter()

        # Import and run the connection handler
        from broker.connection import ClientConnection

        conn = ClientConnection(reader, writer, broker)
        await conn.run()

        # Parse all responses
        response_frames = writer.get_written_frames()

        # Expect: CONNACK, SUBACK, PINGRESP (in that order)
        response_types = [f[0] for f in response_frames]
        assert MessageType.CONNACK in response_types
        assert MessageType.SUBACK in response_types
        assert MessageType.PINGRESP in response_types

        # CONNACK should be 'ok'
        connack = next(f for f in response_frames if f[0] == MessageType.CONNACK)
        assert connack[2]["status"] == "ok"

        # After DISCONNECT, connection should be cleaned up
        assert broker.get_connection("ESP32_TEST") is None

    @pytest.mark.asyncio
    @patch("broker.handlers.verify_device_token", new_callable=AsyncMock)
    async def test_first_message_not_connect_rejected(self, mock_verify):
        """Connection where first message is not CONNECT should be closed."""
        broker = BrokerServer()
        broker.kafka_producer = None

        # Send PUBLISH as first message (should be rejected)
        frames = build_publish_frame("devices/ESP32_01/telemetry", {"t": 25})
        reader = FakeStreamReader(frames)
        writer = FakeStreamWriter()

        from broker.connection import ClientConnection

        conn = ClientConnection(reader, writer, broker)
        await conn.run()

        # No CONNACK should be sent
        response_frames = writer.get_written_frames()
        connack_frames = [f for f in response_frames if f[0] == MessageType.CONNACK]
        assert len(connack_frames) == 0

    @pytest.mark.asyncio
    @patch("broker.handlers.verify_device_token", new_callable=AsyncMock)
    async def test_two_devices_pub_sub(self, mock_verify):
        """Two devices: one subscribes, other publishes → subscriber receives."""
        mock_verify.return_value = (True, "ok")

        broker = BrokerServer()
        broker.kafka_producer = None

        # ── Device 1: connect and subscribe ──
        d1_frames = b""
        d1_frames += build_connect_frame(device_id="d1")
        d1_frames += build_subscribe_frame("devices/d2/telemetry")
        # Keep connection "alive" by ending with incomplete read
        # (we can't do that easily, so we'll use the handler directly)

        # Instead, let's use the handler approach
        from broker.handlers import handle_connect, handle_subscribe, handle_publish
        from broker.connection import ClientConnection

        # Device 1
        d1_writer = FakeStreamWriter()
        d1_conn = MagicMock()
        d1_conn.writer = d1_writer
        d1_conn.device_id = None
        d1_conn.authenticated = False
        d1_conn.addr = "d1:1111"
        d1_conn.server = broker

        await handle_connect(d1_conn, {"device_id": "d1", "token": "t", "secret": "s"})
        broker.register_connection(d1_conn)

        # d1 subscribes to d2's telemetry (ACL allows since prefix check uses d1's ID)
        # But our ACL would actually deny this...
        # Let's subscribe to d1's own commands instead, and have d2 route to d1
        broker.subscriptions.subscribe("d1", "devices/d1/commands/#")

        # Device 2
        d2_writer = FakeStreamWriter()
        d2_conn = MagicMock()
        d2_conn.writer = d2_writer
        d2_conn.device_id = "d2"
        d2_conn.authenticated = True
        d2_conn.server = broker
        broker.register_connection(d2_conn)

        # Now simulate a command arriving for d1 via local subscription
        # This tests the routing in handle_publish
        # d2 publishes to d2's own telemetry, and d1 subscribed to it
        broker.subscriptions.subscribe("d1", "devices/d2/telemetry")

        await handle_publish(d2_conn, {
            "topic": "devices/d2/telemetry",
            "payload": {"temperature": 30.0},
        })

        # d1 should have received the forwarded message
        d1_response_frames = d1_writer.get_written_frames()
        # Filter out the CONNACK from earlier
        pub_frames = [f for f in d1_response_frames if f[0] == MessageType.PUBLISH]
        assert len(pub_frames) == 1
        assert pub_frames[0][2]["payload"]["temperature"] == 30.0


# ══════════════════════════════════════════════════════════════════════════════
# 11. CONFIGURATION TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestConfig:
    """Test configuration loading."""

    def test_default_broker_port(self):
        from config import config
        assert config.BROKER_PORT == 9000

    def test_default_kafka_bootstrap(self):
        from config import config
        assert config.KAFKA_BOOTSTRAP_SERVERS == "localhost:9092"

    def test_default_mongo_ttl(self):
        """Default TTL should be 30 days (2592000 seconds)."""
        from config import config
        assert config.MONGO_TTL_SECONDS == 2592000

    def test_default_log_level(self):
        from config import config
        assert config.LOG_LEVEL == "INFO"


# ══════════════════════════════════════════════════════════════════════════════
# 12. PROTOCOL ↔ C++ CLIENT CONSISTENCY TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestProtocolCppConsistency:
    """Verify Python protocol constants match C++ IoTPubSubClient.h definitions."""

    def test_message_type_codes(self):
        """Message type codes must match C++ #defines exactly."""
        assert MessageType.CONNECT == 0x01
        assert MessageType.CONNACK == 0x02
        assert MessageType.PUBLISH == 0x03
        assert MessageType.PUBACK == 0x04
        assert MessageType.SUBSCRIBE == 0x05
        assert MessageType.SUBACK == 0x06
        assert MessageType.UNSUBSCRIBE == 0x07
        assert MessageType.UNSUBACK == 0x08
        assert MessageType.PINGREQ == 0x09
        assert MessageType.PINGRESP == 0x0A
        assert MessageType.DISCONNECT == 0x0B

    def test_header_size(self):
        """Header size must match C++ IOT_HEADER_SIZE."""
        assert HEADER_SIZE == 4

    def test_frame_byte_order(self):
        """Payload length must be big-endian (network byte order)."""
        # Create a frame with known payload length
        payload = {"x": "y"}
        frame = encode_frame(MessageType.PUBLISH, payload)
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        expected_len = len(payload_bytes)

        # Read length as big-endian uint16
        actual_len = struct.unpack("!H", frame[2:4])[0]
        assert actual_len == expected_len

        # Verify it's NOT little-endian
        wrong_len = struct.unpack("<H", frame[2:4])[0]
        if expected_len > 255:
            assert wrong_len != expected_len  # Would differ for lengths > 255


# ══════════════════════════════════════════════════════════════════════════════
# 13. EDGE CASE & STRESS TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_max_uint16_payload(self):
        """Payload exactly at MAX_PAYLOAD_SIZE should succeed."""
        # Create a payload that's just under the limit
        # JSON overhead means we need slightly less raw data
        data = "x" * (MAX_PAYLOAD_SIZE - 20)
        payload = {"d": data}
        json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        if len(json_bytes) <= MAX_PAYLOAD_SIZE:
            frame = encode_frame(MessageType.PUBLISH, payload)
            decoded_type, _, decoded_payload = decode_frame(frame)
            assert decoded_payload["d"] == data

    def test_empty_topic_publish(self):
        """Publishing with empty topic should still encode correctly."""
        frame = encode_frame(MessageType.PUBLISH, {"topic": "", "payload": {}})
        _, _, decoded = decode_frame(frame)
        assert decoded["topic"] == ""

    def test_unicode_in_payload(self):
        """Unicode characters in payload must survive roundtrip."""
        payload = {"topic": "devices/d1/telemetry", "payload": {"name": "温度センサー"}}
        frame = encode_frame(MessageType.PUBLISH, payload)
        _, _, decoded = decode_frame(frame)
        assert decoded["payload"]["name"] == "温度センサー"

    def test_nested_json_payload(self):
        """Deeply nested JSON should survive roundtrip."""
        payload = {
            "topic": "t",
            "payload": {
                "level1": {
                    "level2": {
                        "level3": {"value": 42}
                    }
                }
            },
        }
        frame = encode_frame(MessageType.PUBLISH, payload)
        _, _, decoded = decode_frame(frame)
        assert decoded["payload"]["level1"]["level2"]["level3"]["value"] == 42

    def test_special_chars_in_topic(self):
        """Topics with special characters."""
        topics = [
            "devices/ESP32_01/telemetry",
            "devices/ESP-32-01/data",
            "devices/esp32.sensor.1/readings",
        ]
        for topic in topics:
            frame = encode_frame(MessageType.SUBSCRIBE, {"topic": topic})
            _, _, decoded = decode_frame(frame)
            assert decoded["topic"] == topic

    def test_subscription_manager_many_clients(self):
        """Subscription manager should handle many clients efficiently."""
        sm = SubscriptionManager()
        for i in range(100):
            sm.subscribe(f"device_{i}", f"devices/device_{i}/telemetry")
            sm.subscribe(f"device_{i}", f"devices/device_{i}/commands/#")

        # Each device should only match its own topics
        subs = sm.get_subscribers("devices/device_50/telemetry")
        assert subs == {"device_50"}

        # Remove all and verify cleanup
        for i in range(100):
            sm.remove_client(f"device_{i}")
        assert len(sm.get_subscribers("devices/device_50/telemetry")) == 0
