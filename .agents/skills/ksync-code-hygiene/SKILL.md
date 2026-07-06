---
name: ksync-code-hygiene
description: >
  The kSync dead-code-slashing discipline: the verified suspect inventory (what is
  safe to delete, what is load-bearing legacy, what must be updated), the
  verify-unused protocol, and the LLM-mess patterns this repo has repeatedly
  suffered. Load this before deleting or archiving anything, during cleanup passes,
  or when you find code whose purpose is unclear.
---

# kSync Code Hygiene

Owner mandate (2026-07-06, verbatim): "we need a really solid overview plus to
relentlessly slash old unused and shitty code from this." This skill is the HOW.
Deletions are changes: they route through `ksync-change-control` (tests pass, grep
clean, CHANGELOG entry, main still boots, one revert-friendly commit per removal).

When NOT to use: to understand WHY something exists → `ksync-failure-archaeology`
first (it may be an incident scar, not cruft).

## The verify-unused protocol (run ALL of these before condemning)

```bash
TARGET=some_module          # the thing you want to delete
grep -rn "$TARGET" --include="*.py" . | grep -v ".venv\|__pycache__\|code_archive"
grep -rn "$TARGET" --include="*.sh" --include="*.md" --include="*.html" --include="*.js" . | grep -v ".venv"
grep -rn "$TARGET" tests/                       # tests import surprising things here
git log --oneline -3 -- path/to/$TARGET         # recently touched = probably alive
grep -rn "getattr\|import_module\|__import__" --include="*.py" . | grep -i "$TARGET"  # dynamic use
```
Then: delete → `python3 -m unittest discover -s tests` → boot check on one Pi before
the fleet pulls.

## Suspect inventory (each item verified 2026-07-06)

| Item | Evidence | Recommendation |
|---|---|---|
| `code_archive/` (whole tree, ~15 files: debug_v2 overlay 43 KB, remote_controller.py 24 KB, legacy setup scripts, midi tools) | **One live edge**: `tests/test_core.py` imports `code_archive.system_state_legacy.SyncTracker`. Nothing else references it | Move `SyncTracker` test coverage into src or delete that test case; then DELETE the tree (git history preserves it — that's what it's for) |
| `kitchensync.service` (tracked file) | setup.sh GENERATES its own service file; the tracked one is browser-overlay-era (Firefox `MOZ_*` env vars, `/home/gsync/ks-env` venv path, display-manager dependency). Verify: `grep -c MOZ kitchensync.service` → nonzero | DELETE (or reduce to a comment pointing at setup.sh §7) — actively misleading |
| `tools/ntp-setup.sh`, `tools/reset-network.sh` | Chrony-era (archaeology E7 — DO-NOT-REOPEN); sync needs no NTP | DELETE ntp-setup.sh; KEEP reset-network.sh only if still used for interface resets — grep docs first |
| `src/protocols/osc_handler.py` + `enable_osc` | Handler is instantiated when enable_osc=true but **never called anywhere** (`grep -n "osc_handler\." collaborator.py` → nothing). Dead feature scaffold | KEEP the file (protocol events revival is planned — ksync-research-frontier item e) but add a comment "scaffold, not wired"; or delete and re-add when needed |
| `sync_params` in the start command | Leader builds and broadcasts it; **collaborator never reads it** (`grep -n sync_params collaborator.py` → nothing). Dead payload, misleading (implies leader-controlled tuning) | Either wire it (collaborator applies on start) or delete from leader.py — decide, don't leave ambiguous |
| `max_samples` config | Collaborator hardcodes `self.max_samples = 3`, ignoring config (property default 10, UI default 3) | Fix: read from config; align defaults to 3 |
| `arduino/test.py` | Standalone hardware util, no imports from main code | KEEP (hardware bring-up tool) but move under tools/ or examples/ |
| `examples/` (3 tracked files: schedule JSONs) | Referenced by docs/MIDI_CONTROL.md workflows | KEEP while MIDI docs exist |
| `research/` | Only research.md + .gitignore tracked; 39 MB of cloned repos are already untracked | KEEP as history; never import from it |
| `GEMINI.md` | Stale manifest: still calls the P-controller *the* sync model; predates netclock, unified config | UPDATE to a thin pointer at docs/PROJECT_OVERVIEW.md + .agents/skills, or delete |
| `docs/MIDI_CONTROL.md` (473 lines) | Feature dormant (enable_midi=false in production; property default true — mismatch) | KEEP doc; add a "dormant as of 2026-07" banner; fix the default mismatch |
| Firefox cleanup flow | Only in code_archive/scripts/cleanup_firefox.sh; TODO.md still carries the revive-or-delete decision | DELETE with code_archive; close the TODO item |
| Unused top-level imports | AST scan 2026-07-06: collaborator.py `signal`; kitchensync.py `time`; config/manager.py `Path`; video/__init__.py `VideoFileManager`; video/driver.py `Optional`; file_manager.py `glob`; core/system_state.py `List, deque`; protocols/midi_handler.py `log_warning, log_error`; tools/verify_gst_hwaccel.py `sys`; tools/generate_sync_video.py `sys` | DELETE the imports (one commit, zero risk after tests) |
| Duplicated code leader.py ↔ collaborator.py | `_log_startup_crash` (identical), `_handle_device_update`/`_do_update` (near-identical ~35 lines), `_handle_log_request` (near-identical), `_message_targets_this_device` (identical) | REFACTOR into `src/core/` shared helpers — this class of drift is how the leader missed the target-filter fix that the collaborator had (b4e153c) |
| `leader.py` non-`--auto` interactive CLI (CommandInterface/StatusDisplay) | Production always runs `--auto` via kitchensync.py | KEEP (debug value) unless src/ui/interface.py rots; re-evaluate |
| `mock` video driver | Used by tests and as leader fallback | KEEP — load-bearing |

