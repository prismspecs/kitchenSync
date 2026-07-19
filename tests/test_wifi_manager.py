#!/usr/bin/env python3
"""Tests for the WiFi provisioning bootstrap (docs/WIFI_PROVISIONING.md)."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from networking import wifi_manager
from networking.wifi_manager import (
    CLUSTER_CON_NAME,
    HOTSPOT_CON_NAME,
    WifiManager,
    _split_terse,
    cluster_ssid,
    ensure_network,
)


class FakeConfig:
    def __init__(self, is_leader=False, wifi_ssid="", wifi_password="",
                 cluster_name="ksync", hotspot_password="kitchensync"):
        self.is_leader = is_leader
        self.wifi_ssid = wifi_ssid
        self.wifi_password = wifi_password
        self.cluster_name = cluster_name
        self.hotspot_password = hotspot_password


def make_manager(**overrides):
    """A fully-stubbed WifiManager in the 'no network yet' state."""
    mgr = MagicMock(spec=WifiManager)
    mgr.available.return_value = True
    mgr.ethernet_connected.return_value = False
    mgr.wifi_device.return_value = "wlan0"
    mgr.wifi_connected_ssid.return_value = None
    mgr.saved_wifi_profiles.return_value = []
    mgr.connect.return_value = False
    mgr.start_hotspot.return_value = True
    for name, value in overrides.items():
        getattr(mgr, name).return_value = value
    return mgr


class TestSplitTerse(unittest.TestCase):
    def test_plain_fields(self):
        self.assertEqual(_split_terse("eth0:ethernet:connected"), ["eth0", "ethernet", "connected"])

    def test_escaped_colon_in_ssid(self):
        self.assertEqual(_split_terse(r"my\:net:70:WPA2"), ["my:net", "70", "WPA2"])

    def test_empty_fields(self):
        self.assertEqual(_split_terse("::"), ["", "", ""])


class TestWifiManagerParsing(unittest.TestCase):
    def _mgr_with_output(self, stdout, returncode=0):
        mgr = WifiManager()
        result = MagicMock(returncode=returncode, stdout=stdout, stderr="")
        mgr._run = MagicMock(return_value=result)
        return mgr

    def test_ethernet_connected(self):
        mgr = self._mgr_with_output("eth0:ethernet:connected\nwlan0:wifi:disconnected\n")
        self.assertTrue(mgr.ethernet_connected())

    def test_ethernet_unplugged(self):
        mgr = self._mgr_with_output("eth0:ethernet:unavailable\nwlan0:wifi:disconnected\n")
        self.assertFalse(mgr.ethernet_connected())

    def test_wifi_device_detection(self):
        mgr = self._mgr_with_output("eth0:ethernet:unavailable\nwlan0:wifi:disconnected\n")
        self.assertEqual(mgr.wifi_device(), "wlan0")

    def test_wifi_connected_ssid_ignores_hotspot(self):
        mgr = self._mgr_with_output(f"{HOTSPOT_CON_NAME}:802-11-wireless:wlan0\n")
        self.assertIsNone(mgr.wifi_connected_ssid())

    def test_wifi_connected_ssid(self):
        mgr = self._mgr_with_output("MuseumNet:802-11-wireless:wlan0\n")
        self.assertEqual(mgr.wifi_connected_ssid(), "MuseumNet")

    def test_saved_profiles_exclude_hotspot(self):
        mgr = self._mgr_with_output(
            f"MuseumNet:802-11-wireless\n{HOTSPOT_CON_NAME}:802-11-wireless\nWired:802-3-ethernet\n"
        )
        self.assertEqual(mgr.saved_wifi_profiles(), ["MuseumNet"])


class TestEnsureNetwork(unittest.TestCase):
    def setUp(self):
        os.environ.pop("KSYNC_NO_NETWORK_BOOTSTRAP", None)
        # Collaborator join-wait polls until a deadline; keep tests instant.
        self._orig_join_wait = wifi_manager.JOIN_WAIT_SECONDS
        self._orig_auto_wait = wifi_manager.AUTOCONNECT_WAIT_SECONDS
        wifi_manager.JOIN_WAIT_SECONDS = 0
        wifi_manager.AUTOCONNECT_WAIT_SECONDS = 0

    def tearDown(self):
        os.environ.pop("KSYNC_NO_NETWORK_BOOTSTRAP", None)
        wifi_manager.JOIN_WAIT_SECONDS = self._orig_join_wait
        wifi_manager.AUTOCONNECT_WAIT_SECONDS = self._orig_auto_wait

    def test_env_var_skips_bootstrap(self):
        os.environ["KSYNC_NO_NETWORK_BOOTSTRAP"] = "1"
        self.assertEqual(ensure_network(FakeConfig(), manager=make_manager()), "skipped")

    def test_no_networkmanager_skips(self):
        mgr = make_manager(available=False)
        self.assertEqual(ensure_network(FakeConfig(), manager=mgr), "skipped")

    def test_ethernet_wins(self):
        mgr = make_manager(ethernet_connected=True)
        self.assertEqual(ensure_network(FakeConfig(is_leader=True), manager=mgr), "ethernet")
        mgr.start_hotspot.assert_not_called()

    def test_already_on_wifi(self):
        mgr = make_manager(wifi_connected_ssid="MuseumNet")
        self.assertEqual(ensure_network(FakeConfig(), manager=mgr), "wifi")
        mgr.connect.assert_not_called()

    def test_no_interfaces_is_offline(self):
        mgr = make_manager(wifi_device=None)
        self.assertEqual(ensure_network(FakeConfig(), manager=mgr), "offline")

    def test_usb_venue_credentials_used_first(self):
        mgr = make_manager(connect=True)
        config = FakeConfig(wifi_ssid="MuseumNet", wifi_password="secret123")
        self.assertEqual(ensure_network(config, manager=mgr), "wifi")
        mgr.connect.assert_called_once_with("MuseumNet", "secret123")

    def test_leader_falls_back_to_hotspot(self):
        mgr = make_manager()
        config = FakeConfig(is_leader=True, cluster_name="gallery")
        self.assertEqual(ensure_network(config, manager=mgr), "hotspot")
        mgr.start_hotspot.assert_called_once_with("kSync-gallery", "kitchensync")

    def test_leader_hotspot_failure_is_offline(self):
        mgr = make_manager(start_hotspot=False)
        self.assertEqual(ensure_network(FakeConfig(is_leader=True), manager=mgr), "offline")

    def test_collaborator_seeds_cluster_profile(self):
        mgr = make_manager()
        config = FakeConfig(is_leader=False, cluster_name="gallery")
        self.assertEqual(ensure_network(config, manager=mgr), "searching")
        mgr.ensure_profile.assert_called_once_with(
            "kSync-gallery", "kitchensync", CLUSTER_CON_NAME
        )
        mgr.start_hotspot.assert_not_called()

    def test_collaborator_joins_when_leader_appears(self):
        mgr = make_manager()
        wifi_manager.JOIN_WAIT_SECONDS = 10
        # Not connected on the pre-check, connected once inside the join wait.
        mgr.wifi_connected_ssid.side_effect = [None, "kSync-gallery"]
        with patch.object(wifi_manager.time, "sleep"):
            result = ensure_network(FakeConfig(cluster_name="gallery"), manager=mgr)
        self.assertEqual(result, "wifi")

    def test_manager_exception_degrades_to_skipped(self):
        mgr = make_manager()
        mgr.ethernet_connected.side_effect = RuntimeError("boom")
        self.assertEqual(ensure_network(FakeConfig(), manager=mgr), "skipped")

    def test_cluster_ssid_format(self):
        self.assertEqual(cluster_ssid("gallery"), "kSync-gallery")


if __name__ == "__main__":
    unittest.main()
