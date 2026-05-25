# Raspberry Pi OS Setup

This project now assumes a Raspberry Pi 5 style deployment path built around X11, Openbox, and GStreamer.

## Base Image

Use Raspberry Pi OS Lite (64-bit), then enable:
- SSH
- a normal user account
- console autologin if this node is appliance-only

## Install kSync

```bash
git clone https://github.com/prismspecs/kitchenSync.git
cd kitchenSync
./setup.sh
sudo reboot
```

## Universal Node Boot Sequence

Upon reboot, the Pi will automatically:
1.  **Initialize Graphics**: Launch X11 and Openbox (via `tools/start_x.sh`).
2.  **Universal Startup**: Run `kitchensync.py`.
3.  **Role Detection**:
    *   **USB Check**: Search for `ksync.ini` at the root of any attached USB drive.
    *   **Fallback**: Check for local `./ksync.ini`.
    *   **Bystander Mode**: If no config is found, the node enters **Bystander Mode**, remaining idle but discoverable via the Remote Controller Web UI.

## Manual Operation (Optional)

While the system is automated, you can still run components manually for debugging:

```bash
source .venv/bin/activate
# Start as Leader
DISPLAY=:0 python3 leader.py --auto
# Start as Collaborator
DISPLAY=:0 python3 collaborator.py
```

## Remote Provisioning

If a node starts in **Bystander Mode**, it will appear in the Remote Controller Web UI. You can then:
1.  Upload video content to the node.
2.  Push a new `ksync.ini` configuration.
3.  The node will automatically restart and assume the assigned role.

## Hardware Acceleration Verification

The repo is configured to prefer hardware-oriented sinks, but full verification must happen on the actual Pi.

For Pi 5 HEVC hardware decode, use this exact order:

```bash
sudo reboot
cd ~/kitchenSync
./tools/start_x.sh
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,pix_fmt,width,height -of json videos/test265.mp4
DISPLAY=:0 XDG_SESSION_TYPE=x11 python3 tools/verify_gst_hwaccel.py --video videos/test265.mp4 --json
```

Expected success indicators:
- `video_stream.codec_name` is `hevc`
- `selected_sink` is `glimagesink` or another hardware-preferred sink
- `playback_progress_ok` is `true`
- `active_decoder` is `v4l2slh265dec`

If `video_stream.codec_name` is not `hevc`, the file on the Pi is not the HEVC sample you intended to test, regardless of its filename.

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
