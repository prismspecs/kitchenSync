# Raspberry Pi OS Setup

This project now assumes a Raspberry Pi 5 style deployment path built around X11, Openbox, and GStreamer.

## Base Image

Use Raspberry Pi OS Lite (64-bit), then enable:
- SSH
- a normal user account
- console autologin if this node is appliance-only

## Install KitchenSync

```bash
git clone https://github.com/prismspecs/kitchenSync.git
cd kitchenSync
./setup.sh
sudo reboot
```

`setup.sh` is a compatibility wrapper. The real provisioning logic lives in `setup_pi5.sh`.

`setup_pi5.sh` now also:
- runs `apt full-upgrade`
- installs `v4l-utils` for decoder/device inspection
- attempts `rpi-eeprom-update -a` when available

## What The Setup Configures

- X11 and Openbox
- Pi 5 Xorg mapping to `/dev/dri/card1`
- GStreamer runtime packages
- `v4l2-ctl` via `v4l-utils`
- `unclutter` for cursor hiding
- the `kitchensync.service` systemd unit

## Manual X11 Bring-Up

If the system is on a text console, start the local display stack:

```bash
./tools/start_x.sh
```

Do this before any manual `DISPLAY=:0` runtime command from SSH. Setting `DISPLAY=:0` without a running X server will not work.

## Manual Runtime Testing

```bash
source ~/ks-env/bin/activate
DISPLAY=:0 python3 collaborator.py --config collaborator_config.ini --debug
DISPLAY=:0 python3 leader.py --config leader_config.ini --debug
```

## Hardware Acceleration Verification

The repo is configured to prefer hardware-oriented sinks, but full verification must happen on the actual Pi.

For Pi 5 HEVC hardware decode, use this exact order:

```bash
sudo reboot
cd ~/kitchenSync
./tools/start_x.sh
DISPLAY=:0 XDG_SESSION_TYPE=x11 python3 tools/verify_gst_hwaccel.py --video videos/test265.mp4 --json
```

Expected success indicators:
- `selected_sink` is `glimagesink` or another hardware-preferred sink
- `playback_progress_ok` is `true`
- `active_decoder` is `v4l2slh265dec`

Expected runtime log examples:

```text
Gst: Using hardware-preferred video sink 'glimagesink'
Gst: Using hardware-preferred video sink 'kmssink'
```

If the runtime falls back to `autovideosink`, hardware acceleration is not fully confirmed.

For a direct GStreamer sanity check on the Pi:

```bash
DISPLAY=:0 gst-launch-1.0 filesrc location=videos/test_video.mp4 ! decodebin ! videoconvert ! glimagesink
```
