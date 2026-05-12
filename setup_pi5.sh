#!/bin/bash
# setup_pi5.sh - Consolidated, idempotent setup for KitchenSync on Raspberry Pi 5
# This script handles GStreamer, X11 permissions, hardware mapping, and UI polishing.

set -e # Exit on error

echo "Starting KitchenSync Pi 5 Appliance Setup..."

# 1. Install System Dependencies
echo "Installing GStreamer and X11 dependencies..."
sudo apt update
sudo apt install -y --no-install-recommends \
    xserver-xorg xinit openbox x11-xserver-utils xserver-xorg-legacy \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-libav \
    gstreamer1.0-tools python3-gst-1.0 gir1.2-gst-plugins-base-1.0 \
    unclutter udevil

# 2. X Server Permissions & Legacy Mode
echo "Configuring X Server permissions..."
sudo usermod -a -G video,render,tty $USER

# Configure Xwrapper for non-root X
XWRAPPER="/etc/X11/Xwrapper.config"
sudo touch $XWRAPPER
grep -q "allowed_users=anybody" $XWRAPPER || echo "allowed_users=anybody" | sudo tee -a $XWRAPPER
grep -q "needs_root_rights=yes" $XWRAPPER || echo "needs_root_rights=yes" | sudo tee -a $XWRAPPER

# 3. Xorg Hardware Mapping (Force card1 for Pi 5)
echo "Applying Xorg hardware mapping for Pi 5..."
sudo mkdir -p /etc/X11/xorg.conf.d
sudo tee /etc/X11/xorg.conf.d/99-vc4.conf <<EOF
Section "Device"
    Identifier "VC4"
    Driver "modesetting"
    Option "kmsdev" "/dev/dri/card1"
EndSection

Section "Screen"
    Identifier "Default Screen"
    Device "VC4"
EndSection
EOF

# 4. Openbox UI Polishing (Borderless & Fullscreen)
echo "Configuring Openbox for borderless operation..."
mkdir -p ~/.config/openbox
if [ ! -f ~/.config/openbox/rc.xml ]; then
    cp /etc/xdg/openbox/rc.xml ~/.config/openbox/rc.xml
fi

# Use Python to idempotently insert the borderless rule
python3 - <<EOF
import os
config_path = os.path.expanduser("~/.config/openbox/rc.xml")
with open(config_path, 'r') as f:
    lines = f.readlines()

new_rule = [
    '  <application class="*">\n',
    '    <decor>no</decor>\n',
    '    <fullscreen>yes</fullscreen>\n',
    '  </application>\n'
]

content = "".join(lines)
if '<decor>no</decor>' not in content:
    with open(config_path, 'w') as f:
        for line in lines:
            if '</applications>' in line:
                f.writelines(new_rule)
            f.write(line)
EOF

# 5. Autostart Configuration (Mouse hiding)
echo "Configuring autostart..."
AUTOSTART=~/.config/openbox/autostart
touch $AUTOSTART
grep -q "unclutter" $AUTOSTART || echo "unclutter -idle 0.1 -root &" >> $AUTOSTART

echo "-------------------------------------------------------"
echo "Setup Complete! Please REBOOT for group changes to take effect."
echo "-------------------------------------------------------"
