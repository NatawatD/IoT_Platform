# IoT Platform — Complete System Architecture and Implementation Guide

> **What is this document?** This is the single source of truth for the entire IoT platform project. It explains every concept from scratch, covers every component in detail, includes all database schemas, API specifications, protocol definitions, and a week-by-week implementation guide. No prior context is assumed.

**Project**: Enterprise-Style IoT Platform Development (Graduate Course Project)  
**Duration**: 5 weeks  
**Version**: Final  
**Date**: March 2026

---

## Table of contents

- Part 1: What are we building?
- Part 2: The six core concepts
  - 2.1 Groups (project isolation)
  - 2.2 Device credentials (NETPIE-style, three-part)
  - 2.3 The custom PubSub broker
  - 2.4 Topic structure
  - 2.5 Data TTL (time-to-live)
  - 2.6 The PubSubClient ESP32 library
- Part 3: System components
- Part 4: The custom binary protocol
- Part 5: Data flow traces
- Part 6: Database design
- Part 7: HTTP API specification
- Part 8: Security architecture
- Part 9: Kubernetes deployment
- Part 10: CI/CD pipeline
- Part 11: Observability and monitoring
- Part 12: Project file structure
- Part 13: Week-by-week implementation guide

---

# Part 1: What are we building?

We are building a complete IoT (Internet of Things) platform from scratch. Think of it like building your own version of NETPIE, ThingsBoard, or AWS IoT Core — a system where:

- Physical sensors (ESP32 microcontrollers with weather sensors) connect to your server over the internet
- They send sensor data (temperature, humidity, pressure) to your platform
- Your platform stores that data, lets users visualize it on dashboards, and lets users send commands back to devices
- Everything is organized into isolated "groups" (like NETPIE projects)
- Users configure how long data is retained before automatic deletion

When the project is complete, a user can:

