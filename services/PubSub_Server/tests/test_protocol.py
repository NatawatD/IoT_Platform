"""
Tests for the protocol library — frame encoding/decoding and model validation.
"""

import struct
import json
import pytest

from protocol.constants import MessageType, HEADER_SIZE, NO_PAYLOAD_TYPES
from protocol.frames import encode_frame, decode_frame, decode_header, ProtocolError
from protocol.models import (
    ConnectPayload,
    ConnackPayload,
    PublishPayload,
    SubscribePayload,
    TelemetryData,
)


class TestFrameEncoding:
    """Test binary frame encoding."""

    def test_encode_connect(self):
        payload = {"device_id": "ESP32_01", "token": "abc123", "secret": "s3cr3t"}
        frame = encode_frame(MessageType.CONNECT, payload)

        assert frame[0] == 0x01  # CONNECT
        assert frame[1] == 0x00  # flags
        payload_len = struct.unpack("!H", frame[2:4])[0]
        assert payload_len == len(json.dumps(payload, separators=(",", ":")))

    def test_encode_publish(self):
        payload = {
            "topic": "devices/ESP32_01/telemetry",
            "payload": {"temperature": 28.5},
        }
        frame = encode_frame(MessageType.PUBLISH, payload)
        assert frame[0] == 0x03  # PUBLISH

    def test_encode_pingreq_no_payload(self):
        frame = encode_frame(MessageType.PINGREQ)
        assert len(frame) == HEADER_SIZE
        assert frame[0] == 0x09
        assert frame[2] == 0x00 and frame[3] == 0x00  # length = 0

    def test_encode_pingresp_no_payload(self):
        frame = encode_frame(MessageType.PINGRESP)
        assert len(frame) == HEADER_SIZE
        assert frame[0] == 0x0A

    def test_encode_disconnect_no_payload(self):
        frame = encode_frame(MessageType.DISCONNECT)
        assert len(frame) == HEADER_SIZE
        assert frame[0] == 0x0B


class TestFrameDecoding:
    """Test binary frame decoding."""

    def test_decode_connect(self):
        payload = {"device_id": "ESP32_01", "token": "secret", "secret": "s3cr3t"}
        frame = encode_frame(MessageType.CONNECT, payload)
        msg_type, flags, decoded = decode_frame(frame)

        assert msg_type == MessageType.CONNECT
        assert flags == 0x00
        assert decoded["device_id"] == "ESP32_01"
        assert decoded["token"] == "secret"
        assert decoded["secret"] == "s3cr3t"

    def test_decode_pingreq(self):
        frame = encode_frame(MessageType.PINGREQ)
        msg_type, flags, decoded = decode_frame(frame)

        assert msg_type == MessageType.PINGREQ
        assert decoded is None

    def test_decode_unknown_type(self):
        bad_frame = struct.pack("!BBH", 0xFF, 0x00, 0)
        with pytest.raises(ProtocolError, match="Unknown message type"):
            decode_frame(bad_frame)

    def test_decode_header_too_short(self):
        with pytest.raises(ProtocolError, match="Header too short"):
            decode_header(b"\x01\x00")

    def test_roundtrip_publish(self):
        original = {
            "topic": "devices/ESP32_01/telemetry",
            "payload": {"temperature": 28.5, "humidity": 65.2},
        }
        frame = encode_frame(MessageType.PUBLISH, original)
        msg_type, flags, decoded = decode_frame(frame)

        assert msg_type == MessageType.PUBLISH
        assert decoded["topic"] == original["topic"]
        assert decoded["payload"]["temperature"] == 28.5

    def test_all_message_types_roundtrip(self):
        """Every message type should survive encode-decode roundtrip."""
        payloads = {
            MessageType.CONNECT: {"device_id": "test", "token": "t", "secret": "s"},
            MessageType.CONNACK: {"status": "ok"},
            MessageType.PUBLISH: {"topic": "a/b", "payload": {}},
            MessageType.PUBACK: {"topic": "a/b", "status": "ok"},
            MessageType.SUBSCRIBE: {"topic": "a/#"},
            MessageType.SUBACK: {"topic": "a/#", "status": "ok"},
            MessageType.UNSUBSCRIBE: {"topic": "a/b"},
            MessageType.UNSUBACK: {"topic": "a/b", "status": "ok"},
        }

        for msg_type, payload in payloads.items():
            frame = encode_frame(msg_type, payload)
            decoded_type, _, decoded_payload = decode_frame(frame)
            assert decoded_type == msg_type
            assert decoded_payload == payload

        # No-payload types
        for msg_type in NO_PAYLOAD_TYPES:
            frame = encode_frame(msg_type)
            decoded_type, _, decoded_payload = decode_frame(frame)
            assert decoded_type == msg_type
            assert decoded_payload is None


class TestModels:
    """Test Pydantic payload models."""

    def test_connect_payload_valid(self):
        p = ConnectPayload(device_id="ESP32_01", token="abc", secret="s3cr3t")
        assert p.device_id == "ESP32_01"
        assert p.secret == "s3cr3t"
        assert p.client_version == "1.0"

    def test_connect_payload_missing_required(self):
        with pytest.raises(Exception):
            ConnectPayload(device_id="ESP32_01", token="abc")  # missing secret

    def test_connack_ok(self):
        p = ConnackPayload(status="ok")
        assert p.reason is None

    def test_connack_error(self):
        p = ConnackPayload(status="error", reason="invalid_token")
        assert p.reason == "invalid_token"

    def test_publish_payload(self):
        p = PublishPayload(
            topic="devices/ESP32_01/telemetry",
            payload={"temperature": 28.5},
        )
        assert p.payload["temperature"] == 28.5

    def test_telemetry_data_defaults(self):
        t = TelemetryData(device_id="ESP32_01")
        assert t.temperature is None
        assert t.humidity is None

    def test_telemetry_data_full(self):
        t = TelemetryData(
            device_id="ESP32_01",
            temperature=28.5,
            humidity=65.2,
            pm25=12.3,
            timestamp=1711396800000,
        )
        assert t.pm25 == 12.3
