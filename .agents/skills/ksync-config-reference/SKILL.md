---
name: ksync-config-reference
description: >
  Complete catalog of every kSync configuration key (type, default, who reads it,
  role, UI-editable, production vs special-purpose), the unified single-section
  config model, and the mandatory add-a-key checklist. Load this when reading or
  editing any ksync.ini, adding/renaming a config key, debugging "my setting was
  ignored/disappeared", or wiring a new option into the web UI.
---

# kSync Config Reference

Facts verified against `src/config/manager.py` and call sites, 2026-07-06.

When NOT to use: what a sync parameter *means* mathematically →
`ksync-sync-theory-reference`; whether a change is allowed → `ksync-change-control`.

## The model (unified since 2026-07-06, commit 20bc1d9)

- One file per device: `~/kitchenSync/ksync.ini`, **untracked in git** (tracked copies
  would collide with device-local files and break fleet `git pull`). Repo mirrors for
  reference only: `ksync.ini` (leader), `ksync_collaborator.ini`, `ksync_webui.ini`.
- A `ksync.ini` at a USB stick's root **overrides** the local file at boot
  (kitchensync.py → USBConfigLoader).
- **Every key lives in the single `[KITCHENSYNC]` section.** A legacy `[DEFAULT]`
  section is still read as fallback and stripped on the first save. Never reintroduce
  two sections: configparser resolves a section's own key before [DEFAULT], and a
  stale duplicate silently shadows edits forever (the wrong-video incident,
  archaeology E10/E11).
- Web-UI saves rewrite the file from the whitelist: any key NOT in
  `CONFIG_ROLE_KEYS[role]` is **silently deleted on save** (this once killed
  `enable_deviation_log` and the deviation CSV with it).

## Key catalog

Legend: role L=leader, C=collaborator, W=web-UI node, D=driver. UI = editable in web
UI config panel. Status: prod = normal use; special = dangerous/special-purpose;
dormant = feature currently off in production.

| Key | Type (default) | Read by | Roles | UI | Status / notes |
|---|---|---|---|---|---|
| role | choice (bystander if absent) | kitchensync.py, manager.role_name | all | yes | prod. Changing it execv-restarts the node |
| device_id | str (hardware-derived `pi-<serial>`) | everywhere | all | yes | prod. Stable IDs from hardware serial |
| video_file | str ("video.mp4") | file discovery; collaborator's own value OVERRIDES leader broadcast | all | yes (dropdown) | prod. Per-device codec strategy depends on the override |
| video_driver | str ("gst") | get_video_driver | all | no | prod. "gst" or "mock"; VLC removed |
| schedule_file | str ("schedule.json") | leader Schedule() | L | yes | dormant (MIDI cue timeline) |
| sync_mode | choice ("udp") | leader, collaborator, gst driver | L,C | yes | prod. MUST match on all nodes; mismatch degrades to udp via fallback |
| sync_port | int (5005) | SyncBroadcaster/Receiver | L,C | no | prod |
| tick_interval | float (0.02; ini ships 0.05) | SyncBroadcaster | L | yes | prod. Clamped [0.02, 5.0] |
| sync_peer_ip | str ("") | leader start_system | L | yes | **special**: sets unicast target and DISABLES broadcast. Direct cable only; must be the COLLABORATOR's IP. Self-IP is detected and refused (ebb773a) |
| max_drift | float (0.15) | collaborator accurate-seek threshold | C | yes | prod |
| min_drift | float (0.005) | collaborator deadband | C | yes | prod |
| kp | float (2.0) | collaborator P-gain | C | yes | prod. High values oscillate (see theory skill) |
| min_rate / max_rate | float (0.9 / 1.2) | collaborator rate clamp | C | yes | prod |
| max_samples | int (3) | collaborator median filter | C | yes | prod. (Was hardcoded 3 ignoring config until 2026-07-07; defaults aligned to 3 everywhere) |
| netclock_port | int (9997) | leader start cmd, gst driver NetTimeProvider, collaborator | L,C,D | no | prod (netclock mode) |
| netclock_max_drift | float (0.5) | collaborator watchdog guard | C | no | prod (netclock mode) |
| video_offset | float (0.0) | collaborator comparison + driver netclock align | C,D | yes (Advanced) | prod. Seconds; positive DELAYS this device. For display-latency deltas only |
| enable_latency_compensation | bool (true) | collaborator tick adjustment | C | yes (Advanced) | prod (udp mode) |
| enable_deviation_log | bool (true) | collaborator CSV writer | C | yes (Advanced) | prod. THE diagnostic; leave on |
| position_poll_interval | float (0.05) | gst driver poll thread | all | yes (Advanced) | prod |
| video_width / video_height | int (0/0) | gst driver sink caps | all | yes (Advanced) | 0 = native |
| crop_mode | choice ("letterbox") | gst driver sink | all | yes | prod ("letterbox"/"crop-to-fill") |
| overlay | bool (false) | debug overlay | all | yes | fragile historically (archaeology E2) |
| enable_audio | bool (true; ini ships false) | gst driver flags | all | yes | prod. false → fakesink audio + flag stripped |
| audio_output | choice ("hdmi") | setup/audio routing | L,C | yes | prod |
| enable_midi | bool (property default TRUE; ini ships false) | leader+collaborator init | L,C | yes (L) | dormant. ⚠ default-true property vs shipped-false ini — set explicitly |
| enable_osc | bool (false) | collaborator init only | C | no | dormant. OscHandler is instantiated but never fed |
| midi_port | int (0) | collaborator MidiManager | C | yes (Advanced) | dormant |
| enable_caching | bool (false) | collaborator file resolution | C | yes (Advanced) | backlog feature |
| enable_system_logging | bool (false) | logger verbosity | all | yes (Advanced-ish) | prod |
| remote_sync_mode | choice ("http") | collaborator media pull | C,W | yes (Advanced) | "http" or "rsync" |
| emulated_render_lag | float (0.05) | web UI state only | W | yes | UI preview offset, not device playback |
| latency_factor | float (0.5) | web UI compensation display | W | no | W-only |
| usb_mount_point | str (auto) | file manager | all | no | written by boot persistence, not hand-set |

