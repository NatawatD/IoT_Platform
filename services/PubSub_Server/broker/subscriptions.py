"""
Subscription manager — maps topics to connected clients with wildcard '#' support.
"""

import logging
from typing import Dict, Set

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """
    Manages topic subscriptions for all connected clients.
    Supports the '#' wildcard at the end of topic patterns
    (e.g. 'devices/ESP32_01/commands/#' matches 'devices/ESP32_01/commands/reboot').
    """

    def __init__(self):
        # topic_pattern -> set of client_ids
        self._subscriptions: Dict[str, Set[str]] = {}
        # client_id -> set of topic_patterns (for cleanup on disconnect)
        self._client_subs: Dict[str, Set[str]] = {}

    def subscribe(self, client_id: str, topic_pattern: str) -> None:
        """Add a subscription for a client."""
        if topic_pattern not in self._subscriptions:
            self._subscriptions[topic_pattern] = set()
        self._subscriptions[topic_pattern].add(client_id)

        if client_id not in self._client_subs:
            self._client_subs[client_id] = set()
        self._client_subs[client_id].add(topic_pattern)

        logger.info(f"Client '{client_id}' subscribed to '{topic_pattern}'")

    def unsubscribe(self, client_id: str, topic_pattern: str) -> None:
        """Remove a subscription for a client."""
        if topic_pattern in self._subscriptions:
            self._subscriptions[topic_pattern].discard(client_id)
            if not self._subscriptions[topic_pattern]:
                del self._subscriptions[topic_pattern]

        if client_id in self._client_subs:
            self._client_subs[client_id].discard(topic_pattern)

        logger.info(f"Client '{client_id}' unsubscribed from '{topic_pattern}'")

    def remove_client(self, client_id: str) -> None:
        """Remove all subscriptions for a disconnected client."""
        patterns = self._client_subs.pop(client_id, set())
        for pattern in patterns:
            if pattern in self._subscriptions:
                self._subscriptions[pattern].discard(client_id)
                if not self._subscriptions[pattern]:
                    del self._subscriptions[pattern]

        if patterns:
            logger.info(f"Removed all subscriptions for client '{client_id}'")

    def get_subscribers(self, topic: str) -> Set[str]:
        """
        Find all client_ids subscribed to a topic, including wildcard matches.

        Wildcard rules:
        - '#' at the end matches any remaining path segments
        - 'devices/ESP32_01/commands/#' matches:
          - 'devices/ESP32_01/commands/reboot'
          - 'devices/ESP32_01/commands/set_interval'
          - 'devices/ESP32_01/commands/a/b/c'
        - Exact match also works: 'devices/ESP32_01/telemetry'
        """
        subscribers: Set[str] = set()

        for pattern, clients in self._subscriptions.items():
            if self._matches(pattern, topic):
                subscribers.update(clients)

        return subscribers

    @staticmethod
    def _matches(pattern: str, topic: str) -> bool:
        """Check if a topic matches a subscription pattern."""
        # Exact match
        if pattern == topic:
            return True

        # Wildcard '#' — matches everything after the prefix
        if pattern.endswith("/#"):
            prefix = pattern[:-2]  # Remove '/#'
            # Topic must start with the prefix and have more segments
            if topic == prefix or topic.startswith(prefix + "/"):
                return True

        # Standalone '#' matches everything
        if pattern == "#":
            return True

        return False

    def get_client_subscriptions(self, client_id: str) -> Set[str]:
        """Get all topic patterns a client is subscribed to."""
        return self._client_subs.get(client_id, set()).copy()