1. Create an account on your web app
2. Create a "group" (a project workspace — like NETPIE's projects)
3. Add a device to the group and receive three secret credentials (clientId, token, secret)
4. Copy those credentials into their ESP32 firmware code
5. The ESP32 boots up, connects to your platform, and starts sending temperature/humidity/pressure readings
6. The user opens a dashboard, drags in chart widgets, and sees live and historical data
7. The user sends commands to the device (e.g., "change reporting interval to 5 seconds")
8. The user configures how long data is kept (7 days, 30 days, 1 year, etc.)
9. Devices in different groups are completely isolated — they cannot see or communicate with each other

## The two halves of the system

The platform is split into two independent halves that share databases and Apache Kafka (a message queue), but have no direct dependency on each other:

**Half 1 — The broker system (handles devices)**

This is the part that ESP32 microcontrollers connect to. It consists of:
- A **broker gateway** — a TCP server that speaks a custom binary protocol with ESP32 devices
- **Apache Kafka** — a durable message queue that sits between the broker and the databases
- A **telemetry worker** — a process that consumes sensor data from Kafka and writes it to databases
- A **TTL cleanup worker** — a scheduled job that deletes expired data based on user-configured retention settings

**Half 2 — The backend app (handles humans)**

This is the part that web browsers connect to. It consists of:
- An **IoT backend** — a FastAPI web server that serves REST APIs for login, device management, dashboards, etc.
- A **web app** — a React single-page application with a drag-and-drop dashboard builder

The data flow looks like this:

```
ESP32 sensor
    | TCP connection (custom binary protocol)
    v
Broker gateway (Python asyncio, port 1883)
    | produces messages to
    v
Apache Kafka (message queue — buffers data safely)
    | consumed by                         | consumed by
    v                                     v
Telemetry worker                    TTL cleanup worker (hourly)
    |         |                     deletes expired data from
    v         v                     MongoDB
MongoDB   MongoDB                        |
(history)  (latest state)                 |
    \         |                           |
     \        |                           |
      v       v                           v
      IoT backend (FastAPI) ← reads from all three databases
          |
          | HTTP REST API
          v
      Web app (React dashboard)
          |
          v
      User's browser
```

There is one connection going the other direction: when a user clicks "send command" in the web app, the backend produces a message to Kafka's `iot.commands` topic. The broker gateway picks it up from Kafka and pushes it to the connected ESP32 device.

## Technology stack

| Component | Technology | Why this choice |
|-----------|-----------|----------------|
| Broker gateway | Python 3.12, asyncio, aiokafka | Single-threaded async handles thousands of TCP connections efficiently |
| Apache Kafka | Kafka 3.7, KRaft mode (no ZooKeeper) | Durable ordered message log with consumer groups for parallel processing |
| Telemetry worker | Python 3.12, aiokafka | Simple consume-write loop, scales by adding replicas |
| TTL cleanup worker | Python 3.12, asyncpg | Standalone script, runs as Kubernetes CronJob |
| IoT backend | Python 3.12, FastAPI, SQLAlchemy, motor | Fast async HTTP framework, ORM for PostgreSQL, async MongoDB driver |
| Web app | React, react-grid-layout | Dashboard builder with drag-and-drop widget layout |
| ESP32 library | C++ (Arduino/PlatformIO), ArduinoJson | Native TCP socket on ESP32, efficient JSON serialization |
| PostgreSQL 16 | Relational database | Users, groups, devices, credentials — needs foreign keys and transactions |
| MongoDB | Time-series database | Optimized for high-throughput sensor data writes and time-range queries |
| MongoDB 7 | Document database | Flexible-schema dashboard configs and fast device state lookups |
| Kubernetes | Container orchestration, Kustomize | Rolling deployments, health checks, scaling, namespace isolation |
| GitHub Actions + GHCR | CI/CD pipeline | Automated testing, building, scanning, and deploying |

---

# Part 2: The six core concepts

## 2.1 Groups (project isolation)

A group is the top-level isolation boundary — like a "project" in NETPIE or an "account" in AWS. Everything in the platform belongs to exactly one group.

**Example:** Alice has two projects: a smart farm and an office HVAC system. She creates two groups:

- `grp_farm_01` — "Smart Farm" (2 devices: soil sensor, weather station)
- `grp_hvac_01` — "Office HVAC" (2 devices: temp controller, air quality sensor)

Every device, dashboard, credential, topic, and piece of telemetry data belongs to exactly one group. The soil sensor in the farm group literally cannot see, message, or interact with the HVAC devices.

**How isolation is enforced at every layer:**

| Layer | How |
|-------|-----|
| Broker gateway | Every PUB/SUB message checked: topic must start with the device's own group_id |
| Kafka | Messages keyed by `{group_id}:{device_id}` — group embedded in every message |
| MongoDB | `group_id` is a tag on every data point; queries always filter by group |
| MongoDB | `group_id` is a field on every document; queries always filter |
| Backend API | Every request validated: user must own the group being accessed |
| Dashboard | Widget device validated: must belong to same group as the dashboard |

**Free tier limit:** Users can create up to 2 groups. Each group has a default device limit of 10.

**Database schema (PostgreSQL):**

```sql
CREATE TABLE groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id VARCHAR(64) UNIQUE NOT NULL,    -- Human-readable: "grp_farm_01"
    name VARCHAR(256) NOT NULL,              -- Display name: "Smart Farm"
    owner_id UUID NOT NULL REFERENCES users(id),
    tier VARCHAR(32) DEFAULT 'free',         -- free (max 2 groups), pro, enterprise
    max_devices INT DEFAULT 10,              -- Per-group device limit
    default_ttl_days INT DEFAULT 30,         -- Default data retention for devices in this group
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## 2.2 Device credentials (NETPIE-style, three-part)

When a user adds a device to a group, the server generates three secret values that look like opaque hash strings — the same pattern as NETPIE.

| Credential | What it looks like | How it is stored on the server |
|-----------|-------------------|-------------------------------|
| Client ID | `6a4f8e2b-9c1d-4b7a-a3e5-8f2d6c0b4a7e` | Plaintext (it is the lookup key, like a username) |
| Token | `d7e3f1a9b5c2084f6e8d0a4b2c9f7e1a` | SHA-256 hash (the original value is never stored) |
| Secret | `9f2a4c6e8b0d1a3c5e7f9b2d4a6c8e0f` | SHA-256 hash (the original value is never stored) |

These three values are shown to the user exactly once when the device is created. The web UI displays a panel: "Copy these credentials now — they will not be shown again." The user copies them into their ESP32 firmware.

**How credentials are generated (Python):**

```python
import uuid, secrets, hashlib

def generate_credentials():
    client_id  = str(uuid.uuid4())           # UUID v4: "6a4f8e2b-9c1d-..."
    token_raw  = secrets.token_hex(32)        # 64 random hex characters
    secret_raw = secrets.token_hex(32)        # 64 random hex characters

    # Hash for storage — original values are NEVER stored
    token_hash  = hashlib.sha256(token_raw.encode()).hexdigest()
    secret_hash = hashlib.sha256(secret_raw.encode()).hexdigest()

    return {
        "client_id": client_id,               # Stored plaintext (lookup key)
        "token": token_raw,                   # Shown to user ONCE, then discarded
        "secret": secret_raw,                 # Shown to user ONCE, then discarded
        "token_hash": token_hash,             # Stored in database
        "secret_hash": secret_hash            # Stored in database
    }
```

**Why SHA-256 instead of bcrypt?** The broker verifies credentials on every device connection (boot, reconnect, WiFi recovery). Bcrypt intentionally takes ~100ms per verification — it is designed to be slow for password cracking protection. SHA-256 takes less than 1ms. Since the tokens are 32 bytes of cryptographic randomness (256 bits of entropy), they cannot be brute-forced regardless of hash speed.

**How verification works (when ESP32 connects):**

1. ESP32 sends CONNECT with `client_id`, `token`, `secret`
2. Broker looks up `client_id` in the `device_credentials` table
3. Computes `SHA-256(received_token)`, compares with stored `token_hash`
4. Computes `SHA-256(received_secret)`, compares with stored `secret_hash`
5. Checks `is_active == true` and `expires_at` has not passed
6. On success: extracts `device_id` and `group_id` from the credential record
7. Tags the TCP session with both values
8. Sends CONNACK with `{"status":"ok","device_id":"ESP32_farm_01","group_id":"grp_farm_01"}`

**Database schema (PostgreSQL):**

```sql
CREATE TABLE device_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id),
    group_id UUID NOT NULL REFERENCES groups(id),
    client_id VARCHAR(128) UNIQUE NOT NULL,   -- Plaintext lookup key
    token_hash VARCHAR(128) NOT NULL,          -- SHA-256 hash
    secret_hash VARCHAR(128) NOT NULL,         -- SHA-256 hash
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_credentials_client ON device_credentials(client_id);
```

## 2.3 The custom PubSub broker

This is the most technically interesting part of the platform. You are building your own message broker — a server that ESP32 devices connect to via TCP.

**Why not just use an existing MQTT broker like Mosquitto?** The project requirement says to build your own. But there are real benefits: you get full control over authentication (three-part credential verification integrated directly), group isolation (enforced at the protocol level, not bolted on), and Kafka integration (no need for a separate MQTT-to-Kafka bridge).

**What the broker does:**

The broker is a Python program using `asyncio` (Python's built-in async/await system for handling thousands of simultaneous connections on a single thread). It listens on TCP port 1883.

When an ESP32 connects:

1. ESP32 opens a TCP socket to `your-server:1883`
2. ESP32 sends a CONNECT frame with `client_id`, `token`, `secret`
3. Broker verifies credentials (SHA-256 hash comparison)
4. If valid: sends CONNACK with device_id and group_id
5. Session is now authenticated — the broker knows this connection belongs to a specific device in a specific group
6. ESP32 can now publish telemetry and subscribe to commands

**When a device publishes telemetry**, instead of routing it to other devices (like a traditional MQTT broker), our broker produces the message to Apache Kafka. A separate process called the telemetry worker consumes from Kafka and writes data to databases. This decoupled design means:

- If MongoDB goes down temporarily, Kafka buffers the messages — no data is lost
- The telemetry worker can be scaled independently (more workers = more throughput)
- The broker stays focused on TCP connections and does not slow down doing database writes

**Broker internal components (all inside one Python asyncio process):**

| Component | What it does |
|-----------|-------------|
| TCP listener | `asyncio.start_server()` on port 1883, spawns one coroutine per client |
| Protocol parser | Reads 4-byte binary header, then reads the JSON payload |
| Connection manager | Tracks active sessions: socket, device_id, group_id, subscriptions, last_ping |
| Device authenticator | Verifies client_id + token + secret via backend's internal API, caches results (5 min TTL) |
| Access control | Checks every PUB: topic must start with `{own_group}/{own_device}/`. Checks every SUB: topic must start with `{own_group}/` |
| Topic mapper | Translates `grp_farm_01/ESP32_farm_01/telemetry` to Kafka topic `iot.telemetry` with key `grp_farm_01:ESP32_farm_01` |
| Kafka producer | Produces messages asynchronously. Config: acks=1, linger_ms=5, snappy compression |
| Subscription registry | Maps topic patterns to TCP sessions. Supports wildcards: `+` (one level), `#` (multi-level) |
| Subscription dispatcher | Background task consuming `iot.commands` from Kafka, pushes PUB frames to matched TCP clients |

