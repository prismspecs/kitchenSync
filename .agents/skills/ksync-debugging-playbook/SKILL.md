---
name: ksync-debugging-playbook
description: >
  Symptom → triage runbook for kSync failures: collaborator lagging or ahead, sync not
  correcting, deviation CSV missing or pathological, wrong video playing, video won't
  start, stutter, web UI showing stale/false state, uploads vanishing, devices offline.
  Load this FIRST for any live misbehavior on the Pis or in the web UI. Contains exact
  log signatures and the discriminating command for each.
---

# kSync Debugging Playbook

Triage runbook. Every log string below is quoted verbatim from the code (as of
2026-07-06). Workflow: run the First Five, match a symptom row, run its discriminating
experiment, then apply the fix or load the owning skill.

When NOT to use this skill: for why-is-it-designed-this-way → `ksync-architecture-contract`;
for theory/math → `ksync-sync-theory-reference`; for "was this tried before?" →
`ksync-failure-archaeology`; for measurement tooling details → `ksync-diagnostics-toolkit`.

## The First Five (run on any sync complaint)

```bash
# 1. Are sync ticks arriving? (on the collaborator; expect ~20 packets/s)
sudo tcpdump -i any udp port 5005 -c 5

# 2. Same sync_mode on ALL nodes? (on each device)
grep sync_mode ~/kitchenSync/ksync.ini

# 3. Hardware decode active? (on each device)
grep -E "Active hardware decoder|PERFORMANCE WARNING" ~/kitchenSync/logs/kitchensync.log | tail -3

# 4. What does the instrument say? (on the collaborator)
tail -5 ~/kitchenSync/logs/sync_deviation.csv

# 5. What IPs/interfaces are actually live?
ip -4 addr show | grep inet
```

CSV columns: `timestamp,leader_time,video_pos,deviation,rate,hard_seeks`.
deviation = collaborator_position − leader_position (negative = behind).

## Symptom table

