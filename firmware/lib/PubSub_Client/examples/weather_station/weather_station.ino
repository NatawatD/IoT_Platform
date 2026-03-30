/*
 * Weather Station Example — IoTPubSubClient
 * ==========================================
 * Example sketch for Wilfred showing how to use the IoTPubSubClient
 * library with an ESP32 + ET WEATHER PM2.5/H/T sensor.
 *
 * This is a near-identical replacement for a PubSubClient sketch.
 * Only the #include, constructor, and connect() call change.
 */

#include <WiFi.h>
#include <IoTPubSubClient.h>

// ── WiFi Config ─────────────────────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// ── Broker Config ───────────────────────────────────────────────────────────
const char* BROKER_HOST = "192.168.1.100";  // PubSub_Server IP
const int   BROKER_PORT = 9000;

// ── Device Config ───────────────────────────────────────────────────────────
const char* DEVICE_ID    = "ESP32_01";
const char* DEVICE_TOKEN = "YOUR_AUTH_TOKEN";  // from POST /api/v1/devices/{id}/token

// ── Telemetry interval ──────────────────────────────────────────────────────
const unsigned long PUBLISH_INTERVAL = 10000;  // 10 seconds
unsigned long lastPublish = 0;

// ── Client setup ────────────────────────────────────────────────────────────
WiFiClient wifiClient;
IoTPubSubClient client(wifiClient);

// ── Callback for incoming commands ──────────────────────────────────────────
void onMessage(const char* topic, const uint8_t* payload, unsigned int length) {
    Serial.print("Command received on [");
    Serial.print(topic);
    Serial.print("]: ");

    char msg[length + 1];
    memcpy(msg, payload, length);
    msg[length] = '\0';
    Serial.println(msg);

    // TODO: Parse command JSON and act on it
    // Example commands: set_interval, reboot, set_led
}

// ── WiFi connection ─────────────────────────────────────────────────────────
void setupWiFi() {
    delay(10);
    Serial.print("Connecting to WiFi...");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println(" connected!");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
}

// ── Broker reconnect ────────────────────────────────────────────────────────
void reconnect() {
    while (!client.connected()) {
        Serial.print("Connecting to broker...");

        // ── This is the key difference from PubSubClient ──
        // PubSubClient: client.connect("ESP32_01", "user", "pass");
        // IoTPubSubClient: client.connect("ESP32_01", "my_token", "my_device_secret"); // Authenticate (3-part auth: clientId, token, secret)
        if (client.connect(DEVICE_ID, DEVICE_TOKEN, "")) { // Pass empty secret for now
            Serial.println(" connected!");

            // Subscribe to commands (wildcard # catches all command types)
            client.subscribe("devices/ESP32_01/commands/#");

            // Publish online status
            client.publish("devices/ESP32_01/status",
                           "{\"status\":\"online\"}");
        } else {
            Serial.print(" failed, state=");
            Serial.print(client.state());
            Serial.println(" retrying in 5s...");
            delay(5000);
        }
    }
}

// ── Setup ───────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    setupWiFi();

    client.setServer(BROKER_HOST, BROKER_PORT);
    client.setCallback(onMessage);
    client.setKeepAlive(60);
}

// ── Loop ────────────────────────────────────────────────────────────────────
void loop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();  // Handle keepalive + incoming messages

    // Publish telemetry at interval
    unsigned long now = millis();
    if (now - lastPublish >= PUBLISH_INTERVAL) {
        lastPublish = now;

        // TODO: Replace with actual sensor readings
        float temperature = 28.5;  // Read from sensor
        float humidity    = 65.2;  // Read from sensor
        float pm25        = 12.3;  // Read from sensor

        // Build JSON payload
        char payload[256];
        snprintf(payload, sizeof(payload),
                 "{\"device_id\":\"%s\","
                 "\"temperature\":%.1f,"
                 "\"humidity\":%.1f,"
                 "\"pm25\":%.1f,"
                 "\"timestamp\":%lu}",
                 DEVICE_ID, temperature, humidity, pm25,
                 (unsigned long)(millis() / 1000));

        client.publish("devices/ESP32_01/telemetry", payload);
        Serial.println("Telemetry published");
    }
}
