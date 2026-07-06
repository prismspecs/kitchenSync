#!/usr/bin/env python3
"""
kSync netclock golden harness.

Verifies the two netclock guarantees end-to-end using real GStreamer pipelines:
  1. LATE JOIN: a collaborator joining ~1.5s after the leader aligns to the
     leader's timeline (steady-state |offset| < threshold).
  2. REALIGN: after a deliberate 3s leader seek (which desyncs a netclock
     follower by design), netclock_realign-style re-anchoring recovers.

Mirrors src/video/drivers/gst_driver.py: use_network_clock + _align_to_network_clock
+ netclock_realign. Uses fakesink sync=true so pipelines are clocked like a display.

Usage:
  python3 netclock_verify.py [/path/to/video.mp4] [--threshold-ms 50]
  (no video argument -> videotestsrc, 30s virtual duration)

Exit: 0 = both PASS, 1 = FAIL.
"""
import os
import sys
import time

import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstNet", "1.0")
from gi.repository import Gst, GstNet  # noqa: E402

Gst.init(None)
PORT = 39999
MARGIN_NS = int(0.5 * Gst.SECOND)


def make_pipeline(video):
    if video:
        p = Gst.ElementFactory.make("playbin", None)
        p.set_property("uri", "file://" + os.path.abspath(video))
        p.set_property("flags", p.get_property("flags") & ~(1 << 1))  # audio off
        sink = Gst.ElementFactory.make("fakesink", "videosink")
        sink.set_property("sync", True)
        p.set_property("video-sink", sink)
        return p
    return Gst.parse_launch("videotestsrc ! video/x-raw,framerate=30/1 ! fakesink sync=true")


def wait_settled(p, timeout_s=5.0):
    ret, cur, _ = p.get_state(int(timeout_s * Gst.SECOND))
    return ret != Gst.StateChangeReturn.FAILURE


def duration_ns(p):
    ok, d = p.query_duration(Gst.Format.TIME)
    return d if ok and d > 0 else 30 * Gst.SECOND


def pos_s(p):
    ok, v = p.query_position(Gst.Format.TIME)
    return v / Gst.SECOND if ok else None


def segment_seek(p, start_ns, stop_ns):
    return p.seek(1.0, Gst.Format.TIME,
                  Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE | Gst.SeekFlags.SEGMENT,
                  Gst.SeekType.SET, start_ns, Gst.SeekType.SET, stop_ns)


def steady_offset_ms(leader, collab, samples=8, dt=0.5):
    vals = []
    for _ in range(samples):
        lp, cp = pos_s(leader), pos_s(collab)
        if lp is not None and cp is not None:
            vals.append((cp - lp) * 1000.0)
        time.sleep(dt)
    tail = vals[-4:] if len(vals) >= 4 else vals
    return sum(tail) / len(tail) if tail else float("nan")


def main():
    video = None
    threshold = 50.0
    args = sys.argv[1:]
    for i, a in enumerate(list(args)):
        if a == "--threshold-ms":
            threshold = float(args[i + 1])
        elif not a.startswith("--") and (i == 0 or args[i - 1] != "--threshold-ms"):
            video = a

    # --- leader ---
    leader = make_pipeline(video)
    leader.set_state(Gst.State.PLAYING)
    assert wait_settled(leader), "leader failed to start"
    provider = GstNet.NetTimeProvider.new(leader.get_clock(), "127.0.0.1", PORT)  # noqa: F841
    # arm gapless looping like GstDriver._enable_gapless_looping
    segment_seek(leader, 0, duration_ns(leader))
    wait_settled(leader)
    base_time = leader.get_base_time()  # settled read (get_state above)
    print(f"[leader] running; settled base_time={base_time}")

    time.sleep(1.5)  # simulate start-command latency + collaborator startup

    # --- collaborator: use_network_clock + align ---
    collab = make_pipeline(video)
    clock = GstNet.NetClientClock.new("ksync-verify", "127.0.0.1", PORT, 0)
    synced = clock.wait_for_sync(5 * Gst.SECOND)
    print(f"[collab] net clock synced={synced}")
    collab.use_clock(clock)
    collab.set_start_time(Gst.CLOCK_TIME_NONE)

    collab.set_state(Gst.State.PAUSED)
    assert wait_settled(collab), "collab preroll failed"
    dur = duration_ns(collab)
    t0 = clock.get_time() + MARGIN_NS
    target = (t0 - base_time) % dur
    assert segment_seek(collab, target, dur), "align seek rejected"
    wait_settled(collab)
    collab.set_base_time(t0)
    collab.set_state(Gst.State.PLAYING)
    wait_settled(collab)

    join = steady_offset_ms(leader, collab)
    join_ok = abs(join) < threshold
    print(f"JOIN    steady-state offset {join:+.1f}ms -> {'PASS' if join_ok else 'FAIL'}")

    # --- deliberate leader divergence, then realign ---
    print("[leader] seeking +3s (simulates operator seek -> follower desync)")
    lp = pos_s(leader) or 0.0
    leader.seek(1.0, Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                Gst.SeekType.SET, int(((lp + 3.0) % (dur / Gst.SECOND)) * Gst.SECOND),
                Gst.SeekType.NONE, -1)
    wait_settled(leader)
    time.sleep(1.0)

    # netclock_realign recipe: seek to leader_pos+margin, anchor base_time=now+margin
    lp = pos_s(leader)
    t0 = clock.get_time() + MARGIN_NS
    target = int(((lp + 0.5) % (dur / Gst.SECOND)) * Gst.SECOND)
    assert segment_seek(collab, target, dur), "realign seek rejected"
    collab.set_base_time(t0)
    wait_settled(collab)

    re = steady_offset_ms(leader, collab)
    re_ok = abs(re) < threshold
    print(f"REALIGN steady-state offset {re:+.1f}ms -> {'PASS' if re_ok else 'FAIL'}")

    leader.set_state(Gst.State.NULL)
    collab.set_state(Gst.State.NULL)
    return 0 if (join_ok and re_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
