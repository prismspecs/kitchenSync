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

    def __init__(self, debug_mode: bool = False):
        if not GST_AVAILABLE:
            raise ImportError("GStreamer or GObject Introspection not found. Install via OS_SETUP.md.")

        Gst.init(None)
        self.debug_mode = debug_mode
        self.pipeline = None
        self.video_path = None
        self.state = PlayerState.STOPPED
        self.current_rate = 1.0
        self.video_sink_name = None
        self.hardware_accel_preferred = False
        self.decoder_name = None
        self.decoder_candidates = []
        self.pipeline_kind = "playbin"
        
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
        """Prefer hardware decoders over software decoders when both exist."""
        available_hw = []
        primary_rank = int(getattr(Gst.Rank, "PRIMARY", 256))
        secondary_rank = int(getattr(Gst.Rank, "SECONDARY", 128))

        for offset, decoder_name in enumerate(self._hardware_decoder_names()):
            factory = Gst.ElementFactory.find(decoder_name)
            if factory is None:
                continue
            factory.set_rank(primary_rank + 64 - offset)
            available_hw.append(decoder_name)

        if not available_hw:
            return

        for decoder_name in self._software_decoder_names():
            factory = Gst.ElementFactory.find(decoder_name)
            if factory is None:
                continue
            factory.set_rank(min(factory.get_rank(), secondary_rank - 1))

        log_info(
            f"Gst: Re-prioritized decoders, preferring hardware path: {', '.join(available_hw)}"
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
            # On Pi with X11/Openbox, xvimagesink is generally more stable than gl
            return ["xvimagesink", "glimagesink", "autovideosink"]
        return ["kmssink", "glimagesink", "autovideosink"]

    def _create_video_sink(self):
        """Create the best available sink for the current runtime."""
        for sink_name in self._preferred_sink_names():
            sink = Gst.ElementFactory.make(sink_name, "videosink")
            if sink:
                return sink, sink_name
        return None, None

    def _probe_video_stream(self, video_path: str) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name,profile,pix_fmt,width,height",
                    "-of",
                    "json",
                    video_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return {"probe_ok": False, "probe_error": "ffprobe not installed"}

        if result.returncode != 0:
            return {"probe_ok": False, "probe_error": result.stderr.strip() or "ffprobe failed"}

        try:
            payload = __import__("json").loads(result.stdout)
        except Exception:
            return {"probe_ok": False, "probe_error": "ffprobe returned invalid JSON"}

        streams = payload.get("streams") or []
        if not streams:
            return {"probe_ok": False, "probe_error": "No video stream found"}

        stream = streams[0]
        return {
            "probe_ok": True,
            "codec_name": stream.get("codec_name", "unknown"),
            "profile": stream.get("profile", "unknown"),
            "pix_fmt": stream.get("pix_fmt", "unknown"),
            "width": stream.get("width", 0),
            "height": stream.get("height", 0),
        }

    def _should_use_explicit_hevc_pipeline(self, video_path: str) -> bool:
        video_stream = self._probe_video_stream(video_path)
        if video_stream.get("codec_name") != "hevc":
            return False
        return all(
            Gst.ElementFactory.find(name) is not None
            for name in ["qtdemux", "h265parse", "v4l2slh265dec", "videoconvert"]
        )

    def _build_explicit_hevc_pipeline(self, video_path: str):
        pipeline = Gst.Pipeline.new("player")
        filesrc = Gst.ElementFactory.make("filesrc", "filesrc")
        demux = Gst.ElementFactory.make("qtdemux", "demux")
        queue = Gst.ElementFactory.make("queue", "videoqueue")
        parser = Gst.ElementFactory.make("h265parse", "videoparse")
        decoder = Gst.ElementFactory.make("v4l2slh265dec", "videodecoder")
        convert = Gst.ElementFactory.make("videoconvert", "videoconvert")
        sink, sink_name = self._create_video_sink()

        elements = [filesrc, demux, queue, parser, decoder, convert, sink]
        if not pipeline or any(element is None for element in elements):
            return None, None

        filesrc.set_property("location", os.path.abspath(video_path))

        for element in elements:
            pipeline.add(element)

        if not filesrc.link(demux):
            return None, None
        if not queue.link(parser):
            return None, None
        if not parser.link(decoder):
            return None, None
        if not decoder.link(convert):
            return None, None
        if not convert.link(sink):
            return None, None

        def on_pad_added(_demux, pad):
            sink_pad = queue.get_static_pad("sink")
            if sink_pad and not sink_pad.is_linked():
                pad.link(sink_pad)

        demux.connect("pad-added", on_pad_added)
        return pipeline, sink_name

    def load(self, video_path: str) -> bool:
        if not os.path.exists(video_path):
            log_error(f"Gst: Video file not found: {video_path}")
            return False

        self.video_path = video_path
        self._reprioritize_decoders()

        if self._should_use_explicit_hevc_pipeline(video_path):
            self.pipeline, sink_name = self._build_explicit_hevc_pipeline(video_path)
            self.pipeline_kind = "explicit-hevc"
            if not self.pipeline:
                log_error("Gst: Failed to create explicit HEVC pipeline")
                return False
        else:
            self.pipeline = Gst.ElementFactory.make("playbin", "player")
            self.pipeline_kind = "playbin"
            if not self.pipeline:
                log_error("Gst: Failed to create playbin element")
                return False

            uri = "file://" + os.path.abspath(video_path)
            self.pipeline.set_property("uri", uri)

            sink, sink_name = self._create_video_sink()
            if sink:
                self.pipeline.set_property("video-sink", sink)

        self.decoder_candidates = []
        self.decoder_name = None
        self.pipeline.connect("deep-element-added", self._on_deep_element_added)

        self.video_sink_name = sink_name
        self.hardware_accel_preferred = sink_name in {"kmssink", "glsinkbin(glimagesink)", "glimagesink", "xvimagesink"}
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
        time.sleep(0.1)
        self.decoder_name = self._discover_active_decoder()
        if not self.decoder_name and self.decoder_candidates:
            self.decoder_name = self.decoder_candidates[-1]
        if self.decoder_name:
            log_info(f"Gst: Active decoder '{self.decoder_name}'")
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

        # INSTANT_RATE_CHANGE requires NONE/NONE seek types and no FLUSH.
        # Using position-based seek parameters here triggers GStreamer assertions
        # and causes all fine-grained sync corrections to fail.
        event = Gst.Event.new_seek(
            rate,
            Gst.Format.TIME,
            Gst.SeekFlags.INSTANT_RATE_CHANGE,
            Gst.SeekType.NONE, 0,
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
        self.decoder_candidates = []
        log_info("Gst: Cleanup complete")

    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info["video_sink"] = self.video_sink_name or "default"
        info["hardware_accel_preferred"] = self.hardware_accel_preferred
        info["decoder"] = self.decoder_name or "unknown"
        info["pipeline_kind"] = self.pipeline_kind
        return info
