---
name: ksync-sync-theory-reference
description: >
  The domain-theory pack for kSync synchronization: GStreamer's clock/base_time/
  running-time/segment model, the netclock anchor math as implemented here,
  GstNetClientClock, the udp P-controller equations and stability, RTT/2 latency
  compensation, why NTP is unnecessary, and display-chain latency physics. Load this
  when reasoning about WHY sync behaves as it does, before modifying sync math, or
  when evaluating a new synchronization approach.
---

# kSync Sync Theory Reference

The theory a mid-level engineer needs, exactly as it applies to this repo.
Code references verified 2026-07-06 (commit cb09752).

When NOT to use: live triage → `ksync-debugging-playbook`; encoding/codecs →
`ksync-media-encoding-reference`; executing the precision campaign →
`ksync-sub10ms-campaign`.

## 1. The GStreamer time model (the part everyone gets wrong)

Definitions (first use, remember these):

- **Pipeline clock**: a monotonically increasing time source shared by all elements of
  a pipeline. Default: system monotonic clock. Can be replaced (`pipeline.use_clock`).
- **base_time**: the clock timestamp at which the pipeline "started". Sinks render a
  buffer when `clock_time == base_time + buffer_running_time`.
- **running time**: time elapsed in PLAYING state; restarts at 0 after a **flushing**
  seek; **accumulates** across non-flushing SEGMENT seeks (that's what makes gapless
  looping gapless).
- **stream time / position**: where you are in the media file (what `query_position`
  reports).
- **segment**: the mapping between buffer timestamps and running time; seeks install a
  new segment.
- `pipeline.set_start_time(GST_CLOCK_TIME_NONE)`: disables the pipeline's automatic
  base_time recalculation, so OUR base_time survives state changes and flushes. Both
  netclock join and realign rely on this (src/video/drivers/gst_driver.py,
  `use_network_clock`).

Critical consequences used all over kSync:

- A **FLUSH seek resets running time to 0**. With automatic management the pipeline
  redistributes a fresh base_time when the seek settles — this is the base_time race:
  reading `get_base_time()` mid-seek returns a value that will be stale a moment later.
  kSync's `get_pipeline_base_time()` therefore blocks on `get_state()` first.
- A **SEGMENT (non-flushing) seek back to 0 at SEGMENT_DONE** keeps running time
  accumulating → loop playback with continuous timeline (`_on_bus_message`,
  `_enable_gapless_looping`).

## 2. The netclock anchor math (as implemented)

Goal: collaborator's position tracks `position_L(t) = (t − B_L) mod D` where `B_L` is
the leader's (settled) base_time and `D` the duration, `t` = shared clock time.

Join (`GstDriver._align_to_network_clock`), executed prerolled-PAUSED:

```
T0     = clock.now + margin            # margin = 0.5s
target = (T0 − B_L − video_offset) mod D
seek FLUSH|ACCURATE|SEGMENT to target (stop = D)   # SEGMENT arms gapless looping
set_base_time(T0)                       # running-time 0 == position `target` renders at T0
set_state(PLAYING)
```

Why it works: after the flush, buffer at position `target` has running time 0, so it
renders at `base_time + 0 = T0`. Thereafter
`position_C(t) = target + (t − T0) = t − B_L − video_offset ≡ position_L(t) − video_offset (mod D)`.
Both pipelines share the clock, so rates are identical by construction — zero drift,
only a possible constant offset, which is exactly what `video_offset` and the watchdog
address. If the align seek settles later than `margin`, the first frames are late by
the overrun; QoS absorbs small overruns and the watchdog catches gross ones.

Why the naive version failed (archaeology E9): sharing `B_L` but starting at position
0 makes every frame ~1s late; sinks drop late frames only as fast as the decoder can
produce them, and Pi decoders run ≈1–3× realtime — catch-up never completes. **Late-
join must be solved by seeking, not by frame-dropping.**

Realign while PLAYING (`netclock_realign(leader_position)`): same recipe with
`target = (leader_position + margin) · s`, `set_base_time(clock.now + margin)` after
issuing the seek. Used by the collaborator watchdog when |median deviation| >
`netclock_max_drift` (default 0.5s) — e.g. after a leader manual seek or an EOS
flushing fallback.

## 3. GstNetTimeProvider / GstNetClientClock

- Leader (netclock mode, and only when NOT itself a net client) serves its pipeline
  clock: `GstNet.NetTimeProvider.new(clock, "0.0.0.0", 9997)` (gst_driver.play()).
- Collaborator creates `GstNet.NetClientClock.new("ksync-clock", leader_ip, 9997, 0)`
  and `wait_for_sync(5s)`. The protocol is simple UDP request/response time sampling
  with jitter filtering — think "purpose-built NTP for pipelines".
