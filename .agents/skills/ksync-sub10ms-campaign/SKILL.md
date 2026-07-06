---
name: ksync-sub10ms-campaign
description: >
  The executable, decision-gated campaign for kSync's hardest live problem: prove and
  HOLD sub-10ms visual sync, from the current 2-node setup through 5 and 20 nodes.
  Numbered phases with exact commands, expected numbers at every gate, branch tables
  for every deviation from expectation, ranked solution menu, and fenced-off wrong
  paths. Load this to run the precision campaign or to evaluate where the project
  stands on it.
---

# kSync Sub-10ms Campaign

Status as of 2026-07-06: netclock mechanism desktop-proven (±0.1ms position level);
**nothing proven on Pi hardware, nothing tested above 2 nodes.** Goal (owner):
sub-10ms visual sync, holding, at 2 → 20 devices. Success is measured, never eyeballed.

When NOT to use this skill: a node is misbehaving right now → `ksync-debugging-playbook`
first; theory questions raised by a gate → `ksync-sync-theory-reference`.

Prerequisites: per-device encodes per `ksync-media-encoding-reference` (Pi5=HEVC,
Pi4=H.264, keyint=fps, same fps+duration); both Pis on latest main; wired into one
switch; wlan down during measurement (`sudo ip link set wlan0 down`).
Wrong paths, fenced (do not spend time there): chrony/NTP (archaeology E7) ·
`sync_peer_ip` unicast (E8) · QoS catch-up reliance (E9) · tuning kp/max_rate at a
decode or transport problem · judging by eye.

## Phase 0 — Baseline (udp mode, 2 nodes)

```bash
# both Pis: sync_mode = udp; restart; start playback from web UI; run 10+ minutes
# then on the collaborator:
python3 .agents/skills/ksync-diagnostics-toolkit/scripts/analyze_deviation.py \
    logs/sync_deviation.csv --goal-ms 50
```
**Gate G0**: VERDICT PASS — |dev| p95 ≤ 50ms, 0 post-settle hard seeks, rate
time-at-max ≈ 0%.

| If instead | Branch |
|---|---|
| constant deviation, rate 1.0000 | ticks not flowing → debugging-playbook rows 1–3 |
| rate pinned at max | decode bottleneck → media-encoding-reference (wrong codec for that Pi) |
| hard seeks recurring | check GOP (long-GOP file) and log for realign/seek reasons |
| p95 50–100ms but stable | proceed anyway; note it — netclock replaces this mechanism |

## Phase 1 — Netclock, 2 nodes (pipeline-level proof)

```bash
# BOTH Pis: sync_mode = netclock (config editor or ini); restart BOTH; play; 10+ min
python3 .../analyze_deviation.py logs/sync_deviation.csv --goal-ms 10
grep -E "NetClock|Clock sync" logs/kitchensync.log | tail -5
```
**Gate G1**: p95 ≤ 10ms, 0 realigns after startup, log shows
`Gst: NetClock aligned - starting at ...` and NO `Clock sync timeout`.

| If instead | Branch |
|---|---|
| `Cannot use NetClock yet (… base_time=None)` | leader not in netclock mode — fix both, restart both |
| `Clock sync timeout. Proceeding anyway` | port 9997 blocked/unreachable → tcpdump 9997; expect request/response pairs ~1/s |
| `netclock configured but no net clock established` + udp-like CSV | fallback engaged — same as above, netclock never attached |
| p95 10–30ms, stable, no realigns | clock sync jitter on Pi NIC — record numbers; consider PTP track (menu §M3) before concluding |
| periodic realigns at loop seam | EOS fallback looping (SEGMENT unsupported for this file) — check log `looping (flush fallback)`; re-encode or fix segment support |

Record: 10-minute CSV + analyzer output archived (this is baseline evidence for any
future claim).

## Phase 2 — Glass measurement (the number that counts)

Protocol (`ksync-diagnostics-toolkit` §4): phone slow-mo 240fps, both screens in one
shot, motion-rich content; 3 measurements; median.
**Gate G2**: ≤ 1 content frame at 30fps (≤ 33ms) offset; target ≤ 10ms
(sub-half-frame — needs 240fps footage to resolve).

