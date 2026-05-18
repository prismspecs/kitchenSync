#!/usr/bin/env python3
"""Regression tests for KitchenSync networking."""

import json
import socket
import sys
import threading
import time
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from networking.communication import CommandListener, CommandManager


class TestCommandListener(unittest.TestCase):
    def test_large_start_command_is_received_intact(self):
        """Large start commands should not be truncated by the UDP receive buffer."""
        listener = CommandListener(control_port=0)
        received = {}
        message_seen = threading.Event()

        def callback(msg, _addr):
            received["msg"] = msg
            message_seen.set()

        listener.register_callback(callback)
        listener.start_listening()

        try:
            port = listener.control_sock.getsockname()[1]
            schedule = [
                {
                    "time": index * 0.5,
                    "note": 60 + (index % 12),
                    "velocity": 100,
                    "label": f"cue-{index:03d}",
                }
                for index in range(40)
            ]
            command = {
                "type": "start",
                "schedule": schedule,
                "start_time": time.time(),
                "debug_mode": True,
            }
            payload = json.dumps(command).encode()

            self.assertGreater(len(payload), 1024)

            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sender.sendto(payload, ("127.0.0.1", port))
            finally:
                sender.close()

            self.assertTrue(message_seen.wait(timeout=1.0))
            self.assertEqual(received["msg"]["type"], "start")
            self.assertEqual(received["msg"]["schedule"], schedule)
        finally:
            listener.stop_listening()


class TestCommandManagerLatency(unittest.TestCase):
    def test_rtt_is_recorded_from_pong_only(self):
        manager = CommandManager()
        manager._ping_sent_at["collab-1"] = time.monotonic() - 0.05

        manager._handle_default_message(
            {"type": "heartbeat", "device_id": "collab-1", "status": "ready"},
            ("127.0.0.1", 5006),
        )
        self.assertEqual(manager.get_average_rtt(), 0.0)

        manager._ping_sent_at["collab-1"] = time.monotonic() - 0.05
        manager._handle_default_message(
            {"type": "pong", "device_id": "collab-1"},
            ("127.0.0.1", 5006),
        )

        self.assertGreater(manager.get_average_rtt(), 0.0)
        self.assertLess(manager.get_average_rtt(), 0.5)


if __name__ == "__main__":
    unittest.main()