## LLM-mess patterns to hunt (all have happened HERE)

1. **Handler defined but never registered** — leader's `_handle_file_list_request`
   sat dead for weeks (Available Videos empty); earlier: b53e2a9 (config saves
   silently dropped). Hunt: for every `def _handle_*`, grep a matching
   `register_handler(`/dispatcher entry.
2. **Duplicate method definitions** — second silently wins in Python: c7b0886
   (duplicate `_handle_config_request`). Hunt:
   `grep -rn "def " leader.py collaborator.py src/**/*.py | sort | uniq -d` on names.
3. **Whitelist/schema drift** — key exists in code but not in `CONFIG_ROLE_KEYS` →
   silently stripped on save (enable_deviation_log incident). Hunt: config-reference
   skill's regeneration greps.
4. **Two copies of one fact drifting apart** — leader/collaborator duplicated
   handlers; max_samples 3-vs-10; property defaults vs UI defaults. Hunt: any
   constant that appears twice.
5. **Fallbacks for removed subsystems** — VLC references in src/video/__init__.py
   and tests' `sys.modules["vlc"]` mock outlive the backend; Firefox env vars in the
   tracked service file. Acceptable short-term; label or remove.
6. **Comments describing the previous version of the code** — after 797 commits of
   fast iteration, treat comments as hints, not truth; delete wrong ones on sight.
7. **Stale cache-busters/versions** — remote.js `?v=N` must move with the file
   (currently v15; check `grep "remote.js?v=" src/remote/templates/index.html`).

## Cleanup batching rules

- One theme per commit (unused imports ≠ code_archive removal ≠ service file).
- Never mix cleanup with behavior change — the bf53a41 revert lesson.
- After each batch: full test suite + boot one Pi before the fleet updates.

## Provenance and maintenance

Written 2026-07-06 from a full-tree audit (grep evidence embedded above).
Re-verify before acting:
- code_archive still test-imported: `grep -rn "code_archive" tests/`
- sync_params still dead: `grep -n "sync_params" collaborator.py`
- OSC still unwired: `grep -n "osc_handler\." collaborator.py`
- Unused imports still unused: re-run an AST scan or pyflakes if available
- Tracked service still stale: `grep -c MOZ kitchensync.service`
