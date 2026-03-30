"""
Per-client TCP connection handler.

Each connected device gets a ClientConnection instance that runs a read loop,
dispatching incoming frames to the appropriate handler.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from protocol.constants import MessageType
from protocol.frames import read_frame, ProtocolError
from .handlers import (
    handle_connect,
    handle_publish,
    handle_subscribe,
    handle_unsubscribe,
    handle_pingreq,
)

if TYPE_CHECKING:
    from .server import BrokerServer

logger = logging.getLogger(__name__)


class ClientConnection:
    """Represents a single device connection to the broker."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        server: "BrokerServer",
    ):
        self.reader = reader
        self.writer = writer
        self.server = server
        self.device_id: str | None = None
        self.authenticated: bool = False
        self.connected_at: float = time.time()

        # Get peer address for logging
        peername = writer.get_extra_info("peername")
        self.addr: str = f"{peername[0]}:{peername[1]}" if peername else "unknown"

    async def run(self) -> None:
        """
        Main read loop for this connection.
        First message must be CONNECT; then we dispatch all subsequent messages.
        """
        logger.info(f"New TCP connection from {self.addr}")

        try:
            # ── Step 1: Wait for CONNECT ─────────────────────────────────
            msg_type, flags, payload = await asyncio.wait_for(
                read_frame(self.reader),
                timeout=10.0,  # 10s to send CONNECT
            )

            if msg_type != MessageType.CONNECT:
                logger.warning(
                    f"First message from {self.addr} was {msg_type.name}, "
                    f"expected CONNECT. Closing."
                )
                return

            authenticated = await handle_connect(self, payload)
            if not authenticated:
                return

            # Register this connection
            self.server.register_connection(self)

            # Notify device status (online)
            if self.server.kafka_producer:
                await self.server.kafka_producer.send_status(
                    self.device_id, "online"
                )

            # ── Step 2: Message dispatch loop ────────────────────────────
            while True:
                try:
                    msg_type, flags, payload = await asyncio.wait_for(
                        read_frame(self.reader),
                        timeout=120.0,  # 2x keepalive timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Device '{self.device_id}' timed out (no keepalive)"
                    )
                    break

                if msg_type == MessageType.PUBLISH:
                    await handle_publish(self, payload)

                elif msg_type == MessageType.SUBSCRIBE:
                    await handle_subscribe(self, payload)

                elif msg_type == MessageType.UNSUBSCRIBE:
                    await handle_unsubscribe(self, payload)

                elif msg_type == MessageType.PINGREQ:
                    await handle_pingreq(self)

                elif msg_type == MessageType.DISCONNECT:
                    logger.info(f"Device '{self.device_id}' sent DISCONNECT")
                    break

                else:
                    logger.warning(
                        f"Unexpected message type {msg_type.name} "
                        f"from '{self.device_id}'"
                    )

        except asyncio.IncompleteReadError:
            logger.info(f"Connection closed by {self.addr} (device: {self.device_id})")
        except ProtocolError as e:
            logger.error(f"Protocol error from {self.addr}: {e}")
        except asyncio.TimeoutError:
            logger.warning(f"Connection from {self.addr} timed out waiting for CONNECT")
        except Exception as e:
            logger.error(f"Unexpected error from {self.addr}: {e}", exc_info=True)
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up on disconnect."""
        if self.device_id:
            self.server.subscriptions.remove_client(self.device_id)
            self.server.unregister_connection(self.device_id)

            # Notify device status (offline)
            if self.server.kafka_producer:
                await self.server.kafka_producer.send_status(
                    self.device_id, "offline"
                )

            logger.info(f"Device '{self.device_id}' disconnected from {self.addr}")

        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
