#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from remote import controller
from remote.controller import compute_latency_compensation, resolve_byte_range


class TestRemoteController(unittest.TestCase):
    def test_resolve_byte_range_accepts_common_browser_requests(self):
        self.assertIsNone(resolve_byte_range(None, 1000))
        self.assertEqual(resolve_byte_range("bytes=100-199", 1000), (100, 199))
        self.assertEqual(resolve_byte_range("bytes=100-", 1000), (100, 999))
        self.assertEqual(resolve_byte_range("bytes=-200", 1000), (800, 999))

    def test_resolve_byte_range_clamps_suffix_to_file_size(self):
        self.assertEqual(resolve_byte_range("bytes=-1500", 1000), (0, 999))

    def test_resolve_byte_range_rejects_invalid_ranges(self):
        invalid_ranges = [
            "items=0-1",
            "bytes=500-100",
            "bytes=1000-1001",
            "bytes=-0",
        ]

        for range_header in invalid_ranges:
            with self.subTest(range_header=range_header):
                with self.assertRaises(ValueError):
                    resolve_byte_range(range_header, 1000)

    def test_compute_latency_compensation_respects_toggle(self):
        self.assertEqual(compute_latency_compensation(0.040, True, 0.5), 0.020)
        self.assertEqual(compute_latency_compensation(0.040, False, 0.5), 0.0)
        self.assertEqual(compute_latency_compensation(0.0, True, 0.5), 0.0)

    def test_build_ui_state_includes_latency_metrics(self):
        fake_command_manager = type(
            "FakeCommandManager",
            (),
            {
                "get_collaborators": lambda self: {
                    "collab-1": {
                        "ip": "10.0.0.2",
                        "status": "ready",
                        "online": True,
                        "video_file": "clip.mp4",
                        "hard_seeks": 3,
                    }
                },
                "get_average_rtt": lambda self: 0.040,
                "get_device_average_rtt": lambda self, device_id: 0.025 if device_id == "collab-1" else 0.0,
            },
        )()

        with patch.object(controller, "command_manager", fake_command_manager), patch.object(
            controller,
            "config",
            type(
                "FakeConfig",
                (),
                {
                    "enable_latency_compensation": True,
                    "latency_factor": 0.5,
                    "emulated_render_lag": 0.05,
                    "role_name": lambda *args: "leader",
                    "video_driver": "gstreamer",
                },
            )(),
        ), patch.object(controller, "refresh_local_snapshot", lambda: None), patch.object(
            controller,
            "list_available_videos",
            lambda: ["clip.mp4"],
        ), patch.object(controller, "list_available_schedules", lambda: []):
            state = controller.build_ui_state()

        self.assertEqual(state["latency"]["avg_rtt_ms"], 40.0)
        self.assertEqual(state["latency"]["compensation_ms"], 20.0)
        collaborator = next(device for device in state["devices"] if device["device_id"] == "collab-1")
        self.assertEqual(collaborator["latency_ms"], 25.0)
        self.assertEqual(collaborator["hard_seeks"], 3)

    def test_start_remote_starts_listener_before_latency_probing(self):
        call_order = []

        class FakeCommandManager:
            def register_handler(self, *_args, **_kwargs):
                return None

            def start_listening(self):
                call_order.append("start_listening")

            def start_latency_probing(self):
                call_order.append("start_latency_probing")

        class FakeThread:
            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                return None

        fake_server = MagicMock()

        with patch.object(controller, "update_runtime_from_config", lambda: None), patch.object(
            controller,
            "command_manager",
            FakeCommandManager(),
        ), patch.object(controller.sync_broadcaster, "setup_socket", lambda: None), patch.object(
            controller.threading,
            "Thread",
            FakeThread,
        ), patch.object(controller, "RobustRemoteServer", MagicMock(return_value=fake_server)), patch.object(
            controller,
            "log_info",
            lambda *args, **kwargs: None,
        ):
            controller.start_remote()

        self.assertEqual(call_order, ["start_listening", "start_latency_probing"])


if __name__ == "__main__":
    unittest.main()