**Kafka topics:**

| Topic | Partitions | Retention | Purpose |
|-------|-----------|-----------|---------|
| `iot.telemetry` | 6 | 7 days | Sensor data from devices |
| `iot.commands` | 3 | 1 day | Commands to devices |
| `iot.device-events` | 3 | 3 days | Device status changes |
| `iot.cmd-responses` | 3 | 1 day | Command acknowledgments |

All messages are keyed by `{group_id}:{device_id}`. Kafka hashes the key to determine the partition, so all messages from the same device land on the same partition — guaranteeing per-device ordering.

**The telemetry worker** is a standalone Python process that consumes from `iot.telemetry` and writes to two databases for every message:

1. **MongoDB** — appends a time-series data point with tags `group_id`, `device_id`, `sensor_type` and field `value`. This powers historical queries like "show me temperature for the last 24 hours."
2. **MongoDB** — upserts the latest device state document. This powers instant lookups like "what is the current temperature?"

The worker scales via Kafka consumer groups: with 6 partitions, you can run up to 6 worker replicas, each handling a subset of partitions.

## 2.4 Topic structure

Topics are hierarchical paths that organize messages. The group_id is always the first segment — this is the isolation boundary.

```
{group_id}/{device_id}/telemetry              — Sensor readings (device → platform)
{group_id}/{device_id}/status                 — Online/offline (device → platform)
{group_id}/{device_id}/commands/{cmd_type}    — Commands (platform → device)
{group_id}/{device_id}/commands/response      — Command acknowledgment (device → platform)
```

**Real examples:**

```
grp_farm_01/ESP32_farm_01/telemetry           — Farm soil sensor data
grp_farm_01/ESP32_farm_02/status              — Farm weather station status
grp_hvac_01/ESP32_hvac_01/commands/reboot     — Reboot the HVAC controller
```

**Wildcards (for subscribing):**

- `+` matches exactly one topic level: `grp_farm_01/+/telemetry` matches ALL farm devices' telemetry
- `#` matches zero or more levels: `grp_farm_01/ESP32_farm_01/commands/#` matches any command type (set_interval, reboot, set_led, etc.)

**Access control rules:**

| Action | Rule | Example |
|--------|------|---------|
| PUBLISH | Must start with `{own_group}/{own_device}/` | ESP32_farm_01 can publish to `grp_farm_01/ESP32_farm_01/telemetry` |
| SUBSCRIBE (own device) | Must start with `{own_group}/` | Can subscribe to `grp_farm_01/ESP32_farm_01/commands/#` |
| SUBSCRIBE (group-wide) | Must start with `{own_group}/` | Can subscribe to `grp_farm_01/+/telemetry` |
| Cross-group access | BLOCKED | Farm device cannot access `grp_hvac_01/*` in any way |

**How topics map to Kafka:**

| PubSub topic pattern | Kafka topic | Kafka key |
|---------------------|-------------|-----------|
| `{group}/{device}/telemetry` | `iot.telemetry` | `{group}:{device}` |
| `{group}/{device}/status` | `iot.device-events` | `{group}:{device}` |
| `{group}/{device}/commands/response` | `iot.cmd-responses` | `{group}:{device}` |

## 2.5 Data TTL (time-to-live)

Users can configure how long telemetry data is retained before automatic deletion. This is configurable at two levels:

- **Group default** — applies to all devices unless overridden (e.g., 30 days)
- **Per-device override** — a specific device can have a different TTL (e.g., 7 days for a test sensor, 365 days for a critical monitor)

The effective TTL for any device is: `device.ttl_days` if set, otherwise `group.default_ttl_days`.

**Preset options:** 7 days, 30 days, 90 days, 180 days, 365 days, or custom (any integer 1–3650).

**How TTL is enforced — the TTL cleanup worker:**

A standalone Python script runs as a Kubernetes CronJob every hour. Each run:

1. Connects to PostgreSQL, reads all device TTL configurations:
   ```sql
   SELECT d.device_id, g.group_id,
          COALESCE(d.ttl_days, g.default_ttl_days) AS effective_ttl
   FROM devices d JOIN groups g ON d.group_id = g.id
   ```
2. For each device, calculates: `cutoff = now - effective_ttl_days`
3. Deletes all MongoDB data points older than the cutoff for that device and group
4. Deletes stale MongoDB device_state documents older than the cutoff
5. Logs a summary and exits

**Why not use MongoDB's built-in retention policies?** Because retention policies apply to an entire bucket, not per-device. Since one device might have a 7-day TTL and another 365 days (both in the same `telemetry` bucket), we need application-level cleanup.

**The backend API respects TTL too:** When the web app queries historical data, the backend clamps the time range. If a device has a 7-day TTL, requesting `from=30d ago` gets automatically clamped to `from=7d ago`. The dashboard widget time range picker disables options beyond the device's TTL.

**TTL change behavior:**
- **Reducing TTL** (90d → 7d): Destructive — the next hourly cleanup deletes all data older than 7 days. The UI shows a confirmation dialog.
- **Increasing TTL** (7d → 90d): Safe — no data deleted, future data kept longer.

## 2.6 The PubSubClient ESP32 library

This is a C++ library that ESP32 firmware developers include in their Arduino/PlatformIO project. It handles all the complexity of communicating with the broker.

