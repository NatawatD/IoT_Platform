# IoT Platform

Enterprise-style IoT Platform for real-time telemetry ingestion, device management, and dashboard visualization.

## System Architecture

📄 [System Architecture Proposal](docs/System_Architecture_Proposal.md)

![System Architecture Diagrams](asset/System_Architecture_Diagrams.png)

## Component: TCP Broker & Protocol Backend

```
ESP32 (IoTPubSubClient 3-part Auth)
  │ TCP:1883
  ▼
PubSub_Server (Custom TCP Broker)
  │
  ├── Kafka producer → [iot.telemetry] → Kafka consumer → MongoDB (Time Series + TTL)
  ├── Kafka producer → [iot.device-events]
  └── Kafka consumer ← [iot.commands] ← REST API
```

## Quick Start

```bash
# 1. Copy environment config
cp .env.example .env

# 2. Start all services
docker compose up -d

# 3. View broker logs
docker compose logs -f broker
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| TCP Broker | 1883 | Device connections (custom binary protocol) |
| Query API | 8080 | REST API for telemetry queries |
| Kafka | 9092 | Internal message bus |
| MongoDB | 27017 | Time-series database |
| Mongo-Express | 8081 | Web UI for MongoDB administration |

## Project Structure

```
Em_Iot_platform/
├── PubSub_Server/          # TCP broker + Kafka + MongoDB + API
│   ├── protocol/           # Binary protocol library (Library Design)
│   ├── broker/             # asyncio TCP server (Auth, ACL)
│   ├── kafka_bridge/       # Kafka producer/consumer
│   ├── mongodb_layer/      # MongoDB async client, Time Series writer, queries
│   ├── api/                # FastAPI query endpoints
│   ├── main.py             # Entrypoint
│   └── Dockerfile
├── Pubsub_Client/          # Arduino C++ library (Library Design)
│   ├── src/                # IoTPubSubClient.h/.cpp
│   └── examples/           # Example sketch for ESP32
├── docs/                   # Protocol specification
├── docker-compose.yml      # Kafka + MongoDB + broker
└── .env.example            # Configuration template
```

## API Endpoints (Telemetry)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/devices/{id}/telemetry` | Historical telemetry |
| GET | `/api/v1/devices/{id}/telemetry/latest` | Latest reading |

## Documentation

- [Protocol Design](docs/protocol_design.md) — Binary frame format, message types, 3-part auth, topic structure
