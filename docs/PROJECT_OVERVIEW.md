# kSync Project Overview

A single reference for how the system fits together, how sync actually works,
and how to diagnose it when it doesn't. Written 2026-07 after the
"collaborator one second behind" investigation; the failure history at the
bottom explains several design decisions.

## System summary

kSync plays the same video on multiple Raspberry Pis in frame-close sync.
One node is the **leader** (authoritative playback + time source), the rest
are **collaborators** (slave their playback to the leader). A web UI
(port 8080 on the leader, `src/remote/controller.py`) provides start/stop,
config editing, media upload, and per-device sync diagnostics.

Current hardware:

| Node | Device | device_id | Decode notes |
|------|--------|-----------|--------------|
| Leader | Pi 5 | `pi5_1` | **No H.264 hardware decode** (BCM2712) — h264 falls back to software (`avdec_h264`). HEVC decodes in hardware (rpivid). |
| Collaborator | Pi 4 | `pi4_1` | H.264 hardware decode (`v4l2h264dec`) — always solid. HEVC hardware decode needs the stateless `v4l2slh265dec` (Bookworm / GStreamer ≥ 1.22); without it HEVC lands on software decode and **stutters at 1080p**. |

There is no single codec both Pis decode well, so encode **one file per
codec from the same source** and point each device at its own via
`video_file` in its `ksync.ini` (a collaborator's configured `video_file`
overrides the filename the leader broadcasts). Sync compares positions, not
content — different encodes stay in sync as long as fps and duration are
identical.

```bash
# Pi 4 (H.264 hardware decode):
ffmpeg -i SOURCE -an -vf "fps=30,format=yuv420p" \
  -c:v libx264 -profile:v high -level 4.2 -preset slow \
  -x264-params keyint=30:min-keyint=30:scenecut=0 \
  -b:v 10M -maxrate 12M -bufsize 20M \
  sync_test_pi4_h264.mp4

# Pi 5 (HEVC hardware decode):
ffmpeg -i SOURCE -an -vf "fps=30,format=yuv420p" \
  -c:v libx265 -preset medium -tag:v hvc1 \
  -x265-params keyint=30:min-keyint=30:scenecut=0 \
  -b:v 10M -maxrate 12M -bufsize 20M \
  sync_test_pi5_hevc.mp4
```

The 1-second keyframe interval (`keyint=30` at 30 fps, scene-cut off) is
load-bearing: fast KEY_UNIT seeks snap to the nearest keyframe, so with
default encoder GOPs (~8 s for x265) a "hard seek to the leader" can land
seconds away from its target and the corrector spirals. Verify which
decoder is actually active on a device with:

```bash
grep -E "Active hardware decoder|PERFORMANCE WARNING" logs/kitchensync.log | tail -3
gst-inspect-1.0 | grep -E "v4l2(sl)?h?(264|265|evc)"
```

## Process / file map

- `kitchensync.py` — boot entry point (systemd `kitchensync.service`). Loads
  `ksync.ini` (USB root takes priority over local), then `execv`s into the
  role: `leader.py --auto` or `collaborator.py`.
- `leader.py` — loads and plays the video, broadcasts sync ticks, sends the
  `start` command, answers web-UI/config/discovery messages.
- `collaborator.py` — listens for commands + sync ticks, plays the video,
  runs the sync correction loop, sends heartbeats every 2 s.
- `src/video/drivers/gst_driver.py` — GStreamer playbin driver: hardware
  decoder selection, gapless looping (SEGMENT seeks), rate control, and the
  netclock join/realign logic.
- `src/networking/communication.py` — `SyncBroadcaster`/`SyncReceiver`
  (ticks), `CommandManager`/`CommandListener` (commands, heartbeats, RTT).
- `src/config/manager.py` — config schema, editable-field definitions used
  by the web UI, defaults.
- `tools/` — `ntp-setup.sh` (chrony; see "NTP" below — not actually
  required), `reset-network.sh`, `generate_sync_video.py`.

## Configuration & deployment model

Each device reads a local `ksync.ini` (a `ksync.ini` on a USB stick's root
overrides it). **`ksync.ini` is untracked in git** — a `git pull` never
changes a device's config.

