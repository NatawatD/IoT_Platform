# System Architecture Proposal

**Project**: Enterprise IoT Platform — Device Management and Data Visualization  
**Course**: Graduate IoT Systems Engineering  
**Date**: March 2026  
**Duration**: 5 weeks

---

## 1. Project overview

We are building a complete IoT platform where ESP32 microcontrollers connect to a cloud server, transmit sensor data (temperature, humidity, pressure), receive remote commands, and users manage devices and visualize data through a web dashboard.

Key differentiators of this architecture:

- **Custom PubSub broker** (project requirement) — we build our own TCP-based message broker with a custom binary protocol, not an off-the-shelf MQTT broker
- **Custom PubSubClient library** — a C++ library for ESP32 that speaks our custom protocol
- **Kafka backbone** — Apache Kafka provides durable, ordered message delivery inside the broker
- **Group isolation** — NETPIE-style project model where devices are isolated by group
- **Three-part device credentials** — NETPIE-inspired authentication using clientId + token + secret (SHA-256 hashed)
- **Automatic data expiry** — MongoDB built-in TTL indexes handle data retention with zero application code

---

## 2. High-level architecture

The platform is split into **two independent subsystems** that share Kafka and databases:

### Subsystem 1 — Custom PubSub broker system (complex)

Handles all device-to-platform communication:

| Component | Role |
|-----------|------|
| Broker gateway | Python asyncio TCP server on port 1883. Speaks custom binary protocol, authenticates devices with 3-part credentials, enforces group isolation on topics, produces messages to Kafka |
| Apache Kafka | Message backbone. 4 topics: `iot.telemetry`, `iot.commands`, `iot.device-events`, `iot.cmd-responses`. KRaft mode (3 nodes) |
| Telemetry worker | Kafka consumer (3 replicas). Reads `iot.telemetry`, writes to MongoDB (both telemetry history and latest device state) |

### Subsystem 2 — IoT backend application (simple)

Handles all human-facing operations:

| Component | Role |
|-----------|------|
| IoT backend | FastAPI monolith. REST API for auth, group/device CRUD, telemetry queries, dashboard management. Only Kafka interaction: produce to `iot.commands` when user sends a command |
| Web app | React SPA. Dashboard builder with drag-and-drop widgets, device management UI |

### Data ownership rule

The telemetry worker **writes** to MongoDB. The backend **reads** from MongoDB and **reads/writes** to PostgreSQL. No write conflicts between subsystems.

---

## 3. Data flow

### 3.1 Telemetry path (sensor data)

```
ESP32 sensor reading
  → [TCP] PUB frame with 3-part auth
  → Broker gateway (validate group, map topic)
  → [Kafka] iot.telemetry topic (key: group:device)
  → Telemetry worker (consumer group, 3 replicas)
  → MongoDB: telemetry collection (with TTL index for auto-expiry)
  → MongoDB: device_state collection (upsert latest)
  → IoT backend reads on API request
  → Web dashboard displays chart/gauge
```

### 3.2 Command path (user → device)

```
User clicks "Send command" in web dashboard
  → [HTTP] POST /api/v1/groups/{gid}/devices/{did}/commands
  → IoT backend produces to Kafka iot.commands
  → Broker gateway's subscription dispatcher consumes
  → Matches device's TCP session from subscription registry
  → [TCP] PUB frame pushed to ESP32
  → ESP32 PubSubClient.loop() fires onMessage callback
```

### 3.3 Data expiry (automatic — no custom worker needed)

```
MongoDB TTL index on telemetry.expires_at field
  → MongoDB background thread runs every 60 seconds
  → Automatically deletes documents where expires_at < now
  → Zero application code — the database handles it natively
```

---

## 4. Technology stack

| Layer | Technology | Justification |
|-------|-----------|---------------|
| Device | ESP32 + PlatformIO + ArduinoJson | Course requirement, widely available |
| Broker | Python 3.12 asyncio + aiokafka | High-concurrency TCP server with Kafka integration |
| Message bus | Apache Kafka 3.7 (KRaft) | Durable ordered log, consumer groups, partition-based scaling |
| Backend | Python 3.12 + FastAPI + SQLAlchemy + motor | Async REST API with ORM and MongoDB async driver |
| Frontend | React + react-grid-layout | Dashboard builder with draggable widgets |
| User management DB | PostgreSQL 16 | Users, groups, device credentials — relational integrity with FK constraints |
| Data DB | MongoDB 7 | Telemetry history (TTL-indexed), latest device state, dashboard configs — flexible schema, built-in TTL |
| Orchestration | Kubernetes + Kustomize | Scaling, health checks, rolling deploys |
| CI/CD | GitHub Actions + GHCR | Automated test → build → deploy pipeline |

---

## 5. Database design (2 databases)

