#!/usr/bin/env python3
"""
GStreamer Implementation of the VideoDriver interface.
Provides high-performance, rate-based synchronization for Raspberry Pi.
"""

import os
import threading
import time
from typing import Optional, Dict, Any

try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstVideo', '1.0')
    from gi.repository import Gst, GObject, GLib, GstVideo
    GST_AVAILABLE = True
except ImportError:
    GST_AVAILABLE = False

from video.driver import VideoDriver, PlayerState
from core.logger import log_info, log_error, log_warning

class GstDriver(VideoDriver):
    """
    GStreamer Driver for KitchenSync.
    Uses playbin for robustness and custom seek events for seamless rate control.
    """

    def __init__(self, debug_mode: bool = False):
        if not GST_AVAILABLE:
            raise ImportError("GStreamer or GObject Introspection not found. Install via OS_SETUP.md.")

        Gst.init(None)
        self.debug_mode = debug_mode
        self.pipeline = None
        self.video_path = None
        self.state = PlayerState.STOPPED
        self.current_rate = 1.0
        
        # MainLoop for GStreamer bus messages
        self.loop = None
        self.loop_thread = None

    def load(self, video_path: str) -> bool:
        if not os.path.exists(video_path):
            log_error(f"Gst: Video file not found: {video_path}")
            return False

        self.video_path = video_path
        
        # Create playbin element
        self.pipeline = Gst.ElementFactory.make("playbin", "player")
        if not self.pipeline:
            log_error("Gst: Failed to create playbin element")
            return False

        # Set the URI
        uri = "file://" + os.path.abspath(video_path)
        self.pipeline.set_property("uri", uri)

        # Configure video sink.
        # autovideosink lets GStreamer pick the best available backend:
        # xvimagesink (X11), kmssink (DRM/KMS), glimagesink (GL), etc.
        sink = Gst.ElementFactory.make("autovideosink", "videosink")
        if sink:
            self.pipeline.set_property("video-sink", sink)
            log_info("Gst: Using autovideosink")
        else:
            log_warning("Gst: autovideosink unavailable; using default sink")

        # Set up the bus to watch for messages
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        # Start the GLib MainLoop in a separate thread
        self.loop = GLib.MainLoop()
        self.loop_thread = threading.Thread(target=self.loop.run, daemon=True)
        self.loop_thread.start()

        log_info(f"Gst: Loaded {video_path}")
        return True

    def _on_bus_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            log_info("Gst: End of stream reached, looping...")
            self.seek(0)
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            log_error(f"Gst Error: {err.message}")
            self.state = PlayerState.ERROR

    def play(self) -> bool:
        if not self.pipeline:
            return False
        
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            log_error("Gst: Failed to set pipeline to PLAYING")
            self.state = PlayerState.ERROR
            return False
            
        self.state = PlayerState.PLAYING
        return True

    def pause(self) -> bool:
        if self.pipeline:
            self.pipeline.set_state(Gst.State.PAUSED)
            self.state = PlayerState.PAUSED
            return True
        return False

    def stop(self) -> None:
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.state = PlayerState.STOPPED

    def seek(self, seconds: float) -> bool:
        """
        Perform a precise seek.
        """
        if not self.pipeline:
            return False
        
        # Convert seconds to nanoseconds
        nanos = int(seconds * Gst.SECOND)
        
        # Seek with flush for immediate response
        # Using KEY_UNIT to seek to nearest keyframe for speed
        # or ACCURATE for exact frame (slower)
        success = self.pipeline.seek_simple(
            Gst.Format.TIME, 
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 
            nanos
        )
        return success

    def set_speed(self, rate: float) -> bool:
        """
        Adjust playback rate seamlessly without flushing buffers.
        This is the core of KitchenSync's new 'invisible' synchronization.
        """
        if not self.pipeline:
            return False
            
        if rate == self.current_rate:
            return True

        # GStreamer allows changing rate via a Seek event
        # We use a non-flushing seek to keep playback smooth
        pos = self.get_position()
        pos_nanos = int(pos * Gst.SECOND)

        # Rate change event
        # If rate is 1.0, it plays normally. If 1.001, it catches up.
        event = Gst.Event.new_seek(
            rate,
            Gst.Format.TIME,
            Gst.SeekFlags.INSTANT_RATE_CHANGE, # Most efficient rate change
            Gst.SeekType.SET, pos_nanos,
            Gst.SeekType.NONE, -1
        )
        
        success = self.pipeline.send_event(event)
        if success:
            self.current_rate = rate
            log_info(f"Gst: Playback rate adjusted to {rate:.4f}")
        else:
            log_warning(f"Gst: Failed to adjust rate to {rate}")
            
        return success

    def get_position(self) -> float:
        if not self.pipeline:
            return 0.0
        
        success, position = self.pipeline.query_position(Gst.Format.TIME)
        if success:
            return position / Gst.SECOND
        return 0.0

    def get_duration(self) -> float:
        if not self.pipeline:
            return 0.0
        
        success, duration = self.pipeline.query_duration(Gst.Format.TIME)
        if success:
            return duration / Gst.SECOND
        return 0.0

    def get_state(self) -> PlayerState:
        if not self.pipeline:
            return PlayerState.STOPPED
        
        _, current, _ = self.pipeline.get_state(0.1)
        if current == Gst.State.PLAYING:
            return PlayerState.PLAYING
        elif current == Gst.State.PAUSED:
            return PlayerState.PAUSED
        elif current == Gst.State.NULL:
            return PlayerState.STOPPED
        return self.state

    def set_fullscreen(self, enabled: bool) -> None:
        # glimagesink handles its own windowing. For Openbox, 
        # the window manager handles making the window fullscreen.
        pass

    def cleanup(self) -> None:
        self.stop()
        if self.loop:
            self.loop.quit()
        self.pipeline = None
        log_info("Gst: Cleanup complete")
