"""
Device authentication — verifies device tokens against the backend API.

The backend endpoint is provided by Peem/Jam's team. Until confirmed,
this module includes a stub mode that accepts any token for development.
"""

import logging
import os

import aiohttp

from config import config

logger = logging.getLogger(__name__)

# Stub mode for development (no backend available yet)
STUB_AUTH = os.getenv("STUB_AUTH", "true").lower() == "true"


async def verify_device_token(device_id: str, token: str, secret: str) -> tuple[bool, str]:
    """
    Verify a device's authentication token and secret.

    Args:
        device_id: The device identifier.
        token: The auth token to verify.
        secret: The device secret (3-part auth).

    Returns:
        Tuple of (is_valid, reason).
        - (True, "ok") if valid
        - (False, "reason string") if invalid
    """
    if STUB_AUTH:
        logger.warning(
            f"STUB AUTH: accepting device '{device_id}' without verification "
            f"(set STUB_AUTH=false to enable real auth)"
        )
        return True, "ok"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.AUTH_VERIFY_URL,
                json={"device_id": device_id, "token": token, "secret": secret},
                timeout=aiohttp.ClientTimeout(total=config.AUTH_TIMEOUT),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "ok":
                        logger.info(f"Device '{device_id}' authenticated successfully")
                        return True, "ok"
                    else:
                        reason = data.get("reason", "rejected")
                        logger.warning(f"Device '{device_id}' auth failed: {reason}")
                        return False, reason
                else:
                    logger.error(
                        f"Auth endpoint returned status {response.status} "
                        f"for device '{device_id}'"
                    )
                    return False, "auth_service_error"

    except aiohttp.ClientError as e:
        logger.error(f"Auth service connection error: {e}")
        return False, "auth_service_unavailable"
    except Exception as e:
        logger.error(f"Unexpected auth error: {e}")
        return False, "internal_error"
