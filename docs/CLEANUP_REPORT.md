# kSync Code Cleanup Report — 2026-07-06

> **Execution status (2026-07-07)**: Batches 1–4 DONE (commits 9b1273a, 955a100,
> cec11ee..1b8908a, and the node_common/socket/logging batch). Live per-item status
> is tracked in `.agents/skills/ksync-code-hygiene`. Batch 5 (C3/C4/D1 organizational
> splits) is intentionally deferred until those files are next touched for a feature.

Full-tree audit: what to remove, fix, optimize, and reorganize. Every item carries
its evidence; nothing has been deleted yet. Execution rules per
`.agents/skills/ksync-change-control` (one theme per commit, tests green, boot one Pi
before the fleet pulls). Companion discipline: `.agents/skills/ksync-code-hygiene`.

Scale of the problem: 104 tracked files; the audit found ~70 KB of confirmed-dead
tracked code, four bugs-in-waiting, two real inefficiencies, and a handful of
misleading artifacts that actively lie to newcomers.

---

## A. DELETE (confirmed dead, evidence attached)

| # | Item | Evidence | Effort |
|---|------|----------|--------|
| A1 | `code_archive/` — entire tree (~70 KB: debug_v2 browser overlay 43 KB, legacy remote_controller.py 24 KB, legacy setup scripts, Firefox cleanup scripts, midi tools) | Single live edge: `tests/test_core.py:22` imports `code_archive.system_state_legacy.SyncTracker`. Nothing in src/ references the tree. Git history preserves it forever — that is what history is for | Small: move/retire the one SyncTracker test, then `git rm -r code_archive/`. Also closes the TODO.md "Firefox cleanup flow" decision (delete) |
| A2 | `kitchensync.service` (tracked file) | **Actively misleading**: browser-overlay era — `Requires=display-manager.service`, `/home/gsync/ks-env` venv path (current is `.venv`), 10 Firefox `MOZ_*` env vars. setup.sh §7 generates the real service itself | Trivial: `git rm`; add a comment in setup.sh noting it's the only source of truth |
| A3 | `tools/ntp-setup.sh` | Chrony dead end, DO-NOT-REOPEN (archaeology E7). Keeping it invites the next person to re-run it "to fix sync" | Trivial |
| A4 | Unused top-level imports (11 across 10 files) | AST scan: collaborator.py `signal`; kitchensync.py `time`; config/manager.py `Path`; video/__init__.py `VideoFileManager`; video/driver.py `Optional`; file_manager.py `glob`; core/system_state.py `List, deque`; protocols/midi_handler.py `log_warning, log_error`; tools/verify_gst_hwaccel.py `sys`; tools/generate_sync_video.py `sys` | Trivial, zero risk |
| A5 | `GEMINI.md` | Stale manifest: still calls the P-controller *the* sync model; predates netclock, unified config, the whole 2026-07 repair. Two better docs exist (PROJECT_OVERVIEW.md + skills) | Replace body with a 5-line pointer, or delete |
| A6 | `sync_params` block in leader.py start command | Leader builds+broadcasts it every 30 s; `grep -n sync_params collaborator.py` → **zero readers**. Dead payload that falsely implies leader-controlled tuning | Small. (Alternative: wire it on the collaborator — decide, don't leave ambiguous. Recommend delete; per-device config is the actual mechanism) |

Judgment call, owner input wanted: `tools/reset-network.sh` (chrony-era but generic
interface reset — keep if you actually use it), `arduino/test.py` (keep; relocate
under tools/).

## B. FIX (bugs-in-waiting / drift)

| # | Item | Problem | Fix |
|---|------|---------|-----|
| B1 | `max_samples` | Collaborator hardcodes `self.max_samples = 3` (collaborator.py:117), ignoring config; property default is 10 (manager.py:445); UI default is 3. Three values for one fact | Read from config in `__init__`; align property default to 3 |
| B2 | `enable_midi` default | Property default **True** (manager.py) while production ships false and MIDI is dormant — a fresh config without the key silently enables MIDI init | Flip property default to False; banner in docs/MIDI_CONTROL.md ("dormant as of 2026-07") |
| B3 | `requirements.txt` | Lists `python-rtmidi` which setup.sh does NOT install; install instructions reference the dead `~/ks-env` venv path. Two sources of truth already drifted | Make setup.sh pip-install `-r requirements.txt`; fix the header text; reconcile the package list |
| B4 | Duplicated leader/collaborator code | `_log_startup_crash` (identical), `_handle_device_update`+`_do_update` (~35 near-identical lines), `_handle_log_request` (near-identical), `_message_targets_this_device` (identical). This drift class already caused b4e153c (collaborator had target filtering, leader didn't) | Extract `src/core/node_common.py`; both entry points import. ~1 h, big future payoff |
| B5 | `src/protocols/osc_handler.py` | Instantiated when enable_osc=true, then **never called** (`grep "osc_handler\." collaborator.py` → nothing). Scaffold masquerading as a feature | Add a one-line "scaffold — not wired" comment now; wire or delete when frontier item F5 (protocol events) is picked up |

## C. OPTIMIZE (measured or structural)

| # | Item | Problem | Fix |
|---|------|---------|-----|
| C1 | `CommandListener.send_message` (communication.py:705) | Creates a **new socket per message** and, for broadcasts, calls `_get_broadcast_address()` which opens *another* socket and connects to 8.8.8.8 — on every heartbeat, every 2 s, on every collaborator. At 20 nodes: ~20 socket-pair creations/s cluster-wide for no reason | Cache one send socket + the broadcast address (invalidate on send failure). ~30 min |
| C2 | `[NET]`/`[DISCOVER]`/`[CONFIG]` `print()` calls in communication.py (10), leader.py, controller.py | Leader prints one line per received datagram → journald writes scale with N × heartbeat rate; at 20 nodes ≥ 10 lines/s of noise burying real errors, on SD cards | Route through `core.logger` at DEBUG level (existing `enable_system_logging` gate), delete the rest |
| C3 | `src/remote/controller.py` (968 lines) | One `BaseHTTPRequestHandler` class holds routing, state assembly, uploads, config, media, logs. Functional but the single hardest file to modify safely | Organizational split when next touched: `state.py` (snapshot stores + build_ui_state), `http_api.py` (routes), `udp_bridge.py` (command_manager wiring). No behavior change; do NOT bundle with anything else |
| C4 | `remote.js` (997 lines, one file) | Same monolith pattern client-side | Split only when the UI overhaul happens (owner: UI must become "VERY EASY" — that's the moment) |
| C5 | file_manager metadata cache | Disk write per cache MISS only (hit path returns early) — fine today; worth a re-check if media libraries grow | No action; noted so nobody "optimizes" it blind |

## D. ORGANIZE / DOCS

- **D1** `.agents/agents/*.md` (8 agent definitions, written pre-repair era 411f44d):
  review against the new skill library; several likely restate what skills now own.
  Keep agents thin ("load skill X"), delete overlap.
- **D2** `arduino/test.py` → `tools/`; `examples/` stays (referenced by MIDI docs).
- **D3** docs/MIDI_CONTROL.md (473 lines): add dormant-feature banner (see B2).
- **D4** One-home-per-fact sweep: ports table, codec matrix, and recipes now live in
  PROJECT_OVERVIEW + skills; TESTING.md and INSTALLATION.md should point, not copy.
- **D5** TODO.md: half the items are done — prune against CHANGELOG.

## E. LOOKS DEAD — IS NOT (do not touch)

| Item | Why it stays |
|---|---|
| `udp` sync mode | The safety net netclock falls back to; never delete |
| `mock` video driver | Test suite + leader fallback depend on it |
| leader.py interactive CLI (non-`--auto`) | SSH debugging path |
| `research/` | History of record (only research.md tracked; 39 MB of clones already untracked) |
| Settle windows / loop-seam suppression in collaborator.py | Each is an incident scar (seek storms, seam spikes) |
| `is_wall_clock` / fakesink handling | Headless + mock-leader paths |
| `examples/*.json` | Referenced by MIDI docs |

## Recommended batch order

1. **Batch 1 — zero-risk deletions** (A2, A3, A4, A5, D5): one commit, tests, push.
2. **Batch 2 — code_archive** (A1): fix the SyncTracker test first, then remove.
3. **Batch 3 — config/schema fixes** (B1, B2, B3, A6): each touches behavior — one
   commit each, config-reference skill updated in-commit.
4. **Batch 4 — shared node_common refactor** (B4) + heartbeat socket cache (C1) +
   print→logger (C2): mechanical but broad; full test run + one-Pi boot check.
5. **Batch 5 — organizational splits** (C3/C4/D1): only when those files are next
   touched for a feature; never as drive-by.

After batches 1–4 the tree drops ~70 KB of dead weight, four latent bugs, and its
two worst sources of newcomer confusion (the stale service file and manifest) — with
zero behavior change intended anywhere except B1/B2 default alignment.

---
*Audit method: full git history read (797 commits), AST unused-import scan, reference
tracing (grep across py/sh/md/js/html), runtime-path reading of every src/ module,
and the 2026-07-06 incident session. Re-verification one-liners for each claim live
in `.agents/skills/ksync-code-hygiene/SKILL.md`.*
