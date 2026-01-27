#!/usr/bin/env python3
"""
GStreamer Video Player Management for KitchenSync
Handles hardware-accelerated video playback with precise sync capabilities.
Replaces the legacy VLC player.
"""

import os
import sys
import time
import threading
from typing import Optional
from core.logger import log_info, log_error, log_warning

# Check for GStreamer availability
try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib
    GST_AVAILABLE = True
except ImportError:
    GST_AVAILABLE = False
    log_error("GStreamer python bindings not found. Run setup.sh", component="gst")

class GstVideoPlayer:
    """
    GStreamer-based video player using hardware acceleration (v4l2h264dec).
    Supports seamless rate adjustment for synchronization.
    """

    def __init__(self, debug_mode: bool = False, headless: bool = False):
        if not GST_AVAILABLE:
            raise RuntimeError("GStreamer not available")

        self.debug_mode = debug_mode
        self.headless = headless
        self.pipeline = None
        self.bus = None
        self.main_loop = None
        self.main_loop_thread = None
        self.video_path = None
        self.is_playing = False
        self.duration = 0.0
        self.current_rate = 1.0
        
        # Initialize GStreamer
        try:
            if not Gst.is_initialized():
                Gst.init(None)
        except Exception as e:
            log_error(f"Failed to initialize GStreamer: {e}", component="gst")
            raise

    def load_video(self, video_path: str) -> bool:
        """Construct the pipeline and load the video file"""
        if not os.path.exists(video_path):
            log_error(f"Video file not found: {video_path}", component="gst")
            return False

        self.video_path = os.path.abspath(video_path)
        
        # Cleanup existing pipeline if any
        if self.pipeline:
            self.cleanup()

        try:
            # Build the pipeline string
            # Hardware decoding: filesrc -> qtdemux -> h264parse -> v4l2h264dec -> videoconvert -> sink
            # sink is fakesink (headless) or autovideosink (display)
            sink = "fakesink sync=true" if self.headless else "autovideosink"
            
            # Note: We use 'parse-bin' logic implicitly or construct explicit elements.
            # Using gst-launch syntax via parse_launch is robust and easy to modify.
            pipeline_str = (
                f"filesrc location={self.video_path} ! "
                "qtdemux ! h264parse ! v4l2h264dec ! "
                f"videoconvert ! {sink}"
            )

            log_info(f"Creating pipeline: {pipeline_str}", component="gst")
            self.pipeline = Gst.parse_launch(pipeline_str)

            # Setup Bus for messaging (Errors, EOS, etc.)
            self.bus = self.pipeline.get_bus()
            self.bus.add_signal_watch()
            self.bus.connect("message", self._on_bus_message)

            return True

        except Exception as e:
            log_error(f"Error loading video: {e}", component="gst")
            return False

    def start_playback(self) -> bool:
        """Start the pipeline state to PLAYING"""
        if not self.pipeline:
            return False

        try:
            # Start the GLib MainLoop in a background thread to handle bus messages
            if not self.main_loop:
                self.main_loop = GLib.MainLoop()
                self.main_loop_thread = threading.Thread(target=self.main_loop.run, daemon=True)
                self.main_loop_thread.start()

            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                log_error("Failed to set pipeline to PLAYING", component="gst")
                return False
            
            self.is_playing = True
            log_info("Playback started", component="gst")
            
            # Wait a moment for duration to be available
            threading.Thread(target=self._query_duration_async, daemon=True).start()
            
            return True
        except Exception as e:
            log_error(f"Error starting playback: {e}", component="gst")
            return False

    def stop_playback(self):
        """Stop playback and reset state"""
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        self.is_playing = False
        log_info("Playback stopped", component="gst")

    def pause(self) -> bool:
        """Pause playback"""
        if not self.pipeline:
            return False
        self.pipeline.set_state(Gst.State.PAUSED)
        self.is_playing = False
        return True

    def resume(self) -> bool:
        """Resume playback"""
        if not self.pipeline:
            return False
        self.pipeline.set_state(Gst.State.PLAYING)
        self.is_playing = True
        return True

    def get_position(self) -> Optional[float]:
        """Get current position in seconds"""
        if not self.pipeline:
            return 0.0
        
        try:
            success, position = self.pipeline.query_position(Gst.Format.TIME)
            if success:
                return position / Gst.SECOND
        except Exception:
            pass
        return 0.0

    def set_position(self, seconds: float) -> bool:
        """Seek to specific position (HARD SEEK)"""
        if not self.pipeline:
            return False
        
        target_ns = int(seconds * Gst.SECOND)
        
        # Standard seek: Flush pipeline, accurate position, keep playing
        flags = Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE
        
        success = self.pipeline.seek_simple(Gst.Format.TIME, flags, target_ns)
        if success:
            log_info(f"Seeked to {seconds}s", component="gst")
        else:
            log_warning(f"Seek to {seconds}s failed", component="gst")
        return success

    def set_rate(self, rate: float) -> bool:
        """
        Adjust playback rate (speed) without changing position (seamless if possible).
        Used for synchronization drift correction.
        """
        if not self.pipeline:
            return False

        # If rate is effectively the same, ignore
        if abs(self.current_rate - rate) < 0.01:
            return True

        log_info(f"Adjusting rate: {self.current_rate} -> {rate}", component="gst")
        
        try:
            # To change rate, we perform a seek to the CURRENT position with the NEW rate.
            # We omit the FLUSH flag to try and keep it smooth, but this depends on the decoder.
            # If latency is high, we might need FLUSH.
            
            position_ns = 0
            success, pos = self.pipeline.query_position(Gst.Format.TIME)
            if success:
                position_ns = pos

            # Create a seek event
            # Start: current position, Stop: End of stream (-1)
            seek_event = Gst.Event.new_seek(
                rate,
                Gst.Format.TIME,
                Gst.SeekFlags.ACCURATE, # Try without FLUSH first for smoothness
                Gst.SeekType.SET, position_ns,
                Gst.SeekType.NONE, 0
            )

            if self.pipeline.send_event(seek_event):
                self.current_rate = rate
                return True
            else:
                log_error("Rate change failed (event rejected)", component="gst")
                return False

        except Exception as e:
            log_error(f"Error setting rate: {e}", component="gst")
            return False

    def get_duration(self) -> float:
        """Get total video duration in seconds"""
        return self.duration

    def get_video_info(self) -> dict:
        """Return status dictionary (compatible with UI)"""
        return {
            "current_time": self.get_position(),
            "total_time": self.duration,
            "is_playing": self.is_playing,
            "rate": self.current_rate,
            "backend": "gstreamer"
        }

    def cleanup(self):
        """Free resources"""
        self.stop_playback()
        if self.main_loop and self.main_loop.is_running():
            self.main_loop.quit()
        self.pipeline = None

    def _on_bus_message(self, bus, message):
        """Handle GStreamer bus messages"""
        t = message.type
        if t == Gst.MessageType.EOS:
            log_info("End of Stream reached. Looping...", component="gst")
            # Loop logic: Seek to 0
            self.set_position(0)
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            log_error(f"GStreamer Error: {err.message} | {debug}", component="gst")
            self.stop_playback()

    def _query_duration_async(self):
        """Retry querying duration until successful"""
        attempts = 0
        while attempts < 10:
            if not self.pipeline:
                return
            success, dur = self.pipeline.query_duration(Gst.Format.TIME)
            if success:
                self.duration = dur / Gst.SECOND
                # log_info(f"Duration detected: {self.duration}s", component="gst")
                return
            time.sleep(0.5)
            attempts += 1
