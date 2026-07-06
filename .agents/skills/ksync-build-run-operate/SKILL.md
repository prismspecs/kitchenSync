---
name: ksync-build-run-operate
description: >
  Recreate a kSync node from scratch and operate the system: Pi bring-up with
  setup.sh, systemd service anatomy, manual debug runs over SSH, X11 startup, USB
  provisioning conventions, web UI operations, fleet update/rollback, and where every
  log/artifact lands. Load this for new-device setup, boot failures, service
  management, running components by hand, or deployment questions.
---

# kSync Build, Run, Operate

Verified against setup.sh, tools/start_x.sh, restart.sh, kitchensync.py and
docs/INSTALLATION.md on 2026-07-06.

When NOT to use: sync misbehavior → `ksync-debugging-playbook`; encoding content →
`ksync-media-encoding-reference`; config keys → `ksync-config-reference`.

## Fresh Pi bring-up (the only supported path)

1. Flash Raspberry Pi OS **Lite 64-bit**; enable SSH, a normal user, console autologin.
2. ```bash
   git clone https://github.com/prismspecs/kitchenSync.git
   cd kitchenSync
   ./setup.sh
   sudo reboot
   ```
3. `setup.sh` (idempotent, `set -e`) does, in order: apt installs (X11/openbox +
   GStreamer base/good/bad/libav + python3-gst + gir bindings + unclutter wmctrl
   v4l-utils); X permissions (video/render/tty groups, Xwrapper `allowed_users=anybody`
   + `needs_root_rights=yes`); Pi 5 Xorg mapping (`/etc/X11/xorg.conf.d/99-vc4.conf`
   forcing `/dev/dri/card1`); Openbox borderless/fullscreen rule; unclutter autostart;
   `.venv` with `--system-site-packages` (so GStreamer gi bindings from apt are
   visible) + pip installs `mido pyserial python-osc`; **generates and enables the
   systemd service itself** (see next section); passwordless sudo for
   reboot/shutdown/systemctl (`/etc/sudoers.d/ksync-reboot`) — required by the remote
   Update & Reboot flow.
4. After reboot the node self-configures: USB `ksync.ini` at drive root wins → local
   `./ksync.ini` → otherwise **Bystander mode** (idle, discoverable in the web UI).

Trap: `python3-gst-1.0` and the gir packages come from apt, not pip — a venv without
`--system-site-packages` cannot import `gi` and the driver dies at import.

## The systemd service — trust setup.sh, not the tracked file

`setup.sh` writes `/etc/systemd/system/kitchensync.service` with the CURRENT user,
paths, and `.venv` python, `ExecStartPre=tools/start_x.sh`, `Restart=always`.

⚠ The `kitchensync.service` file **tracked in the repo is a stale artifact** from the
browser-overlay era (references `/home/gsync/ks-env`, Firefox/MOZ_* environment
variables, `Requires=display-manager.service`). Do not install it by hand; it is a
cleanup candidate. (Noted 2026-07-06.)

Service management:
```bash
sudo systemctl status kitchensync.service
sudo systemctl restart kitchensync.service
journalctl -u kitchensync.service -f          # live logs
```

## Running by hand (SSH debugging)

```bash
cd ~/kitchenSync
sudo systemctl stop kitchensync.service       # get the service out of the way
./tools/start_x.sh                            # as the normal user, NEVER sudo (root-owned X breaks GStreamer auth)
.venv/bin/python kitchensync.py               # full boot flow, or:
.venv/bin/python leader.py --auto --config ksync.ini --debug
.venv/bin/python collaborator.py --config ksync.ini --debug
```
Flags (verified argparse): leader.py `--config/--debug/--auto` (no `--auto` = an
interactive CLI with start/stop/status/set); collaborator.py `--config/--debug`.

`restart.sh` = git pull + service restart + last 10 journal lines. The web UI's
"Update & Reboot" sends `device_update` → the device runs `git pull` + reboot —
**this is why main must always boot**: a broken main bricks the fleet's update path
(rollback = push a revert commit to main, then Update & Reboot again).

## Web UI operations

Runs on any machine on the show LAN: `python3 src/remote/controller.py` (config:
`ksync_webui.ini`), port 8080. Capabilities: Play/Stop cluster, per-device config
editor (devices restart after saving), **Load** per video (sets that device's
video_file + restarts playback), media upload, logs viewer, Update & Reboot.

Upload is TWO-HOP: file lands in the UI host's `media/` first, then the target device
pulls it over HTTP in the background — failure shows only in the device log
(`Download failed`). For large files prefer:
```bash
scp video.mp4 gsync@<device-ip>:~/kitchenSync/media/
```

## USB conventions

- `ksync.ini` at USB root: overrides local config at boot (provisioning path).
- Video files on USB are discovered by the file manager (USB outranks local media/).
- `upgrade/<anything>.zip` on USB (or in the repo dir): applied at boot by
  kitchensync.py `apply_upgrade_if_available` — replaces the whole tree except
  upgrade/.git/.gitignore/media/logs. Powerful and blunt; prefer git.

## Where things land

| Artifact | Path |
|---|---|
| Main log | `~/kitchenSync/logs/kitchensync.log` |
| Sync instrument | `~/kitchenSync/logs/sync_deviation.csv` |
| Import/boot crashes | `~/kitchenSync/logs/startup_crash.log` |
| Service stdout | `journalctl -u kitchensync.service` |
| X startup log (manual) | `/tmp/xstart.log` |
| Media | `~/kitchenSync/media/` (2.5 GB locally; NOT in git) |
| Device config | `~/kitchenSync/ksync.ini` (NOT in git) |

## Network requirements

One L2 subnet for all nodes + web UI host; UDP broadcast must work. Ports: 5005/udp
ticks, 5006/udp commands, 9997/udp netclock, 8080/tcp UI. Dual-NIC Pis are
ambiguity bombs — for wired tests: `sudo ip link set wlan0 down`.
`tools/ntp-setup.sh` and `tools/reset-network.sh` are chrony-era artifacts — sync does
NOT need them (see ksync-failure-archaeology E7).

## Provenance and maintenance

Written 2026-07-06. Re-verify:
- setup.sh package list / service template: `grep -n "apt install\|tee /etc/systemd" setup.sh`
- Tracked-service staleness still true: `grep -c MOZ kitchensync.service` (nonzero = still stale)
- Entry flags: `grep -n "add_argument" leader.py collaborator.py`
- Upgrade path: `grep -n "apply_upgrade_if_available" kitchensync.py`
