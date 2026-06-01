#!/usr/bin/env python3
"""Tests for audio-only project support in kSync."""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

# Mock GStreamer before imports
sys.modules.setdefault("gi", MagicMock())
sys.modules.setdefault("gi.repository", MagicMock())

from video.file_manager import VideoFileManager
from video.drivers import gst_driver


class TestVideoFileManagerAudioSupport(unittest.TestCase):
    def test_audio_extensions_present_in_supported_extensions(self):
        manager = VideoFileManager()
        for ext in [".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".aiff"]:
            self.assertIn(ext, manager.SUPPORTED_EXTENSIONS)
            self.assertIn(ext, manager.SUPPORTED_AUDIO_EXTENSIONS)

    def test_is_audio_file_detection(self):
        manager = VideoFileManager()
        self.assertTrue(manager.is_audio_file("music.wav"))
        self.assertTrue(manager.is_audio_file("sounds/ambient.MP3"))
        self.assertTrue(manager.is_audio_file("/path/to/track.flac"))
        
        self.assertFalse(manager.is_audio_file("movie.mp4"))
        self.assertFalse(manager.is_audio_file("video.MOV"))
        self.assertFalse(manager.is_audio_file(""))
        self.assertFalse(manager.is_audio_file(None))


class TestGstDriverAudioBypass(unittest.TestCase):
    def setUp(self):
        self.fake_gst = SimpleNamespace(
            SECOND=1_000_000_000,
            Format=SimpleNamespace(TIME="time"),
            init=MagicMock(),
            ElementFactory=SimpleNamespace(
                make=MagicMock(return_value=MagicMock()),
                find=MagicMock(return_value=None),
                list_get_elements=MagicMock(return_value=[]),
            ),
            StateChangeReturn=SimpleNamespace(FAILURE=0, SUCCESS=1),
            State=SimpleNamespace(PAUSED=3, PLAYING=4),
            MainLoop=MagicMock(return_value=MagicMock()),
            SeekFlags=SimpleNamespace(FLUSH=1, KEY_UNIT=2, ACCURATE=4, SEGMENT=8),
            SeekType=SimpleNamespace(SET=1, NONE=0),
            Rank=SimpleNamespace(PRIMARY=256, SECONDARY=128, NONE=0),
            ELEMENT_FACTORY_TYPE_DECODER=1,
            ELEMENT_FACTORY_TYPE_MEDIA_VIDEO=2,
            MessageType=SimpleNamespace(
                ERROR=1,
                EOS=2,
                ASYNC_DONE=3,
                SEGMENT_DONE=4,
            ),
            ELEMENT_METADATA_KLASS="klass",
        )
        self.original_gst = gst_driver.Gst
        self.original_available = gst_driver.GST_AVAILABLE
        
        gst_driver.Gst = self.fake_gst
        gst_driver.GST_AVAILABLE = True

    def tearDown(self):
        gst_driver.Gst = self.original_gst
        gst_driver.GST_AVAILABLE = self.original_available

    @patch("video.drivers.gst_driver.os.path.exists")
    @patch("video.drivers.gst_driver.threading.Thread")
    def test_load_audio_only_bypasses_video_sink(self, mock_thread, mock_exists):
        mock_exists.return_value = True
        
        # Instantiate GstDriver with enable_audio=False to verify it is forced to True
        driver = gst_driver.GstDriver(enable_audio=False)
        driver._create_video_sink = MagicMock(return_value=(MagicMock(), "glimagesink"))
        
        # Load a pure audio path
        success = driver.load("soundscape.wav")
        
        self.assertTrue(success)
        self.assertTrue(driver.is_audio_only)
        self.assertTrue(driver.enable_audio)  # Must be forced to True
        
        # Verify video sink was NEVER created or set on the pipeline
        driver._create_video_sink.assert_not_called()
        self.assertEqual(driver.video_sink_name, "none (audio-only)")
        self.assertFalse(driver.hardware_accel_preferred)

    @patch("video.drivers.gst_driver.os.path.exists")
    @patch("video.drivers.gst_driver.threading.Thread")
    def test_load_video_creates_video_sink(self, mock_thread, mock_exists):
        mock_exists.return_value = True
        
        driver = gst_driver.GstDriver(enable_audio=True)
        fake_sink = MagicMock()
        driver._create_video_sink = MagicMock(return_value=(fake_sink, "glimagesink"))
        
        # Load a video path
        success = driver.load("movie.mp4")
        
        self.assertTrue(success)
        self.assertFalse(driver.is_audio_only)
        
        # Verify video sink WAS created and set
        driver._create_video_sink.assert_called_once()
        driver.pipeline.set_property.assert_any_call("video-sink", fake_sink)
        self.assertEqual(driver.video_sink_name, "glimagesink")

    @patch("video.drivers.gst_driver.subprocess.run")
    def test_set_fullscreen_ignored_for_audio_only(self, mock_run):
        driver = gst_driver.GstDriver()
        driver.is_audio_only = True
        
        # Call set_fullscreen
        driver.set_fullscreen(True)
        
        # Verify no subprocess (wmctrl/wlrctl) was run
        mock_run.assert_not_called()

    @patch("video.drivers.gst_driver.threading.Thread")
    def test_audio_error_classification_restarts_for_audio_element(self, mock_thread):
        driver = gst_driver.GstDriver(enable_audio=True)
        driver.video_path = "movie.mp4"
        driver._restart_minimal = MagicMock()
        
        # Mock GStreamer Message
        mock_msg = MagicMock()
        mock_msg.type = gst_driver.Gst.MessageType.ERROR
        
        # Set up message source to look like an audio sink
        mock_src = MagicMock()
        mock_src.get_name.return_value = "autoaudiosink0"
        mock_factory = MagicMock()
        mock_factory.get_metadata.return_value = "Sink/Audio"
        mock_src.get_factory.return_value = mock_factory
        mock_msg.src = mock_src
        
        # Mock message parse_error returning (ErrorObject, DebugString)
        mock_err = MagicMock()
        mock_err.message = "Unable to prepare device."
        mock_msg.parse_error.return_value = (mock_err, "debug details")
        
        # Fire the message handler
        driver._on_bus_message(None, mock_msg)
        
        # It should trigger restart minimal since it's an audio element
        mock_thread.assert_called_once_with(target=driver._restart_minimal, daemon=True)
        self.assertFalse(driver.enable_audio)

    @patch("video.drivers.gst_driver.threading.Thread")
    def test_audio_error_classification_fails_for_video_element(self, mock_thread):
        driver = gst_driver.GstDriver(enable_audio=True)
        driver.video_path = "movie.mp4"
        driver._restart_minimal = MagicMock()
        
        # Mock GStreamer Message
        mock_msg = MagicMock()
        mock_msg.type = gst_driver.Gst.MessageType.ERROR
        
        # Set up message source to look like a video decoder
        mock_src = MagicMock()
        mock_src.get_name.return_value = "v4l2slh264dec0"
        mock_factory = MagicMock()
        mock_factory.get_metadata.return_value = "Codec/Decoder/Video"
        mock_src.get_factory.return_value = mock_factory
        mock_msg.src = mock_src
        
        # Mock message parse_error returning (ErrorObject, DebugString)
        mock_err = MagicMock()
        mock_err.message = "Unable to prepare device. wrong format"
        mock_msg.parse_error.return_value = (mock_err, "debug details")
        
        # Fire the message handler
        driver._on_bus_message(None, mock_msg)
        
        # It should NOT trigger restart minimal since it's a video element, and state should be set to ERROR
        driver._restart_minimal.assert_not_called()
        self.assertTrue(driver.enable_audio)
        self.assertEqual(driver.state, gst_driver.PlayerState.ERROR)

    @patch("video.drivers.gst_driver.threading.Thread")
    def test_audio_error_classification_restarts_for_openal_sink(self, mock_thread):
        driver = gst_driver.GstDriver(enable_audio=True)
        driver.video_path = "movie.mp4"
        driver._restart_minimal = MagicMock()
        
        # Mock GStreamer Message
        mock_msg = MagicMock()
        mock_msg.type = gst_driver.Gst.MessageType.ERROR
        
        # Set up message source to look like openalsink0
        mock_src = MagicMock()
        mock_src.get_name.return_value = "openalsink0"
        mock_factory = MagicMock()
        mock_factory.get_metadata.return_value = "Sink/Audio"
        mock_src.get_factory.return_value = mock_factory
        mock_msg.src = mock_src
        
        # Mock message parse_error returning (ErrorObject, DebugString)
        mock_err = MagicMock()
        mock_err.message = "Unable to prepare device."
        mock_msg.parse_error.return_value = (mock_err, "debug details")
        
        # Fire the message handler
        driver._on_bus_message(None, mock_msg)
        
        # It should trigger restart minimal since it's an OpenAL audio element
        mock_thread.assert_called_once_with(target=driver._restart_minimal, daemon=True)
        self.assertFalse(driver.enable_audio)


if __name__ == "__main__":
    unittest.main()
