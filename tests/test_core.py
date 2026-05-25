#!/usr/bin/env python3
"""
Sanity tests for kSync core logic.
Verifies that drivers and state management work as expected.
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Mock GStreamer before importing video
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()

from video import get_video_driver
from video.driver import PlayerState
from core import SyncTracker, SystemState

class TestkSync(unittest.TestCase):
    def test_video_driver_factory(self):
        """Verify the driver factory returns the correct classes."""
        gst = get_video_driver("gstreamer")
        self.assertIsNotNone(gst)

        mock = get_video_driver("mock")
        self.assertIsNotNone(mock)

        legacy_alias = get_video_driver("vlc")
        self.assertIsNotNone(legacy_alias)

    def test_sync_tracker(self):
        """Verify the sync tracker correctly calculates drift."""
        tracker = SyncTracker()
        
        # Initial sync
        tracker.record_sync(100.0, 100.0)
        
        # Simulate 0.1s drift (leader time advanced more than local time)
        # Local time advances 1s, Leader time advances 1.1s
        tracker.record_sync(101.1, 101.0)
        
        # Drift should be 0.1
        self.assertAlmostEqual(tracker.get_average_drift(), 0.1)
        
    def test_system_state(self):
        """Verify session state transitions."""
        state = SystemState()
        self.assertFalse(state.is_running)
        
        state.start_session()
        self.assertTrue(state.is_running)
        self.assertIsNotNone(state.start_time)
        
        state.stop_session()
        self.assertFalse(state.is_running)

if __name__ == "__main__":
    unittest.main()
