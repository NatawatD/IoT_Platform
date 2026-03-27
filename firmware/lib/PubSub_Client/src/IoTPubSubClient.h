/*
 * IoTPubSubClient.h — Drop-in replacement for PubSubClient
 * =========================================================
 * ⚠️ LIBRARY DESIGN DELIVERABLE
 *
 * This library replaces the standard PubSubClient (MQTT) with a custom
 * binary TCP protocol designed for this IoT platform.
 *
 * Binary Frame Format:
 *   [type: 1B][flags: 1B][length_hi: 1B][length_lo: 1B][JSON payload: NB]
 *
 * Usage (nearly identical to PubSubClient):
 *   #include <IoTPubSubClient.h>
 *   WiFiClient wifiClient;
 *   IoTPubSubClient client(wifiClient);
 *   client.setServer("broker.local", 9000);
 *   client.setCallback(callback);
 *   client.connect("ESP32_01", "my_token");
 *   client.subscribe("devices/ESP32_01/commands/#");
 *   client.publish("devices/ESP32_01/telemetry", "{\"temperature\":28.5}");
 *   client.loop(); // call in Arduino loop()
 */

#ifndef IoTPubSubClient_h
#define IoTPubSubClient_h

#include <Arduino.h>
#include <Client.h>
#include <ArduinoJson.h>

// ── Message Type Codes ──────────────────────────────────────────────────────
// Matches PubSub_Server/protocol/constants.py exactly
#define IOT_MSG_CONNECT      0x01
#define IOT_MSG_CONNACK      0x02
#define IOT_MSG_PUBLISH      0x03
#define IOT_MSG_PUBACK       0x04
#define IOT_MSG_SUBSCRIBE    0x05
#define IOT_MSG_SUBACK       0x06
#define IOT_MSG_UNSUBSCRIBE  0x07
#define IOT_MSG_UNSUBACK     0x08
#define IOT_MSG_PINGREQ      0x09
#define IOT_MSG_PINGRESP     0x0A
#define IOT_MSG_DISCONNECT   0x0B

// ── Header Size ─────────────────────────────────────────────────────────────
#define IOT_HEADER_SIZE 4

// ── Default Configuration ───────────────────────────────────────────────────
#ifndef IOT_MAX_PACKET_SIZE
#define IOT_MAX_PACKET_SIZE 1024
#endif

#ifndef IOT_KEEPALIVE
#define IOT_KEEPALIVE 60
#endif

#ifndef IOT_SOCKET_TIMEOUT
#define IOT_SOCKET_TIMEOUT 15
#endif

// ── Connection States ───────────────────────────────────────────────────────
#define IOT_CONNECTION_TIMEOUT    -4
#define IOT_CONNECTION_LOST       -3
#define IOT_CONNECT_FAILED        -2
#define IOT_DISCONNECTED          -1
#define IOT_CONNECTED              0
#define IOT_CONNECT_BAD_TOKEN      1
#define IOT_CONNECT_REJECTED       2

// ── Callback Signature ──────────────────────────────────────────────────────
// callback(topic, payload, length) — same pattern as PubSubClient
#define IOTPUBSUB_CALLBACK_SIGNATURE void (*callback)(const char*, const uint8_t*, unsigned int)

class IoTPubSubClient {
private:
    Client* _client;
    uint8_t* _buffer;
    uint16_t _bufferSize;
    uint16_t _keepAlive;
    uint16_t _socketTimeout;
    unsigned long _lastOutActivity;
    unsigned long _lastInActivity;
    bool _pingOutstanding;

    const char* _domain;
    IPAddress _ip;
    uint16_t _port;
    int _state;

    IOTPUBSUB_CALLBACK_SIGNATURE;

    // Internal frame methods
    boolean sendFrame(uint8_t msgType, const char* jsonPayload);
    boolean sendFrameNoPayload(uint8_t msgType);
    boolean readFrame(uint8_t* msgType, char* payload, uint16_t* payloadLen);
    boolean waitForResponse(uint8_t expectedType, char* payload, uint16_t* payloadLen);

public:
    IoTPubSubClient();
    IoTPubSubClient(Client& client);
    IoTPubSubClient(const char* domain, uint16_t port, Client& client);
    IoTPubSubClient(const char* domain, uint16_t port, IOTPUBSUB_CALLBACK_SIGNATURE, Client& client);

    ~IoTPubSubClient();

    // Configuration (chainable, matches PubSubClient pattern)
    IoTPubSubClient& setServer(const char* domain, uint16_t port);
    IoTPubSubClient& setServer(IPAddress ip, uint16_t port);
    IoTPubSubClient& setCallback(IOTPUBSUB_CALLBACK_SIGNATURE);
    IoTPubSubClient& setKeepAlive(uint16_t keepAlive);
    IoTPubSubClient& setSocketTimeout(uint16_t timeout);
    boolean setBufferSize(uint16_t size);
    uint16_t getBufferSize();

    // ── Connection ─────────────────────────────────────────────────────────

    /**
     * Authenticate with the broker using the custom protocol.
     * Uses 3-part auth: clientId, token, and secret.
     */
    boolean connect(const char* deviceId, const char* token, const char* secret);
    boolean connect(const char* deviceId, const char* token, const char* secret, const char* clientVersion);
    void disconnect();
    boolean connected();
    int state();

    // Publish (matches PubSubClient API)
    boolean publish(const char* topic, const char* payload);
    boolean publish(const char* topic, const uint8_t* payload, unsigned int plength);

    // Subscribe / Unsubscribe
    boolean subscribe(const char* topic);
    boolean unsubscribe(const char* topic);

    // Must be called in Arduino loop() — handles keepalive + incoming messages
    boolean loop();
};

#endif
