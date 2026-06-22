# Changelog

## [Unreleased]

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
