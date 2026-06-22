# kSync

kSync is a Raspberry Pi video-sync system for synchronized playback and protocol output (MIDI, OSC) across leader and collaborator nodes.

The active stack is:
- **GStreamer** for high-performance video playback
- **Openbox/X11** for the display session
- **UDP Broadcast** for time sync and cluster control
- **USB-driven** configuration and media discovery
- **MIDI/OSC** synchronized protocol output

## Current Project Structure

- `kitchensync.py`: Main boot-time entry point (handles USB mounting and role detection).
- `leader.py`: Leader runtime (broadcasts time, manages schedule).
- `collaborator.py`: Collaborator runtime (receives sync, adjusts playback speed).
- `setup.sh`: Primary Raspberry Pi setup and provisioning script.
- `src/`: Core implementation modules (networking, video, protocols, etc.).
- `src/remote/`: Web-based remote controller and schedule editor.
- `docs/`: Detailed guides for installation, testing, and MIDI control.
- `arduino/`: Firmware for Arduino-based MIDI relay control.
- `code_archive/`: Legacy scripts and tools for reference.

## Quick Start

### 1. Installation
```bash
git clone https://github.com/prismspecs/kitchenSync.git
cd kitchenSync
./setup.sh
sudo reboot
```

After reboot, the `kitchensync.service` launches `kitchensync.py`, which detects USB configuration and starts either `leader.py` or `collaborator.py`.

### 2. Manual Execution (For Debugging)

If you are testing from SSH or a text console, ensure the local X session is running:
```bash
./tools/start_x.sh
```

**Run Leader:**
```bash
./.venv/bin/python3 leader.py --config ksync_webui.ini --debug
```

**Run Collaborator:**
```bash
DISPLAY=:0 ./.venv/bin/python3 collaborator.py --config collaborator_config.ini --debug
```

**Run Remote Controller:**
```bash
./.venv/bin/python3 src/remote/controller.py
```
Available at `http://<pi-ip>:8080`

## Documentation

- [Installation Guide](docs/INSTALLATION.md) - OS setup and provisioning.
- [Testing Guide](docs/TESTING.md) - Manual and automated testing procedures.
- [MIDI Control Guide](docs/MIDI_CONTROL.md) - Using MIDI for relay and show control.
- [Project Roadmap](docs/ROADMAP.md) - Future enhancements and architecture goals.

## USB Drive Layout

The system is designed for "plug-and-play" operation using USB drives.

**Leader USB:**
```text
kitchensync.ini
test_video.mp4
schedule.json # optional, needed for sending MIDI, DMX, (etc.) data
desktop-background.png   # optional
```

**Collaborator USB:**
```text
kitchensync.ini
collaborator_video.mp4   # can be different from leader
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

## Remote Control & Monitoring

kSync includes a web-based remote controller for cluster management:

```bash
python3 src/remote/controller.py
```
Available at `http://<pi-ip>:8080`

## Hardware Acceleration (Pi 5)

kSync prefers hardware-accelerated GStreamer sinks:
- **X11/Openbox**: `glimagesink`
- **KMS/DRM**: `kmssink`

To verify HEVC hardware decoding on a Pi 5:
```bash
DISPLAY=:0 python3 tools/verify_gst_hwaccel.py --video videos/bbb_1080p_24fps_hevc.mp4 --json
```

Successful decode signal: `"active_decoder": "v4l2slh265dec"`

## Looping Behavior

Leader and collaborator both loop locally inside the GStreamer driver when they receive EOS. At the loop seam, raw positions can briefly jump from `duration` back to `0`, so sync logic must treat that boundary as wrapped time rather than linear drift.

Current behavior:
- The Gst driver resets its cached position to `0` before issuing the EOS loop seek so leader broadcasts do not keep advertising a stale tail-frame timestamp.
- The collaborator normalizes loop-boundary drift against video duration, which prevents false multi-second deviation spikes and unnecessary hard seeks immediately after looping.

## Testing

Run the automated test suite:
```bash
python3 -m unittest tests/test_core.py
python3 -m unittest tests/test_networking.py
python3 -m unittest tests/test_sync_regressions.py
pytest tests/test_sync_regressions.py tests/test_sync_simulation.py
```

If you need a sample file for manual testing, download a test video into `videos/`:
```bash
mkdir -p videos
wget -O videos/bbb_1080p_24fps_h264.mov https://download.blender.org/peach/bigbuckbunny_movies/big_buck_bunny_1080p_h264.mov
```

For distributed manual testing, use the commands in [docs/TESTING.md](docs/TESTING.md).
