# kSync — Resident Context

This is the canonical entry point for any coding agent working in this repo
(Claude Code, Pi, Gemini, or otherwise). Keep this file itself short — it is
loaded on every turn. Project knowledge belongs in the files it points to,
not here.

kSync is a Raspberry Pi video-sync system for synchronized playback and
protocol output (MIDI, OSC) across leader/collaborator/bystander nodes over
UDP. Stack: GStreamer, Openbox/X11, USB-driven config, netclock-based sync.

## Where things live

- **`docs/PROJECT_OVERVIEW.md`** — architecture, sync modes, ports, config
  model, diagnostics runbook. Read this first for orientation.
- **`.agents/skills/`** — the project's skill library (16 skills). Each
  `SKILL.md` says in its own description when to load it. Start with
  `ksync-architecture-contract`, `ksync-debugging-playbook`, and
  `ksync-change-control` before doing anything nontrivial.
- **`CHANGELOG.md`** — what changed and why, newest first.
- **`TODO.md`** — open work; the active technical campaign is
  `.agents/skills/ksync-sub10ms-campaign`.
- **`docs/CLEANUP_REPORT.md`** — tracked cleanup/dead-code items.

## Subagent personas

`.agents/agents/*.md` (8 files) are thin role definitions that point into the
skill library above (D1 cleanup, done 2026-09-23) — treat the skill they point
to as authoritative, not the persona file, if they ever disagree.

## Non-negotiables (see `ksync-change-control` for the full list + incidents)

- One theme per commit; tests green before committing.
- Boot-test on one Pi before a fleet-wide pull for anything touching sync,
  config schema, or the web UI.
- Before deleting anything, check `ksync-code-hygiene`'s suspect inventory —
  code that looks dead here has repeatedly turned out to be load-bearing.

## Quick commands

```bash
python3 -m unittest tests/test_core.py tests/test_networking.py tests/test_sync_regressions.py
pytest tests/test_sync_regressions.py tests/test_sync_simulation.py
```

Full run/deploy instructions: `README.md` and `.agents/skills/ksync-build-run-operate`.
