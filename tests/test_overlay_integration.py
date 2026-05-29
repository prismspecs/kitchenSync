#!/usr/bin/env python3
import os
import sys
import unittest
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from video.drivers.gst_driver import GstDriver
from video.driver import PlayerState

# Detect if GStreamer is missing or mocked globally by other pytest suites
is_mocked = False
try:
    from gi.repository import Gst
    from unittest.mock import MagicMock, Mock
    if isinstance(Gst, (MagicMock, Mock)) or Gst.__class__.__name__ == "MagicMock":
        is_mocked = True
except (ImportError, AttributeError):
    is_mocked = True

@unittest.skipIf(is_mocked, "GStreamer (gi.repository) is mocked globally or not available")
class TestOverlayIntegration(unittest.TestCase):
    def test_pure_production_pipeline_has_no_overlay(self):
        """Verify that when debug_mode is False, no textoverlay element is built (0% CPU/RAM copy)."""
        driver = GstDriver(debug_mode=False, enable_audio=False)
        video_path = str(Path(__file__).parent.parent / "videos/sync_test.mp4")
        
        self.assertTrue(driver.load(video_path))
        
        # Verify no textoverlay element exists
        overlay = driver.pipeline.get_by_name("overlay")
        self.assertIsNone(overlay, "Overlay element should not be built in production mode!")
        
        driver.cleanup()

    def test_debug_pipeline_has_overlay_and_accepts_text(self):
        """Verify that when debug_mode is True, textoverlay exists and accepts dynamic text."""
        driver = GstDriver(debug_mode=True, enable_audio=False)
        video_path = str(Path(__file__).parent.parent / "videos/sync_test.mp4")
        
        self.assertTrue(driver.load(video_path))
        # Verify textoverlay exists
        overlay = driver.video_sink.get_by_name("overlay")
        self.assertIsNotNone(overlay, "Overlay element should be compiled in debug mode!")
        
        # Test setting overlay text
        driver.set_overlay_text("kSync Integration Test Running!")
        self.assertEqual(overlay.get_property("text"), "kSync Integration Test Running!")
        
        driver.cleanup()

if __name__ == "__main__":
    unittest.main()