The config is **unified**: every key lives in the single `[KITCHENSYNC]`
section. (Historically keys were split between `[DEFAULT]` and
`[KITCHENSYNC]`; configparser resolves a section's own key before
`[DEFAULT]`, so a stale duplicate could shadow an edit forever — that bug
pinned the leader to an old video no matter what was saved. Legacy
two-section files still read correctly and are migrated to the unified
layout on the first save.) The repo keeps reference mirrors for the two
devices: `ksync.ini` (leader, pi5_1) and `ksync_collaborator.ini`
(collaborator, pi4_1 — deploy it *as* `ksync.ini` on that Pi).

Ways to change config on a device:
1. Web UI → device card → Config (writes `ksync.ini`, restarts the node).
2. SSH and edit `ksync.ini` directly, then restart the service.
3. USB stick with `ksync.ini` at its root (takes priority at boot).

Code updates: web UI "Update" button → `git pull && reboot` on the device.

## Network

All discovery/commands assume the nodes share **one L2 network** (UDP
broadcast must reach everyone). Simplest reliable setup: every Pi wired into
the same router/switch, single subnet, WiFi off or ignored.

| Port | Proto | Purpose |
|------|-------|---------|
| 5005 | UDP | Sync ticks, leader → collaborators (broadcast, 20 Hz default) |
| 5006 | UDP | Commands, heartbeats, ping/pong RTT probes (both directions) |
| 9997 | UDP | GStreamer net clock (`GstNetTimeProvider`), netclock mode only |
| 8080 | TCP | Web UI + media download (leader) |

Pitfalls learned the hard way:

- **`sync_peer_ip` disables broadcast.** It exists only for a direct-cable
  link to a single collaborator and must be the *collaborator's* IP. In July
  2026 it was set to the leader's own address — the leader unicast every sync
  tick to itself and the collaborator received nothing. `leader.py` now
  detects a self-IP and falls back to broadcast with an error log, and send
  failures are rate-limit logged instead of swallowed. Unless you are
  actually on a direct cable: leave it unset.
- **Dual-homed Pis are ambiguous.** With eth0 and wlan0 both up, broadcast
  addresses are derived from whichever interface holds the default route
  (`_get_broadcast_address()`), so commands, ticks, and the net clock can
  travel different paths. Prefer a single active network per Pi.
- **NTP/chrony is NOT required.** All cross-device math uses either
  same-clock deltas or RTT/2 (leader measures RTT via ping/pong and pushes
  `latency_update` to each collaborator; netclock mode has its own clock
  protocol). The June 2026 chrony effort can stay parked.

## Sync modes

Selected by `sync_mode` in `ksync.ini` — **must match on leader and
collaborators**. Current production setting: `udp`.

### `udp` — measured-position P-controller (default, battle-tested)

Leader broadcasts its media position 20×/s (`tick_interval = 0.05`).
Collaborator compares against its own position and corrects:

- `|deviation| < min_drift` (5 ms): do nothing.
- deadband → `max_drift` (0.15 s): playback-rate nudging,
  `rate = 1 − deviation·kp`, clamped to [`min_rate`, `max_rate`].
- `≥ max_drift`: accurate (flushing) seek to the leader position.
- `> 2 s` (5 s near the loop seam): fast keyframe seek.
- Median-of-3 filtering, settle windows after seeks (1.0–2.5 s), loop-seam
  suppression, kernel receive timestamps (`SO_TIMESTAMPNS`), sender-lag and
  EWMA one-way-latency compensation.

Expected steady-state on a wired LAN: a few tens of ms or better. All the
sync tuning in the web UI applies to this mode.

### `netclock` — shared GStreamer clock (precision mode, repaired 2026-07)

Leader serves its pipeline clock on port 9997; collaborators run a
`GstNetClientClock` against it, so playback *rate* is locked by GStreamer
itself and there is nothing to tune. The subtle part is the position anchor
(`base_time`), and this is where the original implementation failed — see
history. The repaired design:

1. **Leader** broadcasts a *settled* `gst_base_time` inside the `start`
   command and re-reads it fresh on every 30 s re-broadcast
   (`get_pipeline_base_time()` now waits for pending seeks to settle).
