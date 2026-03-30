/*
 * IoTPubSubClient.cpp — Implementation
 * ======================================
 * ⚠️ LIBRARY DESIGN DELIVERABLE
 *
 * Implements the custom binary TCP protocol to communicate with PubSub_Server.
 * Frame format: [type:1B][flags:1B][len_hi:1B][len_lo:1B][JSON payload:NB]
 */

#include "IoTPubSubClient.h"

// ── Constructors / Destructor ───────────────────────────────────────────────

IoTPubSubClient::IoTPubSubClient() {
    _state = IOT_DISCONNECTED;
    _client = nullptr;
    _domain = nullptr;
    _port = 9000;
    _buffer = nullptr;
    _bufferSize = 0;
    _keepAlive = IOT_KEEPALIVE;
    _socketTimeout = IOT_SOCKET_TIMEOUT;
    _pingOutstanding = false;
    _lastInActivity = 0;
    _lastOutActivity = 0;
    callback = nullptr;
    setBufferSize(IOT_MAX_PACKET_SIZE);
}

IoTPubSubClient::IoTPubSubClient(Client& client) : IoTPubSubClient() {
    _client = &client;
}

IoTPubSubClient::IoTPubSubClient(const char* domain, uint16_t port, Client& client)
    : IoTPubSubClient(client) {
    setServer(domain, port);
}

IoTPubSubClient::IoTPubSubClient(const char* domain, uint16_t port,
                                 IOTPUBSUB_CALLBACK_SIGNATURE, Client& client)
    : IoTPubSubClient(domain, port, client) {
    setCallback(callback);
}

IoTPubSubClient::~IoTPubSubClient() {
    free(_buffer);
}

// ── Configuration ───────────────────────────────────────────────────────────

IoTPubSubClient& IoTPubSubClient::setServer(const char* domain, uint16_t port) {
    _domain = domain;
    _port = port;
    return *this;
}

IoTPubSubClient& IoTPubSubClient::setServer(IPAddress ip, uint16_t port) {
    _ip = ip;
    _domain = nullptr;
    _port = port;
    return *this;
}

IoTPubSubClient& IoTPubSubClient::setCallback(IOTPUBSUB_CALLBACK_SIGNATURE) {
    this->callback = callback;
    return *this;
}

IoTPubSubClient& IoTPubSubClient::setKeepAlive(uint16_t keepAlive) {
    _keepAlive = keepAlive;
    return *this;
}

IoTPubSubClient& IoTPubSubClient::setSocketTimeout(uint16_t timeout) {
    _socketTimeout = timeout;
    return *this;
}

boolean IoTPubSubClient::setBufferSize(uint16_t size) {
    if (size == 0) return false;
    if (_buffer) free(_buffer);
    _buffer = (uint8_t*)malloc(size);
    if (!_buffer) {
        _bufferSize = 0;
        return false;
    }
    _bufferSize = size;
    return true;
}

uint16_t IoTPubSubClient::getBufferSize() {
    return _bufferSize;
}

// ── Internal Frame Methods ──────────────────────────────────────────────────

boolean IoTPubSubClient::sendFrame(uint8_t msgType, const char* jsonPayload) {
    if (!_client || !_client->connected()) return false;

    uint16_t payloadLen = strlen(jsonPayload);
    if (payloadLen + IOT_HEADER_SIZE > _bufferSize) return false;

    // Build header: [type, flags=0x00, len_hi, len_lo]
    _buffer[0] = msgType;
    _buffer[1] = 0x00;  // flags reserved
    _buffer[2] = (payloadLen >> 8) & 0xFF;  // big-endian high byte
    _buffer[3] = payloadLen & 0xFF;         // big-endian low byte

    // Copy payload after header
    memcpy(_buffer + IOT_HEADER_SIZE, jsonPayload, payloadLen);

    size_t written = _client->write(_buffer, IOT_HEADER_SIZE + payloadLen);
    _lastOutActivity = millis();
    return (written == IOT_HEADER_SIZE + payloadLen);
}

boolean IoTPubSubClient::sendFrameNoPayload(uint8_t msgType) {
    if (!_client || !_client->connected()) return false;

    _buffer[0] = msgType;
    _buffer[1] = 0x00;
    _buffer[2] = 0x00;
    _buffer[3] = 0x00;

    size_t written = _client->write(_buffer, IOT_HEADER_SIZE);
    _lastOutActivity = millis();
    return (written == IOT_HEADER_SIZE);
}

