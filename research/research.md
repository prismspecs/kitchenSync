# kSync Sync Precision Research

**Goal:** Reduce sync deviation between leader (Pi 5) and collaborator (Pi 4) from ~40ms to <5ms over Ethernet.

## Current Architecture

### Data Flow

```
Leader (Pi 5)                              Collaborator (Pi 4)
─────────────────                         ─────────────────────
GstDriver.get_position()                  
  → poll worker: pipeline query every 50ms
  → cached_position extrapolated by elapsed*rate
   ├→ SyncBroadcaster loop (every 20ms)
  │    time_provider() → get_position()
  │    JSON {time, sent_at, source, duration}
  │    → UDP unicast to 192.168.0.165:5005
  │                                     ├→ SyncReceiver.listen_loop()
  │                                     │    recvfrom() → drain buffer → newest packet
  │                                     │    _handle_sync() → store state
  │                                     │
   │                                     ├→ _sync_processor_loop (every 10ms)
  │                                     │    _process_sync_tick()
  │                                     │    → latency compensation (RTT/2 via ping/pong)
  │                                     │    → _maintain_video_sync()
  │                                     │       deviation = video_pos - leader_time
  │                                     │       if |deviation| > max_drift → seek
  │                                     │       elif |deviation| > min_drift → rate adjust
  │                                     │       else → rate=1.0
```

### Timing Parameters

| Parameter | Current Value | Location |
|---|---|---|
| `tick_interval` | 0.02 (was 0.1) | config default + SyncBroadcaster |
| `_sync_processor_loop` sleep | 0.01 (was 0.05) | `collaborator.py:477` |
| Position poll interval | 0.05 | `gst_driver.py` (configurable) |
| `max_drift` | 0.3 | config default |
| `min_drift` | 0.01 | config default |
| `kp` | 0.25 | config default |
| `min_rate` | 0.9 | config default |
| `max_rate` | 1.2 | config default |
| `position_read_time` compensation | added | collaborative per-packet |

### Sources of 40ms Error (Ordered by Impact)

1. ~~Broadcast tick interval (was 100ms)~~ **Fixed: now 20ms.** Position sampled 5x more often. At 30fps (33ms per frame), this means ~1 sampling interval per frame instead of ~3.

2. **UDP send-to-receive jitter:** `time.sleep(0.02)` in Python has ±5-10ms granularity. Combined with GIL, thread scheduling, and JSON serialization (now includes `position_read_time` to correct for sender-side lag). Remaining jitter: ~5-15ms.

3. ~~Position read vs. send timestamp mismatch~~ **Fixed: position_read_time recorded at query time, sent alongside packet.** Collaborator computes `sent_at - position_read_time` and adds it to leader_time.

4. **Position extrapolation in GstDriver:** `get_position()` returns `cached_position + elapsed * rate`. Cached position updated every 50ms by poll worker. Extrapolation error when rate ≠ 1.0. Unchanged.

5. **Sender-side latency:** ~~Not compensated~~ **Fixed: position_read_time allows precise sender-side lag compensation.**

6. **Clock drift between devices:** Without NTP/PTP, each Pi's `time.time()` drifts independently. Sync compares media position (not wall time), so clock drift affects only `sent_at` timing. **NTP attempted but currently blocked** (see chrony issue below).

7. **Rate change latency:** `set_speed()` uses `INSTANT_RATE_CHANGE` or flushing seek. Time from rate command to actual pipeline effect is not measured.

## Reference Projects Analysis

### Cloned Repositories

All four projects are in `research/`:

| Project | Technique | Best Precision | Weakness |
|---|---|---|---|
| `rpi-video-sync-looper` | Master UDP broadcast + slave seek | ~50ms (claimed tolerance) | omxplayer deprecated, 1s broadcast interval |
| `Multichannel-Video` | (deployment guide for omxplayer-sync) | Same as above | Same as above |
| `raspi-video-sync` | GStreamer + UDP broadcast + seek | ~2.5s threshold | No clock sync, coarse threshold |
| `synchronized4kplaybackrpi4` | VLC + UDP broadcast command sync | No claim (start-time only) | No drift correction |

**Key takeaway:** None of these projects use NTP, PTP, or GstNetClock. They all rely on reactive seeking. kSync is already more sophisticated than all four.

### External Projects

