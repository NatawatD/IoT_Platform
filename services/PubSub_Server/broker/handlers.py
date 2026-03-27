"""
Message handlers — process each message type from connected devices.
"""

import json
import logging
import time
from typing import TYPE_CHECKING

from protocol.constants import MessageType
from protocol.frames import encode_frame
from protocol.models import (
    ConnectPayload,
    ConnackPayload,
    PublishPayload,
    SubscribePayload,
    SubAckPayload,
    UnsubscribePayload,
    UnsubAckPayload,
)
from .acl import check_publish_acl, check_subscribe_acl
from .auth import verify_device_token

if TYPE_CHECKING:
    from .connection import ClientConnection

logger = logging.getLogger(__name__)


async def handle_connect(conn: "ClientConnection", payload: dict) -> bool:
    """
    Handle CONNECT message — authenticate the device.
    Returns True if authenticated, False otherwise.
    """
    try:
        connect_data = ConnectPayload(**payload)
    except Exception as e:
        logger.warning(f"Invalid CONNECT payload: {e}")
        response = ConnackPayload(status="error", reason="invalid_payload")
        frame = encode_frame(MessageType.CONNACK, response.model_dump())
        conn.writer.write(frame)
        await conn.writer.drain()
        return False

    logger.info(
        f"CONNECT from device '{connect_data.device_id}' "
        f"(version: {connect_data.client_version})"
    )

    # Verify token & secret (3-part auth)
    is_valid, reason = await verify_device_token(
        connect_data.device_id, connect_data.token, connect_data.secret
    )

    if is_valid:
        conn.device_id = connect_data.device_id
        conn.authenticated = True
        response = ConnackPayload(status="ok")
        logger.info(f"Device '{connect_data.device_id}' authenticated successfully")
    else:
        response = ConnackPayload(status="error", reason=reason)
        logger.warning(f"Device '{connect_data.device_id}' authentication failed: {reason}")

    frame = encode_frame(
        MessageType.CONNACK,
        response.model_dump(exclude_none=True),
    )
    conn.writer.write(frame)
    await conn.writer.drain()

    return is_valid


async def handle_publish(conn: "ClientConnection", payload: dict) -> None:
    """Handle PUBLISH message — check ACL, route to subscribers and Kafka."""
    try:
        pub_data = PublishPayload(**payload)
    except Exception as e:
        logger.warning(f"Invalid PUBLISH payload from '{conn.device_id}': {e}")
        return

    # ACL check
    if not check_publish_acl(conn.device_id, pub_data.topic):
        return  # silently rejected per Peem's spec

    logger.debug(f"PUBLISH from '{conn.device_id}' to '{pub_data.topic}'")

    # Route to local subscribers
    subscribers = conn.server.subscriptions.get_subscribers(pub_data.topic)
    for sub_client_id in subscribers:
        if sub_client_id == conn.device_id:
            continue  # don't echo back to sender
        sub_conn = conn.server.get_connection(sub_client_id)
        if sub_conn:
            try:
                frame = encode_frame(
                    MessageType.PUBLISH,
                    {"topic": pub_data.topic, "payload": pub_data.payload},
                )
                sub_conn.writer.write(frame)
                await sub_conn.writer.drain()
            except Exception as e:
                logger.error(f"Error forwarding to '{sub_client_id}': {e}")

    # Forward to Kafka (if bridge is available)
    if conn.server.kafka_producer:
        await conn.server.kafka_producer.send_message(pub_data.topic, pub_data.payload, conn.device_id)


async def handle_subscribe(conn: "ClientConnection", payload: dict) -> None:
    """Handle SUBSCRIBE message — register subscription with ACL check."""
    try:
        sub_data = SubscribePayload(**payload)
    except Exception as e:
        logger.warning(f"Invalid SUBSCRIBE payload from '{conn.device_id}': {e}")
        return

    # ACL check
    if not check_subscribe_acl(conn.device_id, sub_data.topic):
        response = SubAckPayload(topic=sub_data.topic, status="error")
        frame = encode_frame(MessageType.SUBACK, response.model_dump())
        conn.writer.write(frame)
        await conn.writer.drain()
        return

    conn.server.subscriptions.subscribe(conn.device_id, sub_data.topic)

    response = SubAckPayload(topic=sub_data.topic, status="ok")
    frame = encode_frame(MessageType.SUBACK, response.model_dump())
    conn.writer.write(frame)
    await conn.writer.drain()


async def handle_unsubscribe(conn: "ClientConnection", payload: dict) -> None:
    """Handle UNSUBSCRIBE message — remove subscription."""
    try:
        unsub_data = UnsubscribePayload(**payload)
    except Exception as e:
        logger.warning(f"Invalid UNSUBSCRIBE payload from '{conn.device_id}': {e}")
        return

    conn.server.subscriptions.unsubscribe(conn.device_id, unsub_data.topic)

    response = UnsubAckPayload(topic=unsub_data.topic, status="ok")
    frame = encode_frame(MessageType.UNSUBACK, response.model_dump())
    conn.writer.write(frame)
    await conn.writer.drain()


async def handle_pingreq(conn: "ClientConnection") -> None:
    """Handle PINGREQ — respond with PINGRESP."""
    frame = encode_frame(MessageType.PINGRESP)
    conn.writer.write(frame)
    await conn.writer.drain()
    logger.debug(f"PONG sent to '{conn.device_id}'")
