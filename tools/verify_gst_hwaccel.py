#!/usr/bin/env python3
"""Verify the active GStreamer playback path on the current machine."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst, GLib

    GST_AVAILABLE = True
except ImportError:
    GST_AVAILABLE = False


KNOWN_DECODERS = [
    "v4l2h264dec",
    "v4l2slh264dec",
    "v4l2h265dec",
    "v4l2slh265dec",
    "v4l2slhevcdec",
    "vah264dec",
    "vah265dec",
    "vaapih264dec",
    "vaapih265dec",
    "nvh264dec",
    "nvh265dec",
    "avdec_h264",
    "avdec_h265",
]


def _probe_video_stream(video_path: Path) -> dict:
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
                str(video_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return {
            "probe_ok": False,
            "probe_error": "ffprobe not installed",
        }

    if result.returncode != 0:
        return {
            "probe_ok": False,
            "probe_error": result.stderr.strip() or "ffprobe failed",
        }

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "probe_ok": False,
            "probe_error": "ffprobe returned invalid JSON",
        }

    streams = payload.get("streams") or []
    if not streams:
        return {
            "probe_ok": False,
            "probe_error": "No video stream found",
        }

    stream = streams[0]
    return {
        "probe_ok": True,
        "codec_name": stream.get("codec_name", "unknown"),
        "profile": stream.get("profile", "unknown"),
        "pix_fmt": stream.get("pix_fmt", "unknown"),
        "width": stream.get("width", 0),
        "height": stream.get("height", 0),
    }


def _element_available(name: str) -> bool:
    return Gst.ElementFactory.find(name) is not None


def _preferred_sink_names() -> list[str]:
    if os.environ.get("DISPLAY"):
        return ["glsinkbin(glimagesink)", "glimagesink", "xvimagesink", "autovideosink"]
    return ["kmssink", "glimagesink", "autovideosink"]


def _create_gl_sinkbin():
    sink_bin = Gst.ElementFactory.make("glsinkbin", "videosink")
    inner_sink = Gst.ElementFactory.make("glimagesink", "glimagesink")
    if not sink_bin or not inner_sink:
        return None, None

    sink_bin.set_property("sink", inner_sink)
    return sink_bin, "glsinkbin(glimagesink)"


def _create_video_sink():
    if os.environ.get("DISPLAY"):
        sink, sink_name = _create_gl_sinkbin()
        if sink:
            return sink, sink_name

    for sink_name in _preferred_sink_names():
        if sink_name == "glsinkbin(glimagesink)":
            continue
        sink = Gst.ElementFactory.make(sink_name, "videosink")
        if sink:
            return sink, sink_name
    return None, None


def _create_explicit_hevc_sink():
    sink = Gst.ElementFactory.make("autovideosink", "videosink")
    if sink:
        return sink, "autovideosink"
    return _create_video_sink()


def _create_video_converter():
    for converter_name in ["v4l2convert", "videoconvert"]:
        converter = Gst.ElementFactory.make(converter_name, converter_name)
        if converter:
            return converter, converter_name
    return None, None


def _should_use_explicit_hevc_pipeline(video_stream: dict) -> bool:
    if video_stream.get("codec_name") != "hevc":
        return False
    return all(
        Gst.ElementFactory.find(name) is not None
        for name in ["parsebin", "v4l2slh265dec"]
    )


def _build_explicit_hevc_pipeline(video_path: Path, report: dict):
    # v4l2slh265dec outputs NV12 via DMA-buf.  autovideosink on X11 may choose
    # xvimagesink which cannot import DMA-buf, causing backwards caps negotiation
    # to fail and v4l2slh265dec to report "no valid frames found".  Use
    # glimagesink (EGL / DMA-buf import) on X11, kmssink on headless KMS.
    if os.environ.get("DISPLAY") and _element_available("glimagesink"):
        sink_elem = "glimagesink"
        sink_name = "glimagesink"
    elif _element_available("kmssink"):
        sink_elem = "kmssink"
        sink_name = "kmssink"
    else:
        sink_elem = "autovideosink"
        sink_name = "autovideosink"

    # v4l2slh265dec is a stateless V4L2 decoder that requires exactly one
    # access unit per buffer in Annex-B byte-stream format (alignment=au).
    # parsebin autoplugs h265parse internally to satisfy those caps;
    # an explicit capsfilter here causes parsebin to try to route audio
    # through the video caps filter, which fails at the qtdemux level with
    # a fatal NOT_LINKED bus error.  Let parsebin handle caps negotiation.
    pipeline = Gst.parse_launch(
        f"filesrc name=filesrc ! parsebin ! v4l2slh265dec ! {sink_elem} name=videosink"
    )
    if not pipeline:
        raise RuntimeError("Gst.parse_launch failed to create explicit HEVC pipeline")

    filesrc = pipeline.get_by_name("filesrc")
    if not filesrc:
        raise RuntimeError("filesrc element not found in parsed HEVC pipeline")
    filesrc.set_property("location", str(video_path.resolve()))

    report["pipeline_kind"] = "explicit-hevc"
    report["selected_converter"] = "none"
    return pipeline, sink_name


def _ensure_display_session_ready():
    display = os.environ.get("DISPLAY")
    if not display:
        return

    result = subprocess.run(
        ["xset", "q"],
        env=os.environ,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "DISPLAY is set but no X11 session is responding. Start the local X session first with ./tools/start_x.sh, then rerun the verifier."
        )


def _reprioritize_decoders():
    hardware_decoder_names = [
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
    software_decoder_names = ["avdec_h264", "avdec_h265"]

    primary_rank = int(getattr(Gst.Rank, "PRIMARY", 256))
    secondary_rank = int(getattr(Gst.Rank, "SECONDARY", 128))
    available_hw = []

    for offset, decoder_name in enumerate(hardware_decoder_names):
        factory = Gst.ElementFactory.find(decoder_name)
        if factory is None:
            continue
        factory.set_rank(primary_rank + 64 - offset)
        available_hw.append(decoder_name)

    if not available_hw:
        return []

    for decoder_name in software_decoder_names:
        factory = Gst.ElementFactory.find(decoder_name)
        if factory is None:
            continue
        factory.set_rank(min(factory.get_rank(), secondary_rank - 1))

    return available_hw


def _discover_active_decoder(pipeline):
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
        iterator = pipeline.iterate_recurse()
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


def _is_video_decoder_factory(factory) -> bool:
    if factory is None:
        return False

    klass = factory.get_metadata(Gst.ELEMENT_METADATA_KLASS) or ""
    return "Decoder" in klass and "Video" in klass


def _attach_decoder_probe(pipeline, report):
    report["observed_decoder_candidates"] = []

    def on_deep_element_added(_bin, _sub_bin, element):
        factory = element.get_factory()
        if not _is_video_decoder_factory(factory):
            return

        factory_name = factory.get_name()
        if factory_name not in report["observed_decoder_candidates"]:
            report["observed_decoder_candidates"].append(factory_name)

    pipeline.connect("deep-element-added", on_deep_element_added)


def build_report(video_path: Path, sample_seconds: float) -> dict:
    if not GST_AVAILABLE:
        raise RuntimeError("GStreamer Python bindings are not available")

    Gst.init(None)
    _ensure_display_session_ready()

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    report = {
        "video": str(video_path),
        "display": os.environ.get("DISPLAY", ""),
        "session_type": os.environ.get("XDG_SESSION_TYPE", ""),
        "video_stream": _probe_video_stream(video_path),
        "preferred_sinks": _preferred_sink_names(),
        "available_sinks": {
            name: _element_available(name)
            for name in ["glsinkbin", "glimagesink", "xvimagesink", "kmssink", "autovideosink"]
        },
        "available_converters": {
            name: _element_available(name) for name in ["v4l2convert", "videoconvert"]
        },
        "available_decoders": {
            name: _element_available(name) for name in KNOWN_DECODERS
        },
    }

    report["reprioritized_hardware_decoders"] = _reprioritize_decoders()

    if _should_use_explicit_hevc_pipeline(report["video_stream"]):
        pipeline, sink_name = _build_explicit_hevc_pipeline(video_path, report)
    else:
        pipeline = Gst.ElementFactory.make("playbin", "verifier")
        if not pipeline:
            raise RuntimeError("Failed to create GStreamer playbin")

        report["pipeline_kind"] = "playbin"
        report["selected_converter"] = "autoplugged"

        sink, sink_name = _create_video_sink()
        if sink is not None:
            pipeline.set_property("video-sink", sink)
        pipeline.set_property("uri", video_path.resolve().as_uri())

    _attach_decoder_probe(pipeline, report)
    report["selected_sink"] = sink_name or "default"
    report["hardware_preferred_sink"] = sink_name in {"kmssink", "glsinkbin(glimagesink)", "glimagesink", "xvimagesink"}

    loop = GLib.MainLoop()
    loop_thread = None

    bus = pipeline.get_bus()
    bus.add_signal_watch()

    def on_message(_bus, message):
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            report["pipeline_error"] = err.message
            if debug:
                report["pipeline_debug"] = debug
        elif message.type == Gst.MessageType.EOS:
            report["eos_seen"] = True

    bus.connect("message", on_message)

    try:
        loop_thread = __import__("threading").Thread(target=loop.run, daemon=True)
        loop_thread.start()

        if report.get("pipeline_kind") == "explicit-hevc":
            ret = pipeline.set_state(Gst.State.PAUSED)
            if ret == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Failed to preroll explicit HEVC pipeline")
            pipeline.get_state(Gst.SECOND * 5)

        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Failed to start GStreamer playback")

        time.sleep(sample_seconds)
        report["active_decoder"] = (
            _discover_active_decoder(pipeline)
            or ("v4l2slh265dec" if report.get("pipeline_kind") == "explicit-hevc" else None)
            or (report["observed_decoder_candidates"][-1] if report["observed_decoder_candidates"] else None)
            or "unknown"
        )

        state_change = pipeline.get_state(0.5)
        state = state_change.state if hasattr(state_change, "state") else state_change[1]
        state_name = state.value_nick if hasattr(state, "value_nick") else str(state)

        pos_ok, position = pipeline.query_position(Gst.Format.TIME)
        dur_ok, duration = pipeline.query_duration(Gst.Format.TIME)

        report.update(
            {
                "position_after_sample": (position / Gst.SECOND) if pos_ok else 0.0,
                "duration": (duration / Gst.SECOND) if dur_ok else 0.0,
                "state": state_name,
            }
        )
        report["playback_progress_ok"] = report["position_after_sample"] > 0.0
        report["display_path_verified"] = bool(
            report["hardware_preferred_sink"] and report["playback_progress_ok"]
        )
        report["decode_path_verified"] = report["active_decoder"] in set(
            report["reprioritized_hardware_decoders"]
        )
        report["decode_path_note"] = (
            "Hardware decode is only confirmed when the active decoder is a hardware decoder element, "
            "not avdec_h264/avdec_h265."
        )
        if report["video_stream"].get("probe_ok"):
            source_codec = report["video_stream"].get("codec_name")
            if source_codec == "h264" and report["active_decoder"] == "avdec_h264":
                report["decode_path_note"] += (
                    " The sampled file itself is H.264 on this machine, so this run does not test HEVC decode."
                )
            elif source_codec == "hevc" and report["active_decoder"] == "avdec_h264":
                report["decode_path_note"] += (
                    " The sampled file probes as HEVC, but playback instantiated avdec_h264, so verify the file path and GStreamer stream selection on this Pi."
                )
    finally:
        pipeline.set_state(Gst.State.NULL)
        if loop.is_running():
            loop.quit()
        if loop_thread is not None:
            loop_thread.join(timeout=1.0)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify KitchenSync GStreamer hardware acceleration")
    parser.add_argument(
        "--video",
        default="videos/test_video.mp4",
        help="Path to a local video file to sample",
    )
    parser.add_argument(
        "--sample-seconds",
        type=float,
        default=1.5,
        help="How long to let playback run before inspecting state",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the verification report as JSON",
    )
    args = parser.parse_args()

    try:
        report = build_report(Path(args.video), args.sample_seconds)
    except Exception as exc:
        error_report = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(error_report, indent=2, sort_keys=True))
        else:
            print(f"Verification failed: {exc}")
        return 1

    report["ok"] = bool(
        report.get("display_path_verified") and report.get("decode_path_verified")
    )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ok"] else 2

    print("GStreamer Hardware Verification")
    print(f"Video: {report['video']}")
    print(f"DISPLAY: {report['display'] or 'unset'}")
    print(f"Session: {report['session_type'] or 'unknown'}")
    print(f"Preferred sinks: {', '.join(report['preferred_sinks'])}")
    print(f"Selected sink: {report.get('selected_sink', 'unknown')}")
    print(f"Selected converter: {report.get('selected_converter', 'unknown')}")
    print(f"Playback state: {report.get('state', 'unknown')}")
    print(f"Source codec: {report.get('video_stream', {}).get('codec_name', 'unknown')}")
    print(f"Source profile: {report.get('video_stream', {}).get('profile', 'unknown')}")
    print(f"Source pixel format: {report.get('video_stream', {}).get('pix_fmt', 'unknown')}")
    print(f"Position after sample: {report.get('position_after_sample', 0.0):.3f}s")
    print(f"Duration: {report.get('duration', 0.0):.3f}s")
    print(f"Hardware-preferred sink: {report.get('hardware_preferred_sink', False)}")
    print(f"Playback progressed: {report.get('playback_progress_ok', False)}")
    print(f"Hardware decode verified: {report.get('decode_path_verified', False)}")
    print("Available decoders:")
    for name, available in report["available_decoders"].items():
        print(f"  {name}: {'yes' if available else 'no'}")
    print(report["decode_path_note"])
    if report["ok"]:
        print("Result: hardware display and hardware decode verified")
        return 0
    if report.get("display_path_verified"):
        print("Result: hardware display verified, but hardware decode is not yet verified")
        return 2
    print("Result: hardware acceleration not fully verified")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())