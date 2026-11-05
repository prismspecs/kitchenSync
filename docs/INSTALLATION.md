# Raspberry Pi OS Setup

This project now assumes a Raspberry Pi 5 style deployment path built around X11, Openbox, and GStreamer.
x86 mini PCs running Debian 13 are experimental; see [Mini PC (x86) with Debian 13](#mini-pc-x86-with-debian-13).

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

## Mini PC (x86) with Debian 13

Experimental, first trialed 2026-11 on an ACEMAGICIAN K1 (AMD Ryzen 3 4300U).
AMD's hardware decoder handles **both H.264 and HEVC** (the Pi 5 has no
H.264 hardware decode). It has no AV1 hardware decode.

**BIOS first:** turn on "Restore on AC Power Loss" (the name varies) so the
PC boots when power is applied, like a Pi. Then boot the installer from USB.

**Installer** (`debian-13.x-amd64-netinst.iso`, ethernet plugged in):
- **Root password: leave it blank.** Your user then gets `sudo`, which
  `setup.sh` needs.
- Partitioning: guided, use the entire disk. This erases the preinstalled Windows.
- Software selection: untick "Debian desktop environment" and "GNOME"; keep
  "SSH server" and "standard system utilities".

**Install kSync** (as your normal user):
```bash
sudo apt install -y git
git clone https://github.com/prismspecs/kitchenSync.git
cd kitchenSync
./setup.sh
sudo reboot
```

On a PC, `setup.sh` also does the following:
- installs what Raspberry Pi OS ships but a minimal Debian lacks (VA-API
  hardware decode, GStreamer GL/X sinks, NetworkManager, avahi, ffmpeg);
- turns on amdgpu TearFree and turns off screen blanking;
- auto-mounts USB sticks at `/media/usb-<name>`;
- hands the network from ifupdown to NetworkManager.

After the reboot the PC may get a new IP address; reach it as `<hostname>.local`.

**Verify hardware decode** after the reboot:
```bash
vainfo | grep -E "H264|HEVC"                 # expect VAProfileH264*/VAProfileHEVC* ... VAEntrypointVLD
gst-inspect-1.0 va | grep -E "vah26[45]dec"   # expect vah264dec and vah265dec
DISPLAY=:0 python3 tools/verify_gst_hwaccel.py --video videos/test265.mp4 --json   # active_decoder: vah265dec
```

The leader's hotspot depends on the WiFi chip supporting AP mode. If this
PC will be a leader without ethernet, test the hotspot early.

**Measured on the K1** (2026-11-05, 20 s test patterns on a 1080p60 HDMI screen):
- **1080p30 H.264 and HEVC, and 4K30 HEVC:** hardware decode, a solid 30 fps
  with 2 frames dropped at startup, and under half of one CPU core.
- **4K60:** decoding has headroom (103 fps HEVC and 166 fps H.264, with
  nothing displayed). Playback to the screen is not yet clean:
  - HEVC reached 59.5 fps with 7 drops in 1,200 frames, but only with the
    GPU forced to `high` (`power_dpm_force_performance_level`) and a video-only
    playbin (`flags=0x41`).
  - H.264 dropped 2–4% of frames.
  - kSync's own sink bin was not measured at 4K60, and neither was a real
    4K screen.
- **WiFi:** a Realtek RTL8821CE (`rtw88`) that supports AP mode.

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

## Network Setup

Full design and rationale: [WIFI_PROVISIONING.md](WIFI_PROVISIONING.md).
The nodes only need to reach each other (video is local; sync is small UDP
packets on one L2 network) — internet is never required.

### Option 1: Ethernet (most reliable)
Wire every Pi into the same router/switch. The boot sequence detects the
wired network and does nothing else.

### Option 2: kSync private WiFi (zero configuration)
If a node boots with no ethernet and no known WiFi:
- The **leader** hosts an access point: SSID `kSync-<cluster_name>`
  (default `kSync-ksync`), WPA2 password `kitchensync`.
- **Collaborators** search for that SSID and join automatically — at boot
  and continuously afterwards (NetworkManager keeps retrying, so boot order
  doesn't matter).

Nothing to configure. For multiple installations in one building, give each
its own `cluster_name` in `ksync.ini` (all nodes of a cluster must match;
same for a custom `hotspot_password`, minimum 8 characters).

### Option 3: Venue WiFi (optional, via the setup portal)
1. Join the `kSync-...` network with a phone (password `kitchensync`).
2. The setup page opens automatically; if not, visit `http://10.42.0.1`.
3. Pick the venue network from the list (or type it), enter its password,
   submit. The page shows how many devices confirmed; ~20 seconds later the
   whole cluster switches together.
4. If the venue WiFi fails (wrong password, network change, router down),
   the devices revert to the kSync private network by themselves within a
   few minutes — the system cannot be locked out by bad credentials.

You can also pre-provision venue WiFi with `wifi_ssid` / `wifi_password`
in the USB `ksync.ini`.

**Beware venue/guest WiFi limitations:** many institutional networks
isolate clients from each other or block UDP broadcast, which silently
breaks sync. kSync detects this (leader connected, collaborators
unreachable) and falls back to its private network. If you need WiFi *and*
internet reliably, a small travel router (GL.iNet-class, ~$30) is the
robust answer: the cluster treats it as ordinary known WiFi and it adds
ethernet ports.

**Pi radio limits:** the leader's hotspot is 2.4 GHz and comfortably
handles ~10 collaborators of sync traffic, but range through gallery walls
is modest — for large spaces prefer ethernet or the travel router.

To disable all of this (e.g. on a dev machine), set the environment
variable `KSYNC_NO_NETWORK_BOOTSTRAP=1`.

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
