#!/usr/bin/env python3
import os
import sys
import json
import unittest
import time
from pathlib import Path
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ui.native_overlay import NativeDebugOverlay

class TestNativeOverlay(unittest.TestCase):
    def setUp(self):
        # Create a mock node and video player
        self.mock_video_player = MagicMock()
        self.mock_video_player.get_info.return_value = {
            "position": 42.0,
            "duration": 100.0,
            "state": "playing",
            "decoder": "h264",
            "video_sink": "glimagesink"
        }
        self.mock_video_player.current_rate = 1.002
        
        self.mock_config = MagicMock()
        self.mock_config.device_id = "test-device-pi"
        
        self.mock_node = MagicMock()
        self.mock_node.config = self.mock_config
        self.mock_node.video_player = self.mock_video_player
        self.mock_node.deviation_samples = [0.0015] # 1.5ms
        self.mock_node.command_manager = MagicMock()
        self.mock_node.command_manager.get_collaborators.return_value = {}

    def test_status_file_writing(self):
        # Create overlay
        overlay = NativeDebugOverlay(self.mock_node, role="collaborator")
        
        # We don't want to spawn actual subprocess during unittest, so mock subprocess.Popen
        from unittest.mock import patch
        with patch("subprocess.Popen") as mock_popen:
            # Set up mock env so start() thinks DISPLAY is present to trigger the code path
            with patch.dict(os.environ, {"DISPLAY": ":99"}):
                overlay.start()
                
                # Wait briefly for status loop thread to write the file
                time.sleep(0.3)
                
                status_path = "/dev/shm/ksync_overlay.json"
                self.assertTrue(os.path.exists(status_path))
                
                # Verify JSON structure
                with open(status_path, "r") as f:
                    data = json.load(f)
                    
                self.assertEqual(data["device_id"], "test-device-pi")
                self.assertEqual(data["role"], "collaborator")
                self.assertEqual(data["state"], "playing")
                self.assertEqual(data["position"], 42.0)
                self.assertEqual(data["duration"], 100.0)
                self.assertEqual(data["sync_dev_ms"], 1.5)
                self.assertEqual(data["speed"], 1.002)
                
                overlay.stop()
                
                # Verify file cleaned up on stop
                self.assertFalse(os.path.exists(status_path))

if __name__ == "__main__":
    unittest.main()
