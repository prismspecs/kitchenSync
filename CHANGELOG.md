# Changelog

## [Unreleased]

### setup.sh: x86 Mini PC (Debian 13) Path (2026-11-05)

- `setup.sh` now detects the platform (`/proc/device-tree/model` says "Raspberry Pi" → `pi`, otherwise `pc`). The Pi path runs the same commands as before. The one shared addition, creating the `netdev` group if it is missing, does nothing on Pi OS.
- **PC path**, for a minimal Debian 13 install (first trial: ACEMAGICIAN K1, Ryzen 3 4300U):
  - **Packages** Pi OS ships but Debian lacks:
    - VA-API hardware decode (`mesa-va-drivers`, `vainfo`)
    - GStreamer GL/X/ALSA plugins and Mesa GL
    - the NetworkManager stack plus `polkitd`, `iptables` and `iw` (to check whether the WiFi chip supports AP mode)
    - `avahi-daemon`, `python3-venv` and `ffmpeg`
    - on AMD only, `xserver-xorg-video-amdgpu` and `firmware-amd-graphics`
  - **Display**: the Pi-only `99-vc4.conf` (which forces `/dev/dri/card1`) is not written, and is removed if present. AMD gets `TearFree`. Screen blanking/DPMS is turned off: Xorg's 10-minute idle blank otherwise fires during playback.
  - **NetworkManager permissions**: a polkit rule lets `netdev` manage NetworkManager. Debian's own rule only covers an active desktop session, so the kSync service could not create the hotspot.
  - **USB auto-mount**: a udev rule plus `systemd-mount` mounts sticks at `/media/usb-<name>`, where `USBConfigLoader` and `VideoFileManager` look. A minimal Debian mounts nothing by itself, which breaks USB provisioning.
  - **Network handover**: moves the network from the installer's ifupdown config to NetworkManager, which ignores interfaces listed in `/etc/network/interfaces`. WiFi credentials from the installer carry over, the original is backed up to `interfaces.ksync-bak`, and the change applies at the next reboot. The file is read with `sudo`: the installer makes it root-only when it holds a WiFi password, and an unprivileged read had silently skipped the whole step (found on the hardware).
- **Verified on the K1** (Debian 13.7, WiFi-only install):
  - `setup.sh` ran cleanly.
  - After the reboot the WiFi came back under NetworkManager, and X ran on amdgpu with TearFree.
  - kSync booted to bystander mode, and `vah264dec`/`vah265dec` were the active decoders.
  - 1080p30 and 4K30 played cleanly; 4K60 is not yet clean (numbers in `docs/INSTALLATION.md`).
- Docs:
  - `docs/INSTALLATION.md` gains a "Mini PC (x86) with Debian 13" section (BIOS, installer choices, decode verification, measured results). It's the single home for the details; the docs below point to it.
  - The PC was added to the PROJECT_OVERVIEW hardware table and to the codec matrix (`ksync-media-encoding-reference`).
  - An x86 section was added to `gstreamer-hwaccel-verify`, and the PC bring-up to `ksync-build-run-operate`.
  - Notes in ROADMAP A5, DEPLOYMENT_CHECKLIST and CLAUDE.md, plus the open follow-ups in TODO.md.

### NetClock Fallback, Video Offset, Leader HEVC Badge (2026-07-06)

- **netclock → udp fallback**: a collaborator configured for netclock whose net clock never establishes (leader in udp mode, port blocked) now falls back to the UDP rate controller with a one-time warning. Previously it sat ~1s off forever with rate pinned at 1.0 while the watchdog attempted ~14,000 futile realigns (the inflated hard-seek counter in sync_deviation.csv). Failed realigns now back off 2.5s and no longer increment the counter.
- **`video_offset`** (collaborator, Advanced): static per-device offset in seconds — positive delays the device relative to the leader. Applied in both udp comparison and the netclock join. This is the knob for display-chain latency differences between screens, the residual clock sync cannot see (e.g. device appears 30ms ahead → set 0.030).
- **Leader HEVC badge fixed**: `leader_announce` never included `is_optimized` and the web UI hardcoded it to False, so the leader always showed "Non-HEVC" regardless of the file.

### Unified Config — Single [KITCHENSYNC] Section (2026-07-06)