| # | Symptom | Meaning | Discriminating experiment | Action |
|---|---------|---------|---------------------------|--------|
| 1 | Constant lag (e.g. −0.96s), CSV `rate` pinned `1.0000`, never corrects | No correction loop is running: mode mismatch, or no ticks | Check #2 First-Five; log: `Sync: netclock configured but no net clock established` | Set same `sync_mode` on all nodes, restart. Since 5570b2d the collaborator auto-falls-back to udp, so persistent constant lag now means NO TICKS (see row 2) |
| 2 | tcpdump on 5005 shows nothing | Ticks not reaching this device | On leader log: `Sync: Sending unicast to [...]` or `Sync: Broadcasting on ...` ; also `Sync: send failed ... check network / sync_peer_ip` | Remove `sync_peer_ip` unless on a direct cable; verify same L2 subnet; single active NIC (`sudo ip link set wlan0 down` for wired tests) |
| 3 | Log: `Sync: sync_peer_ip <ip> is THIS device's own address` | The self-IP incident guard fired | — | Delete `sync_peer_ip` from leader config (guard already fell back to broadcast) |
| 4 | Log: `Sync: Cannot use NetClock yet (ip=..., base_time=None)` | Collaborator is netclock but leader sent no base_time → leader is in udp mode | Check leader's `sync_mode` | Align modes on both, restart both |
| 5 | Log: `Gst: Clock sync timeout. Proceeding anyway...` | NetClientClock couldn't reach leader's port 9997 | `sudo tcpdump -i any udp port 9997 -c 5` on collaborator while restarting playback | Check leader running + netclock mode; firewall/subnet; watchdog+fallback will keep video roughly right meanwhile |
| 6 | CSV `hard_seeks` column incrementing on many consecutive rows | Historical: failed-realign spin (pre-5570b2d) or genuine seek storm | `grep "NetClock realign failed" logs/kitchensync.log` | Pull latest main; if current code: pipeline not ready — check decoder health (row 10) |
| 7 | Collaborator sits at 0:00 until leader loops around, then syncs | Keyframe hover: fast seeks snap to a distant keyframe on long-GOP files | `gst-discoverer-1.0 media/<file>` + check GOP: stock downloads often have multi-second GOPs | Re-encode with `keyint = fps` (see ksync-media-encoding-reference). cb09752 escalates repeat seeks to ACCURATE, but long-GOP ACCURATE seeks are slow on Pi — encoding is the real fix |
| 8 | Collaborator slightly AHEAD (tens of ms), stable | Display-chain latency difference between screens, not a sync bug | Phone slow-mo of both screens in one shot; frames × (1000/fps) ms | Policy: identical display model + game mode. Mixed displays: set `video_offset` on the fast device (positive = delay it) |
| 9 | CSV rate stuck at `max_rate` (e.g. 1.2000), gap not closing | Decoder can't sustain even 1.0×; catch-up impossible | Row 10 check; CPU: `top` during playback | Fix decode (codec matrix) — do NOT raise kp/max_rate; that's tuning a transport knob for a decode problem |
| 10 | Log: `PERFORMANCE WARNING: Using software decoder 'avdec_h265'` (or avdec_h264 on Pi 4) | Wrong codec for this Pi's hardware | `gst-inspect-1.0 | grep -E "v4l2(sl)?h?(264|265|evc)"` | Pi 5 → HEVC file; Pi 4 → H.264 file. See ksync-media-encoding-reference |
| 11 | `logs/sync_deviation.csv` doesn't exist | Deviation logging off, or key was stripped by an old web-UI save | `grep enable_deviation_log ksync.ini` | Add `enable_deviation_log = true` (default true since dafdb91); pull latest main |
| 12 | Playing the WRONG file; config edits "revert" | Historical: [KITCHENSYNC]-shadows-[DEFAULT] duplicate keys | `grep -c video_file ksync.ini` (>1 across sections = legacy shadowed file) | Pull main (unified config, 20bc1d9); rewrite ksync.ini single-section; one web-UI save also migrates it |
| 13 | Leader's ksync.ini suddenly has `role = collaborator` / wrong device_id | Historical pre-b4e153c: leader applied broadcast config updates addressed to others | `git log --oneline -1` on device | Pull main; restore leader ksync.ini by hand; restart |
| 14 | Same file shows "HEVC" on one device, "Non-HEVC" on another | Metadata fallback parser divergence (fixed cdc43a7) or leader badge hardcoded (fixed 5570b2d) | `gst-discoverer-1.0` the file yourself | Pull main on the devices AND the web-UI machine |
| 15 | Upload via web UI "succeeds" in a second but the file never appears on the device | Two-hop upload: file landed on the web-UI host's media/, device's background HTTP pull failed | `grep -E "Download failed|HTTP:" logs/kitchensync.log` on the target device | Use `scp <file> gsync@<device>:~/kitchenSync/media/` for large files |
| 16 | Log: `Could not find any video file in search paths` (repeating) | Configured `video_file` not present in media/ | `ls ~/kitchenSync/media/` | Copy the file in, or web-UI Load an existing one |
| 17 | Log: `Window with terms [...] not found within 8 seconds` / `Could not identify video window for resizing` | Cosmetic: window-manager helper can't find the GStreamer window title | Is video actually visible? Usually yes | Ignore, unless video is also invisible → X11 session issue, see ksync-build-run-operate |
| 18 | Log: `Broadcast failed ...: [Errno 101] Network is unreachable` | Host has no usable route (typical on a dev workbench without the show LAN) | `ip route` | Harmless on the workbench; on a Pi it means the network is actually down |
| 19 | Device shows Offline in web UI but is up | Heartbeats (port 5006) not crossing; or web UI on a different subnet | tcpdump 5006 on the web-UI host | Same-L2 requirement; check dual-NIC ambiguity |
| 20 | Web UI Dev: 0.000 constantly while screens visibly differ | Pre-5570b2d netclock reported nothing; post: collaborator not receiving ticks so no measurement to send | Rows 1–2 | Fix tick flow; then trust CSV, not the badge |
| 21 | CSV `leader_time` steps BACKWARD ~40ms occasionally, deviation blips then recovers | Leader position-cache extrapolation jitter (poll thread corrects the extrapolation) | — | Benign at this magnitude. Investigate only if steps exceed ~100ms or deviation doesn't recover |
| 22 | Everything stutters on Pi 5 with an H.264 file | Pi 5 has NO H.264 hardware decode (BCM2712) | Row 10 | Use HEVC on Pi 5. This is hardware, not configuration |

## Traps that cost real time (one-liners)

- **Silence is not health**: two whole failure classes here are "message handled by
  nobody" (handler never registered) and "config key silently stripped" (not
  whitelisted). When something "does nothing," grep for the handler registration and
  the whitelist BEFORE reading the logic. (Incidents: b53e2a9, dafdb91.)
- **The badge lies, the CSV doesn't**: UI fields are derived/heartbeat state with
  failure modes of their own. Judge sync only from `logs/sync_deviation.csv`.
- **Don't tune parameters at a transport problem**: rate pinned at max_rate, or
  constant offset, are decode/topology problems. kp/max_drift tuning is for jitter
  around zero.
- **Two changes, one regression** → revert both, re-land separately (the bf53a41
  lesson).
- **NTP is a rabbit hole with no rabbit**: sync needs no NTP. See
  ksync-failure-archaeology E7 before touching chrony.

## Provenance and maintenance

Written 2026-07-06. All log strings verified against collaborator.py, leader.py,
src/networking/communication.py, src/video/drivers/gst_driver.py at that date.
Re-verify after code changes:

- Log strings still exact: `grep -rn "Cannot use NetClock yet\|Clock sync timeout\|is THIS device's own address\|no net clock established\|NetClock realign failed" --include=*.py .`
- CSV columns: `grep -n "timestamp,leader_time" collaborator.py`
- Defaults: `grep -n "enable_deviation_log\|netclock_max_drift" src/config/manager.py`