**What the library handles:**
- TCP connection to the broker
- The custom binary protocol (frame serialization/deserialization)
- Three-part authentication (CONNECT with clientId + token + secret)
- Auto-prepending `{group_id}/{device_id}/` to topics — the firmware developer just writes `publish("telemetry", data)` and the library handles the rest
- Keepalive: sends PING every 30 seconds, expects PONG within 10 seconds
- Auto-reconnect: if the connection drops, retries every 3 seconds and re-subscribes to all topics
- Incoming message callback for receiving commands

**API:**

```cpp
class PubSubClient {
public:
    PubSubClient(const char* host, uint16_t port = 1883);

    // Connect with NETPIE-style 3-part credentials
    bool connect(const char* clientId, const char* token, const char* secret);
    void disconnect();
    bool connected();

    // After connect, these are available from CONNACK:
    const char* deviceId();    // "ESP32_farm_01"
    const char* groupId();     // "grp_farm_01"

    // Publish — library auto-prepends {group}/{device}/
    bool publish(const char* topicSuffix, const char* payload);

    // Subscribe — library auto-prepends {group}/{device}/
    bool subscribe(const char* topicSuffix);

    void onMessage(MessageCallback callback);
    void loop();  // Call in Arduino loop() — handles everything

    PubSubClient& setKeepAlive(uint16_t seconds);
    PubSubClient& setAutoReconnect(bool enabled);
};
```

**Usage example (complete ESP32 weather station firmware):**

```cpp
#include <WiFi.h>
#include "PubSubClient.h"
#include <ArduinoJson.h>

// Credentials from the web UI (shown once when device was created)
const char* CLIENT_ID = "6a4f8e2b-9c1d-4b7a-a3e5-8f2d6c0b4a7e";
const char* TOKEN     = "d7e3f1a9b5c2084f6e8d0a4b2c9f7e1a...";
const char* SECRET    = "9f2a4c6e8b0d1a3c5e7f9b2d4a6c8e0f...";

PubSubClient client("iot-broker.example.com", 1883);
unsigned long lastReport = 0;
unsigned long reportInterval = 10000; // 10 seconds

void onCommand(const char* topic, const char* payload, uint16_t len) {
    StaticJsonDocument<256> doc;
    deserializeJson(doc, payload, len);
    const char* cmd = doc["command"];
    if (strcmp(cmd, "set_interval") == 0) {
        reportInterval = doc["params"]["interval_ms"];
    }
}

void setup() {
    Serial.begin(115200);
    WiFi.begin("YOUR_SSID", "YOUR_PASSWORD");
    while (WiFi.status() != WL_CONNECTED) delay(500);

    client.setKeepAlive(30).setAutoReconnect(true);
    client.onMessage(onCommand);
    client.connect(CLIENT_ID, TOKEN, SECRET);
    // After connect: client.deviceId() = "ESP32_farm_01"
    //                client.groupId()  = "grp_farm_01"

    client.subscribe("commands/#");
    // Auto-expands to: grp_farm_01/ESP32_farm_01/commands/#
}

void loop() {
    client.loop(); // Handles PING, incoming messages, reconnect

    if (client.connected() && millis() - lastReport >= reportInterval) {
        StaticJsonDocument<256> doc;
        doc["temperature"] = readTemperature();
        doc["humidity"] = readHumidity();
        doc["pressure"] = readPressure();

        char buf[256];
        serializeJson(doc, buf);
        client.publish("telemetry", buf);
        // Auto-expands to: grp_farm_01/ESP32_farm_01/telemetry

        lastReport = millis();
    }
}
```

---

# Part 3: System components

Here is every component, what it does, what it connects to, and how it runs:

| # | Component | Role | Inputs | Outputs | K8s workload |
|---|-----------|------|--------|---------|-------------|
| 1 | Broker gateway | TCP server for ESP32 devices | TCP connections from ESP32s | Kafka messages | StatefulSet, 2 replicas |
| 2 | Apache Kafka | Message queue backbone | Messages from broker + backend | Messages to workers + broker | StatefulSet, 3 replicas (Strimzi) |
| 3 | Telemetry worker | Writes sensor data to DBs | Kafka `iot.telemetry` | MongoDB points + MongoDB docs | Deployment, 3 replicas |
| 4 | TTL cleanup worker | Deletes expired data | PostgreSQL TTL configs | Deletes from MongoDB | CronJob, hourly |
| 5 | IoT backend | REST API server | HTTP requests from web app | Reads/writes PostgreSQL, reads MongoDB, produces to Kafka | Deployment, 2 replicas |
| 6 | Web app | Dashboard UI | User interactions | HTTP calls to backend | Deployment, 2 replicas |
| 7 | PostgreSQL | Relational database | Writes from backend | Reads by backend + TTL worker | StatefulSet, 1 replica, PVC 10Gi |
| 8 | MongoDB | Time-series database | Writes from telemetry worker | Reads by backend, deletes by TTL worker | StatefulSet, 1 replica, PVC 20Gi |
| 9 | MongoDB | Document database | Writes from telemetry worker + backend | Reads by backend, deletes by TTL worker | StatefulSet, 1 replica, PVC 10Gi |

**Data ownership rule:** The telemetry worker writes to MongoDB. The backend reads from them. This clear ownership means no write conflicts and no coordination required.

**The backend's one Kafka interaction:** When a user sends a command via the web app, the backend produces a single message to `iot.commands`. The broker gateway's subscription dispatcher picks this up and pushes it to the connected ESP32 device.

---

# Part 4: The custom binary protocol

Every message between an ESP32 and the broker uses this frame format:

```
+----------+----------+----------+----------+-- - - - - - - --+
| Byte 0   | Byte 1   | Byte 2   | Byte 3   | Bytes 4+        |
| Type     | Flags    | Len (hi) | Len (lo) | JSON payload    |
| 1 byte   | 1 byte   | 2 bytes big-endian  | 0–65535 bytes   |
+----------+----------+----------+----------+-- - - - - - - --+
```

**Byte 0 — Message type:**

| Code | Name | Direction | Has payload? |
|------|------|-----------|-------------|
| 0x01 | CONNECT | ESP32 → Broker | Yes |
| 0x02 | CONNACK | Broker → ESP32 | Yes |
| 0x03 | PUB | Both directions | Yes |
| 0x04 | SUB | ESP32 → Broker | Yes |
| 0x05 | SUBACK | Broker → ESP32 | Yes |
| 0x06 | UNSUB | ESP32 → Broker | Yes |
| 0x07 | PING | ESP32 → Broker | No (length=0) |
| 0x08 | PONG | Broker → ESP32 | No (length=0) |
| 0x09 | DISCONNECT | Both | No (length=0) |