- Every config key now lives in one `[KITCHENSYNC]` section; the `[DEFAULT]`/`[KITCHENSYNC]` split is gone. The split caused a live-observed bug class: configparser resolves a section's own key before `[DEFAULT]`, so a stale duplicate (stamped at boot) shadowed every later edit — the pi5 kept playing `bbb_1080p_24fps_hevc.mp4` while `[DEFAULT]` said `sync_test_pi5_hevc.mp4`.
- All writers (`clean_and_save_config`, `update_local_config`, `set_param`) target the unified section and strip legacy `[DEFAULT]` duplicates; readers keep a `[DEFAULT]` fallback, so existing device files work unchanged and migrate on first save. `CONFIG_ROLE_SECTIONS` → flat `CONFIG_ROLE_KEYS`; `section` dropped from editable-field definitions.
- Repo config mirrors (`ksync.ini`, `ksync_collaborator.ini`, `ksync_webui.ini`) rewritten in the unified format.

### Web UI: Load Button, Leader Media List, Edit Stability (2026-07-06)

- **Load button** on every Available Videos entry: sets that file as the device's `video_file` and restarts playback (new `/api/media/load`; leader now restarts on video change like it does on role change).
- **Available Videos fixed for the Pi leader**: `leader.py` never registered a `file_list_request` handler (and the dead implementation used a hardcoded `leader-pi` id + broadcast reply); now registered, target-filtered, unicast reply. Frontend also auto-requests media for the Pi leader (was collaborators-only).
- **Edit stability**: the 1.5s refresh loop no longer re-renders while a config field is focused (edits were being clobbered mid-typing). After Save/Load the UI re-pulls the device's config at +4s/+9s so the panel shows what was actually persisted post-restart.
- **Deviation CSV restored**: `enable_deviation_log` (plus `netclock_max_drift`/`netclock_port`) were missing from the config-save whitelist, so ANY web-UI save silently stripped them from ksync.ini — that's why logs/sync_deviation.csv stopped appearing. Whitelisted, exposed as an Advanced toggle, and default flipped to true.

### Codec Detection & Per-Device Media Strategy (2026-07-06)

- Fixed `_discover_via_cli` in `file_manager.py`: it only understood the legacy `Video:` gst-discoverer output, so on modern GStreamer it parsed nothing, and the dotted `"h.265"` codec string failed the HEVC check — the same file showed **HEVC** on one Pi and **Non-HEVC** on another purely depending on which metadata fallback ran. Parser now handles `video #N: H.265 (...)` and strips dots before matching.
- Documented the per-device codec reality (Pi 5: HEVC HW only; Pi 4: H.264 HW always, HEVC HW only with `v4l2slh265dec`) plus ffmpeg recipes with 1s keyframe intervals in `docs/PROJECT_OVERVIEW.md`. Sparse default GOPs (~8s) made KEY_UNIT hard seeks land seconds off target — the observed 23-hard-seek divergence spiral.

### Leader Config Clobbering Fix (2026-07-06)

- **Critical**: `config_update`/`config_request` are sent with a `target_device_id` but also broadcast; the collaborator filtered by target, the leader did not. Editing a collaborator's config in the web UI therefore overwrote the leader's `ksync.ini` with the collaborator's entire config (`role = collaborator`, `device_id = pi4_1`, …), demoting the leader to a second collaborator on restart. Leader now ignores config messages addressed to other devices (`_message_targets_this_device`, same as collaborator). Regression tests added.

### Sync Investigation & NetClock Repair (2026-07-06)

Root-caused the constant ~1s collaborator lag (three compounding issues) and repaired the netclock path. Full write-up: `docs/PROJECT_OVERVIEW.md`.

- **Config**: `sync_mode` returned to `udp` on both device mirrors; `sync_peer_ip` removed — it was set to the **leader's own IP**, so sync ticks were unicast to ourselves with broadcast disabled and the collaborator received nothing.
- **Guard**: leader now detects a self-IP `sync_peer_ip`, logs an error, and falls back to broadcast. `SyncBroadcaster` send failures are rate-limit logged instead of silently swallowed.
- **NetClock join fixed** (`GstDriver._align_to_network_clock`): collaborator prerolls paused, seeks to where the leader will be 0.5s from now, and anchors `base_time` so that frame renders exactly then. Previously it shared base_time and started at position 0, relying on QoS frame-dropping that Pi decoders can't sustain — the source of the permanent startup lag.
- **NetClock watchdog**: `_maintain_video_sync` now runs in netclock mode too — deviation CSV + heartbeat `Dev` stay honest (they previously reported 0.000 forever) — and realigns via `GstDriver.netclock_realign()` when |median deviation| > `netclock_max_drift` (default 0.5s), recovering from leader seeks/EOS rebases.
- **Stale base_time race fixed**: `get_pipeline_base_time()` waits for pending seeks to settle (the gapless-loop SEGMENT seek redistributes base_time when it completes), and the leader re-reads base_time on every 30s start re-broadcast instead of caching the initial value.
- **fakesink fallback** now sets `sync=true` so headless pipelines stay clocked at realtime instead of free-running.
- Verified end-to-end with the real driver on desktop GStreamer 1.28: late join settles at +0.0ms; a deliberate 5s leader seek recovers to -0.1ms after one realign. Test suite extended (`test_netclock_watchdog`); 36/36 pass.

