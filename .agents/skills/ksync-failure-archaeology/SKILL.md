---
name: ksync-failure-archaeology
description: >
  The kSync incident chronicle: every major investigation, dead end, rejected fix,
  and revert as symptom → root cause → evidence → status. Load this BEFORE attempting
  any fix that feels obvious (NTP/chrony, unicast sync, QoS catch-up, config sections,
  decoder ranking, overlay, RTT smoothing) — it has probably been fought before. Also
  load when a git-log subject line or a commented-out block needs historical context,
  or when deciding whether old code is load-bearing.
---

# kSync Failure Archaeology

Chronicle of settled battles. Do not re-fight them. Each entry: **symptom → root cause →
evidence → status**. Hashes are verifiable with `git log --oneline | grep <hash>`.
Facts current as of 2026-07-06.

When NOT to use this skill: for a live problem you haven't identified yet, start with
`ksync-debugging-playbook` (symptom → triage). Come here when you want to know *why*
something is the way it is, or whether an idea was already tried.

## Settled questions (the short list)

| Tempting idea | Verdict | See era |
|---|---|---|
| "Install chrony/NTP to fix sync" | **DO NOT REOPEN.** No sync path needs NTP; all cross-device math is same-clock deltas or RTT/2. Chrony was attempted, blocked (Pi4→Pi5 port 123 unreachable, cause never found), then proven unnecessary. | E7 |
| "Unicast sync over a dedicated IP is tighter than broadcast" | Only for a literal direct cable. `sync_peer_ip` **disables broadcast** and was once set to the leader's own IP, silently killing all sync. | E8 |
| "Share the GStreamer base_time and let QoS catch the late node up" | Pi decoders cannot drop ~1s of frames; the node stays behind forever. Netclock needs the seek-and-anchor join. | E9 |
| "Query the display's latency via EDID/HDMI-CEC" | Consumer TVs report these fields rarely and dishonestly. Policy: identical display model + game mode (owner decision 2026-07-06). | E10 |
| "Commit ksync.ini so devices get config via git" | A tracked ksync.ini collides with each device's untracked local file and **breaks `git pull` on the whole fleet**. Gitignored in ebb773a. | E9 |
| "Split config into [DEFAULT] and [KITCHENSYNC] sections" | Caused permanent silent shadowing of edits. Config is unified single-section since 20bc1d9. | E11 |
| "Sync using wall-clock time between devices" | Reverted era: wall-clock subtraction is clock-drift-vulnerable; replaced by RTT/2 (c752c16). | E5 |

## E1 — Early players: DBUS/omxplayer → VLC → GStreamer

- **Symptom**: no single player gave frame-close sync control on Pi.
- **History**: earliest commits control playback via DBUS (`a4ec9ef "using DBUS"` —
  omxplayer-era pattern); `research/` still holds omxplayer-sync, raspi-video-sync,
  rpi-video-sync-looper, synchronized4kplaybackrpi4 studies. A VLC backend followed and
  was fully removed — `src/video/__init__.py` still logs
  "VLC backend has been removed; falling back to GStreamer" if configured.
- **Status**: settled. GStreamer playbin is the only real driver (plus `mock`).
  Cost rating from owner: "insanely costly." Do not propose player swaps without
  overwhelming evidence.

## E2 — Overlay wars (browser → tkinter → deletion → native)

