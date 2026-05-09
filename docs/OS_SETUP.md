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
    xserver-xorg xinit openbox x11-xserver-utils \
    udevil firefox-esr vlc libvlc-dev python3-vlc \
    python3-pip python3-dev python3-full \
    alsa-utils libasound2-dev libdbus-1-dev libglib2.0-dev libgl1-mesa-dri

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

Create/Edit `~/.config/openbox/autostart`:
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

## 7. Performance Tuning
- **GPU Memory:** For Pi 4/5, ensure `dtoverlay=vc4-kms-v3d` is in `/boot/config.txt`.
- **Network:** Use a static IP or reserved DHCP for faster discovery.
- **USB:** High-speed USB 3.0 drives are recommended for high-bitrate video.
