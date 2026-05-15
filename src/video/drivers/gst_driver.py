#!/usr/bin/env python3
"""
GStreamer Implementation of the VideoDriver interface.
Provides high-performance, rate-based synchronization for Raspberry Pi.
"""

import os
import subprocess
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

    def __init__(self, debug_mode: bool = False, enable_audio: bool = True):
        if not GST_AVAILABLE:
            raise ImportError("GStreamer or GObject Introspection not found. Install via OS_SETUP.md.")

        Gst.init(None)
        self.debug_mode = debug_mode
        self.enable_audio = enable_audio
        self.pipeline = None
        self.video_path = None
        self.state = PlayerState.STOPPED
        self.current_rate = 1.0
        self.video_sink_name = None
        self.hardware_accel_preferred = False
        self.decoder_name = None
        self.decoder_candidates = []
        self.pipeline_kind = "playbin"
        self.is_seeking = False
        
        # MainLoop for GStreamer bus messages
        self.loop = None
        self.loop_thread = None

    def _hardware_decoder_names(self):
        return [
            "v4l2slh264dec",
            "v4l2h264dec",
            "v4l2slh265dec",
            "v4l2slhevcdec",
            "v4l2h265dec",
            "vah264dec",
            "vah265dec",
            "vaapih264dec",
            "vaapih265dec",
            "nvh264dec",
            "nvh265dec",
        ]

    def _software_decoder_names(self):
        return ["avdec_h264", "avdec_h265"]

    def _reprioritize_decoders(self):
        """Prefer hardware decoders and sinks over software when both exist."""
        available_hw = []
        primary_rank = int(getattr(Gst.Rank, "PRIMARY", 256))
        secondary_rank = int(getattr(Gst.Rank, "SECONDARY", 128))

        # 1. Prioritize Hardware Decoders
        for offset, decoder_name in enumerate(self._hardware_decoder_names()):
            factory = Gst.ElementFactory.find(decoder_name)
            if factory is None:
                continue
            factory.set_rank(primary_rank + 64 - offset)
            available_hw.append(decoder_name)

        # 2. Prioritize GL Sinks and Converters (Critical for Pi 5 DMA-bufs)
        for element_name in ["glupload", "glcolorconvert", "glimagesink"]:
            factory = Gst.ElementFactory.find(element_name)
            if factory:
                factory.set_rank(primary_rank + 10)

        if not available_hw:
            return

        for decoder_name in self._software_decoder_names():
            factory = Gst.ElementFactory.find(decoder_name)
            if factory is None:
                continue
            factory.set_rank(min(factory.get_rank(), secondary_rank - 1))

        log_info(
            f"Gst: Re-prioritized decoders and sinks for hardware path: {', '.join(available_hw)}"
        )

    def _discover_active_decoder(self):
        """Return the active decoder element name if one is present in the pipeline."""
        if not self.pipeline:
            return None

        def has_video_output(element):
            try:
                pad_iterator = element.iterate_src_pads()
                while True:
                    pad_result, pad = pad_iterator.next()
                    if pad_result == Gst.IteratorResult.OK:
                        caps = pad.get_current_caps() or pad.query_caps(None)
                        if not caps:
                            continue
                        for index in range(caps.get_size()):
                            structure = caps.get_structure(index)
                            if structure and structure.get_name().startswith("video/"):
                                return True
                    elif pad_result == Gst.IteratorResult.DONE:
                        break
                    else:
                        break
            except Exception:
                return False
            return False

        try:
            iterator = self.pipeline.iterate_recurse()
            while True:
                result, value = iterator.next()
                if result == Gst.IteratorResult.OK:
                    factory = value.get_factory()
                    if factory is None:
                        continue
                    factory_name = factory.get_name()
                    if "dec" in factory_name and factory_name not in {
                        "decodebin",
                        "uridecodebin",
                        "decodebin3",
                    } and has_video_output(value):
                        return factory_name
                elif result == Gst.IteratorResult.DONE:
                    break
                else:
                    break
        except Exception:
            return None

        return None

    def _is_video_decoder_factory(self, factory) -> bool:
        if factory is None:
            return False

        klass = factory.get_metadata(Gst.ELEMENT_METADATA_KLASS) or ""
        return "Decoder" in klass and "Video" in klass

    def _on_deep_element_added(self, _bin, _sub_bin, element):
        factory = element.get_factory()
        if not self._is_video_decoder_factory(factory):
            return

        factory_name = factory.get_name()
        if factory_name not in self.decoder_candidates:
            self.decoder_candidates.append(factory_name)

    def _preferred_sink_names(self):
        """Return sink candidates in priority order for the current environment."""
        if os.environ.get("DISPLAY"):
            # On Pi 5 with X11, glimagesink is the best performer for HW decoders
            return ["glimagesink", "xvimagesink", "autovideosink"]
        return ["kmssink", "glimagesink", "autovideosink"]

    def _create_video_sink(self):
        """Create a hardware-optimized sink bin for the current runtime."""
        if os.environ.get("DISPLAY"):
            # Explicitly build a GL bin. This is MUCH more robust for Pi 5's 
            # stateless decoder which outputs tiled DMA-bufs.
            try:
                # Using glupload and glcolorconvert ensures the hardware 
                # decoder's output is correctly brought into the GL context.
                bin_desc = "glupload ! glcolorconvert ! glimagesink name=sink"
                sink_bin = Gst.parse_bin_from_description(bin_desc, True)
                if sink_bin:
                    return sink_bin, "gl-optimized-bin"
            except Exception as e:
                log_warning(f"Gst: Failed to create GL sink bin: {e}")

        for sink_name in self._preferred_sink_names():
            sink = Gst.ElementFactory.make(sink_name, "videosink")
            if sink:
                return sink, sink_name
        return None, None

    def load(self, video_path: str) -> bool:
        if not os.path.exists(video_path):
            log_error(f"Gst: Video file not found: {video_path}")
            return False

        self.video_path = video_path
        self._reprioritize_decoders()

        # Always use playbin - it is much more robust at negotiating hardware 
        # buffers (DMABuf) than a manually constructed pipeline.
        self.pipeline = Gst.ElementFactory.make("playbin", "player")
        self.pipeline_kind = "playbin"
        if not self.pipeline:
            log_error("Gst: Failed to create playbin element")
            return False

        uri = "file://" + os.path.abspath(video_path)
        self.pipeline.set_property("uri", uri)

        # Conditionally disable audio in playbin to avoid PipeWire/ALSA errors 
        # when a sound card is missing or not needed.
        if not self.enable_audio:
            # Flag 1 << 1 is GST_PLAY_FLAG_AUDIO
            self.pipeline.set_property("flags", self.pipeline.get_property("flags") & ~(1 << 1))
            log_info("Gst: Audio output disabled by configuration")
        else:
            log_info("Gst: Audio output enabled")

        sink, sink_name = self._create_video_sink()
        if sink:
            self.pipeline.set_property("video-sink", sink)

        self.decoder_candidates = []
        self.decoder_name = None
        self.pipeline.connect("deep-element-added", self._on_deep_element_added)

        self.video_sink_name = sink_name
        self.hardware_accel_preferred = sink_name in {"kmssink", "gl-optimized-bin", "glimagesink", "xvimagesink"}
        if sink_name:
            if self.hardware_accel_preferred:
                log_info(f"Gst: Using hardware-preferred video sink '{sink_name}'")
            else:
                log_warning(
                    f"Gst: Using fallback video sink '{sink_name}'; hardware acceleration is not confirmed"
                )
        else:
            log_warning("Gst: No explicit video sink available; using default sink")

        # Set up the bus to watch for messages
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        # Start the GLib MainLoop in a separate thread
        self.loop = GLib.MainLoop()
        self.loop_thread = threading.Thread(target=self.loop.run, daemon=True)
        self.loop_thread.start()

        log_info(f"Gst: Loaded {video_path} with pipeline '{self.pipeline_kind}'")
        return True

    def _on_bus_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            log_info("Gst: End of stream reached, looping...")
            self.seek(0)
        elif t == Gst.MessageType.ASYNC_DONE:
            self.is_seeking = False
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            log_error(f"Gst Error: {err.message}")
            self.state = PlayerState.ERROR

    def _is_ready(self) -> bool:
        """Check if the pipeline is in a state that allows queries and seeks."""
        if not self.pipeline:
            return False
        # Use a short timeout (0) to check current state without blocking
        success, current, _ = self.pipeline.get_state(0)
        return success != Gst.StateChangeReturn.FAILURE and current >= Gst.State.PAUSED

    def play(self) -> bool:
        if not self.pipeline:
            return False
        
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            log_error("Gst: Failed to set pipeline to PLAYING")
            self.state = PlayerState.ERROR
            return False
            
        self.state = PlayerState.PLAYING
        
        # Wait up to 100ms (reduced from 500ms) for the pipeline to reach PAUSED/PLAYING
        self.pipeline.get_state(0.1 * Gst.SECOND)
        
        self.decoder_name = self._discover_active_decoder()
        if not self.decoder_name and self.decoder_candidates:
            self.decoder_name = self.decoder_candidates[-1]
            
        if self.decoder_name:
            if any(sw in self.decoder_name for sw in self._software_decoder_names()):
                log_warning(
                    f"Gst: PERFORMANCE WARNING: Using software decoder '{self.decoder_name}'. Sync may be unstable on Pi!"
                )
            else:
                log_info(f"Gst: Active hardware decoder '{self.decoder_name}'")
        else:
            log_warning("Gst: Could not identify active decoder element")
            
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
            self.is_seeking = False

    def seek(self, seconds: float, accurate: bool = True) -> bool:
        """
        Perform a seek.
        accurate=True: Uses ACCURATE flag (slow, precise)
        accurate=False: Uses KEY_UNIT flag (fast, snaps to keyframe)
        """
        if not self._is_ready():
            return False
        
        # Convert seconds to nanoseconds
        nanos = int(seconds * Gst.SECOND)
        
        flags = Gst.SeekFlags.FLUSH
        if accurate:
            flags |= Gst.SeekFlags.ACCURATE
        else:
            flags |= Gst.SeekFlags.KEY_UNIT
        
        self.is_seeking = True
        success = self.pipeline.seek(
            self.current_rate,
            Gst.Format.TIME, 
            flags, 
            Gst.SeekType.SET, nanos,
            Gst.SeekType.NONE, -1
        )
        return success

    def set_speed(self, rate: float) -> bool:
        """
        Adjust playback rate. Attempts seamless rate change, fallbacks to 
        flushing seek if hardware (like Pi 5 v4l2sl) rejects it.
        """
        if not self._is_ready():
            return False
            
        if abs(rate - self.current_rate) < 0.001:
            return True

        # 1. Try INSTANT_RATE_CHANGE (seamless)
        event = Gst.Event.new_seek(
            rate,
            Gst.Format.TIME,
            Gst.SeekFlags.INSTANT_RATE_CHANGE,
            Gst.SeekType.NONE, 0,
            Gst.SeekType.NONE, -1
        )
        
        if self.pipeline.send_event(event):
            self.current_rate = rate
            log_info(f"Gst: Playback rate adjusted to {rate:.4f} (seamless)")
            return True

        # 2. Fallback to Flushing Seek (for hardware that rejects instant changes)
        # This is less seamless (minor flicker) but works on Pi 5.
        pos = self.get_position()
        if pos is None:
            log_warning("Gst: Cannot adjust rate (position query failed)")
            return False

        success = self.pipeline.seek(
            rate,
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
            Gst.SeekType.SET, int(pos * Gst.SECOND),
            Gst.SeekType.NONE, -1
        )
        
        if success:
            self.current_rate = rate
            if self.debug_mode:
                log_info(f"Gst: Playback rate adjusted to {rate:.4f} (flushing fallback)")
        else:
            log_warning(f"Gst: Failed to adjust rate to {rate}")
            
        return success

    def get_position(self) -> Optional[float]:
        if not self._is_ready():
            return None
        
        success, position = self.pipeline.query_position(Gst.Format.TIME)
        if success:
            return position / Gst.SECOND
        return None

    def get_duration(self) -> float:
        if not self._is_ready():
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
        pass

    def cleanup(self) -> None:
        self.stop()
        if self.loop:
            self.loop.quit()
        self.pipeline = None
        self.decoder_candidates = []
        log_info("Gst: Cleanup complete")

    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info["video_sink"] = self.video_sink_name or "default"
        info["hardware_accel_preferred"] = self.hardware_accel_preferred
        info["decoder"] = self.decoder_name or "unknown"
        info["pipeline_kind"] = self.pipeline_kind
        info["is_seeking"] = self.is_seeking
        
        # Add human-readable hardware status
        is_hw = False
        if self.decoder_name:
            is_hw = not any(sw in self.decoder_name for sw in self._software_decoder_names())
            
        info["is_hardware_accelerated"] = is_hw
        return info