- **Symptom**: debug overlay caused boot loops and X11 crashes.
- **History**: browser-based overlay abandoned (TODO.md: "non-browser based debug
  overlay… to avoid browser overhead"); tkinter overlay moved to a standalone
  subprocess to dodge multi-threaded X11 conflicts and a boot loop (`3090dd6`); a
  720p-forcing bug fought around the same time (`a40bcde`); finally
  `0305805 "overlay deleted, starting fresh"`.
- **Status**: overlay is a config flag (`overlay`) of limited trust. X11 window
  management remains fragile — "Could not identify video window for resizing" warnings
  are cosmetic (src/ui/window_manager.py title matching), not playback failures.

## E3 — Sync blackout revert (the canonical revert)

- **Symptom**: screens going black during sync corrections.
- **History**: `c32c1f8` introduced non-flushing seeks + parameter smoothing to
  eliminate blackouts → made things undebuggable → **reverted** in
  `bf53a41 "revert: undo sync smoothing and non-flushing seek to debug blackouts"` →
  real fix landed as `ab702ac "resolve playback restart loop causing blackouts"`.
- **Lesson**: when two mechanisms change at once and a regression appears, revert both
  and re-land separately. Non-flushing SEGMENT seeks later returned *for looping only*
  (`483df82` gapless looping) — a narrower, correct use.

## E4 — Web UI / networking stabilization era

- `6a270b4` "deadly silence" bug: discovery/heartbeats stopped flowing; fixed with
  broadcast discovery + restored heartbeats.
- `5923deb`: leader and remote-controller processes unified to resolve port conflicts
  (both wanted 5006). Later re-split; today the web UI is a standalone node
  (`LOCAL_LEADER_ID = "remote-leader"` in src/remote/controller.py).
- Broadcast PermissionError era (`79ca756`, `38929f5`, `abb5d28`, `cbe0e85`): some hosts
  refuse UDP broadcast; leader answers discover/config via **unicast** since then.
  This is why `_send_unicast` exists in leader.py.
- `1a57a01`: log payloads over UDP were truncated → capped (UDP datagram limits are
  real; see UDP_MAX_DATAGRAM_SIZE in src/networking/communication.py).
- `393483d`: "surgical DOM reconciliation" — the web UI's morphing renderer exists
  because naive innerHTML refresh destroyed user input (this bit again in 2026-07,
  see E12).

## E5 — Latency compensation evolution (includes a revert)

- Per-device RTT compensation built (`6d4384b`, `908b9e7`) → decentralized RTT
  experiment (`cf0af41`, `24fe567`) → **reverted to leader-measured average RTT**
  (`a021f66`) → per-device again, done right: `c752c16` replaced clock-drift-vulnerable
  wall-clock subtraction with **RTT/2** measured by leader ping/pong, pushed to each
  collaborator as `latency_update`, EWMA-smoothed (alpha 0.3) in collaborator.py.
- **Status**: current design. This is also *why NTP is unnecessary*: no math crosses
  two different clocks.

## E6 — Pi 5 decoder ranking mistake and correction

- **Symptom**: Pi 5 playback broken/stuttering with wrong decoder selection.
- **History**: `491edc0` disabled hardware HEVC on Pi 5 (wrong — Pi 5's rpivid HEVC is
  its ONLY hardware decode) → corrected in `b9e05ad`: keep `v4l2slhevcdec`, demote
  H.264 *hardware* decoders instead (Pi 5 has no H.264 hardware).
- **Status**: settled in `_reprioritize_decoders` (src/video/drivers/gst_driver.py).
  The rule: **Pi 5 = HEVC hardware, H.264 software; Pi 4 = H.264 hardware always,
  HEVC hardware only via v4l2slh265dec.** See `ksync-media-encoding-reference`.

## E7 — The chrony/NTP dead end (June 2026)

- **Symptom**: pursuit of tighter sync led to chrony leader-as-stratum-10 setup.
- **What happened**: Pi 4 could never reach Pi 5's NTP (port 123 timeouts; no firewall
  found; seccomp and config-ordering hypotheses tested; cause never identified).
  Full debug log preserved in `research/research.md` ("Phase 1 Blocked — NTP Not
  Working").
- **Resolution**: NTP proven unnecessary (see E5). `tools/ntp-setup.sh` was deleted
  2026-07-07; `tools/reset-network.sh` remains as a generic interface-reset tool.
- **Status**: **DO-NOT-REOPEN** for sync purposes. If a future feature genuinely needs
  wall-clock agreement (e.g., "start show at 19:00"), that is a new problem — document
  it as such.

## E8 — sync_peer_ip and the self-IP incident (June → 2026-07-06)

- **Symptom (2026-07-06)**: collaborator a constant ~1s behind, nothing correcting.
- **Root cause**: leader's `sync_peer_ip = 192.168.0.165` was the **leader's own old
  eth0 address** (direct-cable era leftover after moving both Pis to a router).
  Setting it disables broadcast (`use_broadcast=False`), so every sync tick went to the
  leader itself; send failures were silently swallowed.
- **Evidence**: research/research.md topology (Pi5 eth0=192.168.0.165,
  Pi4=192.168.0.164); fix commit `ebb773a`.
- **Status**: fixed — leader detects a self-IP target, logs an error, falls back to
  broadcast; send errors rate-limit logged. `sync_peer_ip` remains ONLY for a literal
  direct cable, and must be the COLLABORATOR's IP.

## E9 — Netclock naive startup + base_time race (d7a463e → ebb773a)

- **Symptom**: netclock mode landed (d7a463e, 2026-06-26) but collaborator stayed ~1s
  behind forever; deviation CSV read 0.000 (measurement was disabled in netclock mode).
- **Root causes** (three, compounding):
  1. Join shared base_time and started at position 0, relying on QoS frame-dropping to
     catch up — Pi decoders can't sustain it.
  2. Netclock mode bypassed `_maintain_video_sync` entirely — no measurement, no
     correction, UI showed fake perfect sync.
  3. Leader broadcast a base_time captured **before** the gapless-loop FLUSH|SEGMENT
     seek settled; the value was stale by exactly the settle delta (proven by local
     reproduction: final offset == delta).
- **Fix (`ebb773a`)**: `_align_to_network_clock` (preroll paused → seek to leader
  position 0.5s ahead → anchor base_time so that frame renders exactly then),
  `netclock_realign()`, watchdog in collaborator, settled base_time reads re-read on
  every 30s re-broadcast. Local desktop verification: join +0.0ms; deliberate 5s
  leader seek recovered to −0.1ms. **Desktop numbers — unproven on Pi hardware.**

## E10 — The 2026-07-06 repair saga (nine commits, one day)

All in `git log ebb773a..cb09752` and CHANGELOG.md. Condensed:

| Commit | Incident |
|---|---|
| ebb773a | E8 + E9 fixes; ksync.ini gitignored; PROJECT_OVERVIEW.md created |
| b4e153c | **Leader config clobber**: config_update is broadcast; leader didn't filter `target_device_id`; editing pi4's config in the web UI overwrote pi5's ksync.ini wholesale (role=collaborator, device_id=pi4_1) and execv-restarted the leader AS a collaborator |
| cdc43a7 | gst-discoverer CLI parser only understood legacy "Video:" format; dotted "h.265" failed the codec match → same file labeled HEVC on one Pi, Non-HEVC on the other |
| dafdb91 | Web-UI Load button; leader file_list_request was never registered (Available Videos permanently empty for the leader); refresh loop clobbered in-progress config edits; **whitelist stripping**: any web-UI save silently deleted non-whitelisted keys (killed enable_deviation_log → no CSV) |
| 1c83673 / 20bc1d9 | **Section shadowing**: configparser resolves a section's own key before [DEFAULT]; boot stamped video_file into [KITCHENSYNC]; pi5 kept playing bbb_1080p_24fps_hevc.mp4 while [DEFAULT] said sync_test_pi5_hevc.mp4. Root fix: unified single-section config |
| 5570b2d | **Mode mismatch + 14k realign spin**: pi4 netclock + pi5 udp → no net clock → watchdog attempted realign every tick (~14,000 failures, visible as the hard-seek CSV column incrementing every row) with the P-controller disabled → 0.96s off at rate 1.0000 forever. Fix: netclock→udp automatic fallback + failed-realign backoff. Also: `video_offset` knob, leader HEVC badge |
| cb09752 | **Keyframe hover**: KEY_UNIT hard seeks snap to keyframes; long-GOP files snapped to 0:00, collaborator hovered there until the leader looped around. Fix: repeat hard seek within 15s escalates to ACCURATE |

- Display latency decision (same day): clock sync ends at the HDMI connector; panels
  add invisible latency. **Policy: identical display model + game mode** → video_offset
  stays 0. Calibration wizard / GPIO photodiode auto-cal are DEFERRED candidates
  (see `ksync-research-frontier`).

## E11 — Config format history

Two-section [DEFAULT]/[KITCHENSYNC] format (original) → whitelist save path
`clean_and_save_config` (per-role sections) → boot persistence wrote to KITCHENSYNC
unconditionally → shadowing class of bugs (E10) → **unified single [KITCHENSYNC]
section** (20bc1d9). Legacy files read via fallback and migrate on first save.
Also: `b53e2a9` (leader silently dropped config saves — handler never registered) and
`e420104` (sync_peer_ip lost on save — not whitelisted) were earlier instances of the
same two bug *classes* that returned in 2026-07. The classes are: (1) handler exists
but is never registered; (2) key exists but is not whitelisted. Check both whenever
config or messaging "silently does nothing."

## E12 — Web UI edit-clobber (recurring class)

Naive re-render destroyed user input twice: first fixed by surgical DOM morphing
(`393483d`), regressed in practice via the 1.5s poll re-rendering focused forms —
fixed in dafdb91 (refresh pauses while a config field has focus; Save/Load re-pull
device config at +4s/+9s because devices restart after applying updates).

## Open items (not failures — just unfinished)

- Netclock sub-10ms: proven on desktop, **unproven on Pi hardware** — see
  `ksync-sub10ms-campaign`.
- N>2 nodes: nothing above 2 nodes has ever been tested (as of 2026-07-06).
- Upload two-hop (web-UI host → device HTTP pull) fails silently-ish; scp is the
  reliable path for large files.
- Firefox cleanup flow revival-or-delete decision still open (TODO.md).
- Dual-NIC ambiguity: eth0+wlan0 on one subnet makes traffic paths unpredictable;
  single active NIC during tests.

## Provenance and maintenance

Written 2026-07-06 from git history (797 commits), CHANGELOG.md, research/research.md,
TODO.md, and the 2026-07-06 investigation session. Re-verify:

- Hashes exist: `git log --oneline | grep -E "ebb773a|20bc1d9|cb09752|bf53a41|a021f66|b9e05ad"`
- New incidents since this was written: `git log --oneline --since=2026-07-06`
- Chrony artifacts stay deleted: `ls tools/ntp-setup.sh 2>&1` (expect "No such file")
- VLC removal warning still in place: `grep -rn "VLC backend has been removed" src/video/__init__.py`
