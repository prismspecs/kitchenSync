---
name: ksync-diagnostics-toolkit
description: >
  How to MEASURE kSync instead of eyeballing it: the deviation CSV and its shipped
  analyzer script, tcpdump recipes per port, log grep recipes, hardware-decode probes,
  the glass-level slow-mo camera protocol, and how to read the web UI's live fields.
  Load this whenever you need numbers about sync quality, network flow, or decode
  health — before AND after any sync-related change.
---

# kSync Diagnostics Toolkit

Rule zero of this project: **sync quality is judged by instruments, never by eye.**
The two admissible instruments are the deviation CSV (pipeline-level) and slow-mo
camera footage (glass-level). Facts verified 2026-07-06.

When NOT to use: interpreting a specific failure signature → `ksync-debugging-playbook`;
pass/fail thresholds and golden tests → `ksync-validation-and-qa`.

## 1. The deviation CSV (primary instrument)

Location: `~/kitchenSync/logs/sync_deviation.csv` on each collaborator. Written per
processed sync tick (~10–20 Hz) in BOTH sync modes when `enable_deviation_log = true`
(default). Columns (from collaborator.py `_log_deviation`):

```
timestamp,leader_time,video_pos,deviation,rate,hard_seeks
```

- `deviation` = video_pos − leader_time (mod-wrapped), seconds. Negative = behind.
- `rate` = current playback-rate command (1.0000 in netclock mode — the clock rules).
- `hard_seeks` = cumulative counter; INCREMENTS are the events.

### The analyzer (ships with this skill)

```bash
python3 .agents/skills/ksync-diagnostics-toolkit/scripts/analyze_deviation.py \
    logs/sync_deviation.csv --goal-ms 50        # udp mode; use --goal-ms 10 for the netclock goal
```

Verified example output (synthetic 60s capture):

```
rows            : 1200 total, 1000 after 10.0s settle
span            : 60.0s  (20.0 samples/s)
deviation (settled, seconds):
  mean/median   : +0.0009 / +0.0012
  |dev| p50/p95/max : 7.6 / 21.8 / 31.3 ms
rate            : min 0.9373  max 1.0626  time-at-max 0%  time-at-min 0%
hard seeks      : 1 total, 0 after settle  (last at t+5.0s)
loop seams seen : 2
VERDICT: PASS — |dev| p95 21.8ms ≤ 50.0ms, no post-settle hard seeks
```

Exit code 0 = PASS, 1 = FAIL (usable in scripts/gates), 2 = insufficient data.
`--plot out.png` renders a timeline if matplotlib is available.

### Signature gallery (real numbers from real incidents)

| CSV pattern | Reading |
|---|---|
| deviation constant (e.g. −0.962) for minutes, rate 1.0000 | NO correction running — historically netclock-without-clock; today means no ticks arriving |
| hard_seeks +1 on EVERY row | failed-realign spin (pre-5570b2d builds) |
| rate glued to max_rate, gap shrinking slowly or not at all | decoder can't exceed ~1.0× — codec/hardware mismatch, not a tuning problem |
| deviation sawtooth ±~1s exactly at leader_time wrap | loop-seam artifact; suppression handles it; disappears when baseline lag is fixed |
| leader_time steps backward ~40ms, deviation blips, recovers | leader position-cache extrapolation jitter — benign at this size |
| clean near-zero deviation but screens LOOK offset | display-chain latency — go to the camera protocol (§4) |

## 2. Network instruments

```bash
sudo tcpdump -i any udp port 5005 -c 5     # sync ticks reaching this device? (~20/s)
sudo tcpdump -i any udp port 5006 -c 5     # commands/heartbeats flowing?
sudo tcpdump -i any udp port 9997 -c 5     # netclock traffic (client polls leader)
ping <peer-ip>                              # wired LAN baseline ~0.1–0.5ms
ip -4 addr show | grep inet                 # which interfaces are actually up
```

## 3. Decode / media instruments

```bash
grep -E "Active hardware decoder|PERFORMANCE WARNING" logs/kitchensync.log | tail -3
gst-inspect-1.0 | grep -E "v4l2(sl)?h?(264|265|evc)"   # decoders present on this device
gst-discoverer-1.0 media/<file> | grep -E "video|Duration"
.venv/bin/python tools/verify_gst_hwaccel.py            # full environment probe
top                                                     # during playback: avdec_* burns CPU, v4l2 doesn't
```

## 4. Glass-level measurement (the only truth for "visible sync")

Phone slow-mo (120/240 fps), both screens in ONE shot, during motion or a flash cue.
Step through frames; find the same content event on each screen.

```
offset_ms = frame_difference × (1000 / content_fps)     # 30fps content → 33.3ms per content frame
```

Do three separate measurements; report the median. A consistent offset with a clean
CSV = display-chain latency → policy is identical display model + game mode;
`video_offset` compensates mixed hardware (positive delays that device).

## 5. Web UI live fields (convenience, not evidence)

Device cards show Dev / Rate / Hard Seeks from 2-second heartbeats
(collaborator `_current_deviation` / `_current_playback_rate` / `hard_seek_count`).
Good for spotting gross state; never cite them as results — heartbeats have failure
modes of their own (a collaborator receiving no ticks reports a stale/zero Dev).

## Provenance and maintenance

Written 2026-07-06; analyzer tested against a synthetic 20 Hz capture the same day.
Re-verify:
- CSV columns unchanged: `grep -n "timestamp,leader_time" collaborator.py`
- Analyzer still runs: `python3 .agents/skills/ksync-diagnostics-toolkit/scripts/analyze_deviation.py --help`
- Heartbeat fields: `grep -n "sync_deviation\|playback_rate" collaborator.py src/networking/communication.py | head`
