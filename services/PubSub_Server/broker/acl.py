"""
Access Control List — enforces that devices can only publish to their own topic prefix.

ACL Rule (from Peem):
  A device authenticated as 'ESP32_01' can only publish to topics starting with
  'devices/ESP32_01/'. Publishing to another device's topic is silently rejected.
"""

import logging

logger = logging.getLogger(__name__)


def check_publish_acl(device_id: str, topic: str) -> bool:
    """
    Check if a device is allowed to publish to a given topic.

    Args:
        device_id: The authenticated device ID.
        topic: The topic the device wants to publish to.

    Returns:
        True if allowed, False if rejected.
    """
    allowed_prefix = f"devices/{device_id}/"

    if topic.startswith(allowed_prefix):
        return True

    logger.warning(
        f"ACL DENIED: device '{device_id}' tried to publish to '{topic}' "
        f"(allowed prefix: '{allowed_prefix}')"
    )
    return False


def check_subscribe_acl(device_id: str, topic_pattern: str) -> bool:
    """
    Check if a device is allowed to subscribe to a given topic pattern.

    Current rule: devices can only subscribe to their own prefix.
    This prevents a device from snooping on other devices' commands.

    Args:
        device_id: The authenticated device ID.
        topic_pattern: The topic pattern to subscribe to.

    Returns:
        True if allowed, False if rejected.
    """
    allowed_prefix = f"devices/{device_id}/"

    # Strip wildcard for prefix check
    check_topic = topic_pattern.rstrip("#").rstrip("/")
    allowed_check = allowed_prefix.rstrip("/")

    if check_topic.startswith(allowed_check):
        return True

    logger.warning(
        f"ACL DENIED: device '{device_id}' tried to subscribe to '{topic_pattern}' "
        f"(allowed prefix: '{allowed_prefix}')"
    )
    return False