### Ethernet Direct-Cable Sync
- Added `sync_peer_ip` config field for leader (e.g. `10.0.0.2` for Pi 4's Ethernet IP).
- When set, leader sends sync packets via unicast over Ethernet (port 5005) instead of WiFi broadcast.
- Eliminates ~0.3ms ping jitter from WiFi for tighter sync.
- Collaborator receives unicast without changes (listener binds to all interfaces).
- To activate: configure `sync_peer_ip` on the leader, set static Ethernet IPs on both Pis (`/etc/dhcpcd.conf`), and restart.
- Also added `set_unicast_targets()` to `SyncBroadcaster` so future code can add more peers easily.

### Logger & Driver Diagnostics
- `_should_log` in `logger.py` now passes WARNING+ through always (was ERROR+). Warnings like "Falling back to mock driver" appear in the log without `--debug`.
- `video_driver_name` tracked dynamically (`"gst"`, `"mock"`, `"gst (fakesink)"`) on leader and collaborator.
- Driver name included in all heartbeats and discover responses.
- Web UI device card shows `Driver: gst / mock / gst (fakesink)`.

### Web UI Sync Diagnostics
- Collaborator tracks `_current_deviation` and `_current_playback_rate` in `_maintain_video_sync()`.
- Sent in heartbeats every 2s, displayed per-device as `Dev: -0.500s` and `Rate: 1.1250x`.
- Fixed display condition to show when value is `0` (was hiding falsy `0.0`).
- `Hard Seeks` counter displayed for all collaborators.

### Max Drift & Seek Threshold
- Default `max_drift` lowered from `0.5` to `0.3`.
- Comparison changed from `>` to `>=` so a deviation of exactly the threshold triggers a seek.
- Fixed the case where rate control (1.125x) was ineffective because the decoder couldn't sustain 33.75fps.

### Config Editor
- All numeric config fields now have `min`/`max` bounds and explicit `step` values.
- JS added `clampValue()` to enforce min/max on `onchange` events.
- `step="any"` replaced with field-appropriate steps (e.g. `0.01` for floats, `1` for ints).
- Prevents spinner buttons from going negative or past reasonable bounds.
- Config cache busted to `v13` (browser hard refresh required).

### Sync Source Fix (Fakesink)
- `SyncBroadcaster.is_wall_clock` flag added.
- When set (fakesink/mock), sync packets send `source: "wall"` regardless of time provider.
- Collaborator uses wall-clock time base (`now - _play_start_wall`) instead of hardware-decoded position, fixing ~400ms offset from pipeline delay.

### Device Update / Reboot
- `_handle_device_update` now tries 4 reboot methods: `reboot`, `/sbin/reboot`, `/usr/sbin/reboot`, `systemctl reboot`.
- Actual stderr from each attempt logged to file for diagnostics.
- Previous: only one `reboot` attempt with static error message.

### Cleanup
- Removed duplicate (dead) `_handle_config_request` method in `leader.py`.
- First implementation (flat fields + unicast) was overwritten by second implementation (editable fields + broadcast).
- Second implementation is the active one used by the web UI config panel.

### Persistent Ethernet IP Setup
Two Pis connected via direct Ethernet cable need static IPs. On each Pi, edit `/etc/dhcpcd.conf`:

**Pi 5** (leader, 10.0.0.1):
```
interface eth0
static ip_address=10.0.0.1/24
```

**Pi 4** (collaborator, 10.0.0.2):
```
interface eth0
static ip_address=10.0.0.2/24
```

Then reboot or `sudo systemctl restart dhcpcd`.

**Important:** The `sync_peer_ip` config field in `ksync_webui.ini` on the leader must be set to the collaborator's Ethernet IP (`10.0.0.2`). Without this, sync still uses WiFi broadcast.
