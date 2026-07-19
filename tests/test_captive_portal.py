#!/usr/bin/env python3
"""Tests for the captive portal, credential push, and network watchdogs."""

import http.client
import json
import sys
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from networking import captive_portal, wifi_manager
from networking.captive_portal import CaptivePortalServer, WifiProvisioner
from networking.wifi_manager import (
    VENUE_CON_NAME,
    WifiManager,
    handle_wifi_provision,
    start_collaborator_network_watchdog,
)


class FakeConfig:
    is_leader = True
    cluster_name = "gallery"
    hotspot_password = "kitchensync"
    wifi_ssid = ""
    wifi_password = ""
    device_id = "pi-test"


class FakeCommandManager:
    def __init__(self):
        self.collaborators = {"pi-a": {}, "pi-b": {}}
        self.handlers = {}
        self.sent = []

    def register_handler(self, msg_type, handler):
        self.handlers[msg_type] = handler

    def send_command(self, command, target_pi=None):
        self.sent.append(command)


def make_wifi_mgr(**overrides):
    mgr = MagicMock(spec=WifiManager)
    mgr.available.return_value = True
    mgr.connect.return_value = True
    mgr.start_hotspot.return_value = True
    mgr.venue_active.return_value = True
    for name, value in overrides.items():
        getattr(mgr, name).return_value = value
    return mgr


class TestWifiProvisioner(unittest.TestCase):
    def setUp(self):
        self._orig = (captive_portal.MIGRATE_DELAY_SECONDS,
                      captive_portal.PUSH_INTERVAL_SECONDS,
                      captive_portal.MIGRATE_HEADSTART_SECONDS)
        captive_portal.MIGRATE_DELAY_SECONDS = 0.3
        captive_portal.PUSH_INTERVAL_SECONDS = 0.05
        captive_portal.MIGRATE_HEADSTART_SECONDS = 0.05

    def tearDown(self):
        (captive_portal.MIGRATE_DELAY_SECONDS,
         captive_portal.PUSH_INTERVAL_SECONDS,
         captive_portal.MIGRATE_HEADSTART_SECONDS) = self._orig

    def _run_provision(self, mgr):
        cm = FakeCommandManager()
        prov = WifiProvisioner(FakeConfig(), cm, mgr)
        self.assertTrue(prov.begin("MuseumNet", "secret123"))
        deadline = time.monotonic() + 5
        while prov.status()["state"] in ("pushing", "migrating") and time.monotonic() < deadline:
            time.sleep(0.05)
        return prov, cm

    def test_push_sends_and_migrates(self):
        mgr = make_wifi_mgr()
        prov, cm = self._run_provision(mgr)
        self.assertEqual(prov.status()["state"], "done")
        self.assertGreaterEqual(len(cm.sent), 1)
        msg = cm.sent[0]
        self.assertEqual(msg["type"], "wifi_provision")
        self.assertEqual(msg["ssid"], "MuseumNet")
        self.assertEqual(msg["psk"], "secret123")
        self.assertIn("token", msg)
        mgr.stop_hotspot.assert_called_once()
        mgr.connect.assert_called_once()

    def test_failed_migration_restores_hotspot(self):
        mgr = make_wifi_mgr(connect=False)
        prov, _ = self._run_provision(mgr)
        self.assertEqual(prov.status()["state"], "failed")
        mgr.start_hotspot.assert_called_once_with("kSync-gallery", "kitchensync")

    def test_acks_are_tracked_by_token(self):
        cm = FakeCommandManager()
        prov = WifiProvisioner(FakeConfig(), cm, make_wifi_mgr())
        prov.token = "tok1"
        cm.handlers["wifi_provision_ack"]({"device_id": "pi-a", "token": "tok1"}, ("10.42.0.2", 5006))
        cm.handlers["wifi_provision_ack"]({"device_id": "pi-b", "token": "WRONG"}, ("10.42.0.3", 5006))
        status = prov.status()
        self.assertEqual(status["devices_acked"], 1)
        self.assertEqual(status["acked"], ["pi-a"])
        self.assertEqual(status["devices_total"], 2)

    def test_begin_rejects_concurrent_push(self):
        prov = WifiProvisioner(FakeConfig(), FakeCommandManager(), make_wifi_mgr())
        prov.state = "pushing"
        self.assertFalse(prov.begin("Other", "pw"))