**Byte 1 — Flags:** Always `0x00` (reserved for future use, e.g., QoS levels).

**Bytes 2–3 — Payload length:** Big-endian 16-bit integer (high byte first). Maximum 65535 bytes.

**Building a frame in C++ (ESP32 side):**

```cpp
uint8_t header[4];
header[0] = msgType;                        // e.g., 0x01 for CONNECT
header[1] = 0x00;                           // Flags: always 0x00
header[2] = (payloadLen >> 8) & 0xFF;       // Length high byte
header[3] = payloadLen & 0xFF;              // Length low byte
tcp.write(header, 4);                       // Send header
tcp.write(jsonPayload, payloadLen);         // Send payload
```

**Reading a frame in Python (broker side):**

```python
header = await reader.readexactly(4)
msg_type = header[0]
flags    = header[1]
length   = (header[2] << 8) | header[3]    # Big-endian decode
payload  = await reader.readexactly(length)
data     = json.loads(payload)
```

**CONNECT payload (ESP32 sends):**

```json
{
  "client_id": "6a4f8e2b-9c1d-4b7a-a3e5-8f2d6c0b4a7e",
  "token": "d7e3f1a9b5c2084f6e8d0a4b2c9f7e1a3d5b8c0e2f4a6d8b0c2e4a6f8d0b",
  "secret": "9f2a4c6e8b0d1a3c5e7f9b2d4a6c8e0f1a3b5d7e9c2a4f6b8d0e2a4c6f8b",
  "client_version": "1.0"
}
```

**CONNACK payload (broker responds — success):**

```json
{
  "status": "ok",
  "device_id": "ESP32_farm_01",
  "group_id": "grp_farm_01"
}
```

**CONNACK payload (broker responds — failure):**

```json
{
  "status": "error",
  "reason": "invalid_credentials"
}
```

**PUB payload (publishing telemetry):**

```json
{
  "topic": "grp_farm_01/ESP32_farm_01/telemetry",
  "data": {
    "temperature": 28.5,
    "humidity": 65.2,
    "pressure": 1013.25
  },
  "qos": 0
}
```

**SUB payload (subscribing to commands):**

```json
{
  "topic": "grp_farm_01/ESP32_farm_01/commands/#"
}
```

---

# Part 5: Data flow traces

## Trace 1: Sensor reading → Dashboard chart

Here is exactly what happens when an ESP32 reads its temperature sensor and the user sees it on a chart:

1. **ESP32** reads temperature sensor: 28.5°C
2. **ESP32** sends PUB frame over TCP: `[0x03][0x00][0x00][0x5A]{"topic":"grp_farm_01/ESP32_farm_01/telemetry","data":{"temperature":28.5},"qos":0}`
3. **Broker gateway** receives the frame, checks: is this device authenticated? Is the topic prefix correct for this device's group? Both yes.
4. **Broker** maps topic to Kafka: topic=`iot.telemetry`, key=`grp_farm_01:ESP32_farm_01`, and produces the message asynchronously.
5. **Kafka** stores the message in partition 3 (determined by `hash(key) % 6`).
6. **Telemetry worker** consumes the message from Kafka:
   - Writes to MongoDB: `sensor,group_id=grp_farm_01,device_id=ESP32_farm_01,sensor_type=temperature value=28.5`
   - Writes to MongoDB: `{_id:"grp_farm_01:ESP32_farm_01", temperature:28.5, last_updated:now()}`
7. **User** opens the web dashboard. A chart widget calls: `GET /api/v1/groups/grp_farm_01/devices/ESP32_farm_01/telemetry/history?sensor_type=temperature&from=24h_ago&interval=5m`
8. **Backend** queries MongoDB with the time range clamped by the device's TTL setting. Returns an array of `{time, value}` points.
9. **React chart widget** renders the line graph.
10. **TTL cleanup worker** (runs hourly): if this device has TTL=7 days, deletes all MongoDB points and MongoDB docs older than 7 days.

## Trace 2: User command → ESP32

Here is what happens when a user clicks "set interval to 5 seconds" in the web dashboard:

1. **User** clicks the button in the web app.
2. **Web app** calls: `POST /api/v1/groups/grp_farm_01/devices/ESP32_farm_01/commands` with body `{"command":"set_interval","params":{"interval_ms":5000}}`
3. **Backend** produces to Kafka: topic=`iot.commands`, key=`grp_farm_01:ESP32_farm_01`, value=the command JSON. Returns `{"status":"sent"}` immediately.
4. **Broker's subscription dispatcher** (a background Kafka consumer) reads the message.
5. **Dispatcher** reconstructs the PubSub topic: `grp_farm_01/ESP32_farm_01/commands/set_interval`. Checks the subscription registry: ESP32_farm_01 subscribed to `grp_farm_01/ESP32_farm_01/commands/#`. Pattern match: `commands/#` matches `commands/set_interval`. Yes!
6. **Broker** builds a PUB frame and writes it to the ESP32's TCP socket: `[0x03][0x00][0x00][0x55]{"topic":"...","data":{"command":"set_interval","params":{"interval_ms":5000}}}`
7. **ESP32's** `PubSubClient.loop()` reads the frame, calls `onCommand()`. The firmware code changes `reportInterval = 5000`. The device now reports every 5 seconds.

## Full session trace (byte level)

