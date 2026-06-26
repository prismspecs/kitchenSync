#!/usr/bin/env python3
"""
Sync Simulation Test for kSync
Simulates drift and verifies that the P-controller settles without oscillating.
"""

import sys
import unittest
from unittest.mock import patch, MagicMock
import time
from pathlib import Path

# Add src to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from video.drivers.mock_driver import MockVideoDriver
from collaborator import CollaboratorPi

class MockConfig:
    def __init__(self, kp=0.1, max_samples=5, min_drift=0.01, max_drift=0.5):
        self.device_id = "test-pi"
        self.video_file = "test.mp4"
        self.video_driver = "mock"
        self.usb_mount_point = None
        self.enable_system_logging = False
        self.debug_mode = False
        self.enable_midi = False
        self.enable_osc = False
        self.enable_audio = True
        self.kp = kp
        self.max_samples = max_samples
        self.min_drift = min_drift
        self.max_drift = max_drift
        self.min_rate = 0.9
        self.max_rate = 1.2
        self.enable_deviation_log = False

    def getint(self, key, default, section=None):
        return getattr(self, key, default)

    def role_name(self) -> str:
        return "collaborator"

class SyncSimulationTest(unittest.TestCase):
    def get_collaborator(self, config):
        """Helper to create a collaborator with a mock driver."""
        with patch('collaborator.get_video_driver', return_value=MockVideoDriver()):
            with patch('collaborator.ConfigManager', return_value=config):
                collab = CollaboratorPi()
                collab.system_state.is_running = True
                return collab

    def test_settle_constant_offset(self):
        """Verify that it settles a constant 0.2s offset."""
        print("\nTesting settle from constant 0.2s offset...")
        
        with patch('time.time') as mock_time:
            current_t = 1000.0
            mock_time.return_value = current_t
            
            config = MockConfig(kp=0.1, max_samples=5)
            collab = self.get_collaborator(config)
            
            # Initial state: leader at 0, collab at 0.2
            collab.video_player.play()
            collab.video_player.seek(0.2)
            
            drifts = []
            for i in range(500):
                leader_time = i * 0.1
                collab._handle_sync(leader_time, current_t, "leader-001")
                collab._process_sync_tick()
                
                drifts.append(collab.video_player.get_position() - leader_time)
                
                current_t += 0.1
                mock_time.return_value = current_t
            
            final_drift = drifts[-1]
            print(f"Final drift (kp=0.1): {final_drift:.4f}s")
            self.assertLess(abs(final_drift), 0.01)

    def test_extreme_gain_oscillates(self):
        """Verify that extreme gain DOES oscillate (baseline for simulation)."""
        print("\nVerifying that extreme gain (kp=20.0, no clamping) oscillates...")
        
        with patch('time.time') as mock_time:
            current_t = 1000.0
            mock_time.return_value = current_t
            
            config = MockConfig(kp=20.0, max_samples=1)
            config.min_rate = -10.0
            config.max_rate = 10.0
            collab = self.get_collaborator(config)
            
            collab.video_player.play()
            collab.video_player.seek(0.2)
            
            drifts = []
            for i in range(50):
                leader_time = i * 0.1
                collab._handle_sync(leader_time, current_t, "leader-001")
                collab._process_sync_tick()
                drifts.append(collab.video_player.get_position() - leader_time)
                
                current_t += 0.1
                mock_time.return_value = current_t
            
            crossings = 0
            for i in range(1, len(drifts)):
                if drifts[i] * drifts[i-1] < 0:
                    crossings += 1
            
            print(f"Number of zero crossings (extreme kp): {crossings}")
            self.assertGreaterEqual(crossings, 2)

    def test_tuned_gain_stability(self):
        """Verify that tuned gain (kp=0.1) is stable."""
        print("\nVerifying that tuned gain (kp=0.1) is stable...")
        
        with patch('time.time') as mock_time:
            current_t = 1000.0
            mock_time.return_value = current_t
            
            config = MockConfig(kp=0.1, max_samples=5)
            collab = self.get_collaborator(config)
            
            collab.video_player.play()
            collab.video_player.seek(0.2)
            
            drifts = []
            for i in range(100):
                leader_time = i * 0.1
                collab._handle_sync(leader_time, current_t, "leader-001")
                collab._process_sync_tick()
                drifts.append(collab.video_player.get_position() - leader_time)
                
                current_t += 0.1
                mock_time.return_value = current_t
            
            crossings = 0
            for i in range(1, len(drifts)):
                if drifts[i] * drifts[i-1] < 0:
                    crossings += 1
            
            print(f"Number of zero crossings (tuned kp): {crossings}")
            self.assertLessEqual(crossings, 1)

    def test_deviation_logging(self):
        """Verify that deviation logging writes to a CSV when enabled."""
        import tempfile
        import shutil
        from pathlib import Path
        
        temp_dir = tempfile.mkdtemp()
        try:
            config = MockConfig(kp=0.1, max_samples=5)
            config.enable_deviation_log = False
            
            collab = self.get_collaborator(config)
            
            # Now enable and point to temp path
            collab.enable_deviation_log = True
            collab.deviation_log_path = Path(temp_dir) / "test_deviation.csv"
            collab._init_deviation_log = lambda: None
            
            # Manually set up
            with open(collab.deviation_log_path, "w") as f:
                f.write("timestamp,leader_time,video_pos,deviation,rate,hard_seeks\n")
                
            # Simulate a sync tick
            with patch('time.time', return_value=1000.0):
                collab.video_player.play()
                collab.video_player.seek(0.2)
                collab._handle_sync(0.0, 1000.0, "leader-001")
                collab._process_sync_tick()
                
            # Verify data was written
            with open(collab.deviation_log_path, "r") as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 2)  # Header + 1 data line
            data_parts = lines[1].strip().split(",")
            self.assertEqual(len(data_parts), 6)
            self.assertEqual(data_parts[0], "1000.000000")
            self.assertEqual(data_parts[1], "0.000000")
            self.assertEqual(data_parts[2], "0.200000")
            self.assertAlmostEqual(float(data_parts[3]), 0.2)
            self.assertEqual(data_parts[4], "0.9800")
        finally:
            shutil.rmtree(temp_dir)

    def test_netclock_sync_mode(self):
        """Verify netclock sync mode handling."""
        config = MockConfig(kp=0.1, max_samples=5)
        config.sync_mode = "netclock"
        
        collab = self.get_collaborator(config)
        collab.video_manager.find_video_file = MagicMock(return_value="/mock/path/test.mp4")
        
        # Add a mocked use_network_clock to the mock video driver
        collab.video_player.use_network_clock = MagicMock()
        
        msg = {
            "type": "start",
            "video_file": "test.mp4",
            "leader_id": "leader-001",
            "start_time": 0.0,
            "gst_base_time": 123456789,
            "netclock_port": 9998
        }
        addr = ("192.168.0.221", 5000)
        
        collab._handle_start_command(msg, addr)
        
        # Assertions
        self.assertEqual(collab.discovered_leader_ip, "192.168.0.221")
        collab.video_player.use_network_clock.assert_called_once_with(
            "192.168.0.221", 123456789, 9998
        )
        
        # Verify _maintain_video_sync is bypassed when sync_mode is netclock
        collab._maintain_video_sync = MagicMock()
        
        with patch('time.time', return_value=1000.0):
            # Simulate a sync tick
            collab._handle_sync(10.0, 1000.0, "leader-001")
            collab._process_sync_tick()
            
        collab._maintain_video_sync.assert_not_called()

if __name__ == "__main__":
    unittest.main()
