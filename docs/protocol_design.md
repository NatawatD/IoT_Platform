# IoT Platform — Binary Protocol Design

> **Author**: Emmanuel  
> **Status**: Draft (pending Peem confirmation on message type codes)  
> **Version**: 1.0

## 1. Overview

This platform uses a **custom binary TCP protocol** (not standard MQTT) for device-to-broker communication. The protocol is designed for simplicity, debuggability (JSON payloads), and full control over the communication layer.

## 2. Frame Format

Every TCP message consists of a **4-byte fixed header** followed by an optional **JSON payload**.

```
┌────────┬────────┬────────────┬────────────┬───────────────────┐
│ Byte 0 │ Byte 1 │  Byte 2    │  Byte 3    │ Bytes 4..N        │
│  Type  │ Flags  │ Length Hi  │ Length Lo  │ JSON Payload      │
│ (1B)   │ (1B)   │ (1B)       │ (1B)       │ (0–65535 bytes)   │
└────────┴────────┴────────────┴────────────┴───────────────────┘
```

| Field | Size | Description |
|-------|------|-------------|
| Type | 1 byte | Message type code (see table below) |
| Flags | 1 byte | Reserved (`0x00`); future use for QoS |
| Length | 2 bytes | Payload length, big-endian uint16 |
| Payload | 0–65535 bytes | UTF-8 JSON string (empty for PING/PONG/DISCONNECT) |

## 3. Message Types

| Code | Name | Direction | Has Payload |
|------|------|-----------|-------------|
| `0x01` | CONNECT | Device → Broker | ✅ |
| `0x02` | CONNACK | Broker → Device | ✅ |
| `0x03` | PUBLISH | Bidirectional | ✅ |
| `0x04` | PUBACK | Receiver → Sender | ✅ |
| `0x05` | SUBSCRIBE | Device → Broker | ✅ |
| `0x06` | SUBACK | Broker → Device | ✅ |
| `0x07` | UNSUBSCRIBE | Device → Broker | ✅ |
| `0x08` | UNSUBACK | Broker → Device | ✅ |
| `0x09` | PINGREQ | Device → Broker | ❌ |
| `0x0A` | PINGRESP | Broker → Device | ❌ |
| `0x0B` | DISCONNECT | Device → Broker | ❌ |

## 4. Payload Schemas

### CONNECT (0x01)
```json
{
  "device_id": "ESP32_01",
  "token": "auth_token_from_api",
  "secret": "my_device_secret",
  "client_version": "1.0"
}
```
- `device_id` (required): Device identifier
- `token` (required): Auth token from backend API
- `secret` (required): Device secret for 3-part auth verification
- `client_version` (optional): Protocol version

### CONNACK (0x02)
```json
{"status": "ok"}
```
or
```json
{"status": "error", "reason": "invalid_token"}
```

### PUBLISH (0x03)
```json
{
  "topic": "devices/ESP32_01/telemetry",
  "payload": {
    "temperature": 28.5,
    "humidity": 65.2,
    "pm25": 12.3,
    "timestamp": 1711396800000
  }
}
```

### SUBSCRIBE (0x05)
```json
{"topic": "devices/ESP32_01/commands/#"}
```

### SUBACK (0x06)
```json
{"topic": "devices/ESP32_01/commands/#", "status": "ok"}
```

## 5. Topic Structure


| Topic Pattern | Direction | Purpose | Kafka Mapping |
|---------------|-----------|---------|---------------|
| `devices/{id}/telemetry` | Device → Broker | Sensor data | `iot.telemetry` |
| `devices/{id}/status` | Device → Broker | Online/offline | `iot.device-events` |
| `devices/{id}/commands/#` | Broker → Device | Control commands | `iot.commands` |
| `devices/{id}/commands/response` | Device → Broker | Command ACK | `iot.cmd-responses` |

### Access Control
- Devices can only publish to `devices/{own_id}/`
- Devices can only subscribe to `devices/{own_id}/`
- Publishing to another device's topic is **silently rejected**

## 6. Session Flow Example

```
Device                              Broker
  │                                   │
  │──── TCP Connect ─────────────────▶│
  │                                   │
  │──── [0x01] CONNECT ──────────────▶│  verify token
  │◀─── [0x02] CONNACK {"ok"} ───────│
  │                                   │
  │──── [0x05] SUBSCRIBE ────────────▶│  "devices/ESP32_01/commands/#"
  │◀─── [0x06] SUBACK {"ok"} ────────│
  │                                   │
  │──── [0x03] PUBLISH ──────────────▶│  telemetry → Kafka → MongoDB
  │                                   │
  │──── [0x09] PINGREQ ─────────────▶│
  │◀─── [0x0A] PINGRESP ─────────────│
  │                                   │
  │◀─── [0x03] PUBLISH ──────────────│  command from API
  │──── [0x03] PUBLISH ──────────────▶│  command response
  │                                   │
  │──── [0x0B] DISCONNECT ───────────▶│
  │                                   │
```

## 7. Default Telemetry Fields

Based on ET WEATHER PM2.5/H/T sensor:

| Field | Type | Unit |
|-------|------|------|
| temperature | float | °C |
| humidity | float | % |
| pm25 | float | µg/m³ |
| timestamp | int64 | Unix ms |