```
1.  ESP32 opens TCP socket to broker:1883

2.  CONNECT:
    [0x01][0x00][0x00][0x8A]{"client_id":"6a4f8e2b-...","token":"d7e3...","secret":"9f2a...","client_version":"1.0"}

3.  CONNACK (success):
    [0x02][0x00][0x00][0x3E]{"status":"ok","device_id":"ESP32_farm_01","group_id":"grp_farm_01"}

4.  SUB (subscribe to commands):
    [0x04][0x00][0x00][0x30]{"topic":"grp_farm_01/ESP32_farm_01/commands/#"}

5.  SUBACK:
    [0x05][0x00][0x00][0x38]{"topic":"grp_farm_01/ESP32_farm_01/commands/#","status":"ok"}

6.  PUB (telemetry, every 10 seconds):
    [0x03][0x00][0x00][0x6A]{"topic":"grp_farm_01/ESP32_farm_01/telemetry","data":{"temperature":28.5,"humidity":65.2},"qos":0}

7.  PING (every 30 seconds):
    [0x07][0x00][0x00][0x00]

8.  PONG:
    [0x08][0x00][0x00][0x00]

9.  Incoming command (broker pushes):
    [0x03][0x00][0x00][0x55]{"topic":"grp_farm_01/ESP32_farm_01/commands/set_interval","data":{"command":"set_interval","params":{"interval_ms":5000}}}

10. Command response:
    [0x03][0x00][0x00][0x4A]{"topic":"grp_farm_01/ESP32_farm_01/commands/response","data":{"command":"set_interval","status":"ok"}}

11. DISCONNECT:
    [0x09][0x00][0x00][0x00]
```

---

# Part 6: Database design

## PostgreSQL (relational data — users, groups, devices, credentials, tokens)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(256) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    full_name VARCHAR(256),
    role VARCHAR(32) DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(256) NOT NULL,
    owner_id UUID NOT NULL REFERENCES users(id),
    tier VARCHAR(32) DEFAULT 'free',
    max_devices INT DEFAULT 10,
    default_ttl_days INT DEFAULT 30,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id VARCHAR(128) NOT NULL,
    group_id UUID NOT NULL REFERENCES groups(id),
    name VARCHAR(256),
    device_type VARCHAR(64) DEFAULT 'weather_station',
    status VARCHAR(32) DEFAULT 'offline',
    last_seen TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    ttl_days INT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(device_id, group_id)
);

CREATE TABLE device_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id),
    group_id UUID NOT NULL REFERENCES groups(id),
    client_id VARCHAR(128) UNIQUE NOT NULL,
    token_hash VARCHAR(128) NOT NULL,
    secret_hash VARCHAR(128) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE user_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    refresh_token_hash VARCHAR(256) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_revoked BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_groups_owner ON groups(owner_id);
CREATE INDEX idx_devices_group ON devices(group_id);
CREATE INDEX idx_credentials_client ON device_credentials(client_id);
CREATE INDEX idx_user_tokens_user ON user_tokens(user_id);
```

## MongoDB (time-series sensor data)

```
measurement: sensor
tags:
  group_id (string)     — "grp_farm_01"
  device_id (string)    — "ESP32_farm_01"
  sensor_type (string)  — "temperature", "humidity", "pressure"
fields:
  value (float)         — 28.5
timestamp: nanosecond precision

Written by: telemetry worker only
Read by: IoT backend only
Cleaned by: TTL cleanup worker
```

## MongoDB collections

**device_state** (latest readings per device — written by telemetry worker, read by backend):

```json
{
    "_id": "grp_farm_01:ESP32_farm_01",
    "group_id": "grp_farm_01",
    "device_id": "ESP32_farm_01",
    "temperature": 28.5,
    "humidity": 65.2,
    "pressure": 1013.25,
    "last_updated": "2026-03-25T09:55:00Z"
}
```

**dashboards** (user-created dashboards — written and read by backend):

```json
{
    "_id": "dash-uuid",
    "group_id": "grp_farm_01",
    "owner_id": "user-uuid",
    "name": "Farm overview",
    "widgets": [
        {
            "id": "w1",
            "type": "line_chart",
            "title": "Temperature 24h",
            "position": {"x": 0, "y": 0, "w": 6, "h": 4},
            "config": {
                "device_id": "ESP32_farm_01",
                "sensor_type": "temperature",
                "time_range": "24h"
            }
        }
    ],
    "created_at": "2026-03-25T10:00:00Z"
}
```

---

# Part 7: HTTP API specification

## Authentication (no JWT required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Create account (email + password) |
| POST | `/api/v1/auth/login` | Returns JWT access token (15 min) + refresh token (7 day) |
| POST | `/api/v1/auth/refresh` | Exchange refresh token for new pair (old revoked) |
| POST | `/api/v1/auth/logout` | Revoke refresh token |

## Groups (JWT required)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/groups` | List user's groups |
| POST | `/api/v1/groups` | Create group (max 2 for free tier) |
| GET | `/api/v1/groups/{gid}` | Group details + default_ttl_days |
| PUT | `/api/v1/groups/{gid}` | Update name, default_ttl_days |
| DELETE | `/api/v1/groups/{gid}` | Delete group + all devices + data |

## Devices (JWT required, scoped to group)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/groups/{gid}/devices` | List devices in group |
| POST | `/api/v1/groups/{gid}/devices` | Create device → returns 3-part credentials (shown ONCE) |
| GET | `/api/v1/groups/{gid}/devices/{did}` | Device details + effective TTL + latest state |
| PUT | `/api/v1/groups/{gid}/devices/{did}` | Update name, metadata, ttl_days |
| DELETE | `/api/v1/groups/{gid}/devices/{did}` | Remove device + revoke credentials |
| POST | `/api/v1/groups/{gid}/devices/{did}/credentials/regenerate` | Generate new credentials, revoke old |

**POST create device response (credentials shown once):**

```json
{
  "device_id": "ESP32_farm_01",
  "group_id": "grp_farm_01",
  "credentials": {
    "client_id": "6a4f8e2b-9c1d-4b7a-a3e5-8f2d6c0b4a7e",
    "token": "d7e3f1a9b5c2084f6e8d0a4b2c9f7e1a3d5b8c0e2f4a6d8b0c2e4a6f8d0b",
    "secret": "9f2a4c6e8b0d1a3c5e7f9b2d4a6c8e0f1a3b5d7e9c2a4f6b8d0e2a4c6f8b"
  },
  "warning": "Credentials are shown once. Store them securely."
}
```

## Telemetry (JWT required, range clamped by TTL)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/groups/{gid}/devices/{did}/telemetry` | Latest readings (from MongoDB) |
| GET | `/api/v1/groups/{gid}/devices/{did}/telemetry/history?sensor_type=temperature&from=...&to=...&interval=5m` | Historical data (from MongoDB, range clamped by device TTL) |

## Commands (JWT required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/groups/{gid}/devices/{did}/commands` | Send command (→ Kafka → broker → device) |
| GET | `/api/v1/groups/{gid}/devices/{did}/commands/history` | Command log |

