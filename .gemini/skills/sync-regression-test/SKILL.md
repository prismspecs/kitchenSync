---
name: sync-regression-test
description: >
  Run and interpret kSync sync regression tests. Executes the sync test suite
  (test_sync_regressions.py, test_sync_simulation.py) and provides analysis of
  failures, particularly loop-boundary regressions, deviation spikes, and
  hard-seek storms.
---

# kSync Sync Regression Test Runner

Use this skill when:
- Modifying `collaborator.py` sync logic (P-controller, loop handling)
- Changing `SyncBroadcaster` or `SyncReceiver` in `communication.py`
- Tuning sync parameters (kp, max_drift, min_drift, rates)
- Before merging any PR that touches sync-related code

## Test Execution

### Quick Sync Tests (Tier 1 — No hardware needed)
```bash
cd /home/grayson/workbench/kitchenSync
python3 -m pytest tests/test_sync_regressions.py tests/test_sync_simulation.py -v
```

### Full Test Suite
```bash
python3 -m pytest tests/ -v
```

### Focused Test (single test case)
```bash
python3 -m pytest tests/test_sync_regressions.py::TestSyncRegressions::test_loop_boundary -v
```

## Test File Reference

### `tests/test_sync_regressions.py` (~11K)
Regression tests for specific sync bugs that were fixed:
- **Loop boundary:** Verifies EOS wrap doesn't trigger false hard seeks
- **Deviation calculation:** Confirms modular arithmetic for wrapped timelines
- **Settle window:** Ensures no sync corrections during settle period after seek
- **Startup fast-sync:** Tests raw deviation mode for first N samples

### `tests/test_sync_simulation.py` (~8.7K)
Multi-node simulation tests:
- **Leader broadcast + collaborator receive:** End-to-end sync flow
- **Rate correction convergence:** P-controller settles within bounds
- **Multiple collaborators:** Concurrent sync with independent deviations

### `tests/test_core.py` (~1.8K)
Core module tests (schedule loading, system state)

### `tests/test_networking.py` (~4.2K)
Networking unit tests (packet format, broadcast detection)

## Interpreting Failures

### Loop Boundary Regression
**Symptom:** `test_loop_boundary` fails with unexpected hard seek
**Root cause:** Usually means the deviation wrapping logic was broken:
```python
# This MUST exist in _maintain_video_sync:
if deviation > duration/2: deviation -= duration
elif deviation < -duration/2: deviation += duration
```

### Deviation Spike
**Symptom:** `test_deviation_calculation` shows deviation > max_drift
**Root cause:** Usually means the median filter is not working or `max_samples` is wrong

### Hard Seek Storm
**Symptom:** Tests show `hard_seek_count` incrementing rapidly
**Root cause:** Usually missing `_settle_until` after seek, or `deviation_samples` not cleared

### Convergence Failure
**Symptom:** `test_rate_convergence` doesn't settle to rate=1.0
**Root cause:** Usually `kp` too low, `min_drift` too high, or `max_samples` too large

## Coverage Requirements

For sync-related changes, these areas MUST have test coverage:
- [ ] P-controller rate calculation: `rate = clamp(1.0 - (dev * kp), min_rate, max_rate)`
- [ ] Deviation wrapping for looping video
- [ ] Loop boundary seek suppression (within 3s of start/end)
- [ ] Settle window enforcement after seeks
- [ ] Startup fast-sync bypass (first `FAST_SYNC_THRESHOLD` samples)
- [ ] Session deduplication (same session key → no restart)
- [ ] Wall-clock vs media-time source handling
