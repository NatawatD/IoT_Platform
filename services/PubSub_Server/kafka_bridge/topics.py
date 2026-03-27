"""
Kafka topic name constants.
"""

# Sensor telemetry from devices (PUB on devices/{id}/telemetry)
TOPIC_TELEMETRY = "iot.telemetry"

# Device status events (online/offline)
TOPIC_DEVICE_STATUS = "iot.device-events"

# Commands to be routed to devices (from HTTP API → Kafka → broker → device)
TOPIC_COMMANDS = "iot.commands"

# Command responses (from device → broker → Kafka → HTTP API)
TOPIC_CMD_RESPONSES = "iot.cmd-responses"