## Dashboards (JWT required, scoped to group)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/groups/{gid}/dashboards` | List dashboards |
| POST | `/api/v1/groups/{gid}/dashboards` | Create dashboard |
| GET | `/api/v1/groups/{gid}/dashboards/{id}` | Get config + widgets |
| PUT | `/api/v1/groups/{gid}/dashboards/{id}` | Update layout/widgets (validates device in group) |
| DELETE | `/api/v1/groups/{gid}/dashboards/{id}` | Delete dashboard |

## Internal (cluster only, no JWT)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/internal/verify-credentials` | Called by broker on device CONNECT |

---

# Part 8: Security architecture

## User authentication
- Passwords hashed with bcrypt (cost factor 12)
- JWT access tokens: 15 minute expiry, contains user_id + role, signed with HS256
- JWT refresh tokens: 7 day expiry, stored as hash in PostgreSQL, rotated on every use (old token revoked immediately)

## Device authentication
- Three-part NETPIE-style: clientId (UUID lookup) + token (SHA-256 verified) + secret (SHA-256 verified)
- Credentials generated on device creation, shown once, never retrievable
- Regenerate endpoint creates new credentials and revokes old ones

## Group isolation
- Broker checks every PUB/SUB: topic must start with device's group_id
- Backend API validates group ownership on every request
- Dashboard widgets validated: target device must belong to same group
- All database queries filter by group_id

## Kubernetes security
- Secrets in K8s Secrets (DB passwords, JWT secret, Kafka credentials)
- Internal endpoints (`/internal/*`) not exposed via Ingress
- Non-root containers with read-only root filesystem
- Network policies restrict pod-to-pod communication

---

# Part 9: Kubernetes deployment

## Three namespaces

| Namespace | Contains |
|-----------|----------|
| `iot-app` | IoT backend (Deployment 2r), web app (Deployment 2r) |
| `iot-broker` | Broker gateway (StatefulSet 2r), telemetry worker (Deployment 3r), TTL cleanup worker (CronJob hourly) |
| `iot-infra` | Kafka (StatefulSet 3r via Strimzi), PostgreSQL (SS 1r), MongoDB (SS 1r), MongoDB (SS 1r) |

## External access

| Service | How exposed | External URL |
|---------|------------|-------------|
| Web app | Nginx Ingress, path `/` | `https://iot.example.com/` |
| IoT backend | Nginx Ingress, path `/api` | `https://iot.example.com/api/*` |
| Broker gateway | LoadBalancer service | `TCP :1883` (ESP32 devices connect here) |
| Everything else | ClusterIP | Internal only |

## Kustomize structure

```
k8s/
├── base/                          # Complete manifests with defaults
│   ├── kustomization.yaml
│   ├── namespaces.yaml
│   ├── configmap.yaml             # DB URLs, Kafka bootstrap, MongoDB settings
│   ├── secrets.yaml               # Template (actual values via sealed-secrets)
│   ├── ingress.yaml               # /api → backend, / → web-app
│   ├── iot-backend/               # deployment.yaml + service.yaml
│   ├── web-app/                   # deployment.yaml + service.yaml
│   ├── pubsub-broker/             # statefulset.yaml + service.yaml (LoadBalancer)
│   ├── telemetry-worker/          # deployment.yaml
│   ├── ttl-cleanup-worker/        # cronjob.yaml
│   ├── kafka/                     # Strimzi Kafka resource
│   ├── postgres/                  # statefulset + service + pvc
│   ├── MongoDB/                  # statefulset + service + pvc
│   └── mongodb/                   # statefulset + service + pvc
└── overlays/
    ├── staging/                   # 1 replica per service, staging domain
    └── production/                # 2-3 replicas, prod domain, TLS, higher resource limits
```

---

# Part 10: CI/CD pipeline

## CI workflow (runs on every push and PR)

1. **Lint + test** — Matrix job for each Python service: ruff (style), mypy (types), pytest (with coverage). Frontend: eslint + vitest. Firmware: PlatformIO compile.
2. **Build Docker images** — Multi-stage builds (builder stage installs deps, final stage copies only runtime). Push to GitHub Container Registry (GHCR) with commit SHA tag.
3. **Security scan** — Trivy scans each image for HIGH/CRITICAL CVEs. Blocks deployment if found.

## CD workflow (runs on merge to main)

4. **Deploy staging** — Kustomize sets image tags to commit SHA, kubectl applies to staging namespace, waits for rollout.
5. **Integration tests** — pytest with httpx runs real HTTP requests against staging API.
6. **Manual approval** — GitHub environment protection rule requires team member to approve.
7. **Deploy production** — Same image SHA as staging, kubectl apply, smoke test, auto-rollback if smoke fails.

---

# Part 11: Observability and monitoring

## Structured logging
All services use `structlog` with JSON output. Every log line includes: event name, timestamp, service name, request method, path, status code, duration_ms, user_id, device_id, group_id.

## Prometheus metrics
- `http_requests_total{method, path, status}` — API request count
- `http_request_duration_seconds` — Latency histogram
- `telemetry_consumer_lag{partition}` — Kafka consumer lag
- `broker_active_connections` — Connected device count
- `ttl_cleanup_duration_seconds` — Cleanup run time
- `ttl_cleanup_points_deleted{group_id}` — Points deleted per group

## Alert rules
- HighAPIErrorRate: 5xx rate > 5% for 5 min → Critical
- TelemetryConsumerLag: lag > 1000 for 3 min → Warning
- PodCrashLooping: > 3 restarts in 15 min → Critical
- BrokerNoConnections: 0 connections for 2 min → Warning
- TTLCleanupFailed: 3 consecutive CronJob failures → Warning

---

# Part 12: Project file structure

