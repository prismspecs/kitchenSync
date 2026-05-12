
import sys
try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstVideo', '1.0')
    from gi.repository import Gst, GObject, GLib, GstVideo
    Gst.init(None)
    print("GStreamer and GstVideo initialized successfully.")
    print(f"GStreamer version: {Gst.version_string()}")
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)

print("Checking for playbin...")
playbin = Gst.ElementFactory.make("playbin", "test-player")
if playbin:
    print("Playbin element created successfully.")
else:
    print("Failed to create playbin element.")

print("Checking for autovideosink...")
sink = Gst.ElementFactory.make("autovideosink", "test-sink")
if sink:
    print("autovideosink element created successfully.")
else:
    print("Failed to create autovideosink element.")
