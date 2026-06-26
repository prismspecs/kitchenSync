import unittest
from unittest.mock import patch, MagicMock
import subprocess
import shutil
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.ntp_check import get_ntp_status

class TestNTPCheck(unittest.TestCase):
    @patch("shutil.which")
    def test_chronyc_missing(self, mock_which):
        mock_which.return_value = None
        status = get_ntp_status()
        self.assertFalse(status["synced"])
        self.assertEqual(status["error"], "chronyc binary not found")

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_chronyc_failed_exit(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/chronyc"
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stderr = "Error: Chrony not running"
        mock_run.return_value = mock_process
        
        status = get_ntp_status()
        self.assertFalse(status["synced"])
        self.assertIn("chronyc exited with code 1", status["error"])

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_chronyc_synchronized_fast(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/chronyc"
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = (
            "Reference ID    : C0A800A5 (192.168.0.165)\n"
            "Stratum         : 11\n"
            "Ref time (UTC)  : Fri Jun 26 15:30:00 2026\n"
            "System time     : 0.000052342 seconds fast of NTP time\n"
            "Last offset     : +0.000012344 seconds\n"
            "RMS offset      : 0.000045612 seconds\n"
            "Leap status     : Normal\n"
        )
        mock_run.return_value = mock_process
        
        status = get_ntp_status()
        self.assertTrue(status["synced"])
        self.assertEqual(status["stratum"], 11)
        self.assertAlmostEqual(status["offset"], 0.000052342)
        self.assertAlmostEqual(status["rms_offset"], 0.000045612)
        self.assertIn("192.168.0.165", status["reference_id"])

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_chronyc_synchronized_slow(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/chronyc"
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = (
            "Reference ID    : C0A800A5 (192.168.0.165)\n"
            "Stratum         : 11\n"
            "Ref time (UTC)  : Fri Jun 26 15:30:00 2026\n"
            "System time     : 0.000052342 seconds slow of NTP time\n"
            "Last offset     : +0.000012344 seconds\n"
            "RMS offset      : 0.000045612 seconds\n"
            "Leap status     : Normal\n"
        )
        mock_run.return_value = mock_process
        
        status = get_ntp_status()
        self.assertTrue(status["synced"])
        self.assertEqual(status["stratum"], 11)
        self.assertAlmostEqual(status["offset"], -0.000052342)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_chronyc_unsynchronized(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/chronyc"
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = (
            "Reference ID    : 00000000 ()\n"
            "Stratum         : 0\n"
            "System time     : 0.000000000 seconds fast of NTP time\n"
            "Last offset     : +0.000000000 seconds\n"
            "RMS offset      : 0.000000000 seconds\n"
            "Leap status     : Not synchronised\n"
        )
        mock_run.return_value = mock_process
        
        status = get_ntp_status()
        self.assertFalse(status["synced"])
        self.assertEqual(status["stratum"], 0)
        self.assertEqual(status["reference_id"], "00000000 ()")
