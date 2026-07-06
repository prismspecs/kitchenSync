---
name: ksync-architecture-contract
description: >
  kSync's load-bearing design decisions with their WHY, the invariants that must hold,
  the full UDP message catalog and data flows, and the honestly-stated weak points.
  Load this before changing any cross-component behavior (roles, messaging, config
  model, sync modes, media strategy), when orienting on the codebase, or when tempted
  to "simplify" something that looks odd — it may be an incident scar.
---

# kSync Architecture Contract

What the system is, why each load-bearing decision was made, what must never break.
Facts current as of 2026-07-06. The living operational doc is `docs/PROJECT_OVERVIEW.md`;
this skill is the contract layer on top of it. `GEMINI.md` is a stale manifest: it still
describes the P-controller as *the* sync model and predates netclock and the unified
config — trust this skill and PROJECT_OVERVIEW over it.

When NOT to use this skill: live failures → `ksync-debugging-playbook`; sync math →
`ksync-sync-theory-reference`; config key catalog → `ksync-config-reference`;
history/reverts → `ksync-failure-archaeology`.

## System shape

```
                    ┌─ web UI node (standalone, LOCAL_LEADER_ID="remote-leader")
                    │  src/remote/controller.py, ThreadingHTTPServer :8080
   one L2 subnet ───┤
                    ├─ LEADER Pi (role=leader)      leader.py
                    │    plays video, broadcasts sync ticks :5005/udp @20Hz,
                    │    serves netclock :9997/udp, answers commands :5006/udp
                    └─ COLLABORATOR Pis (role=collaborator|bystander) collaborator.py
                         play video, correct drift, heartbeat every 2s
```

Every node runs the same repo. `kitchensync.py` (systemd `kitchensync.service`) loads
config (USB-root ksync.ini overrides local), prints role, and `os.execv`s into
`leader.py --auto` or `collaborator.py`.

## Load-bearing decisions and WHY

| Decision | Why (and the scar behind it) |
|---|---|
| **Universal node + execv role pivot** | One codebase, one image for every Pi; role changes are a clean process restart, not in-place state surgery. |
| **GStreamer playbin, not manual pipelines** | playbin negotiates Pi DMA-buf/hardware paths far more robustly (comment in gst_driver.load). Earlier player eras (DBUS/omxplayer, VLC) were "insanely costly" — see archaeology E1. |
| **Decoder re-ranking at load** (`_reprioritize_decoders`) | Pi 5 has NO H.264 hardware decoder; its only HW decode is rpivid HEVC. Ranking was once set exactly backwards (491edc0→b9e05ad). Per-device codec files follow from this. |
| **Gapless looping via SEGMENT seeks** | EOS→flushing-seek looping causes a position discontinuity that looks like huge drift to collaborators. SEGMENT_DONE + non-flushing seek keeps running time continuous (483df82). |
| **Two sync modes behind one flag** | `udp` = measured-position P-controller: self-healing, survives anything, ~tens-of-ms ceiling. `netclock` = shared GStreamer clock + anchored base_time: precision path (desktop-verified ±0.1ms; Pi unproven). Netclock **falls back to udp automatically** when the net clock can't establish (5570b2d — the mode-mismatch incident). |
| **No NTP anywhere** | All cross-device math is same-clock deltas or leader-measured RTT/2 pushed as `latency_update`. Chrony was a costly dead end (archaeology E7). |
| **Unified single-section config** | configparser resolves a section's own key before [DEFAULT]; the old two-section format let stale duplicates shadow edits forever (the wrong-video incident). Since 20bc1d9 every key lives in `[KITCHENSYNC]`; [DEFAULT] is read-only legacy fallback, stripped on save. |
| **Whitelist-based config saves** | Web-UI saves rewrite the whole file from `CONFIG_ROLE_KEYS`. Consequence: an un-whitelisted key is SILENTLY DELETED on save — adding a key has a mandatory checklist (`ksync-config-reference`). |
| **Per-device untracked ksync.ini + repo mirrors** | Devices `git pull` main; a tracked ksync.ini would collide with device-local files and brick fleet updates. Mirrors: `ksync.ini` (leader), `ksync_collaborator.ini`, `ksync_webui.ini`. |
| **Web UI as a standalone node** | It discovers the real leader and delegates (`remote_start`), rather than being the leader — a Pi cluster must run without the UI host present. Port-conflict history: 5923deb. |
| **Unicast replies to discovery/config** | Some hosts refuse UDP broadcast (PermissionError era, cbe0e85); the leader replies unicast to the asker. |
| **Target filtering on EVERY handler** | Commands are broadcast with `target_device_id`; any handler that skips `_message_targets_this_device` applies other devices' commands — this demoted the leader to a collaborator once (b4e153c). |
| **Surgical DOM morphing in the web UI** | Naive innerHTML refresh destroys user input; recurred twice (393483d, dafdb91: refresh now pauses while a config field is focused). |

## UDP message catalog (verify: grep the type string)

Port 5005 (SyncBroadcaster → SyncReceiver): `sync`
{time, leader_id, source: media|wall, duration, sent_at, position_read_time}.