| Project | Technique | Precision |
|---|---|---|
| **gst-sync-server** ([ford-prefect/gst-sync-server](https://github.com/ford-prefect/gst-sync-server)) | GstNetClientClock + GstNetTimeProvider, network-wide clock sync | Sub-frame (measured with oscilloscope) |
| **gst-videowall** ([NHGmaniac/gst-videowall](https://github.com/NHGmaniac/gst-videowall)) | RTP stream + RTCP sync, split video across monitors | ~frame-accurate with RTCP |
| **pi-wall** ([vigsterkr/pi-wall](https://github.com/vigsterkr/pi-wall)) | GstNetTimeProvider for clock sync | Sub-frame |
| **media-mux** ([hackboxguy/media-mux](https://github.com/hackboxguy/media-mux)) | NTP + Kodi JSON-RPC sync | <10ms typical |
| **omxplayer-sync** ([turingmachine/omxplayer-sync](https://github.com/turingmachine/omxplayer-sync)) | UDP broadcast + D-Bus seek | ~50ms tolerance |
| **SatPulse** ([satpulse.net](https://satpulse.net)) | PTP + GPS-disciplined clock on CM4/5 | ~20ns |
| **linuxptp** ([canonical/linuxptp-snap](https://github.com/canonical/linuxptp-snap)) | PTP on Pi 5 via RP1 MAC timestamping | ~20ns |

## Improvement Strategies (Ranked by Impact/Effort)

### 1. Reduce Broadcast Tick Interval (Effort: Low, Impact: Medium)

**Problem:** 100ms tick means position is up to 100ms stale.

**Fix:** Change `tick_interval` from 0.1 to 0.02 (20ms). This is 50 packets/sec, trivial for the CPU and network.

```python
# In SyncBroadcaster.__init__:
self.tick_interval = max(0.02, min(float(tick_interval), 5.0))
```

Already clamped to 0.02 minimum. Just set config or default lower.

**Impact:** Reduces position staleness from 100ms to ~25ms (accounting for sleep jitter). About 15-30ms improvement.

### 2. Record position_read_time (Effort: Low, Impact: Medium)

**Problem:** `get_position()` is called before `sent_at = time.time()` in the broadcast loop. The time between reading position and sending the packet (JSON serialization + socket write) is unaccounted for.

**Fix:** Record the time when position was read and include it in the sync packet. The collaborator can use this to compute a more accurate `position_at_send_time`.

**Current code** (`communication.py:112-140`):
```python
provided_time = self.time_provider()  # position read here
# ... JSON serialization happens ...
payload = json.dumps({
    "time": current_time,
    "sent_at": time.time(),  # recorded after serialization
})
```

**Fix:**
```python
position_read_time = time.time()
provided_time = self.time_provider()
# ... include position_read_time in packet ...
payload = json.dumps({
    "time": current_time,
    "position_read_time": position_read_time,
    "sent_at": time.time(),
})
```

Then on the collaborator, add `(sent_at - position_read_time)` to the adjusted leader time:
```python
adjusted_leader_time += (sent_at - position_read_time)  # sender-side processing lag
```

**Impact:** Eliminates 1-5ms of serialization jitter.

### 3. SO_TIMESTAMPING for Precise Packet Timing (Effort: Medium, Impact: Medium)

**Problem:** `time.time()` in Python has microsecond precision but is called in application context — the actual kernel send/receive timestamps are not captured. Thread scheduling delays between app and kernel add jitter.

**Fix:** Use Linux `SO_TIMESTAMPING` on the sync socket for software (or hardware, if available) timestamps.

```python
# On both leader and collaborator sync sockets
SO_TIMESTAMPING = 37
SOF_TIMESTAMPING_RX_SOFTWARE = (1 << 3)
SOF_TIMESTAMPING_SOFTWARE = (1 << 4)
SOF_TIMESTAMPING_RAW_HARDWARE = (1 << 6)
SOF_TIMESTAMPING_OPT_CMSG = (1 << 10)

flags = (SOF_TIMESTAMPING_RX_SOFTWARE | SOF_TIMESTAMPING_SOFTWARE |
         SOF_TIMESTAMPING_RAW_HARDWARE | SOF_TIMESTAMPING_OPT_CMSG)
s.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPING, flags)
```

Then use `recvmsg()` to read the timestamp from ancillary data:
```python
data, ancdata, flags, addr = s.recvmsg(65535, 1024)
for cmsg in ancdata:
    if cmsg[0] == socket.SOL_SOCKET and cmsg[1] == SCM_TIMESTAMPING:
        # ts[0] = software, ts[2] = hardware
        hw_ts = struct.unpack("iiii", cmsg[2])
```

**Impact:** Reduces timestamp jitter from ~10-30µs (userspace Python) to ~1µs (kernel software) or sub-µs (hardware on Pi 5 RP1).

**Caveats:**
- Pi 5's RP1 MAC supports hardware timestamping but there's a known bug (https://github.com/raspberrypi/linux/issues/5904). Software timestamping works reliably on all hardware.
- Pi 4's BCM54213PE PHY does NOT support hardware timestamping. Only software kernel timestamps.
- Python's `recvmsg()` is required (not `recvfrom()`). Available since Python 3.x.

### 4. NTP Synchronization (Effort: Low, Impact: High)

**Problem:** Without synchronized clocks, `sent_at` (leader's clock) compared with `received_at` (collaborator's clock) has clock offset error. The RTT/2 measurement using ping/pong is affected.

**Fix:** Install and configure `chrony` on both Pis to sync to the leader as an NTP server.

On Pi 5 (leader):
```bash
sudo apt install chrony
sudo tee -a /etc/chrony/chrony.conf <<'EOF'
# Serve time to local network
allow 192.168.0.0/24
local stratum 10
EOF
sudo systemctl restart chrony
```

On Pi 4 (collaborator):
```bash
sudo apt install chrony
# In chrony.conf, add:
# server 192.168.0.165 iburst  # Pi 5 IP
```

**Impact:** NTP over local Ethernet typically achieves 0.1-1ms accuracy. This allows using `sent_at` and `received_at` to compute one-way transport latency directly (not just RTT/2).

### 5. GstNetClientClock (Effort: High, Impact: Very High)

**Problem:** The custom UDP sync is position-based and reactive. GStreamer has built-in network clock synchronization (`GstNetTimeProvider` / `GstNetClientClock`) that synchronizes the pipeline clocks themselves.

**How it works:**
1. Leader creates a `GstNetTimeProvider` that serves its pipeline clock over the network
2. Collaborator creates a `GstNetClientClock` that synchronizes to the leader's clock
3. Collaborator sets this as the pipeline clock via `gst_pipeline_use_clock()`
4. Both pipelines use the same base time → frames are rendered at the same wall-clock time

**Implementation sketch:**
```python
# Leader
from gi.repository import GstNet
provider = GstNet.NetTimeProvider.new("leader-clock", 9997, 0)
# This runs automatically in the GLib main loop

# Collaborator
client_clock = GstNet.NetClientClock.new("sync-clock", "192.168.0.165", 9997, 0)
client_clock.wait_for_sync(Gst.SECOND * 5)  # block until synced
pipeline.use_clock(client_clock)
pipeline.set_base_time(0)  # or some shared absolute time
```

**Impact:** Makes the entire GStreamer pipeline clock-aware. Instead of polling position and seeking, the pipeline itself adjusts its playback speed to stay locked to the leader's clock. This is frame-accurate.

**Caveats:**
- Requires GStreamer's GLib main loop to be running (already done in gst_driver.py)
- `gst_pipeline_use_clock()` after the pipeline is already playing is tricky — it should be set before PLAYING state
- The clock sync quality depends on network RTT stability. Over Ethernet (0.28ms RTT), this should be excellent.
- Will require significant refactoring of both leader and collaborator

### 6. PTP (GstPtpClock) (Effort: High, Impact: Very High)

**Problem:** Same as #5, but using IEEE 1588 PTP for hardware-timestamped clock sync.

**Pi 5 capability:** The RP1 chip provides MAC-based hardware timestamping. `ethtool -T eth0` should show `hardware-transmit` and `hardware-receive`. The linuxptp project confirms Pi 5 can achieve ~20ns sync over Ethernet.

**Pi 4 capability:** The BCM54213PE PHY does NOT support hardware timestamping. Software PTP (via kernel) achieves ~100µs.

**Approach:**
```python
# Requires GstPtpClock (available since GStreamer 1.6)
from gi.repository import GstNet
ok = GstNet.ptp_init()  # starts helper process (needs CAP_NET_ADMIN or setuid)
ptp_clock = GstNet.PtpClock.new("ptp-clock", 0)  # domain 0
pipeline.use_clock(ptp_clock)
```

**GstPtpClock integration** combines hardware-timestamped PTP with GStreamer's pipeline clock mechanism. This would be the gold standard.

**Caveats:**
- Pi 5 PTP hardware timestamping has a known bug (https://github.com/raspberrypi/linux/issues/5904)
- Pi 4 can't do hardware PTP (only software)
- `GstPtpClock` requires the PTP helper process with root privileges
- Mixed Pi 4 + Pi 5 setup limits to software PTP precision (~100µs at best)

### 7. Faster Sync Processing Loop (Effort: Low, Impact: Low)

**Problem:** `_sync_processor_loop` sleeps 50ms between processing ticks. This adds up to 50ms latency between receiving a sync packet and acting on it.

**Fix:** Reduce sleep from 0.05 to 0.01 (10ms).

```python
# collaborator.py:477
time.sleep(0.01)
```

**Impact:** Reduces processing latency from ~25ms average to ~5ms average. Small but additive.

### 8. Rate Control Parameter Tuning (Effort: Low, Impact: Medium)

**Problem:** The P-controller `rate = 1.0 - (deviation * kp)` with current gains may not be aggressive enough to correct 40ms deviation quickly.

**Fix:** Tune `kp` (proportional gain), `min_drift` (deadband), and `min_rate`/`max_rate` for tighter tracking. For example:
- `kp = 5.0` (instead of current default): at 40ms deviation → rate = 1.0 - (0.04 * 5) = 0.8x or 1.2x
- `min_drift = 0.01` (10ms deadband instead of larger)
- `max_rate = 1.15` / `min_rate = 0.85` (wider adjustment range)

**Impact:** Faster correction of small deviations. But beware of oscillation — the P-controller can overcorrect if gains are too high.

## Measurement & Diagnostics

### Current Measurement

Currently sync quality (deviation) is reported via heartbeats as `sync_deviation` in the web UI. This is the collaborator's computed `video_pos - leader_time` sampled every 2s.

### Proposed Diagnostic Tools

1. **Log deviation over time:** Add periodic `log_info` of deviation to a CSV-like format for post-hoc analysis.

2. **tcpdump packet timing:** On the collaborator, capture sync packets with hardware timestamps:
   ```bash
   sudo tcpdump -i eth0 port 5005 -tt -n > sync_timestamps.txt
   ```

3. **On-screen timecode:** Overlay a millisecond counter on both screens from the same clock source and video-record both with a high-speed camera.

4. **GstBus clock statistics:** `GstNetClientClock` can emit messages with clock statistics when a bus is set:
   ```python
   client_clock.set_property("bus", pipeline.get_bus())
   ```
   These messages contain `rtt`, `stddev`, and other metrics.

## Current Status (2026-06-26)

### Phase 1 Completed — Code Changes (commits ae2f681, 5af4196, 89e02f1)

All code changes pushed to Pi 5, restart confirms they're in use:

- [x] **tick_interval 100ms → 20ms**: Default changed from 0.1 to 0.02 in config property, `_create_default_config`, and `EDITABLE_CONFIG_FIELDS`. Leader.py was hardcoding 0.1 and ignoring config — now reads `self.config.tick_interval`.
- [x] **_sync_processor_loop 50ms → 10ms**: `time.sleep(0.05)` → `time.sleep(0.01)` in collaborator.py:477.
- [x] **position_read_time**: Added to sync packet. Recorded when `time_provider()` is called, before serialization overhead. Included in JSON as `"position_read_time"`. Collaborator unpacked as 5-tuple `(leader_time, received_at, sent_at, source, position_read_time)`. Compensates sender-side processing lag: `adjusted_leader_time += max(0, sent_at - position_read_time)`.
- [x] **NTP setup script**: `tools/ntp-setup.sh` — takes eth0 down temporarily for internet access during `apt-get install chrony`, configures leader as local stratum-10 server or collaborator as client of leader.

### Phase 1 Blocked — NTP Not Working

Chrony installed on both Pis. Pi 5 is stratum-10 local clock, serving locally. But Pi 4 cannot reach Pi 5's NTP:

**Chrony Debug Log:**
- Pi 5 config has `allow 192.168.0.0/24` and `local stratum 10` at end of `/etc/chrony/chrony.conf`
- Pi 5 `chronyd` is running (`Active: active (running)`), listening on `0.0.0.0:123`
- Pi 5 serves NTP locally: `python3 NTP query to 127.0.0.1:123` succeeds (48 bytes response)
- Pi 4 can `ping 192.168.0.165` (0.1ms RTT)
- Pi 4 NTP query to 192.168.0.165:123 **times out** — raw NTP v4 client packet gets no response
- `nc -zu 192.168.0.165 123` reports `port blocked`
- `sntp` not installed on Pi 4
- `chronyc sources -v` on Pi 4 shows `192.168.0.165` in `^?` (unreachable/unknown) state
- `chronyc tracking` on Pi 4 shows Stratum 0, Not synchronised
- No firewall on either Pi (`iptables` not installed, `nft list ruleset` empty)
- Pi 5's `chrony.conf` has `confdir /etc/chrony/conf.d` (empty), `sourcedir /etc/chrony/sources.d` (empty)
- Pi 5 chronyd uses `seccomp filter (level 1)` — potential blocker?
- chrony version 4.6.1 on both Pis

**Hypotheses:**
1. `seccomp` filter blocking NTP response socket operations → try `DAEMON_OPTS="-F 0"` to disable seccomp
2. `allow 192.168.0.0/24` directive placement after `confdir` causes it to be ignored by chrony 4.6 → try placing it before `confdir` or in a conf.d file
3. NTS/auth requirement in chrony 4.6 → check `ntsdumpdir` and key config
4. Network: eth0 has static IP 192.168.0.x but maybe the ARP or route is asymmetric (Pi 4 tries to send via wrong interface)
5. Pi 5 responds to localhost but has `bind()` issue on the physical interface → check `ss -tulpn | grep chronyd` shows `0.0.0.0:123` already confirmed

**Next steps to try:**
1. `sudo chronyd -Q -q` to check config parse on Pi 5 (confirmed works, no errors)
2. Move `allow` directives into `/etc/chrony/conf.d/` file instead of main config
3. Disable seccomp: edit `/etc/default/chrony` to set `DAEMON_OPTS="-F 0"`
4. Check Pi 5's `/var/log/chrony/` for NTP access logs
5. `tcpdump -i eth0 port 123` on both Pis simultaneously to see if packets arrive/depart

### Network Topology

```
Pi 5 (leader)
  ├─ eth0: 192.168.0.165  ─── TP-Link switch (no internet) ─── Pi 4 eth0: 192.168.0.164
  └─ wlan0: 192.168.1.128 ─── Router (internet) ─── Workbench (also on 192.168.1.x)

Both Pis have dual network. Default route goes through Ethernet (wrong — no internet).
NTP setup script takes eth0 down temporarily to force apt-get through WiFi.
```

### Phase 2 (Not Started)
- [ ] SO_TIMESTAMPING on sync sockets (software kernel timestamps via `recvmsg()`)
- [ ] Tune rate control parameters (kp, min_drift, max_rate)
- [ ] Verify sender-side processing lag compensation is working

### Phase 3 (Not Started)
- [ ] GstNetClientClock integration (shared pipeline clock across devices via GStreamer's GstNetTimeProvider/GstNetClientClock)
- [ ] If GstNetClientClock works → eliminate custom UDP sync entirely
- [ ] Evaluate GstPtpClock for Pi 5 (if https://github.com/raspberrypi/linux/issues/5904 is fixed)

### Estimated Impact After NTP Fix + Code Changes
- tick_interval 20ms: ~40ms → ~20ms error reduction
- processor loop 10ms: ~5ms additional
- position_read_time: ~1-3ms additional
- After NTP: allows accurate one-way delay measurement, tighter RTT compensation
- Total estimate: ~40ms → ~10-15ms with just Phase 1 completed

## References

- GStreamer NetClocks FOSDEM 2016: https://archive.fosdem.org/2016/schedule/event/synchronised_gstreamer/
- GstNetClientClock docs: https://gstreamer.freedesktop.org/documentation/net/gstnetclientclock.html
- GstPtpClock docs: https://gstreamer.freedesktop.org/documentation/net/gstptpclock.html
- gst-sync-server: https://github.com/ford-prefect/gst-sync-server
- gst-sync-server blog (Arun Raghavan): https://arunraghavan.net/2016/11/gstreamer-and-synchronisation-made-easy/
- Video wall with gst-sync-server: https://arunraghavan.net/2016/12/synchronised-playback-and-video-walls/
- Quantifying sync quality: https://arunraghavan.net/2017/01/quantifying-synchronisation-oscilloscope-edition/
- Pi 5 PTP hardware timestamping bug: https://github.com/raspberrypi/linux/issues/5904
- Canonical linuxptp-snap for Pi 5: https://github.com/canonical/linuxptp-snap
- Pi 5 gPTP implementation: https://olof-astrand.medium.com/implementing-gptp-for-time-sensitive-networking-tsn-on-beagley-y-ai-and-raspberry-pi-5-941aa5db1914
- Pi CM4 PTP guide (Jeff Geerling): https://www.jeffgeerling.com/blog/2022/ptp-and-ieee-1588-hardware-timestamping-on-raspberry-pi-cm4/
- SatPulse: https://satpulse.net
- Linux SO_TIMESTAMPING: https://docs.kernel.org/networking/timestamping.html
- Instantaneous RTP sync: https://coaxion.net/blog/2022/05/instantaneous-rtp-synchronization-retrieval-of-absolute-sender-clock-times-with-gstreamer/
