---
name: ksync-config-diff
description: >
  Audit kSync configuration changes before commit. Validates ksync.ini modifications
  against role-specific key constraints, detects port conflicts, flags dangerous
  parameter changes (sync tuning, role switches), and ensures CONFIG_ROLE_SECTIONS
  and EDITABLE_CONFIG_FIELDS stay in sync with actual config usage.
---

# kSync Config Change Auditor

Use this skill when:
- Modifying `ksync.ini`, `ksync_collaborator.ini`, or `ksync_webui.ini`
- Adding new config keys to `src/config/manager.py`
- Changing default values for sync parameters
- Reviewing PRs that touch configuration

## Audit Steps

### 1. Key Validity Check
For every config key being added or modified, verify it exists in **both**:
- `CONFIG_ROLE_SECTIONS` (line ~16 in `src/config/manager.py`) — determines which keys are persisted per role
- `EDITABLE_CONFIG_FIELDS` (line ~31 in `src/config/manager.py`) — determines which keys appear in the Web UI

A key in one but not the other is a bug:
- In `CONFIG_ROLE_SECTIONS` only → saved but invisible in Web UI
- In `EDITABLE_CONFIG_FIELDS` only → visible in Web UI but not persisted on save

### 2. Section Placement Check
kSync uses two INI sections:
- `[KITCHENSYNC]` — Role identity, feature toggles, display settings
- `[DEFAULT]` — Sync parameters, network settings, video settings

Rules:
- Keys that identify the node (role, device_id) → `KITCHENSYNC`
- Keys that control behavior (kp, max_drift, tick_interval) → `DEFAULT`
- Boolean feature toggles → `KITCHENSYNC`
- The `get()` method searches KITCHENSYNC first, then DEFAULT

### 3. Dangerous Parameter Ranges
Flag if any of these parameters are set outside safe ranges:

| Parameter | Safe Range | Risk |
|-----------|------------|------|
| `kp` | 0.5–5.0 | Oscillation or sluggish sync |
| `tick_interval` | 0.02–5.0 | CPU burn or sluggish sync |
| `max_drift` | 0.05–1.0 | Unnecessary seeks or drift tolerance |
| `min_drift` | 0.001–0.05 | Jitter sensitivity |
| `min_rate` | 0.8–0.99 | Visible slow-motion |
| `max_rate` | 1.01–1.5 | Audio pitch shift, visible speedup |
| `max_samples` | 1–10 | Slow convergence |
| `sync_port` | 1024–65535 | Privileged port or conflict |

### 4. Port Conflict Detection
Check that no two settings share the same port:
- `sync_port` (default 5005) — UDP time sync
- Control port (hardcoded 5006) — UDP commands
- Web UI port (hardcoded 8080) — HTTP server

### 5. Role Consistency
When `role` changes:
- `leader` → must have `video_file` and `schedule_file`
- `collaborator` → should have `device_id` (not `pi-unknown`)
- `bystander` → minimal config is fine

### 6. Cross-File Consistency
If the project has multiple config files, ensure:
- `ksync.ini` — production config (written by the system)
- `ksync_collaborator.ini` — example collaborator config
- `ksync_webui.ini` — Web UI standalone config
- All example configs use valid key names from `CONFIG_ROLE_SECTIONS`

## Output Format

```
✅ PASS: Key 'new_key' registered in CONFIG_ROLE_SECTIONS and EDITABLE_CONFIG_FIELDS
⚠️  WARN: kp=8.0 exceeds safe range (0.5–5.0) — risk of oscillation
❌ FAIL: Key 'new_key' in EDITABLE_CONFIG_FIELDS but missing from CONFIG_ROLE_SECTIONS
```
