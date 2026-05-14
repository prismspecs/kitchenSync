# KitchenSync Deployment Checklist

Use this checklist when setting up a new Raspberry Pi node (Leader or Collaborator).

## 1. Hardware Selection
- [ ] **Raspberry Pi 4B or 5:** Highly recommended for GStreamer hardware acceleration.
- [ ] **High-speed MicroSD:** Class 10/UHS-I or better.
- [ ] **Power Supply:** Official Pi 5.1V 3A+ power supply.
- [ ] **Active Cooling:** Recommended for long-running video playback.

## 2. OS Installation & Base Config
- [ ] **Raspberry Pi OS Lite (64-bit):** Bookworm or Bullseye.
- [ ] **Enable SSH:** `sudo raspi-config` -> Interface Options.
- [ ] **Set Hostname:** `sudo raspi-config` -> System Options -> Hostname.
- [ ] **Memory Split:** `sudo raspi-config` -> Performance Options -> GPU Memory -> Set to `256` (Pi 4).
- [ ] **Update OS:** `sudo apt update && sudo apt upgrade -y`.

## 3. GStreamer & Video Dependencies
- [ ] **Install GStreamer:**
  ```bash
  sudo apt install -y gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
  gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl \
  gstreamer1.0-gtk3 libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
  ```
- [ ] **Verify HW Accel:**
  ```bash
  gst-inspect-1.0 | grep v4l2h264dec
  ```
  *Note: If this returns nothing, hardware H.264 decoding is not available.*

## 4. GUI & Window Management
- [ ] **Install X11 & Openbox:**
  ```bash
  sudo apt install -y xserver-xorg xinit openbox wmctrl unclutter
  ```
- [ ] **Configure Auto-Start:** Ensure `startx` launches on boot or via systemd.
- [ ] **Verify DISPLAY:** `echo $DISPLAY` should return `:0`.

## 5. Python Environment
- [ ] **Install Python Dev:** `sudo apt install -y python3-pip python3-venv python3-tk`.
- [ ] **Create Venv:** `python3 -m venv .venv`.
- [ ] **Install Requirements:** `source .venv/bin/activate && pip install -r requirements.txt`.

## 6. Project Configuration
- [ ] **Identify Role:** Edit `kitchensync.ini` on the USB drive or `leader_config.ini` / `collaborator_config.ini`.
- [ ] **Set Device ID:** Ensure every node has a unique `device_id`.
- [ ] **Configure Networking:** Ensure all nodes are on the same subnet (UDP 5005/5006).

## 7. Performance Hardening (Optional but Recommended)
- [ ] **Disable HDMI Audio:** If using I2S or USB audio.
- [ ] **Overclocking:** Only if 4K playback is required (Pi 4/5).
- [ ] **Static IP:** Configure via `/etc/dhcpcd.conf` or router reservation.

## 8. Verification
- [ ] **Run Sync Test:** `python3 tests/test_sync_simulation.py`.
- [ ] **Verify Sink:** Check debug overlay (Native or HTML) to ensure `glimagesink` or `kmssink` is active.
- [ ] **Check HW Accel:** Verify "HW Accel: ACTIVE" in the debug overlay.