boolean IoTPubSubClient::readFrame(uint8_t* msgType, char* payload, uint16_t* payloadLen) {
    // Read 4-byte header
    uint8_t header[IOT_HEADER_SIZE];
    for (int i = 0; i < IOT_HEADER_SIZE; i++) {
        unsigned long startWait = millis();
        while (!_client->available()) {
            if (millis() - startWait >= (unsigned long)_socketTimeout * 1000UL) {
                return false;
            }
            yield();
        }
        header[i] = _client->read();
    }

    *msgType = header[0];
    uint16_t pLen = ((uint16_t)header[2] << 8) | header[3];
    *payloadLen = pLen;

    if (pLen == 0) {
        payload[0] = '\0';
        _lastInActivity = millis();
        return true;
    }

    if (pLen >= _bufferSize) return false;  // too large

    // Read payload bytes
    for (uint16_t i = 0; i < pLen; i++) {
        unsigned long startWait = millis();
        while (!_client->available()) {
            if (millis() - startWait >= (unsigned long)_socketTimeout * 1000UL) {
                return false;
            }
            yield();
        }
        payload[i] = _client->read();
    }
    payload[pLen] = '\0';

    _lastInActivity = millis();
    return true;
}

boolean IoTPubSubClient::waitForResponse(uint8_t expectedType, char* payload, uint16_t* payloadLen) {
    unsigned long startWait = millis();
    while (!_client->available()) {
        if (millis() - startWait >= (unsigned long)_socketTimeout * 1000UL) {
            return false;
        }
        yield();
    }

    uint8_t receivedType;
    if (!readFrame(&receivedType, payload, payloadLen)) return false;
    return (receivedType == expectedType);
}

// ── Connection ──────────────────────────────────────────────────────────────

boolean IoTPubSubClient::connect(const char* deviceId, const char* token, const char* secret) {
    return connect(deviceId, token, secret, "1.0");
}

boolean IoTPubSubClient::connect(const char* deviceId, const char* token, const char* secret, const char* clientVersion) {
    if (connected()) {
        return true;
    }

    if (!_client) {
        _state = IOT_CONNECT_FAILED;
        return false;
    }

    // TCP connect
    if (!_client->connected()) {
        int result = 0;
        if (_domain != nullptr) {
            result = _client->connect(_domain, _port);
        } else {
            result = _client->connect(_ip, _port);
        }
        if (result != 1) {
            _state = IOT_CONNECT_FAILED;
            return false;
        }
    }

    // Build CONNECT JSON payload
    StaticJsonDocument<256> doc;
    doc["device_id"] = deviceId;
    doc["token"] = token;
    if (clientVersion) {
        doc["client_version"] = clientVersion;
    }

    char jsonBuf[256];
    serializeJson(doc, jsonBuf, sizeof(jsonBuf));

    // Send CONNECT frame
    if (!sendFrame(IOT_MSG_CONNECT, jsonBuf)) {
        _client->stop();
        _state = IOT_CONNECT_FAILED;
        return false;
    }

    // Wait for CONNACK
    char responseBuf[256];
    uint16_t responseLen;
    if (!waitForResponse(IOT_MSG_CONNACK, responseBuf, &responseLen)) {
        _state = IOT_CONNECTION_TIMEOUT;
        _client->stop();
        return false;
    }

    // Parse CONNACK response
    StaticJsonDocument<256> respDoc;
    DeserializationError err = deserializeJson(respDoc, responseBuf);
    if (err) {
        _state = IOT_CONNECT_REJECTED;
        _client->stop();
        return false;
    }

    const char* status = respDoc["status"] | "error";
    if (strcmp(status, "ok") == 0) {
        _state = IOT_CONNECTED;
        _lastInActivity = millis();
        _lastOutActivity = millis();
        _pingOutstanding = false;
        return true;
    } else {
        _state = IOT_CONNECT_BAD_TOKEN;
        _client->stop();
        return false;
    }
}

void IoTPubSubClient::disconnect() {
    sendFrameNoPayload(IOT_MSG_DISCONNECT);
    _state = IOT_DISCONNECTED;
    _client->stop();
}

boolean IoTPubSubClient::connected() {
    if (_client == nullptr) return false;
    if (!_client->connected()) {
        if (_state == IOT_CONNECTED) {
            _state = IOT_CONNECTION_LOST;
            _client->stop();
        }
        return false;
    }
    return (_state == IOT_CONNECTED);
}

int IoTPubSubClient::state() {
    return _state;
}

