#!/usr/bin/env python3
"""Regression tests for sync stability behavior."""

import importlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


sys.modules.setdefault("vlc", MagicMock())
sys.modules.setdefault("gi", MagicMock())
sys.modules.setdefault("gi.repository", MagicMock())


import collaborator
from video.drivers import gst_driver


class TestGstDriverSetSpeed(unittest.TestCase):
    def test_instant_rate_change_uses_none_seek_types(self):
        fake_event = object()
        fake_gst = SimpleNamespace(
            SECOND=1_000_000_000,
            Format=SimpleNamespace(TIME="time"),
            SeekFlags=SimpleNamespace(INSTANT_RATE_CHANGE=4),
            SeekType=SimpleNamespace(NONE="none"),
            Event=SimpleNamespace(new_seek=MagicMock(return_value=fake_event)),
            init=MagicMock(),
        )

        original_gst = gst_driver.Gst
        original_available = gst_driver.GST_AVAILABLE
        gst_driver.Gst = fake_gst
        gst_driver.GST_AVAILABLE = True

        try:
            driver = gst_driver.GstDriver.__new__(gst_driver.GstDriver)
            driver.pipeline = MagicMock()
            driver.pipeline.send_event.return_value = True
            driver.current_rate = 1.0

            success = driver.set_speed(1.02)

            self.assertTrue(success)
            fake_gst.Event.new_seek.assert_called_once_with(
                1.02,
                fake_gst.Format.TIME,
                fake_gst.SeekFlags.INSTANT_RATE_CHANGE,
                fake_gst.SeekType.NONE,
                0,
                fake_gst.SeekType.NONE,
                -1,
            )
            driver.pipeline.send_event.assert_called_once_with(fake_event)
            self.assertEqual(driver.current_rate, 1.02)
        finally:
            gst_driver.Gst = original_gst
            gst_driver.GST_AVAILABLE = original_available


class TestCollaboratorDuplicateStart(unittest.TestCase):
    def test_duplicate_start_ignores_small_drift(self):
        dummy = SimpleNamespace(
            system_state=SimpleNamespace(is_running=True, current_time=12.0),
            video_path="videos/test_video.mp4",
            video_manager=SimpleNamespace(find_video_file=MagicMock(return_value="videos/test_video.mp4")),
            video_player=SimpleNamespace(
                get_position=MagicMock(return_value=12.2),
                seek=MagicMock(),
            ),
            debug_sync_logging=False,
        )

        collaborator.CollaboratorPi._handle_start_command(dummy, {"type": "start"})

        dummy.video_player.seek.assert_not_called()

    def test_duplicate_start_resyncs_large_drift(self):
        dummy = SimpleNamespace(
            system_state=SimpleNamespace(is_running=True, current_time=12.0),
            video_path="videos/test_video.mp4",
            video_manager=SimpleNamespace(find_video_file=MagicMock(return_value="videos/test_video.mp4")),
            video_player=SimpleNamespace(
                get_position=MagicMock(return_value=13.0),
                seek=MagicMock(),
            ),
            debug_sync_logging=False,
        )

        collaborator.CollaboratorPi._handle_start_command(dummy, {"type": "start"})

        dummy.video_player.seek.assert_called_once_with(12.0)


if __name__ == "__main__":
    unittest.main()