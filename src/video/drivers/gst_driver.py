#!/usr/bin/env python3
"""
GStreamer Implementation of the VideoDriver interface.
Provides high-performance, rate-based synchronization for Raspberry Pi.
"""

import os
import shutil
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

def get_screen_resolution() -> tuple[int, int]:
    """Get the screen resolution of the default display on X11/Wayland"""
    xrandr_path = shutil.which("xrandr")
    if xrandr_path:
        try:
            out = subprocess.check_output([xrandr_path], stderr=subprocess.DEVNULL).decode()
            for line in out.splitlines():
                if "*" in line:
                    parts = line.strip().split()
                    if parts and "x" in parts[0]:
                        w, h = parts[0].split("x")
                        return int(w), int(h)
        except Exception:
            pass
            
    xwininfo_path = shutil.which("xwininfo")
    if xwininfo_path and os.environ.get("DISPLAY"):
        try:
            out = subprocess.check_output([xwininfo_path, "-root"], stderr=subprocess.DEVNULL).decode()
            w, h = 0, 0
            for line in out.splitlines():
                if "Width:" in line:
                    w = int(line.split()[-1])
                elif "Height:" in line:
                    h = int(line.split()[-1])
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass
            
    return 0, 0

def get_pi_model() -> str:
    """Detect the Raspberry Pi model name if running on a Pi"""
    for path in ["/sys/firmware/devicetree/base/model", "/proc/device-tree/model"]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
    return ""


