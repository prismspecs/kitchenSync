---
name: ksync-research-methodology
description: >
  The discipline that turns a hunch into an accepted result in kSync: the evidence
  bar, hypothesis-predicts-numbers-first, adversarial refutation, the idea lifecycle
  from experiment to adoption or documented retirement — with the 2026-07-06
  one-second-lag investigation as the worked example. Load this before starting any
  investigation or experiment, and before accepting any conclusion (yours or an
  LLM's).
---

# kSync Research Methodology

How conclusions earn trust here. Verified against the repo's actual history,
2026-07-06.

When NOT to use: executing an already-planned campaign → `ksync-sub10ms-campaign`;
routine fixes → `ksync-debugging-playbook` + `ksync-change-control`.

## The evidence bar

1. **One mechanism must explain ALL observations — including the negatives.**
   "Explains the lag but not why WiFi used to work better" means keep digging.
2. **Hypotheses predict numbers BEFORE the experiment.** "If the broadcast base_time
   is stale by the seek-settle delta, the collaborator's offset will equal that
   delta exactly" — then you run it and it either matches or your mechanism is wrong.
   A hypothesis that only predicts "it will be better" is not testable.
3. **Adversarial refutation before adoption.** Before acting on a conclusion, attack
   it: what OTHER mechanism produces the same evidence? What observation would
   distinguish them? (An LLM investigating its own hypothesis agrees with itself by
   default — force the refutation step explicitly.)
4. **Instruments over impressions.** Deviation CSV and slow-mo frames are admissible;
   "looks synced" is not. Desktop results are labeled desktop.
5. **Negative results are deliverables.** A documented dead end
   (ksync-failure-archaeology) saves the next person weeks. The chrony entry is the
   canonical example.

## Worked example: the one-second lag (2026-07-06)

Symptom: collaborator a constant ~1s behind the leader, wired LAN. Reconstructable
from CHANGELOG.md + `git log ebb773a..cb09752`.

The method moves, in order:

1. **Read the config and topology docs before the code.** research/research.md's
   topology table showed `sync_peer_ip = 192.168.0.165` was the *leader's own* eth0
   address → sync ticks were being unicast to ourselves with broadcast disabled.
   The "network is slow" hypothesis died before any code was read (documented ping:
   0.1ms).
2. **Let the SHAPE of the error select the mechanism class.** A *constant* offset
   that never converges means NO correction is running — a *slow* corrector would
   show decay, an *unstable* one oscillation. That shape-first reasoning exposed
   that netclock mode had disabled the entire measurement/correction path.
3. **Reproduce locally before touching hardware.** A two-pipeline desktop harness
   (now shipped as ksync-validation-and-qa/scripts/netclock_verify.py) reproduced
   the join behavior in minutes instead of Pi-deploy cycles.
4. **Make the mechanism predict an exact number.** Predicted: collaborator offset ==
   leader's base_time shift between broadcast-read and seek-settle. Measured: offset
   +0.020s, base_time delta +0.020s. Exact match = mechanism confirmed (the stale
   base_time race).
5. **Read instrumentation columns as fingerprints.** Later the same day, a CSV alone
   diagnosed a new failure: `hard_seeks` incrementing every row + `rate` pinned
   1.0000 + deviation constant −0.96 ⇒ watchdog spinning against a never-established
   net clock ⇒ the pi4-netclock/pi5-udp mode mismatch — no SSH session needed.
6. **Fix the CLASS, not the instance.** The wrong-video bug was one stale key; the
   fix was eliminating the two-section config format entirely (20bc1d9), plus a
   regression test encoding the new contract.

Transferable checklist: config/topology first → error shape → local repro → numeric
prediction → instrument fingerprints → class-level fix + test.

## The idea lifecycle

```
hunch
  → written hypothesis WITH predicted numbers (a sentence in the campaign/skill/PR)
  → experiment behind a config flag or a local harness — NEVER on main's default path
      (sync_mode is the model: udp stayed default while netclock matured)
  → evidence: CSV/analyzer output or test, archived
  → adversarial pass (what else explains this?)
  → EITHER: adopt via ksync-change-control (tests, CHANGELOG, docs, skills updated)
     OR: retire with a written entry in ksync-failure-archaeology (status: dead end,
         evidence, why) — retirement is a completed deliverable, not a failure
```

## Where good ideas have actually come from here (pattern-verified)

- **Instrumentation built BEFORE tuning**: the deviation CSV (9765d5f) preceded and
  enabled every later sync diagnosis. When stuck: add measurement, not parameters.
- **Upstream design knowledge over invention**: the netclock recipe is standard
  GStreamer distributed-playback practice, applied carefully — reading upstream docs
  beat inventing a custom protocol.
- **Structural fixes after repeated instances**: two whitelist bugs and two
  handler-registration bugs each recurred before the class was named
  (ksync-code-hygiene now hunts them proactively).
- **The repo's own research notes**: research/research.md's improvement list (tick
  rate, kernel timestamps, position_read_time) was mined into shipped commits
  (ae2f681).

## Provenance and maintenance

Written 2026-07-06. Re-verify: worked-example commits
`git log --oneline ebb773a..cb09752` · harness exists
`ls .agents/skills/ksync-validation-and-qa/scripts/netclock_verify.py` ·
CSV instrument predates tuning commits `git log --oneline | grep 9765d5f`
