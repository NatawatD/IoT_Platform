# IoTPubSubClient — Arduino Library

**⚠️ Library Design Deliverable**

Drop-in replacement for the [PubSubClient](https://github.com/knolleary/pubsubclient) MQTT library. Uses the IoT Platform's custom binary TCP protocol instead of standard MQTT.

## Installation

1. Copy the `Pubsub_Client/` folder into your Arduino `libraries/` directory
2. Install dependency: [ArduinoJson](https://arduinojson.org/) v6+

## Migration from PubSubClient

```diff
-#include <PubSubClient.h>
-PubSubClient client(wifiClient);
-client.setServer("broker.example.com", 1883);
-client.connect("ESP32_01", "user", "pass");
+#include <IoTPubSubClient.h>
+IoTPubSubClient client(wifiClient);
+client.setServer("203.154.11.226", 10001);
+client.connect("ESP32_01", "my_auth_token");
```

Everything else stays the same: `publish()`, `subscribe()`, `loop()`, `setCallback()`.

## API Reference

| Method | Description |
|--------|-------------|
| `setServer(host, port)` | Set broker address (default port: 9000) |
| `setCallback(fn)` | Set incoming message callback |
| `connect(deviceId, token)` | Authenticate with broker |
| `publish(topic, payload)` | Publish to a topic |
| `subscribe(topic)` | Subscribe (supports `#` wildcard) |
| `unsubscribe(topic)` | Unsubscribe from topic |
| `loop()` | Process keepalive + incoming messages |
| `connected()` | Check connection status |
| `disconnect()` | Graceful disconnect |

## Example

See [examples/weather_station/](examples/weather_station/weather_station.ino)
