#!/usr/bin/env python3
"""Verify the active GStreamer playback path on the current machine."""

import argparse
import json
import os
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
    "vaapih264dec",
    "nvh264dec",
    "avdec_h264",
]


def _element_available(name: str) -> bool:
    return Gst.ElementFactory.find(name) is not None


def _preferred_sink_names() -> list[str]:
    if os.environ.get("DISPLAY"):
        return ["glimagesink", "xvimagesink", "autovideosink"]
    return ["kmssink", "glimagesink", "autovideosink"]


def _create_video_sink():
    for sink_name in _preferred_sink_names():
        sink = Gst.ElementFactory.make(sink_name, "videosink")
        if sink:
            return sink, sink_name
    return None, None


def build_report(video_path: Path, sample_seconds: float) -> dict:
    if not GST_AVAILABLE:
        raise RuntimeError("GStreamer Python bindings are not available")

    Gst.init(None)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    report = {
        "video": str(video_path),
        "display": os.environ.get("DISPLAY", ""),
        "session_type": os.environ.get("XDG_SESSION_TYPE", ""),
        "preferred_sinks": _preferred_sink_names(),
        "available_sinks": {
            name: _element_available(name)
            for name in ["glimagesink", "xvimagesink", "kmssink", "autovideosink"]
        },
        "available_decoders": {
            name: _element_available(name) for name in KNOWN_DECODERS
        },
    }

    pipeline = Gst.ElementFactory.make("playbin", "verifier")
    if not pipeline:
        raise RuntimeError("Failed to create GStreamer playbin")

    sink, sink_name = _create_video_sink()
    if sink is not None:
        pipeline.set_property("video-sink", sink)
    report["selected_sink"] = sink_name or "default"
    report["hardware_preferred_sink"] = sink_name in {"kmssink", "glimagesink", "xvimagesink"}

    pipeline.set_property("uri", video_path.resolve().as_uri())
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

        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Failed to start GStreamer playback")

        time.sleep(sample_seconds)

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
        report["decode_path_note"] = (
            "Hardware decode cannot be fully proven here; this report only confirms sink preference "
            "and available decoder plugins on the current machine."
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

    report["ok"] = bool(report.get("display_path_verified"))

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ok"] else 2

    print("GStreamer Hardware Verification")
    print(f"Video: {report['video']}")
    print(f"DISPLAY: {report['display'] or 'unset'}")
    print(f"Session: {report['session_type'] or 'unknown'}")
    print(f"Preferred sinks: {', '.join(report['preferred_sinks'])}")
    print(f"Selected sink: {report.get('selected_sink', 'unknown')}")
    print(f"Playback state: {report.get('state', 'unknown')}")
    print(f"Position after sample: {report.get('position_after_sample', 0.0):.3f}s")
    print(f"Duration: {report.get('duration', 0.0):.3f}s")
    print(f"Hardware-preferred sink: {report.get('hardware_preferred_sink', False)}")
    print(f"Playback progressed: {report.get('playback_progress_ok', False)}")
    print("Available decoders:")
    for name, available in report["available_decoders"].items():
        print(f"  {name}: {'yes' if available else 'no'}")
    print(report["decode_path_note"])
    if report["ok"]:
        print("Result: hardware-preferred display path verified")
        return 0
    print("Result: hardware acceleration not fully verified")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())