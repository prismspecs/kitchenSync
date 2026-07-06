---
name: ksync-research-frontier
description: >
  Open problems where kSync could advance the state of the art — zero-infrastructure
  sub-frame sync, auto-calibrating video walls, artist-grade plug-and-play, per-device
  auto-transcoding, and timeline protocol events — each with why current SOTA fails,
  kSync's specific asset, the first three concrete steps in this repo, and a
  falsifiable result milestone. Load this when planning beyond the current campaign,
  scoping new features, or writing anything public about the project.
---

# kSync Research Frontier

Owner-confirmed targets (2026-07-06). Everything here is OPEN or CANDIDATE — nothing
below may be claimed as achieved. Positioning rule: before any public claim, the
evidence must be reproducible by a stranger (published scripts + CSV + camera
methodology; desktop results labeled desktop).

When NOT to use: executing the current precision work → `ksync-sub10ms-campaign`;
evidence discipline → `ksync-research-methodology`.

## F1 — Sub-frame sync on commodity Pis with ZERO network infrastructure

- **Why current SOTA falls short**: existing multi-screen sync (gst-sync-server
  lineage, info-beamer, PiWall descendants, commercial BrightSign-class players)
  assumes managed infrastructure (PTP-capable switches, NTP servers), licensing, or
  a controlled distribution. kSync's bet: consumer router + stock Pis + one repo.
- **kSync's asset**: working netclock anchor math (desktop ±0.1ms), an RTT/2 scheme
  needing no external time source, and a measurement culture (deviation CSV +
  analyzer + glass protocol) most hobby projects lack.
- **First three steps in this repo**: (1) pass campaign gates G1–G2 on Pi hardware;
  (2) add clock-quality telemetry — GstNetClientClock exposes stats via its bus;
  log round-trip/deviation estimates alongside the CSV; (3) repeat over consumer
  WiFi and publish the wired-vs-WiFi delta.
- **Result when**: two stock Pis on an unconfigured consumer router show 10-minute
  CSV p95 < 10ms AND ≤1-frame glass footage, reproduced by someone else from the
  repo docs alone.

## F2 — N-node video walls with automatic calibration

- **Why SOTA fails**: video-wall auto-cal exists in commercial controllers, not in
  open commodity stacks; display-latency deltas are usually hand-tuned.
- **Assets**: `video_offset` knob already wired end-to-end; `tools/generate_sync_video.py`
  (test-pattern generator) as the seed for a calibration pattern; the web UI upload
  path for receiving a phone clip.
- **First three steps**: (1) generate a flashing frame-counter/QR calibration
  pattern per device; (2) web-UI "Calibrate" flow: play pattern on all nodes,
  accept one slow-mo clip upload; (3) decode frame numbers per screen from the clip,
  compute per-device offsets, write `video_offset` via the existing config_update
  path. (Deferred harder variant: GPIO photodiode per node → fully hands-off; owner
  parked both on 2026-07-06 in favor of identical-display policy.)
- **Result when**: mixed-model displays, one button + one phone clip, and the wall
  measures ≤1 frame spread afterwards — no human ever typing a number.

## F3 — Artist-grade plug-and-play (no engineer on site)

- **Why SOTA fails**: open solutions assume a technical operator; commercial ones
  assume a budget.
- **Assets**: USB provisioning (ksync.ini at USB root → role auto-adoption,
  bystander mode for blank nodes), hardware-derived device IDs, single-codebase
  universal node.
- **First three steps**: (1) error surfacing — bystander/failure states must show
  on-screen guidance (TODO.md backlog item "Bystander Status Overlay"); (2) web-UI
  simplification pass with a non-technical tester (owner: UI must become "VERY
  EASY"); (3) a printed/PDF one-page show-day runbook generated from
  docs/DEPLOYMENT_CHECKLIST.md.
- **Result when**: a non-technical person assembles leader + 2 collaborators from
  labeled hardware and a USB stick, unassisted, in under 30 minutes, video synced.

## F4 — Drag/drop per-device auto-transcode (owner: low priority, definitely needed)

- **Why**: the per-device codec matrix (Pi5=HEVC, Pi4=H.264, keyint=fps) is
  currently manual ffmpeg discipline — the #1 place a future user will fail.
- **Options**: extend the browser UI (drop file → server-side ffmpeg per target
  device) or an Electron shell skinning the same UI.
- **First three steps in this repo**: (1) `/api/transcode` in
  src/remote/controller.py: accept upload + target device, shell out to ffmpeg with
  the recipes from `ksync-media-encoding-reference`, job status via the existing
  snapshot-store pattern; (2) ffmpeg presence check + progress parsing (`-progress`);
  (3) decide where transcodes run — UI host (fast desktop, then two-hop push) vs the
  Pi (slow; avoid). 
- **Result when**: dropping one source file yields correctly-encoded, correctly-named
  files on every device with verified codecs (`is_optimized`/discoverer check) and
  identical durations, no terminal involved.

## F5 — Timeline protocol events revival (schedule.json → MIDI/OSC at timecode)

- **Current state (verified)**: machinery exists and is dormant — `src/core/schedule.py`
  (cue parsing, ~25KB, supports JSON and MIDI files via optional mido),
  `src/protocols/midi_handler.py` (MidiManager/MidiScheduler; leader runs a 20ms cue
  loop when enable_midi=true), `docs/MIDI_CONTROL.md` (473 lines), examples/*.json.
  OSC is scaffold-only (handler instantiated, never fed). Production configs ship
  enable_midi=false.
- **Why interesting**: events inherit video-sync quality — a cluster firing relays/
  MIDI within ~10ms of picture across 20 nodes is a real capability gap in open
  tooling.
- **First three steps**: (1) re-validate leader-side MIDI cue loop against current
  playback position source (it polls `video_player.get_position()`); (2) define
  where events fire — leader-only (current design) vs per-node (needs the sync'd
  clock; natural netclock extension); (3) one hardware end-to-end demo: schedule.json
  cue → relay click filmed against on-screen content, measured in ms.
- **Result when**: filmed event-vs-frame offset ≤ 1 frame across 3 consecutive runs.

## Provenance and maintenance

Written 2026-07-06 from owner answers + repo verification. Re-verify:
- Dormant MIDI/OSC state: `grep -n "enable_midi\|enable_osc" ksync.ini ksync_collaborator.ini collaborator.py leader.py | head`
- Calibration assets exist: `ls tools/generate_sync_video.py`
- Bystander overlay still open: `grep -n "Bystander Status Overlay" TODO.md`