2. **Collaborator join** (`GstDriver._align_to_network_clock`): preroll
   paused → compute where the leader will be 0.5 s from now
   (`target = (T0 − base_time) mod duration`) → accurate SEGMENT seek to
   that position → anchor `base_time = T0` → play. Frames start rendering
   on the leader's timeline immediately; no reliance on QoS frame-dropping
   (Pi decoders cannot catch up ~1 s of content — that was the steady
   1-second lag).
3. **Watchdog** (`collaborator._netclock_watchdog`): the UDP measurement
   loop keeps running in netclock mode (deviation CSV + heartbeats stay
   honest). If |median deviation| exceeds `netclock_max_drift` (default
   0.5 s — leader seek, EOS fallback, failed clock sync), the collaborator
   calls `netclock_realign(leader_position)` which re-anchors seek +
   base_time in one step.

Verified end-to-end on desktop GStreamer 1.28 (real driver code, fakesink
`sync=true`): late join settles at **+0.0 ms**; a deliberate 5 s leader seek
is recovered to **−0.1 ms** by a single realign. On the Pis, expect the
clock sync itself to be ~sub-ms wired; residual visual offset comes from
display latency differences.

When to use which: `udp` is the safe default and self-heals from anything.
`netclock` eliminates rate hunting entirely and is worth testing now that
join/realign are fixed — roll it out by flipping `sync_mode` on **both**
devices and watching `logs/sync_deviation.csv`.

## Diagnostics runbook

Sources of truth on each device:

- `logs/kitchensync.log` — startup, driver/decoder selection, sync events.
- `logs/sync_deviation.csv` (collaborator, `enable_deviation_log = true`) —
  `timestamp, leader_time, video_pos, deviation, rate, hard_seeks` for every
  processed tick, both sync modes. Plot this before touching parameters.
- Web UI device cards — `Dev` (deviation), `Rate`, `Hard Seeks`, driver name.
- `logs/startup_crash.log` — import-time/boot crashes.

Failure signatures:

| Symptom | Likely cause |
|---|---|
| Constant offset, never corrects, `Dev: 0.000` in UI | Collaborator isn't receiving sync ticks (check `sync_peer_ip`, subnets, broadcast) — in old netclock builds this was normal, now deviation reports in both modes |
| Log: `sync_peer_ip … is THIS device's own address` | The July 2026 misconfiguration — remove `sync_peer_ip` |
| Log: `Sync: send failed … check network / sync_peer_ip` | Unicast target unreachable / wrong subnet |
| Log: `Cannot use NetClock yet (ip=…, base_time=None)` | Leader isn't in netclock mode or start command predates play — modes mismatched |
| Log: `Clock sync timeout. Proceeding anyway` | Port 9997 blocked / wrong leader IP; watchdog will be doing all the work |
| Log: `PERFORMANCE WARNING: Using software decoder` on Pi 4 | Decoder ranking problem — Pi 4 should always be on v4l2 HW decode |
| Frequent hard seeks in CSV | Rate control losing: check decoder load, `max_rate` sustainable fps, network jitter |
| `Broadcast failed: Network is unreachable` | No usable interface/route (typical on the dev workbench, harmless there) |

Quick checks:

```bash
# is the collaborator receiving ticks? (run on collaborator)
sudo tcpdump -i any udp port 5005 -c 5
# is the net clock reachable? (netclock mode, run on collaborator)
sudo tcpdump -i any udp port 9997 -c 5
# what IPs does each Pi actually have right now?
ip -4 addr show | grep inet
```

## History (why things are the way they are)

- **2026-06**: WiFi-broadcast + udp mode worked well. A direct-cable
  ethernet link (static 192.168.0.x IPs, `sync_peer_ip`) was added for lower
  jitter; chrony/NTP was attempted (blocked, later found unnecessary).
- **2026-06-26**: netclock mode landed (commit d7a463e) and both devices
  were switched to it.
- **2026-07-06**: "collaborator a full second behind" investigation found
  three compounding causes: (1) `sync_peer_ip` pointed at the leader's own
  IP, silently killing the tick stream; (2) netclock mode had disabled the
  entire correction/measurement loop while its share-base_time-and-hope
  startup could not physically converge on Pi decoders; (3) the leader
  broadcast a base_time captured before its gapless-loop seek settled
  (proven off by exactly the settle delta). All three fixed; production
  config returned to `udp`; netclock kept as a now-viable precision option.