class TestHandleWifiProvision(unittest.TestCase):
    def setUp(self):
        wifi_manager._seen_provision_tokens.clear()

    def _msg(self, token="tok", migrate_at=None):
        return {"type": "wifi_provision", "ssid": "MuseumNet", "psk": "secret123",
                "token": token, "migrate_at": migrate_at or time.time()}

    def test_acks_and_schedules_apply(self):
        mgr = make_wifi_mgr()
        acks = []
        result = handle_wifi_provision(self._msg(), FakeConfig(), acks.append, mgr)
        self.assertTrue(result)
        self.assertEqual(acks, ["tok"])
        time.sleep(0.2)  # Timer with ~0 delay
        mgr.connect.assert_called_once_with("MuseumNet", "secret123", VENUE_CON_NAME, priority=100)

    def test_duplicate_token_reacks_without_reapplying(self):
        mgr = make_wifi_mgr()
        acks = []
        handle_wifi_provision(self._msg(), FakeConfig(), acks.append, mgr)
        time.sleep(0.2)
        handle_wifi_provision(self._msg(), FakeConfig(), acks.append, mgr)
        time.sleep(0.2)
        self.assertEqual(acks, ["tok", "tok"])
        self.assertEqual(mgr.connect.call_count, 1)

    def test_invalid_message_not_acked(self):
        acks = []
        self.assertFalse(handle_wifi_provision({"type": "wifi_provision"}, FakeConfig(), acks.append))
        self.assertEqual(acks, [])

    def test_failed_join_reverts_to_cluster(self):
        mgr = make_wifi_mgr(connect=False)
        handle_wifi_provision(self._msg(), FakeConfig(), lambda t: None, mgr)
        time.sleep(0.2)
        mgr.revert_to_cluster.assert_called_once_with("kSync-gallery", "kitchensync")


class TestCollaboratorWatchdog(unittest.TestCase):
    def setUp(self):
        self._orig_grace = wifi_manager.OFFLINE_GRACE_SECONDS
        wifi_manager.OFFLINE_GRACE_SECONDS = 0.05

    def tearDown(self):
        wifi_manager.OFFLINE_GRACE_SECONDS = self._orig_grace

    def _run_watchdog(self, mgr, contact_active, cycles=5):
        start_collaborator_network_watchdog(
            FakeConfig(), contact_active, manager=mgr, interval=0.02
        )
        time.sleep(0.02 * cycles + 0.2)

    def test_reverts_when_leader_silent_on_venue(self):
        mgr = make_wifi_mgr()
        self._run_watchdog(mgr, lambda: False)
        mgr.revert_to_cluster.assert_called_with("kSync-gallery", "kitchensync")

    def test_no_revert_while_leader_active(self):
        mgr = make_wifi_mgr()
        self._run_watchdog(mgr, lambda: True)
        mgr.revert_to_cluster.assert_not_called()

    def test_no_revert_off_venue(self):
        mgr = make_wifi_mgr(venue_active=False)
        self._run_watchdog(mgr, lambda: False)
        mgr.revert_to_cluster.assert_not_called()


class TestCaptivePortalHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.command_manager = FakeCommandManager()
        cls.provisioner = WifiProvisioner(FakeConfig(), cls.command_manager, make_wifi_mgr())
        cls.portal = CaptivePortalServer(FakeConfig(), cls.provisioner, port=0)
        # Bind a single ephemeral-port server directly (start() would also try 80)
        handler = cls.portal._make_handler()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response, data

    def test_setup_page_serves_form(self):
        response, data = self._request("GET", "/setup/wifi")
        self.assertEqual(response.status, 200)
        self.assertIn(b"kSync", data)
        self.assertIn(b"form", data)
        self.assertIn(b"gallery", data)

    def test_connectivity_probe_redirects(self):
        for path in ["/generate_204", "/hotspot-detect.html", "/connecttest.txt", "/anything"]:
            response, _ = self._request("GET", path)
            self.assertEqual(response.status, 302, path)
            self.assertEqual(response.getheader("Location"), "/setup/wifi")

    def test_status_endpoint_returns_json(self):
        response, data = self._request("GET", "/api/wifi/status")
        self.assertEqual(response.status, 200)
        status = json.loads(data)
        self.assertIn("state", status)
        self.assertEqual(status["devices_total"], 2)

    def test_post_starts_provisioning(self):
        with patch.object(self.provisioner, "begin") as begin:
            response, _ = self._request("POST", "/setup/wifi",
                                        body="ssid=MuseumNet&password=secret123")
            self.assertEqual(response.status, 302)
            begin.assert_called_once_with("MuseumNet", "secret123")

    def test_post_manual_ssid_overrides_dropdown(self):
        with patch.object(self.provisioner, "begin") as begin:
            self._request("POST", "/setup/wifi",
                          body="ssid=Listed&ssid_manual=Typed+Net&password=pw")
            begin.assert_called_once_with("Typed Net", "pw")

    def test_post_without_ssid_is_ignored(self):
        with patch.object(self.provisioner, "begin") as begin:
            self._request("POST", "/setup/wifi", body="ssid=&password=pw")
            begin.assert_not_called()


if __name__ == "__main__":
    unittest.main()