## Add-a-key checklist (skipping ANY step has bitten before)

1. Property accessor in `src/config/manager.py` with the code default.
2. Add to `CONFIG_ROLE_KEYS` for every role that may save it — **else every web-UI
   save silently deletes it** (dafdb91 incident).
3. UI-editable? Add an entry to `EDITABLE_CONFIG_FIELDS[role]` (type/label/min/max/
   step/tooltip).
4. Advanced-section placement? Add the key to `ADVANCED_KEYS` in
   `src/remote/templates/static/js/remote.js`.
5. Any remote.js change: bump the version log line AND the cache-buster in
   `src/remote/templates/index.html` (`remote.js?v=N`).
6. Update the repo mirrors (`ksync.ini`, `ksync_collaborator.ini`) if the key ships
   with a non-default value.
7. Test: extend tests (MockConfig in tests/test_sync_simulation.py has
   getint/getfloat passthroughs) and run `python3 -m unittest discover -s tests`.
8. Document: CHANGELOG.md entry; this catalog.

## Reading config in code

Use `self.config.<property>` where a property exists; raw
`self.config.getfloat("key", default)` otherwise. Keep the code default identical to
the EDITABLE_CONFIG_FIELDS default — the max_samples 10-vs-3 mismatch is the
cautionary example.

## Provenance and maintenance

Written 2026-07-06 (commit 608864e era). Re-verify:

- Regenerate property list: `grep -n "def .*: return self.get" src/config/manager.py`
- Regenerate raw reads: `grep -rn "getint(\|getfloat(\|getboolean(" *.py src/ | grep -v manager.py | grep -o '"[a-z_]*"' | sort -u`
- Whitelists: `grep -n "CONFIG_ROLE_KEYS" -A 20 src/config/manager.py`
- sync_params stays removed: `grep -rn '"sync_params"' leader.py collaborator.py` (expect no matches)
- remote.js version: `grep -n "remote.js?v=" src/remote/templates/index.html`
