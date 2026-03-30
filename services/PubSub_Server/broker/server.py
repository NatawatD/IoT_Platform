"""
TCP Broker Server — the core asyncio TCP server.

Accepts device connections, manages the connection registry, and coordinates
with the subscription manager and Kafka bridge.
"""

import asyncio
import logging
from typing import Dict, Optional

from .connection import ClientConnection
from .subscriptions import SubscriptionManager
from config import config

logger = logging.getLogger(__name__)


class BrokerServer:
    """
    The main TCP broker server.

    Responsibilities:
    - Accept TCP connections from IoT devices
    - Manage the connection registry (device_id → ClientConnection)
    - Hold the shared SubscriptionManager
    - Hold a reference to the Kafka producer (if available)
    """

    def __init__(self):
        self.subscriptions = SubscriptionManager()
        self._connections: Dict[str, ClientConnection] = {}
        self._server: Optional[asyncio.AbstractServer] = None
        self.kafka_producer = None  # Set by main.py after Kafka init

    def register_connection(self, conn: ClientConnection) -> None:
        """Register an authenticated device connection."""
        if conn.device_id in self._connections:
            # Disconnect old connection (device reconnected)
            old = self._connections[conn.device_id]
            logger.warning(
                f"Device '{conn.device_id}' reconnecting — closing old connection"
            )
            try:
                old.writer.close()
            except Exception:
                pass
            self.subscriptions.remove_client(conn.device_id)

        self._connections[conn.device_id] = conn
        logger.info(
            f"Device '{conn.device_id}' registered "
            f"(total connections: {len(self._connections)})"
        )

    def unregister_connection(self, device_id: str) -> None:
        """Remove a device connection from the registry."""
        self._connections.pop(device_id, None)
        logger.info(
            f"Device '{device_id}' unregistered "
            f"(total connections: {len(self._connections)})"
        )

    def get_connection(self, device_id: str) -> Optional[ClientConnection]:
        """Get a connection by device ID."""
        return self._connections.get(device_id)

    def get_all_connections(self) -> Dict[str, ClientConnection]:
        """Get all active connections."""
        return self._connections.copy()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Callback for each new TCP connection."""
        conn = ClientConnection(reader, writer, self)
        await conn.run()

    async def start(self) -> None:
        """Start the TCP broker server."""
        self._server = await asyncio.start_server(
            self._handle_client,
            host=config.BROKER_HOST,
            port=config.BROKER_PORT,
        )

        addrs = ", ".join(str(s.getsockname()) for s in self._server.sockets)
        logger.info(f"🚀 TCP Broker listening on {addrs}")

        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        """Gracefully stop the broker."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Broker server stopped")

        # Close all client connections
        for device_id, conn in list(self._connections.items()):
            try:
                conn.writer.close()
                await conn.writer.wait_closed()
            except Exception:
                pass
            logger.info(f"Closed connection to '{device_id}'")

        self._connections.clear()