### 5.1 PostgreSQL — user and device management only

PostgreSQL handles relational data where foreign key integrity matters:

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
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
    tier VARCHAR(32) DEFAULT 'free',
    max_devices INTEGER DEFAULT 10,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id VARCHAR(128) UNIQUE NOT NULL,
    group_id UUID REFERENCES groups(id) ON DELETE CASCADE,
    name VARCHAR(256),
    device_type VARCHAR(64) DEFAULT 'weather_station',
    status VARCHAR(32) DEFAULT 'offline',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE device_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
    group_id UUID REFERENCES groups(id),
    client_id VARCHAR(128) UNIQUE NOT NULL,
    token_hash VARCHAR(256) NOT NULL,
    secret_hash VARCHAR(256) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE user_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash VARCHAR(256) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_revoked BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**What PostgreSQL does NOT store**: No telemetry data, no device state, no dashboards, no TTL configurations.

### 5.2 MongoDB — all IoT operational data

MongoDB handles all data that devices produce and users consume:

**Collection: `telemetry`** — all sensor readings with automatic TTL expiry

```javascript
{
    _id: ObjectId(),
    group_id: "grp_farm_01",
    device_id: "ESP32_farm_01",
    sensor_type: "temperature",
    value: 28.5,
    timestamp: ISODate("2026-03-26T10:00:00Z"),
    expires_at: ISODate("2026-04-25T10:00:00Z")   // TTL — auto-deleted after this
}

// TTL index — MongoDB automatically deletes expired documents
db.telemetry.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 0 })

// Query index for time-range queries
db.telemetry.createIndex({ "group_id": 1, "device_id": 1, "sensor_type": 1, "timestamp": -1 })
```

**How TTL works**: When the telemetry worker writes a document, it sets `expires_at = now + retention_period`. MongoDB's background thread checks every 60 seconds and deletes documents where `expires_at < now`. Different devices can have different retention periods — each document carries its own expiry time.

**Collection: `device_state`** — latest readings per device

```javascript
{
    _id: "grp_farm_01:ESP32_farm_01",
    group_id: "grp_farm_01",
    device_id: "ESP32_farm_01",
    temperature: 28.5,
    humidity: 65.2,
    pressure: 1013.25,
    last_updated: ISODate("2026-03-26T10:00:00Z")
}
```

**Collection: `dashboards`** — user dashboard configurations

```javascript
{
    _id: ObjectId(),
    group_id: "grp_farm_01",
    owner_id: "user-uuid",
    name: "Weather Overview",
    widgets: [
        {
            id: "w1", type: "line_chart",
            title: "Temperature (24h)",
            position: { x: 0, y: 0, w: 6, h: 4 },
            config: { device_id: "ESP32_farm_01", sensor_type: "temperature", time_range: "24h" }
        }
    ]
}
```

### 5.3 Why this split?

| Question | Answer |
|----------|--------|
| Why not all in PostgreSQL? | Telemetry is high-write, schema-flexible, needs TTL. PostgreSQL would need custom cleanup jobs and rigid schemas. |
| Why not all in MongoDB? | User accounts and credentials need relational integrity (FK constraints, unique email, cascade deletes). |
| Why not MongoDB for time-series? | MongoDB with proper indexes handles time-range queries well for a course project. Eliminating MongoDB means 2 databases instead of 3, and MongoDB's built-in TTL replaces a custom cleanup worker entirely. |

---

## 6. Group isolation model

Groups provide multi-tenant isolation, inspired by NETPIE's project concept. Each user can create groups (free tier: max 2). Every device, topic, dashboard, and data point belongs to exactly one group.

Isolation is enforced at every layer: broker validates topic prefix against authenticated group, Kafka keys include group_id, MongoDB queries always filter by group_id, backend API validates group membership, dashboard widgets can only reference devices in the same group.

---

## 7. Device credential system (NETPIE-style)

When a device is registered in a group, the backend generates three values shown once:

| Credential | Format | Stored as |
|-----------|--------|-----------|
| Client ID | UUID v4 (plaintext) | Plaintext — lookup key |
| Token | 32-byte random hex | SHA-256 hash in PostgreSQL |
| Secret | 32-byte random hex | SHA-256 hash in PostgreSQL |

SHA-256 chosen over bcrypt for sub-millisecond verification on frequent device CONNECTs. 256-bit entropy makes brute-force infeasible.

---

## 8. Custom binary protocol

```
[Type: 1 byte] [Flags: 1 byte] [Length: 2 bytes big-endian] [JSON payload]
```