- Expected precision: sub-millisecond on wired LAN; low-millisecond on decent WiFi.
  (kSync desktop loopback measurement: offsets of 0.1–2ms. **Pi-hardware numbers are
  not yet measured** — that's a campaign gate.)
- On `wait_for_sync` timeout the code logs `Clock sync timeout. Proceeding anyway...`
  and continues; since 5570b2d the collaborator additionally falls back to the udp
  controller whenever no net clock is established, so a dead 9997 degrades quality
  instead of killing correction.

## 4. The udp-mode P-controller

Pipeline of compensations applied to each received tick (collaborator.py
`_process_sync_tick`):

```
adjusted = leader_time
         + max(0, sent_at − position_read_time)   # leader-side processing lag (same clock: leader's)
         + smoothed_latency (if enabled)          # one-way transport ≈ RTT/2, EWMA α=0.3
         + max(0, now − received_at)              # local processing lag (same clock: ours)
received_at uses SO_TIMESTAMPNS kernel receive timestamps when available.
```

Note every term is a **same-clock** difference or an RTT-derived estimate — this is
the proof that NTP is unnecessary (archaeology E7).

Correction (`_maintain_video_sync`), where `deviation = video_pos − adjusted` with
mod-duration wrap to ±D/2:

| |median deviation| | action |
|---|---|
| < min_drift (0.005s) | nothing (deadband — prevents jitter chase) |
| deadband → max_drift (0.15s) | rate nudge: `rate = clamp(1 − dev·kp, min_rate, max_rate)`, kp=2.0, [0.9, 1.2] |
| ≥ max_drift | ACCURATE flushing seek to leader position, settle 1.0s |
| > 2s (5s near loop seam) | fast KEY_UNIT seek; repeat within 15s escalates to ACCURATE (keyframe-hover fix cb09752); settle 2.5s |

Filtering: median of last `max_samples` (3) ticks; first `FAST_SYNC_THRESHOLD` (10)
ticks use instantaneous deviation for fast startup. Loop-seam suppression: within 3s
of the seam, seeks are suppressed (rate-only) because non-flushing loop offsets
transiently diverge — but suppression is disabled during startup.

Stability intuition: this is a pure proportional controller on a plant with delay
(decode + measurement latency). Gain too high → overshoot/oscillation.
`tests/test_sync_simulation.py` demonstrates it: kp=20 unclamped produces ~47 zero
crossings; kp=0.1 settles a 0.2s offset to <10ms with zero crossings = 0. The deadband
prevents limit-cycling on measurement noise. Physical ceiling: measurement jitter
(tick transport + position-cache extrapolation, ~±10–20ms) — udp mode cannot reliably
go below a few tens of ms; that is WHY netclock exists.

## 5. Rate changes and seeks on Pi hardware

`set_speed` tries `INSTANT_RATE_CHANGE` (seamless) and falls back to a flushing
ACCURATE seek at the current position (Pi 5 v4l2sl decoders reject instant rate
changes — the flicker on rate change is this fallback). Fast seeks are KEY_UNIT
(land on a keyframe — hence the GOP discipline in `ksync-media-encoding-reference`);
ACCURATE seeks decode from the previous keyframe to the target (cost ∝ GOP length ×
decode speed).

## 6. Display-chain latency (the last mile)

Everything above synchronizes the *signal at the HDMI connector*. Panels then add
scaler/motion-processing/buffering delay — typically 20–100+ms, invisible to software,
different per model and per picture mode. Consequences:

- Perfect clock sync can still LOOK offset; the collaborator "running ahead" with a
  clean CSV is display delta, not a bug.
- Policy (owner decision 2026-07-06): **identical display model + game mode on all
  nodes** → delta ≈ 0. For mixed hardware: `video_offset` (seconds; positive delays
  that device), applied in the udp comparison and the netclock join.
- Measurement: phone slow-mo of both screens in one shot; offset = frame difference ×
  (1000/fps) ms. EDID/CEC latency reporting is NOT trustworthy on consumer TVs.
- The decode-vs-glass distinction also explains why `is_wall_clock`/fakesink modes and
  the CSV all describe *pipeline* time, never glass time.

## Provenance and maintenance

Written 2026-07-06 against gst_driver.py, collaborator.py, leader.py,
communication.py at cb09752. Re-verify:

- Anchor recipe unchanged: `grep -n "_align_to_network_clock\|set_start_time\|set_base_time" src/video/drivers/gst_driver.py`
- Controller constants: `grep -n "FAST_SYNC_THRESHOLD\|max_samples\|def kp\|def max_drift" collaborator.py src/config/manager.py`
- Compensation chain: `grep -n "position_read_time\|_smoothed_latency\|received_at" collaborator.py`
- Oscillation demo still passes: `python3 -m unittest tests.test_sync_simulation -v 2>&1 | tail -5`
