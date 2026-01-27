#!/usr/bin/env python3
import sys
import os
import time
import signal
import gi

# Ensure we have GStreamer
try:
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib
except ImportError:
    print("Error: PyGObject or GStreamer not found.")
    print("Run: sudo apt install python3-gst-1.0 gstreamer1.0-tools")
    sys.exit(1)

class GstHardwareTest:
    def __init__(self, file_path):
        self.file_path = os.path.abspath(file_path)
        Gst.init(None)
        
        # Define the hardware-accelerated pipeline
        # filesrc -> qtdemux -> h264parse -> v4l2h264dec -> videoconvert -> autovideosink
        pipeline_str = (
            f"filesrc location={self.file_path} ! "
            "qtdemux ! h264parse ! v4l2h264dec ! "
            "videoconvert ! autovideosink"
        )
        
        print(f"DEBUG: Launching pipeline: {pipeline_str}")
        
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
        except Exception as e:
            print(f"Error creating pipeline: {e}")
            sys.exit(1)

        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)
        
        self.loop = GLib.MainLoop()

    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("\nEnd of stream reached.")
            self.loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\nError: {err.message}")
            print(f"Debug info: {debug}")
            self.loop.quit()

    def run(self):
        print(f"Starting playback of: {self.file_path}")
        print("Press Ctrl+C to stop.")
        
        self.pipeline.set_state(Gst.State.PLAYING)
        
        # Add a timer to print position
        GLib.timeout_add(500, self.print_position)
        
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            self.pipeline.set_state(Gst.State.NULL)

    def print_position(self):
        success, position = self.pipeline.query_position(Gst.Format.TIME)
        success_dur, duration = self.pipeline.query_duration(Gst.Format.TIME)
        
        if success and success_dur:
            pos_sec = position / Gst.SECOND
            dur_sec = duration / Gst.SECOND
            print(f"Position: {pos_sec:.2f}s / {dur_sec:.2f}s (Rate: 1.0)", end='\r')
        return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_gst_hardware.py <path_to_video.mp4>")
        sys.exit(1)
        
    test = GstHardwareTest(sys.argv[1])
    test.run()