| Code | Name | Direction | Payload |
|------|------|-----------|---------|
| 0x01 | CONNECT | Device → Broker | `{client_id, token, secret, client_version}` |
| 0x02 | CONNACK | Broker → Device | `{status, device_id, group_id}` |
| 0x03 | PUB | Bidirectional | `{topic, data, qos}` |
| 0x04 | SUB | Device → Broker | `{topic}` |
| 0x05 | SUBACK | Broker → Device | `{topic, status}` |
| 0x06 | UNSUB | Device → Broker | `{topic}` |
| 0x07 | PING | Device → Broker | (empty) |
| 0x08 | PONG | Broker → Device | (empty) |
| 0x09 | DISCONNECT | Both | (empty) |

---

## 9. PubSubClient ESP32 library

```cpp
PubSubClient client("203.154.11.226", 10001);
client.connect(CLIENT_ID, TOKEN, SECRET);
client.subscribe("commands/#");              // Auto-prepends {group}/{device}/
client.publish("telemetry", sensorJson);     // Auto-prepends {group}/{device}/
client.loop();                               // Keepalive + incoming messages
```

---

## 10. HTTP API summary

| Category | Endpoints |
|----------|-----------|
| Auth | `POST /api/v1/auth/register, login, refresh, logout` |
| Groups | `GET, POST /api/v1/groups` — `GET, PUT, DELETE /api/v1/groups/{gid}` |
| Devices | `GET, POST /api/v1/groups/{gid}/devices` — `GET, PUT, DELETE .../devices/{did}` |
| Credentials | `POST .../devices/{did}/credentials/regenerate` |
| Telemetry | `GET .../devices/{did}/telemetry` (latest) — `GET .../telemetry/history?sensor_type=...&from=...&to=...` |
| Commands | `POST .../devices/{did}/commands` (→ Kafka) |
| Dashboards | `GET, POST /api/v1/groups/{gid}/dashboards` — `GET, PUT, DELETE .../dashboards/{id}` |
| Internal | `POST /internal/verify-credentials` (broker → backend, cluster-only) |

---

## 11. Security

| Layer | Mechanism |
|-------|-----------|
| User passwords | bcrypt (cost 12) |
| User sessions | JWT access (15 min) + refresh (7 days, rotated) |
| Device auth | 3-part credentials, SHA-256 hashed |
| Topic isolation | Broker enforces `{own_group}/{own_device}/*` |
| API protection | Bearer JWT (except register/login) |
| Internal APIs | ClusterIP only, no Ingress |

---

## 12. Kubernetes deployment

| Namespace | Workloads |
|-----------|-----------|
| iot-app | IoT backend (Deployment 2r), Web app (Deployment 2r) |
| iot-broker | Broker gateway (StatefulSet 2r), Telemetry worker (Deployment 3r) |
| iot-infra | Kafka (StatefulSet 3r), PostgreSQL (StatefulSet 1r), MongoDB (StatefulSet 1r) |

| Service | Exposure |
|---------|----------|
| Web app + API | Nginx Ingress with TLS |
| Broker | LoadBalancer TCP :1883 |
| DBs + Kafka | ClusterIP (internal) |

---

## 13. CI/CD pipeline

| Stage | Actions |
|-------|---------|
| Lint + test | ruff + mypy + pytest, eslint + vitest, PlatformIO build |
| Build | Multi-stage Docker → GHCR (SHA tag) |
| Staging | Kustomize → kubectl apply → rollout → integration tests |
| Production | Manual approval → same image → production overlay |

---

## 14. Implementation plan

| Week | Deliverables |
|------|-------------|
| 1 | GitHub repo + CI, K8s cluster with Kafka + PostgreSQL + MongoDB, schemas, backend auth + group CRUD + credentials |
| 2 | Broker gateway (TCP, protocol, 3-part auth, Kafka), PubSubClient library, telemetry worker (Kafka → MongoDB with TTL), MongoDB indexes |
| 3 | Backend telemetry/command/dashboard endpoints, web app (login, devices, chart), CD pipeline |
| 4 | ESP32 end-to-end, dashboard builder, group isolation demo, TTL demo, K8s manifests |
| 5 | Production overlay, monitoring, deployment guide, final demo |

---

## 15. Key architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Custom broker + Kafka | Gateway (custom) + Kafka backbone | Satisfies "build your own broker" + durability, replay, consumer groups |
| 2 databases (not 3) | PostgreSQL + MongoDB | Removed MongoDB. Simpler deployment, fewer moving parts |
| MongoDB for telemetry | Built-in TTL index | No custom cleanup worker. `expires_at` + TTL index = automatic expiry |
| PostgreSQL for users | Relational integrity | FK constraints, unique email, cascade deletes |
| SHA-256 over bcrypt | Device credentials | Sub-ms verification for frequent connects. 256-bit entropy is sufficient |
| Group isolation | NETPIE-style | Multi-tenant. Enforced at broker, Kafka, MongoDB, API, dashboard |
| No TTL CronJob | MongoDB native TTL | Zero scheduling complexity. Database handles cleanup automatically |