// ── Publish ─────────────────────────────────────────────────────────────────

boolean IoTPubSubClient::publish(const char* topic, const char* payload) {
    if (!connected()) return false;

    // Build PUBLISH JSON: {"topic":"...","payload":{...}} or {"topic":"...","payload":"..."}
    // We construct the JSON manually to support arbitrary payload strings
    // that might themselves be JSON
    String json = "{\"topic\":\"";
    json += topic;
    json += "\",\"payload\":";

    // Try to determine if payload is already a JSON object/array
    if (payload[0] == '{' || payload[0] == '[') {
        json += payload;
    } else {
        json += "\"";
        json += payload;
        json += "\"";
    }
    json += "}";

    return sendFrame(IOT_MSG_PUBLISH, json.c_str());
}

boolean IoTPubSubClient::publish(const char* topic, const uint8_t* payload, unsigned int plength) {
    // Convert binary payload to string and publish
    char* strPayload = (char*)malloc(plength + 1);
    if (!strPayload) return false;
    memcpy(strPayload, payload, plength);
    strPayload[plength] = '\0';
    boolean result = publish(topic, strPayload);
    free(strPayload);
    return result;
}

// ── Subscribe / Unsubscribe ─────────────────────────────────────────────────

boolean IoTPubSubClient::subscribe(const char* topic) {
    if (!connected()) return false;

    StaticJsonDocument<256> doc;
    doc["topic"] = topic;

    char jsonBuf[256];
    serializeJson(doc, jsonBuf, sizeof(jsonBuf));

    if (!sendFrame(IOT_MSG_SUBSCRIBE, jsonBuf)) return false;

    // Wait for SUBACK
    char responseBuf[256];
    uint16_t responseLen;
    if (!waitForResponse(IOT_MSG_SUBACK, responseBuf, &responseLen)) return false;

    StaticJsonDocument<256> respDoc;
    if (deserializeJson(respDoc, responseBuf)) return false;

    const char* status = respDoc["status"] | "error";
    return (strcmp(status, "ok") == 0);
}

boolean IoTPubSubClient::unsubscribe(const char* topic) {
    if (!connected()) return false;

    StaticJsonDocument<256> doc;
    doc["topic"] = topic;

    char jsonBuf[256];
    serializeJson(doc, jsonBuf, sizeof(jsonBuf));

    if (!sendFrame(IOT_MSG_UNSUBSCRIBE, jsonBuf)) return false;

    // Wait for UNSUBACK
    char responseBuf[256];
    uint16_t responseLen;
    if (!waitForResponse(IOT_MSG_UNSUBACK, responseBuf, &responseLen)) return false;

    return true;
}

// ── Loop (must be called in Arduino loop()) ─────────────────────────────────

boolean IoTPubSubClient::loop() {
    if (!connected()) return false;

    unsigned long t = millis();

    // ── Keepalive: send PINGREQ if idle ──
    if ((t - _lastOutActivity > (unsigned long)_keepAlive * 1000UL) ||
        (t - _lastInActivity > (unsigned long)_keepAlive * 1000UL)) {
        if (_pingOutstanding) {
            _state = IOT_CONNECTION_TIMEOUT;
            _client->stop();
            return false;
        } else {
            sendFrameNoPayload(IOT_MSG_PINGREQ);
            _pingOutstanding = true;
        }
    }

    // ── Process incoming frames ──
    while (_client->available()) {
        uint8_t msgType;
        char payload[IOT_MAX_PACKET_SIZE];
        uint16_t payloadLen;

        if (!readFrame(&msgType, payload, &payloadLen)) {
            return false;
        }

        switch (msgType) {

            case IOT_MSG_PINGRESP:
                _pingOutstanding = false;
                break;

            case IOT_MSG_PUBLISH: {
                // Incoming message from broker (e.g. a command)
                if (callback) {
                    StaticJsonDocument<512> doc;
                    DeserializationError err = deserializeJson(doc, payload);
                    if (!err) {
                        const char* topic = doc["topic"] | "";
                        // Serialize the inner payload back to string for callback
                        String innerPayload;
                        serializeJson(doc["payload"], innerPayload);
                        callback(topic,
                                 (const uint8_t*)innerPayload.c_str(),
                                 innerPayload.length());
                    }
                }
                break;
            }

            case IOT_MSG_PUBACK:
                // Publish acknowledged — currently we don't block on PUBACK
                break;

            default:
                // Ignore unknown message types
                break;
        }
    }

    return true;
}
