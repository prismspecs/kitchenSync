---
name: pi-deployment-check
description: >
  Validate Raspberry Pi deployment readiness for kSync. Checks hardware selection,
  OS configuration, GStreamer dependencies, Python environment, network settings,
  and performance hardening against the official deployment checklist.
---

# kSync Pi Deployment Readiness Validator

Use this skill when:
- Setting up a new Raspberry Pi node
- Troubleshooting boot or playback failures on hardware
- Reviewing changes to `setup.sh` or `kitchensync.service`
- Preparing a deployment for a show or installation

## Reference Document
The canonical checklist lives at: `docs/DEPLOYMENT_CHECKLIST.md`

## Validation Categories

### 1. Hardware Validation
```bash
# Check Pi model (should be 4B or 5)
cat /proc/device-tree/model

# Check memory (need 2GB minimum, 4GB recommended)
free -h

# Check GPU memory split (should be 256 for Pi 4)
vcgencmd get_mem gpu

# Check temperature (should be < 80°C under load)
vcgencmd measure_temp
```

### 2. OS Validation
```bash
# Check OS version (Bookworm or Bullseye, 64-bit)
cat /etc/os-release | grep PRETTY_NAME
uname -m  # Should be aarch64

# Check SSH is enabled
systemctl is-active ssh

# Check hostname is set (not default "raspberrypi")
hostname
```

### 3. GStreamer Validation
```bash
# Check GStreamer is installed
gst-inspect-1.0 --version

# Check H.264 hardware decoder (Pi 4/5)
gst-inspect-1.0 | grep v4l2h264dec

# Check H.265 hardware decoder (Pi 5 only)
gst-inspect-1.0 | grep v4l2slh265dec

# Check video sinks
gst-inspect-1.0 | grep -E '(glimagesink|kmssink|xvimagesink)'

# Run full verification
DISPLAY=:0 python3 tools/verify_gst_hwaccel.py --json
```

### 4. Display & Window Manager
```bash
# Check X11 is running
echo $DISPLAY  # Should be :0

# Check window manager
wmctrl -m 2>/dev/null && echo "wmctrl OK" || echo "wmctrl missing"

# Check mouse cursor hiding tool
which unclutter && echo "unclutter OK" || echo "unclutter missing"
```

### 5. Python Environment
```bash
# Check venv exists and has system packages
ls -la ~/ks-env/bin/python3

# Check GStreamer Python bindings
python3 -c "import gi; gi.require_version('Gst', '1.0'); print('GStreamer bindings OK')"

# Check requirements installed
source ~/ks-env/bin/activate && pip list | grep -E '(rtmidi|mido|pyserial|python-osc)'
```

### 6. Network Validation
```bash
# Check IP address (should be on same subnet as other nodes)
ip addr show | grep "inet "

# Check UDP ports are free
ss -ulnp | grep -E '(5005|5006|8080)'

# Check broadcast works
python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
s.sendto(b'test', ('255.255.255.255', 5005))
print('Broadcast OK')
s.close()
"
```

### 7. systemd Service
```bash
# Check service file exists
ls -la /etc/systemd/system/kitchensync.service

# Check service is enabled
systemctl is-enabled kitchensync

# Check service status
systemctl status kitchensync

# Check service logs
journalctl -u kitchensync -n 50 --no-pager
```

### 8. USB Drive Validation
```bash
# Check USB mount points
mount | grep /media/

# Check for ksync.ini on USB
find /media/ -maxdepth 3 -name "ksync.ini" 2>/dev/null

# Check for video files on USB
find /media/ -maxdepth 3 -iname "*.mp4" -o -iname "*.mov" -o -iname "*.mkv" 2>/dev/null
```

## Quick All-in-One Check Script

```bash
echo "=== kSync Deployment Check ==="
echo "Model: $(cat /proc/device-tree/model 2>/dev/null || echo 'Not a Pi')"
echo "OS: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2)"
echo "Arch: $(uname -m)"
echo "GPU Mem: $(vcgencmd get_mem gpu 2>/dev/null || echo 'N/A')"
echo "Temp: $(vcgencmd measure_temp 2>/dev/null || echo 'N/A')"
echo "Display: ${DISPLAY:-NOT SET}"
echo "GStreamer: $(gst-inspect-1.0 --version 2>/dev/null | head -1 || echo 'NOT INSTALLED')"
echo "H264 HW: $(gst-inspect-1.0 2>/dev/null | grep -c v4l2h264dec) decoder(s)"
echo "Python venv: $(ls ~/ks-env/bin/python3 2>/dev/null && echo 'OK' || echo 'MISSING')"
echo "Service: $(systemctl is-active kitchensync 2>/dev/null || echo 'NOT FOUND')"
echo "USB Config: $(find /media/ -maxdepth 3 -name 'ksync.ini' 2>/dev/null | head -1 || echo 'NONE')"
```

## Common Failure Modes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Black screen, no video | `DISPLAY` not set | Add `Environment=DISPLAY=:0` to service |
| Software decode only | GPU memory < 256MB | `raspi-config` → Performance → GPU Memory |
| No sync between nodes | Different subnets | Ensure all on same /24 network |
| Service keeps restarting | Missing Python deps | Run `setup.sh` again |
| USB config ignored | Depth > 1 | Move `ksync.ini` to USB root |
