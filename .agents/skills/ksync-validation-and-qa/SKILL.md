---
name: ksync-validation-and-qa
description: >
  What counts as evidence in kSync, the test suite anatomy and mocking patterns for
  writing new tests, acceptance thresholds for sync quality, and the shipped netclock
  golden harness. Load this before claiming anything works, when adding or modifying
  tests, when reviewing a sync-related change, or when promoting an experimental
  feature to production.
---

# kSync Validation and QA

Verified 2026-07-06. Replaces the old `sync-regression-test` skill.

When NOT to use: instrument interpretation → `ksync-diagnostics-toolkit`; merge
gating policy → `ksync-change-control`; research-grade evidence discipline →
`ksync-research-methodology`.

## The evidence bar

1. **Numbers, never eyes.** Sync claims cite deviation-CSV percentiles or slow-mo
   frame counts. "It looks synced" has been wrong repeatedly in this project.
2. **Label the bench.** Desktop-GStreamer results ≠ Pi results. The netclock repair
   is desktop-verified at ±0.1 ms; the sub-10 ms Pi claim is a GOAL until a Pi CSV +
   glass footage exist (see ksync-sub10ms-campaign).
3. **One mechanism explains everything** — including the observations that got better
   on their own. If your explanation covers 4 of 5 symptoms, it's the wrong one.
4. **Negative results are deliverables**: a proven dead end goes into
   ksync-failure-archaeology so nobody refights it (the chrony entry is the model).

## Test suite anatomy (43 tests, all green as of 2026-07-06)

```bash
python3 -m unittest discover -s tests            # full suite (pytest is NOT installed)
python3 -m unittest tests.test_sync_simulation -v # one file
python3 -m unittest tests.test_sync_simulation.SyncSimulationTest.test_netclock_watchdog
```

| File | Covers |
|---|---|
| test_core.py | driver factory, SystemState (SyncTracker case removed with code_archive, 2026-07-07) |
| test_networking.py | broadcast address calc, SyncBroadcaster/Receiver basics, RTT recording |
| test_ntp_check.py | core.ntp_check parsing |
| test_remote_controller.py | web-UI state building, byte-range resolution |
| test_sync_regressions.py | set_speed event types, EOS cache reset, start-command dedupe, loop-boundary wrap, leader config target-filtering, unified-config persistence/migration |
| test_sync_simulation.py | P-controller settling + oscillation (kp sweep), netclock watchdog (guard/backoff), netclock→udp fallback, KEY_UNIT→ACCURATE escalation, latency compensation |

## Writing new tests (the house patterns)

GStreamer is never imported for real in tests. Standard header (from
tests/test_sync_regressions.py):

```python
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("vlc", MagicMock())
sys.modules.setdefault("gi", MagicMock())
sys.modules.setdefault("gi.repository", MagicMock())
```

Two styles in use:
- **Dummy-object style** (regressions): build a `SimpleNamespace` with exactly the
  attributes the method under test touches, call the unbound method:
  `collaborator.CollaboratorPi._maintain_video_sync(dummy, 5.0)`. Brittle to
  attribute additions — when you add state to `__init__`, grep tests for dummies.
- **MockConfig/MockVideoDriver style** (simulation): `CollaboratorPi()` constructed
  for real with `patch('collaborator.get_video_driver', return_value=MockVideoDriver())`
  and `patch('collaborator.ConfigManager', return_value=MockConfig(...))`. MockConfig
  needs passthrough `getint/getfloat(key, default, section=None)` methods.

Required coverage for a sync-logic change: at least one regression test encoding the
NEW contract (the suite intentionally broke twice on 2026-07-06 when behavior changed
— tests that encode old bugs get UPDATED, with a comment saying why).

## The netclock golden harness (ships with this skill)

End-to-end check of both netclock guarantees with real GStreamer pipelines
(fakesink `sync=true`, NetTimeProvider on port 39999):

```bash
python3 .agents/skills/ksync-validation-and-qa/scripts/netclock_verify.py media/sync_test_definitive.mp4
```

Verified output on desktop GStreamer 1.28 (2026-07-06):

```
[leader] running; settled base_time=1140722820023346
[collab] net clock synced=True
JOIN    steady-state offset +0.0ms -> PASS
[leader] seeking +3s (simulates operator seek -> follower desync)
REALIGN steady-state offset +0.0ms -> PASS
```

Exit 0 = pass. Run it after ANY change to gst_driver.py netclock code
(use_network_clock, _align_to_network_clock, netclock_realign, gapless looping) or
to the base_time handling in leader.py. No video argument → videotestsrc fallback.
Note: this is a desktop harness; it validates the MECHANISM, not Pi performance.

## Acceptance thresholds (as of 2026-07-06)

| Context | Threshold | Instrument |
|---|---|---|
| udp mode, wired LAN, steady state | \|dev\| p95 ≤ 50 ms; 0 hard seeks after settle | `analyze_deviation.py --goal-ms 50` |
| netclock mode, steady state (GOAL) | \|dev\| p95 ≤ 10 ms pipeline; ≤ 1 frame glass | analyzer `--goal-ms 10` + slow-mo protocol |
| Startup | converged within ~5 s of start command | CSV settle window |
| Any mode | rate time-at-max ≈ 0% (else decode bottleneck) | analyzer output |
| Unit suite | 43/43 (or more) OK, always, on main | unittest command above |

Promotion protocol (experimental → recommended default): mechanism validated by the
golden harness → Pi 2-node CSV meets threshold → glass footage meets threshold →
docs/PROJECT_OVERVIEW.md + CHANGELOG updated → then flip defaults. Routed through
`ksync-change-control`.

## Provenance and maintenance

Written 2026-07-06; harness run against media/sync_test_definitive.mp4 (HEVC 30 s)
the same day. Re-verify:
- Suite count/status: `python3 -m unittest discover -s tests 2>&1 | tail -2`
- Harness still passes: `python3 .agents/skills/ksync-validation-and-qa/scripts/netclock_verify.py`
- Mock header unchanged: `head -25 tests/test_sync_regressions.py`