```
iot-platform/
├── .github/workflows/
│   ├── ci.yml                      # Lint, test, build, scan
│   └── cd.yml                      # Deploy staging → production
│
├── k8s/
│   ├── base/                       # All Kubernetes manifests
│   │   ├── iot-backend/
│   │   ├── web-app/
│   │   ├── pubsub-broker/
│   │   ├── telemetry-worker/
│   │   ├── ttl-cleanup-worker/     # CronJob
│   │   ├── kafka/
│   │   ├── postgres/
│   │   ├── MongoDB/
│   │   └── mongodb/
│   └── overlays/
│       ├── staging/
│       └── production/
│
├── services/
│   ├── iot-backend/                # FastAPI monolith
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── groups.py           # Group CRUD + TTL default
│   │   │   ├── devices.py          # Device CRUD + credentials + TTL override
│   │   │   ├── telemetry.py        # Query (range clamped by TTL)
│   │   │   ├── commands.py         # Send commands (→ Kafka)
│   │   │   └── dashboards.py       # Dashboard CRUD (group-scoped)
│   │   ├── services/
│   │   │   ├── user_service.py
│   │   │   ├── group_service.py
│   │   │   ├── device_service.py
│   │   │   ├── credential_service.py
│   │   │   ├── ttl_service.py
│   │   │   ├── telemetry_service.py
│   │   │   ├── command_service.py
│   │   │   └── dashboard_service.py
│   │   ├── models/
│   │   ├── middleware/
│   │   ├── internal/
│   │   │   └── device_auth.py      # /internal/verify-credentials
│   │   └── requirements.txt
│   │
│   ├── pubsub-broker/              # Custom Kafka-backed broker
│   │   ├── Dockerfile
│   │   ├── broker.py               # Main entry (asyncio event loop)
│   │   ├── protocol.py             # Binary frame parser/serializer
│   │   ├── connection_manager.py
│   │   ├── device_authenticator.py # 3-part credential verify
│   │   ├── access_control.py       # Group isolation enforcement
│   │   ├── topic_mapper.py         # PubSub → Kafka mapping
│   │   ├── kafka_producer.py
│   │   ├── subscription_registry.py
│   │   ├── subscription_dispatcher.py
│   │   └── requirements.txt
│   │
│   ├── telemetry-worker/           # Kafka → databases
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   └── requirements.txt
│   │
│   └── ttl-cleanup-worker/         # Periodic data cleanup
│       ├── Dockerfile
│       ├── main.py
│       └── requirements.txt
│
├── firmware/
│   ├── lib/
│   │   └── PubSubClient/
│   │       ├── PubSubClient.h
│   │       └── PubSubClient.cpp
│   ├── src/
│   │   └── main.cpp                # ESP32 weather station firmware
│   └── platformio.ini
│
├── apps/
│   └── web/
│       ├── Dockerfile
│       ├── nginx.conf
│       ├── src/
│       │   ├── pages/              # Login, Groups, Devices, Dashboard
│       │   ├── components/
│       │   │   ├── dashboard/      # Drag-and-drop widget grid
│       │   │   ├── TTLSettings.jsx
│       │   │   └── CredentialDisplay.jsx
│       │   ├── services/           # API client
│       │   └── App.jsx
│       └── package.json
│
├── tests/integration/
│
├── monitoring/
│   ├── prometheus-rules.yaml
│   ├── service-monitors.yaml
│   ├── grafana-dashboards.json
│   └── alertmanager-config.yaml
│
└── docs/
    ├── architecture.md
    ├── api-spec.md
    ├── topics.md
    ├── deployment-guide.md
    └── credential-guide.md
```

---

# Part 13: Week-by-week implementation guide

## Week 1 — Foundation

**Goal:** Working backend with auth, groups, devices, and credential generation.

1. Create GitHub repo with the project structure
2. Set up CI workflow (ruff + pytest on push)
3. Deploy infrastructure on local K8s (minikube/k3s): Kafka + PostgreSQL + MongoDB
4. PostgreSQL: create all tables (users, groups, devices, device_credentials, user_tokens)
5. Backend: auth endpoints (register, login, refresh, logout)
6. Backend: group CRUD with free tier enforcement (max 2 groups)
7. Backend: device CRUD with three-part credential generation
8. Backend: TTL config endpoints (group default + device override)

**Deliverable:** Register → create group → add device → receive credentials → verify they look like NETPIE hash strings.

## Week 2 — Broker + ESP32 connectivity

**Goal:** ESP32 connects, publishes telemetry, receives commands.

1. Broker: TCP listener + protocol parser + connection manager
2. Broker: device authenticator (3-part, calls backend's /internal/verify-credentials)
3. Broker: group-scoped access control
4. Broker: Kafka producer + topic mapper
5. Broker: subscription registry + dispatcher
6. PubSubClient library: connect(clientId, token, secret), publish, subscribe, loop
7. TTL cleanup worker: read configs → delete expired data (CronJob)
8. Test end-to-end: Python test client → CONNECT → PUB → verify in Kafka

**Deliverable:** Device connects with 3-part auth, telemetry flows through Kafka, group isolation verified.

## Week 3 — Data pipeline + dashboard + TTL

**Goal:** Data stored in databases, dashboards work, TTL enforced.

1. Telemetry worker: Kafka consumer → MongoDB (with group_id tag) + MongoDB
2. Backend: telemetry query endpoints (range clamped by TTL)
3. Backend: command endpoint (produce to Kafka)
4. Backend: dashboard CRUD (group-scoped, widget device validation)
5. Web app: login, group selector, device list with TTL badges
6. Web app: TTL settings on group and device pages
7. Web app: dashboard builder with drag-and-drop widgets
8. CD pipeline: build → push GHCR → deploy staging

**Deliverable:** Full data pipeline working, dashboards with TTL-aware widgets, CI/CD deploying to staging.

## Week 4 — Integration demo (70-80%)

**Goal:** Working end-to-end system with all features.

1. Connect real ESP32 weather station hardware with 3-part credentials
2. Dashboard builder: line chart, gauge, status indicator, command button widgets
3. Demonstrate group isolation (two groups, cross-group blocked)
4. Demonstrate TTL (set 7d TTL, verify cleanup deletes old data after 1 hour)
5. Credential regeneration flow
6. K8s manifests complete (Kustomize base + staging overlay)
7. Integration test suite

**Deliverable:** Working system demonstration at 70-80% completion.

## Week 5 — Production + polish

**Goal:** Production-ready deployment, all documentation complete.

1. Production K8s overlay (more replicas, resource limits, TLS via cert-manager)
2. Manual approval gate for production deploy
3. Prometheus metrics + alert rules + Grafana dashboards
4. TTL change confirmation dialog in UI
5. Deployment guide document
6. Security hardening: network policies, non-root containers
7. Final bug fixes

**Deliverable:** Production deployment running, all documentation complete, final presentation.
