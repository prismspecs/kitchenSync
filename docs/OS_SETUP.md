# Raspberry Pi OS Setup & Provisioning

This document outlines the "Appliance Mode" setup for KitchenSync nodes. This configuration uses a minimal OS footprint to ensure maximum stability for video synchronization and protocol timing.

## 1. Base OS Installation
1. Download **Raspberry Pi OS Lite (64-bit)** using the Raspberry Pi Imager.
2. Before flashing, use the **OS Customization** settings:
   - Set hostname: `gSync`.
   - Enable SSH.
   - Set user/password: `gsync`.
   - Configure Wi-Fi if needed (Wired is recommended for sync).
3. Flash the SD card and boot the Pi.

## 2. Initial System Configuration
Run these commands on the first boot:

```bash
# Enter configuration tool
sudo raspi-config
```
**Required Settings:**
- **System Options -> Boot / Auto Login:** Select `Console Autologin`.
- **Localisation Options -> WLAN Country:** Select your country (Critical for enabling the Wi-Fi radio).
- **Advanced Options -> Expand Filesystem:** Ensure you are using the full SD card.
- **Update:** Run the update tool within raspi-config.

## 3. Automated Setup
Once the Pi is booted and connected to the internet, run the following to install the required graphics stack and auto-mounting utilities:

```bash
# Update and install core dependencies
sudo apt update
sudo apt install -y --no-install-recommends \
    xserver-xorg xinit openbox x11-xserver-utils xserver-xorg-legacy \
    udevil firefox-esr vlc libvlc-dev python3-vlc \
    python3-pip python3-dev python3-full \
    alsa-utils libasound2-dev libdbus-1-dev libglib2.0-dev libgl1-mesa-dri \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-libav \
    gstreamer1.0-tools python3-gst-1.0 gir1.2-gst-plugins-base-1.0

# 3.1 Raspberry Pi 5 Specific Configuration
On Raspberry Pi 5, the X server requires specific configuration to identify the correct display controller and permissions.

**X Server Permissions:**
```bash
echo "allowed_users=anybody" | sudo tee /etc/X11/Xwrapper.config
echo "needs_root_rights=yes" | sudo tee -a /etc/X11/Xwrapper.config
sudo usermod -a -G video,render,tty $USER
```

**Xorg Hardware Mapping:**
Create `/etc/X11/xorg.conf.d/99-vc4.conf`:
```text
Section "Device"
    Identifier "VC4"
    Driver "modesetting"
    Option "kmsdev" "/dev/dri/card1"
EndSection

Section "Screen"
    Identifier "Default Screen"
    Device "VC4"
EndSection
```

**GStreamer on Pi 5:**
Note that Pi 5 uses high-performance software decoding for H.264. Use the following pipeline for testing:
```bash
DISPLAY=:0 gst-launch-1.0 filesrc location=your_video.mp4 ! decodebin ! videoconvert ! glimagesink
```

# Enable auto-mounting service
# udevil provides devmon, which handles instant USB mounting to /media/
sudo systemctl enable devmon@$USER
```

## 4. KitchenSync Installation
```bash
git clone https://github.com/prismspecs/kitchenSync.git
cd kitchenSync

# Create a virtual environment with access to system-site-packages
# This allows the app to use hardware-optimized libraries (VLC, GStreamer) from apt
python3 -m venv --system-site-packages ~/ks-env

# Activate and install requirements
source ~/ks-env/bin/activate
pip install -r requirements.txt
```

## 5. Graphical Configuration (Openbox)
KitchenSync runs within a minimal Openbox session.

**Create the config directory:**
```bash
mkdir -p ~/.config/openbox
```

**Create/Edit `~/.config/openbox/autostart`:**
```bash
# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Start KitchenSync using the virtual environment interpreter
cd ~/kitchenSync && ~/ks-env/bin/python3 kitchensync.py
```

## 6. Service Configuration
Update `/etc/systemd/system/kitchensync.service` to use the venv.

**Example `/etc/systemd/system/kitchensync.service`:**
```ini
[Unit]
Description=KitchenSync Appliance
After=network.target

[Service]
User=gsync
WorkingDirectory=/home/gsync/kitchenSync
# Use the absolute path to the venv python interpreter
ExecStart=/usr/bin/startx /usr/bin/openbox-session
Restart=always

[Install]
WantedBy=multi-user.target
```

## 7. Running & Testing via SSH
When you are logged in via SSH, the system doesn't automatically know which screen to use. You must provide the `DISPLAY` variable.

### Start the Graphical Environment
If the Pi is sitting at a black console screen, you can trigger the graphics system manually:
```bash
# This starts X11 and Openbox on the local HDMI port
./tools/start_x.sh
```

### Run KitchenSync from SSH
Once the graphical environment is running on the Pi's HDMI port, you can launch the app from your SSH terminal:
```bash
# Ensure venv is active
source ~/ks-env/bin/activate

# Run with DISPLAY=:0 to project to the HDMI screen
DISPLAY=:0 python3 collaborator.py --debug
```

## 8. Performance Tuning
- **GPU Memory:** For Pi 4/5, ensure `dtoverlay=vc4-kms-v3d` is in `/boot/config.txt`.
- **Network:** Use a static IP or reserved DHCP for faster discovery.
- **USB:** High-speed USB 3.0 drives are recommended for high-bitrate video.

## 8. Test Media
To verify your installation, you can download a standardized H.264 test video:

```bash
mkdir -p ~/kitchenSync/videos
wget -O ~/kitchenSync/videos/test_video.mp4 https://download.blender.org/peach/bigbuckbunny_movies/big_buck_bunny_1080p_h264.mov
```