| If instead | Branch |
|---|---|
| clean CSV (G1 pass) but consistent glass offset > 10ms | display-chain latency delta → Phase 3; do NOT touch sync code |
| glass offset varies run to run | not display latency; re-examine CSV during the filmed window; check thermal throttling (`vcgencmd measure_temp`) |

## Phase 3 — Display policy

Owner policy (2026-07-06): **identical display model + game mode on every node**;
`video_offset` stays 0. Mixed displays (only if unavoidable): measure delta per
Phase 2, set `video_offset = +delta` on the fast device, re-measure. Record display
model + picture mode in the deployment notes — it is part of the sync spec.

## Phase 4 — Hold test

Run 4+ hours looping. **Gate G4**: analyzer on the full CSV still passes at goal;
realigns = 0; no drift trend (compare first-hour vs last-hour mean deviation —
shared clock means there must be NONE by construction; any trend = clock sync
degradation → log it, capture tcpdump 9997, investigate before scaling).

## Phase 5 — Scale to 5 nodes

What changes with N (verified in code, all currently O(N) and untested beyond 2):
`send_command` does per-collaborator direct sends + broadcast; leader RTT-probes every
collaborator every 2s; each node heartbeats every 2s; NetTimeProvider serves N client
clocks on 9997; web UI polls state at 1.5s.

Steps: image 3 more collaborators (build-run-operate runbook) → G1 gate per node
(CSV on EVERY collaborator, not just one) → glass spot-check across all screens in
one shot.
**Gate G5**: every node passes G1 numbers; leader CPU headroom recorded
(`top`, expect sync machinery ≈ negligible vs decode); tick loss check
(`analyze_deviation.py` samples/s ≈ tick rate on every node).

| If instead | Branch |
|---|---|
| one node worse than others | that node's decode/display/NIC — swap hardware to isolate; don't retune globally |
| all nodes degrade together | leader-side: tick send loop, 9997 service load, or switch congestion — tcpdump on leader, count outbound pps |

## Phase 6 — Scale to 20 nodes

Instrument BEFORE judging: expected UDP load is trivial (20 ticks/s broadcast is one
packet regardless of N; direct sends add ~20 pps on start; RTT probes 10 pps
aggregate) — the plausible stress points are 9997 clock-request fan-in, web-UI
snapshot buildup, and media distribution (two-hop upload × 20 → use scp/rsync or
staged USB instead).
**Gate G6**: all 20 pass G1; start command reaches all nodes on first broadcast
(count `start` receipts in logs); a full content update to 20 nodes has a written,
timed procedure.

## Promotion protocol (through ksync-change-control)

Netclock becomes the documented default when: G1+G2 pass on Pi hardware · G4 hold
test passed · G5 at ≥5 nodes · configs/mirrors flipped + PROJECT_OVERVIEW and
CHANGELOG updated · udp mode retained as documented fallback (it is the safety net —
never delete it).

## Solution menu (ranked, with obligations)

- **M1 udp-only** (fallback): ceiling ~tens of ms (measurement jitter floor — theory
  skill §4). No further obligations; already validated.
- **M2 netclock** (primary): desktop-proven; obligations = the gates above. Expected
  wired-LAN clock precision sub-ms; if Pi measurements disagree, capture 9997 traffic
  and clock stats before blaming anything else.
- **M3 PTP (GstPtpClock)** (only if M2 misses ≤10ms on Pi): obligations — read
  research/research.md PTP section first: Pi 5 hardware-timestamp kernel bug
  (raspberrypi/linux#5904), Pi 4 software-PTP only (~100µs class), requires
  privileged helper. Candidate, unproven here; treat as a research item with
  predicted numbers before installing anything.
- **M4 photodiode auto-calibration** (glass-level, deferred): closes display deltas
  automatically; hardware add per node; see ksync-research-frontier.

## Provenance and maintenance

Written 2026-07-06 (nothing above 2 nodes tested; netclock desktop-proven only).
Re-verify: analyzer path exists · `grep -n "NetClock aligned" src/video/drivers/gst_driver.py` ·
O(N) claims: `grep -n "for device_id, info in self.collaborators" src/networking/communication.py`
Update this skill's Status line as gates are passed — it is the campaign log's index.
