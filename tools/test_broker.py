import json
import os
import socket
import struct
import time

HOST = os.getenv("BROKER_HOST", "127.0.0.1")
PORT = int(os.getenv("BROKER_PORT", "1883"))
DEVICE_ID = os.getenv("DEVICE_ID", "dev_aa6682a7f2")
TOKEN = os.getenv(
    "DEVICE_TOKEN",
    "741066dff74c9bcdf8fb0ddea24feb28de73959ed5954b098c6212396bb64fea",
)
SECRET = os.getenv(
    "DEVICE_SECRET",
    "162f11fdc9cce577910cfc2ab859fae0eb7abf0745529273115ee8c9bdd02a63",
)


def encode_frame(msg_type: int, payload: dict | None = None) -> bytes:
    if payload is None:
        header = struct.pack("!BBH", msg_type, 0x00, 0)
        return header
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    header = struct.pack("!BBH", msg_type, 0x00, len(payload_bytes))
    return header + payload_bytes


def read_frame(sock: socket.socket) -> tuple[int, dict]:
    header = sock.recv(4)
    if len(header) < 4:
        raise RuntimeError("Connection closed")
    msg_type, _flags, length = struct.unpack("!BBH", header)
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            raise RuntimeError("Connection closed")
        payload += chunk
    data = json.loads(payload.decode("utf-8")) if payload else {}
    return msg_type, data


def main() -> None:
    with socket.create_connection((HOST, PORT), timeout=10) as sock:
        # CONNECT
        connect_payload = {
            "device_id": DEVICE_ID,
            "token": TOKEN,
            "secret": SECRET,
            "client_version": "1.0",
        }
        sock.sendall(encode_frame(0x01, connect_payload))
        msg_type, payload = read_frame(sock)
        print("CONNACK", msg_type, payload)
        if payload.get("status") != "ok":
            print("Auth failed. Ensure device exists in backend and credentials match.")
            return

        # SUBSCRIBE to commands
        sub_payload = {"topic": f"devices/{DEVICE_ID}/commands/#"}
        sock.sendall(encode_frame(0x05, sub_payload))
        msg_type, payload = read_frame(sock)
        print("SUBACK", msg_type, payload)

        # PUBLISH telemetry
        telemetry_payload = {
            "topic": f"devices/{DEVICE_ID}/telemetry",
            "payload": {
                "temperature": 25.3,
                "humidity": 60.1,
                "timestamp": int(time.time() * 1000),
            },
        }
        sock.sendall(encode_frame(0x03, telemetry_payload))
        print("PUBLISH telemetry sent")

        # PINGREQ
        sock.sendall(encode_frame(0x09, None))
        try:
            msg_type, payload = read_frame(sock)
            print("PINGRESP", msg_type, payload)
        except Exception:
            print("PINGRESP not received (connection closed)")
            return

        # wait briefly for any incoming commands
        sock.settimeout(2)
        try:
            msg_type, payload = read_frame(sock)
            print("INCOMING", msg_type, payload)
        except Exception:
            pass

        # DISCONNECT
        sock.sendall(encode_frame(0x0B, None))
        print("DISCONNECT sent")


if __name__ == "__main__":
    main()