class GstDriver(VideoDriver):
    """
    GStreamer Driver for kSync.
    Uses playbin for robustness and custom seek events for seamless rate control.
    """

    def __init__(self, debug_mode: bool = False, enable_audio: bool = True, video_width: int = 0, video_height: int = 0, poll_interval: float = 0.05, crop_mode: str = "letterbox"):
        if not GST_AVAILABLE:
            raise ImportError("GStreamer or GObject Introspection not found. Install via OS_SETUP.md.")

        Gst.init(None)
        self.debug_mode = debug_mode
        self.enable_audio = enable_audio
        self.video_width = video_width
        self.video_height = video_height
        self.poll_interval = poll_interval
        self.crop_mode = crop_mode
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
        self._gapless_looping = False
        
        # Position polling
        self._cached_position = 0.0
        self._last_poll_time = 0.0
        self._stop_polling = threading.Event()
        self._poll_thread = None

        # MainLoop for GStreamer bus messages
        self.loop = None
        self.loop_thread = None

    def _position_poll_worker(self):
        """Background thread to poll position without blocking the main loop."""
        while not self._stop_polling.is_set():
            try:
                if self.pipeline and self.state == PlayerState.PLAYING and not self.is_seeking:
                    success, pos = self.pipeline.query_position(Gst.Format.TIME)
                    if success:
                        self._cached_position = pos / Gst.SECOND
                        self._last_poll_time = time.time()
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def _start_polling(self):
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._stop_polling.clear()
        self._poll_thread = threading.Thread(target=self._position_poll_worker, daemon=True)
        self._poll_thread.start()

    def _stop_polling_worker(self):
        self._stop_polling.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=0.1)
            self._poll_thread = None

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

        hw_decoders = self._hardware_decoder_names()

        # Optimize decoder rankings for Raspberry Pi 5:
        # - Pi 5 (BCM2712) lacks H.264 hardware decoding, so we disable H.264 hardware decoders to force software fallback.
        # - Pi 5 has a custom stateless HEVC hardware decoder (v4l2slhevcdec). We keep this active but disable
        #   other hardware HEVC decoders (like v4l2slh265dec, v4l2h265dec) which can cause stalls/hangs under X11/GL.
        pi_model = get_pi_model()
        if "Raspberry Pi 5" in pi_model:
            log_info(f"Gst: Detected Raspberry Pi 5 ('{pi_model}'). Demoting unsupported/obsolete hardware decoders.")
            
            # Disable H.264 hardware decoders (not present in hardware)
            unsupported_h264 = ["v4l2slh264dec", "v4l2h264dec", "vah264dec", "vaapih264dec", "nvh264dec"]
            for name in unsupported_h264:
                factory = Gst.ElementFactory.find(name)
                if factory:
                    factory.set_rank(0)  # Gst.Rank.NONE
            
            # Disable problematic HEVC hardware decoders, keeping only the stateless 'v4l2slhevcdec' active
            unsupported_hevc = ["v4l2slh265dec", "v4l2h265dec", "vah265dec", "vaapih265dec", "nvh265dec"]
            for name in unsupported_hevc:
                factory = Gst.ElementFactory.find(name)
                if factory:
                    factory.set_rank(0)  # Gst.Rank.NONE
            
            # Filter our hardware list to reflect these changes
            disabled_names = set(unsupported_h264 + unsupported_hevc)
            hw_decoders = [name for name in hw_decoders if name not in disabled_names]

        # 1. Prioritize Hardware Decoders
        for offset, decoder_name in enumerate(hw_decoders):
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
        self._list_available_decoders()

    def _list_available_decoders(self):
        """Log all available video decoders for diagnostics."""
        factories = Gst.ElementFactory.list_get_elements(
            Gst.ELEMENT_FACTORY_TYPE_DECODER | Gst.ELEMENT_FACTORY_TYPE_MEDIA_VIDEO,
            Gst.Rank.NONE
        )
        names = [f.get_name() for f in factories]
        log_info(f"Gst: System decoders found: {', '.join(names)}")

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
        crop_str = ""
        if getattr(self, "crop_mode", "letterbox") == "crop-to-fill":
            tw, th = self.video_width, self.video_height
            if tw <= 0 or th <= 0:
                tw, th = get_screen_resolution()
            if tw > 0 and th > 0:
                crop_str = f"aspectratiocrop aspect-ratio={tw}/{th} ! "

        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            # build a GL bin with native window size control
            try:
                if self.video_width > 0 and self.video_height > 0:
                    # Use videoscale + capsfilter to FORCE the window size at the GStreamer level
                    bin_desc = (
                        f"videoconvert ! {crop_str}videoscale ! "
                        f"capsfilter caps=\"video/x-raw, width={self.video_width}, height={self.video_height}\" ! "
                        "glupload ! glcolorconvert ! glimagesink name=sink"
                    )
                else:
                    # High-performance zero-copy path without CPU scaling overhead
                    bin_desc = (
                        f"videoconvert ! {crop_str}glupload ! glcolorconvert ! glimagesink name=sink"
                    )
                sink_bin = Gst.parse_bin_from_description(bin_desc, True)
                if sink_bin:
                    self._start_window_management_task()
                    return sink_bin, "gl-optimized-bin"
            except Exception as e:
                log_warning(f"Gst: Failed to create GL sink bin: {e}")

        for sink_name in self._preferred_sink_names():
            sink = Gst.ElementFactory.make(sink_name, "videosink")
            if sink:
                self._start_window_management_task()
                return sink, sink_name
        return None, None

    def _start_window_management_task(self):
        """Launch a background thread to find and resize the video window."""
        def window_task():
            try:
                from ui.window_manager import WindowManager
                wm = WindowManager()
                
                # Sane defaults for desktop
                target_w, target_h = 1280, 720
                if self.video_width > 0 and self.video_height > 0:
                    target_w, target_h = self.video_width, self.video_height
                
                # Potential window titles
                search_terms = ["OpenGL Renderer", "player", "GStreamer"]
                if self.video_path:
                    search_terms.append(os.path.basename(self.video_path))
                
                # Wait for window
                window_id = wm.wait_for_window(search_terms, timeout=8)
                if window_id:
                    log_info(f"Gst: Managing video window '{window_id}'")
                    
                    # 1. Basic Resize (Desktop large window)
                    if not wm.is_wayland:
                        # Move to 100,100 and set size
                        subprocess.run(["wmctrl", "-ir", window_id, "-e", f"0,100,100,{target_w},{target_h}"], check=False)
                    
                    # 2. Check if we should go full screen
                    # For now, we'll try to maximize if on desktop
                    if not wm.is_wayland:
                        # subprocess.run(["wmctrl", "-ir", window_id, "-b", "add,maximized_vert,maximized_horz"], check=False)
                        pass
                else:
                    log_warning("Gst: Could not identify video window for resizing")
            except Exception as e:
                log_error(f"Gst: Window management error: {e}")

        threading.Thread(target=window_task, daemon=True).start()

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
            # Also set audio-sink to fakesink to be doubly sure no audio device is touched
            fakesink = Gst.ElementFactory.make("fakesink", "audiofakesink")
            if fakesink:
                self.pipeline.set_property("audio-sink", fakesink)
            log_info("Gst: Audio output disabled by configuration")
        else:
            # On Pi, sometimes playbin fails if the default audio sink is busy or missing.
            # Using autoaudiosink is generally safe, but we can be explicit.
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

    def _enable_gapless_looping(self):
        """Configure the pipeline for gapless looping using SEGMENT seeks.
        
        Instead of EOS → flushing seek (which causes a position discontinuity
        and breaks collaborator sync), this makes GStreamer emit SEGMENT_DONE
        at the end, allowing a non-flushing seek back to 0.
        """
        if not self._is_ready(timeout_ms=1000):
            log_warning("Gst: Pipeline not ready for SEGMENT seek setup")
            return False

        duration_ns = -1
        success, dur = self.pipeline.query_duration(Gst.Format.TIME)
        if success and dur > 0:
            duration_ns = dur

        result = self.pipeline.seek(
            self.current_rate,
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.SEGMENT,
            Gst.SeekType.SET, 0,
            Gst.SeekType.SET, duration_ns
        )

        if result:
            self._gapless_looping = True
            log_info("Gst: Gapless looping enabled via SEGMENT seek")
        else:
            self._gapless_looping = False
            log_warning("Gst: SEGMENT seek not supported, using EOS-based looping")
        return result

    def _on_bus_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.SEGMENT_DONE:
            # Gapless loop: non-flushing seek back to start
            self.pipeline.seek(
                self.current_rate,
                Gst.Format.TIME,
                Gst.SeekFlags.SEGMENT,  # No FLUSH = gapless
                Gst.SeekType.SET, 0,
                Gst.SeekType.NONE, -1
            )
            self._cached_position = 0.0
            self._last_poll_time = time.time()
            log_info("Gst: Gapless loop point")
        elif t == Gst.MessageType.EOS:
            # Fallback path for hardware that doesn't support SEGMENT seeks
            log_info("Gst: End of stream reached, looping (flush fallback)...")
            self._cached_position = 0.0
            self._last_poll_time = time.time()
            self.seek(0)
        elif t == Gst.MessageType.ASYNC_DONE:
            # Seek complete. Add a tiny grace period to allow hardware to settle
            def clear_seeking():
                time.sleep(0.2)
                self.is_seeking = False
                log_info("Gst: Seek operation settled")
            
            threading.Thread(target=clear_seeking, daemon=True).start()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            log_error(f"Gst Error: {err.message}")
            
            # Heuristic: If we get a device or stream error while audio is enabled, 
            # it's very likely the audio sink failing.
            if self.enable_audio and ("device" in err.message.lower() or "format" in err.message.lower()):
                log_warning("Gst: Critical error detected; attempting to restart WITHOUT audio.", component="video")
                self.enable_audio = False
                # We need to restart the load in a thread to avoid bus deadlocks
                threading.Thread(target=self._restart_minimal, daemon=True).start()
            else:
                self.state = PlayerState.ERROR

    def _restart_minimal(self):
        """Restart the pipeline with minimal settings after a crash."""
        path = self.video_path
        if path:
            self.stop()
            time.sleep(0.5)
            self.load(path)
            self.play()

    def _is_ready(self, timeout_ms: int = 0) -> bool:
        """Check if the pipeline is in a state that allows queries and seeks."""
        if not self.pipeline:
            return False
        # Wait up to timeout_ms for a valid state
        millisecond = getattr(Gst, "MSECOND", int(Gst.SECOND / 1000))
        success, current, _ = self.pipeline.get_state(timeout_ms * millisecond)
        return success != Gst.StateChangeReturn.FAILURE and current >= Gst.State.PAUSED

    def play(self) -> bool:
        if not self.pipeline:
            return False
        
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            log_error("Gst: Failed to set pipeline to PLAYING")
            self.state = PlayerState.ERROR
            return False
            
        # Wait up to 1s for the pipeline to reach PAUSED/PLAYING (important for Pi hardware)
        success, current, _ = self.pipeline.get_state(1.0 * Gst.SECOND)
        if success == Gst.StateChangeReturn.FAILURE:
            log_error("Gst: Pipeline failed to reach a stable state")
            self.state = PlayerState.ERROR
            return False

        self.state = PlayerState.PLAYING
        self._cached_position = 0.0
        self._last_poll_time = time.time() # Reset poll time to current to avoid extrapolation explosion
        self._start_polling()
        
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

        # Enable gapless looping after pipeline is stable
        self._enable_gapless_looping()
            
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
            self._stop_polling_worker()

    def seek(self, seconds: float, accurate: bool = True) -> bool:
        """
        Perform a seek.
        accurate=True: Uses ACCURATE flag (slow, precise)
        accurate=False: Uses KEY_UNIT flag (fast, snaps to keyframe)
        """
        if not self._is_ready(timeout_ms=500):
            log_warning("Gst: Seek failed - pipeline not ready")
            return False
        
        # Convert seconds to nanoseconds
        nanos = int(seconds * Gst.SECOND)
        
        flags = Gst.SeekFlags.FLUSH
        if accurate:
            flags |= Gst.SeekFlags.ACCURATE
        else:
            flags |= Gst.SeekFlags.KEY_UNIT
        
        self.is_seeking = True
        # Do NOT update _cached_position here. 
        # Let the poll thread or the next valid query pick up the REAL new position.
        
        success = self.pipeline.seek(
            self.current_rate,
            Gst.Format.TIME, 
            flags, 
            Gst.SeekType.SET, nanos,
            Gst.SeekType.NONE, -1
        )
        
        if not success:
            self.is_seeking = False
            log_error(f"Gst: Seek to {seconds:.3f}s FAILED")
        else:
            log_info(f"Gst: Seek to {seconds:.3f}s initiated (accurate={accurate})")
            
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
        if not self.pipeline:
            return None
            
        if self.state != PlayerState.PLAYING or self.is_seeking:
            return self._cached_position
            
        # Fast non-blocking query using cache + extrapolation
        if self._last_poll_time <= 0:
            return self._cached_position

        elapsed = time.time() - self._last_poll_time
        # Cap extrapolation to avoid runaway values if poll thread hangs
        if elapsed > 1.0:
            return self._cached_position
            
        return self._cached_position + (elapsed * self.current_rate)

    def get_position_raw(self) -> Optional[int]:
        """Query position in nanoseconds directly."""
        if not self._is_ready():
            return None
        success, position = self.pipeline.query_position(Gst.Format.TIME)
        return position if success else None

    def get_duration(self) -> float:
        if not hasattr(self, "_duration"):
            self._duration = 0.0
            
        if not self._is_ready():
            return self._duration
        
        success, duration = self.pipeline.query_duration(Gst.Format.TIME)
        if success:
            self._duration = duration / Gst.SECOND
        return self._duration

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
        """Attempt to make the video window fullscreen using window management tools."""
        if not enabled:
            return

        def fullscreen_task():
            try:
                from ui.window_manager import WindowManager
                wm = WindowManager()
                
                # Wait for the GStreamer window to appear. 
                # Common titles: "player", "OpenGL Renderer", or the filename.
                search_terms = ["OpenGL Renderer", "player", "GStreamer"]
                if self.video_path:
                    search_terms.append(os.path.basename(self.video_path))
                
                window_id = wm.wait_for_window(search_terms, timeout=5)
                
                if window_id:
                    log_info(f"Gst: Found video window '{window_id}', applying fullscreen...")
                    if wm.is_wayland:
                        # For Wayland, we try to focus/maximize if tool supports it
                        subprocess.run(["wlrctl", "toplevel", "focus", window_id], check=False)
                    else:
                        # For X11, wmctrl can set fullscreen state directly
                        subprocess.run(["wmctrl", "-ir", window_id, "-b", "add,fullscreen"], check=False)
                else:
                    log_warning("Gst: Could not find video window to apply fullscreen")
            except Exception as e:
                log_error(f"Gst: Fullscreen error: {e}")

        # Run in background to not block the pipeline startup
        threading.Thread(target=fullscreen_task, daemon=True).start()

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
