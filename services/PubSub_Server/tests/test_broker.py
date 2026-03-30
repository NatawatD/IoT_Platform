"""
Tests for the broker subscription manager.
"""

import pytest
from broker.subscriptions import SubscriptionManager


class TestSubscriptionManager:
    """Test topic subscription and wildcard matching."""

    def setup_method(self):
        self.sm = SubscriptionManager()

    def test_exact_match(self):
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/telemetry")
        subs = self.sm.get_subscribers("devices/ESP32_01/telemetry")
        assert "ESP32_01" in subs

    def test_no_match(self):
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/telemetry")
        subs = self.sm.get_subscribers("devices/ESP32_02/telemetry")
        assert len(subs) == 0

    def test_wildcard_hash(self):
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/commands/#")
        subs = self.sm.get_subscribers("devices/ESP32_01/commands/reboot")
        assert "ESP32_01" in subs

    def test_wildcard_hash_nested(self):
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/commands/#")
        subs = self.sm.get_subscribers("devices/ESP32_01/commands/set/interval")
        assert "ESP32_01" in subs

    def test_wildcard_hash_exact_prefix(self):
        """'#' wildcard should also match exact prefix without extra segments."""
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/commands/#")
        subs = self.sm.get_subscribers("devices/ESP32_01/commands")
        assert "ESP32_01" in subs

    def test_wildcard_universal(self):
        self.sm.subscribe("admin", "#")
        subs = self.sm.get_subscribers("any/topic/here")
        assert "admin" in subs

    def test_unsubscribe(self):
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/telemetry")
        self.sm.unsubscribe("ESP32_01", "devices/ESP32_01/telemetry")
        subs = self.sm.get_subscribers("devices/ESP32_01/telemetry")
        assert len(subs) == 0

    def test_remove_client(self):
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/telemetry")
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/commands/#")
        self.sm.remove_client("ESP32_01")
        assert len(self.sm.get_subscribers("devices/ESP32_01/telemetry")) == 0
        assert len(self.sm.get_subscribers("devices/ESP32_01/commands/reboot")) == 0

    def test_multiple_subscribers(self):
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/telemetry")
        self.sm.subscribe("dashboard", "devices/ESP32_01/telemetry")
        subs = self.sm.get_subscribers("devices/ESP32_01/telemetry")
        assert len(subs) == 2

    def test_client_subscriptions(self):
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/telemetry")
        self.sm.subscribe("ESP32_01", "devices/ESP32_01/commands/#")
        client_subs = self.sm.get_client_subscriptions("ESP32_01")
        assert len(client_subs) == 2
