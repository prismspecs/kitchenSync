# kSync — Context Pointer

This manifest was retired on 2026-07-07: it had drifted badly from reality (it still
described the udp P-controller as the only sync model, predating netclock and the
unified config).

Authoritative context now lives in:

- **`docs/PROJECT_OVERVIEW.md`** — architecture, sync modes, ports, runbooks (living doc).
- **`.agents/skills/`** — the full skill library: start with `ksync-architecture-contract`,
  `ksync-debugging-playbook`, and `ksync-change-control`.
- **`CHANGELOG.md`** — what changed and why, newest first.

Do not add project knowledge to this file.
