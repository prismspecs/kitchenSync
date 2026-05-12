# KitchenSync

KitchenSync is a Raspberry Pi video-sync system for synchronized playback and protocol output across leader and collaborator nodes.

The active stack is:
- GStreamer for video playback
- Openbox/X11 for the display session
- UDP broadcast for sync and control
- USB-driven configuration and media discovery
- Optional MIDI and OSC output

## Current Runtime Layout

- `kitchensync.py`: boot-time entry point used by `kitchensync.service`
- `leader.py`: leader runtime started by `kitchensync.py`
- `collaborator.py`: collaborator runtime started by `kitchensync.py`
- `setup_pi5.sh`: primary Raspberry Pi setup script
- `setup.sh`: compatibility wrapper that delegates to `setup_pi5.sh`

## Quick Start

```bash
git clone https://github.com/prismspecs/kitchenSync.git
cd kitchenSync
./setup.sh
sudo reboot
```

After reboot, the system service launches `kitchensync.py`, which detects USB configuration and execs either `leader.py` or `collaborator.py`.

If you are testing from SSH on a text console, start the local X session before any `DISPLAY=:0` command:

```bash
./tools/start_x.sh
```

## USB Layout

Leader USB:

```text
kitchensync.ini
test_video.mp4
schedule.json
desktop-background.png   # optional
```

Collaborator USB:

```text
kitchensync.ini
collaborator_video.mp4
```

Example `kitchensync.ini`:

```ini
[KITCHENSYNC]
is_leader = true
device_id = leader-pi
debug = false
video_file = test_video.mp4
video_driver = gst
```

## Manual Operation

```bash
python3 kitchensync.py
python3 leader.py --config leader_config.ini --debug
DISPLAY=:0 python3 collaborator.py --config collaborator_config.ini --debug
```

## Hardware Acceleration

KitchenSync now prefers explicit GStreamer sinks instead of leaving sink choice entirely to `autovideosink`.

- With X11/Openbox, it prefers `glimagesink`, then `xvimagesink`
- Without X11, it prefers `kmssink`
- Only if those are unavailable does it fall back to `autovideosink`

What can be verified from the repo:
- The setup path configures X11/Openbox on Pi 5
- The GStreamer driver prefers hardware-oriented sinks
- Pi 5 Xorg is pinned to `/dev/dri/card1`

What still requires runtime verification on the actual Pi:
- Which sink GStreamer actually instantiated on that machine
- Whether the active sink is using GPU/display hardware exactly as intended
- Whether HEVC playback is using the Pi 5 stateless hardware decoder `v4l2slh265dec`

For Pi 5 HEVC verification, the intended sequence is:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo rpi-eeprom-update -a
sudo reboot
cd ~/kitchenSync
./tools/start_x.sh
DISPLAY=:0 XDG_SESSION_TYPE=x11 python3 tools/verify_gst_hwaccel.py --video videos/test265.mp4 --json
```

The successful HEVC decode signal is `"active_decoder": "v4l2slh265dec"`.

At runtime, check the logs for a line like:

```text
Gst: Using hardware-preferred video sink 'glimagesink'
```

If the log says fallback sink or `autovideosink`, acceleration is not fully confirmed.

## Project Structure

```text
src/                 Core implementation
docs/                Setup and testing docs
tests/               Automated regression and logic tests
tools/               Simulator and helper tools
arduino/             Active Arduino sketch
code_archive/        Archived legacy and uncertain files
```

## Testing

```bash
python3 -m unittest tests.test_core
python3 -m unittest tests.test_networking
python3 -m unittest tests.test_sync_regressions
```

For distributed manual testing, use the commands in `docs/TESTING.md`.