Port 5006 (CommandManager/CommandListener, JSON datagrams):

| type | direction | purpose |
|---|---|---|
| start | leader → all | video_file, schedule, start_time, sync_params; + gst_base_time, netclock_port in netclock mode; re-broadcast every 30s with FRESH base_time |
| stop | leader → all | stop playback |
| register / heartbeat | collab → leader+UI | presence, status, video_file, driver, hard_seeks, sync_deviation, playback_rate (2s cadence) |
| ping / pong | leader↔collab | RTT probe (2s) → `latency_update` {latency: rtt/2} pushed to that collaborator |
| discover / leader_announce | UI ↔ leader | UI finds real leader; announce carries video_file, video_driver, is_optimized |
| config_request / config_state | UI ↔ device | editable fields+values snapshot |
| config_update / config_update_result | UI → device | whitelisted save; device restarts after applying (leader: on role or video_file change) |
| config_reset | UI → device | defaults + restart |
| file_list_request / file_list_response | UI ↔ device | media inventory (leader registered since dafdb91) |
| file_delete_request | UI → device | delete + fresh list |
| file_upload_notify | UI → device | {filename, source_url} → device pulls over HTTP (two-hop) |
| log_request / log_response | UI ↔ device | last 100 log lines (payload capped — UDP truncation incident 1a57a01) |
| device_update | UI → device | git pull + reboot |
| reset_seeks | UI → collab | zero hard-seek counter |
| remote_start / remote_stop / remote_seek / remote_set | UI → leader | delegated transport control |

## Key data flows

**Start**: UI `remote_start` → leader `start_system()` → play() (netclock: leader also
starts NetTimeProvider) → SyncBroadcaster begins ticks → start command (direct sends to
registered collaborators + broadcast; re-broadcast 30s) → collaborator resolves file
(its own configured `video_file` WINS over the leader's broadcast name — per-device
codec strategy depends on this) → netclock: `use_network_clock` then align-on-play;
udp: play from 0 and let the controller catch up.

**Sync correction (udp)**: tick → `_handle_sync` (latest-wins under lock) →
`_process_sync_tick` (10ms loop; latency+lag compensation) → `_maintain_video_sync`:
mod-duration deviation, median filter, deadband → rate nudge → accurate seek → hard
seek (KEY_UNIT, escalating to ACCURATE on repeat within 15s), settle windows, loop-seam
suppression. In netclock mode the same path runs as measurement + coarse watchdog
(realign beyond `netclock_max_drift`, default 0.5s).

**Config update**: UI save → `config_update` (direct+broadcast, target-filtered) →
`clean_and_save_config` (whitelist rewrite, single section) → device restarts →
UI re-pulls config at +4s/+9s.

## Invariants (violation = incident)

1. `main` always boots on a Pi — the fleet updates by `git pull` from main.
2. Per-device encodes share **identical fps and duration** (sync compares positions).
3. `sync_mode` matches on every node (mismatch now degrades to udp, but never ship it).
4. One L2 broadcast domain; UDP broadcast must reach all nodes.
5. Every config key is in `CONFIG_ROLE_KEYS` (else silently stripped on save).
6. Every 5006 handler filters `_message_targets_this_device` when a target is present.
7. Netclock join requires a leader-provided SETTLED base_time (re-read per broadcast).
8. Never commit a device `ksync.ini` (gitignored; collision bricks `git pull`).
9. USB-stick provisioning (ksync.ini at USB root) keeps working.
10. Sync quality claims come from `logs/sync_deviation.csv` or glass footage — never eyes.

## Known weak points (honest, as of 2026-07-06)

- **Nothing above 2 nodes has been tested.** RTT probes, heartbeats, direct sends and
  upload fan-out are all O(N) — see `ksync-sub10ms-campaign` scaling phases.
- **Dual-NIC ambiguity**: broadcast address derives from the default-route interface
  (`_get_broadcast_address` 8.8.8.8 trick); eth0+wlan0 on one subnet makes paths
  unpredictable.
- **EOS flushing-seek loop fallback** (when SEGMENT unsupported) breaks the netclock
  anchor until the watchdog realigns.
- **Upload two-hop** fails quietly on the device side; scp is the reliable path.
- **No CI**; tests are local-only (`python3 -m unittest discover -s tests`, 43 tests).
- **Netclock precision on Pi hardware is unproven** (desktop ±0.1ms only).
- **Display-chain latency** is invisible to software; policy is identical displays +
  game mode; `video_offset` exists for mixed hardware.
- GEMINI.md drift (see header).

## Provenance and maintenance

Written 2026-07-06 against the code at cb09752. Re-verify:

- Message types: `grep -rn '"type":' leader.py collaborator.py src/networking/communication.py src/remote/controller.py | grep -o '"type": *"[a-z_]*"' | sort -u`
- Ports: `grep -rn "5005\|5006\|9997\|8080" src/networking/communication.py src/remote/controller.py | head`
- Invariant 5 whitelist name: `grep -n "CONFIG_ROLE_KEYS" src/config/manager.py`
- Test count: `python3 -m unittest discover -s tests 2>&1 | tail -2`
