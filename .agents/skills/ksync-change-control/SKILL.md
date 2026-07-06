---
name: ksync-change-control
description: >
  How changes are classified, gated, and documented in kSync: the non-negotiables
  with the incident behind each, per-class checklists (sync logic, config schema,
  web UI, driver, deletions, docs), and the docs-of-record discipline. Load this
  before committing, before deleting anything, before changing defaults or schemas,
  and when deciding whether a change needs device-side verification.
---

# kSync Change Control

The gates exist because each was paid for. Verified 2026-07-06.

When NOT to use: finding a bug → `ksync-debugging-playbook`; whether code is dead →
`ksync-code-hygiene`; research-grade claims → `ksync-research-methodology`.

## Non-negotiables (each with its incident)

| Rule | Why (incident) |
|---|---|
| **main must always boot on a Pi.** | The fleet updates via web-UI "Update & Reboot" = `git pull` main + reboot. A broken main bricks the update path itself; recovery is SSH per device. |
| **Never commit a device `ksync.ini`.** | Tracked copies collide with each device's untracked local file and abort `git pull` fleet-wide. Gitignored in ebb773a. Repo mirrors (`ksync.ini`, `ksync_collaborator.ini`) stay untracked reference copies. |
| **Every config key goes in `CONFIG_ROLE_KEYS` or it is silently deleted on any web-UI save.** | enable_deviation_log was stripped this way — the project lost its primary instrument without an error anywhere (dafdb91). |
| **Every port-5006 handler must filter `_message_targets_this_device`.** | The leader once applied a broadcast config_update addressed to a collaborator, overwrote its own identity, and restarted as a second collaborator (b4e153c). |
| **`sync_mode` ships consistent; mode-mismatch is a bug even though it now degrades gracefully.** | pi4-netclock/pi5-udp sat 0.96 s off with 14,000 futile realigns before the fallback existed (5570b2d). |
| **Sync claims come from instruments** (deviation CSV / slow-mo frames), never eyes. | Repeated mis-diagnoses; see ksync-research-methodology. |
| **Don't break USB plug-and-play provisioning** (ksync.ini at USB root, media on USB). | Core deployment story for non-technical users (owner requirement). |
| **One theme per commit; never mix cleanup with behavior change.** | The sync-blackout era required a full revert because two mechanisms landed together (c32c1f8 → bf53a41). |
| **NTP/chrony stays dead.** | Costly dead end; nothing needs it (archaeology E7). |

pip dependencies ARE acceptable (owner-confirmed 2026-07-06); add them to setup.sh's
pip line and requirements.txt.

## Change classes and their gates

Baseline for EVERY class: `python3 -m unittest discover -s tests` green (43+ tests) ·
CHANGELOG.md entry · commit message states symptom → cause → fix for bugfixes.

| Class | Additional gates |
|---|---|
| **Sync logic** (collaborator controller, SyncBroadcaster/Receiver, netclock code in gst_driver.py, base_time handling in leader.py) | New/updated regression test encoding the new contract · run the netclock golden harness (`ksync-validation-and-qa`) if netclock-adjacent · before/after deviation-CSV comparison on hardware for tuning claims · update ksync-sync-theory-reference if the math changed |
| **Config schema** (new/renamed key, default change) | Full add-a-key checklist in `ksync-config-reference` (property + whitelist + UI field + ADVANCED_KEYS + cache-buster + mirrors + test) · default changes get a CHANGELOG line naming old→new |
| **Web UI** (controller.py, remote.js, templates) | Bump remote.js version log line AND `index.html` `remote.js?v=N` cache-buster · never introduce a re-render path that can clobber focused inputs (twice-paid lesson) · target_device_id on every new device-addressed message |
| **Driver/GStreamer** | Golden harness run · verify on BOTH Pi models if decoder/sink paths are touched (Pi 5 and Pi 4 have disjoint hardware) · never trust desktop behavior for decode performance |
| **Deletion/cleanup** | `ksync-code-hygiene` verify-unused protocol · one revert-friendly commit per theme · boot one Pi before the fleet pulls |
| **Docs-only** | No test gate; keep PROJECT_OVERVIEW.md and skills consistent (one home per fact) |

## Docs of record

- `CHANGELOG.md` — every non-trivial change, newest on top, grouped by titled
  sections with date; incident entries name symptom AND root cause (house style:
  read the 2026-07-06 sections as templates).
- `docs/PROJECT_OVERVIEW.md` — the living operational doc; update when
  architecture, ports, sync modes, codec strategy, or runbooks change.
- `.agents/skills/*` — each skill ends with re-verification one-liners; when your
  change invalidates a skill fact, fix the skill IN THE SAME commit.
- `GEMINI.md` — stale legacy manifest; do not extend it (see ksync-code-hygiene).

## Pre-merge checklist (copy-paste)

```
[ ] tests: python3 -m unittest discover -s tests  -> OK
[ ] class-specific gates above satisfied
[ ] CHANGELOG.md updated
[ ] no device ksync.ini staged (git status)
[ ] config keys whitelisted; UI cache-buster bumped if JS touched
[ ] docs/skills touched by this change updated in-commit
[ ] commit is single-theme and revertable
[ ] if risky: one Pi updated and booted BEFORE announcing fleet update
```

## Provenance and maintenance

Written 2026-07-06. Re-verify: incident hashes `git log --oneline | grep -E "b4e153c|dafdb91|5570b2d|bf53a41"` ·
test count `python3 -m unittest discover -s tests 2>&1 | tail -2` ·
whitelist name `grep -n CONFIG_ROLE_KEYS src/config/manager.py | head -1`
