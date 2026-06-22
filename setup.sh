#!/bin/bash
# setup_pi5.sh - Consolidated, idempotent setup for kSync on Raspberry Pi 5
# This script handles GStreamer, X11 permissions, hardware mapping, and UI polishing.

set -e # Exit on error

echo "Starting kSync Setup..."

# 1. Install System Dependencies
echo "Installing GStreamer and X11 dependencies..."
sudo apt update
sudo apt install -y --no-install-recommends \
    xserver-xorg xinit openbox x11-xserver-utils xserver-xorg-legacy \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-libav \
    gstreamer1.0-tools python3-gst-1.0 gir1.2-gst-plugins-base-1.0 \
    unclutter v4l-utils

# 2. GPU Memory Allocation (256MB — needed for HEVC decode on Pi 4)
echo "Setting GPU memory to 256MB..."
BOOT_CFG="/boot/firmware/config.txt"
[ ! -f "$BOOT_CFG" ] && BOOT_CFG="/boot/config.txt"
if grep -q "^gpu_mem=" "$BOOT_CFG"; then
    sudo sed -i 's/^gpu_mem=.*/gpu_mem=256/' "$BOOT_CFG"
else
    echo "gpu_mem=256" | sudo tee -a "$BOOT_CFG"
fi

# 3. X Server Permissions & Legacy Mode
echo "Configuring X Server permissions..."
sudo usermod -a -G video,render,tty $USER

# Configure Xwrapper for non-root X
XWRAPPER="/etc/X11/Xwrapper.config"
sudo touch $XWRAPPER
grep -q "allowed_users=anybody" $XWRAPPER || echo "allowed_users=anybody" | sudo tee -a $XWRAPPER
grep -q "needs_root_rights=yes" $XWRAPPER || echo "needs_root_rights=yes" | sudo tee -a $XWRAPPER

# 4. Xorg Hardware Mapping (Force card1 for Pi 5)
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

# 5. Openbox UI Polishing (Borderless & Fullscreen)
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

# 6. Autostart Configuration (Mouse hiding)
echo "Configuring autostart..."
mkdir -p ~/.config/openbox
AUTOSTART=~/.config/openbox/autostart
# Fix ownership in case it was created as root by mistake
sudo chown -R $USER:$USER ~/.config/openbox
touch $AUTOSTART
grep -q "unclutter" $AUTOSTART || echo "unclutter -idle 0.1 -root &" >> $AUTOSTART

# 7. Python Virtual Environment
echo "Setting up Python virtual environment..."
VENV_DIR="$PWD/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
    echo "Virtual environment created at $VENV_DIR"
fi

echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install mido pyserial python-osc

# 8. Systemd Service Configuration
echo "Configuring systemd service..."
SERVICE_FILE="kitchensync.service"
CURRENT_USER=$(whoami)
INSTALL_DIR=$(pwd)
VENV_PYTHON="$VENV_DIR/bin/python3"

# Create a clean service file with dynamic paths
sudo tee /etc/systemd/system/kitchensync.service <<EOF
[Unit]
Description=kSync Universal Node
After=network.target
# We don't depend on graphical.target because we start our own X session if needed

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR/src
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$CURRENT_USER/.Xauthority
# Ensure the node can start X if it's not already running
ExecStartPre=$INSTALL_DIR/tools/start_x.sh
# Launch the universal bootstrapper
ExecStart=$VENV_PYTHON kitchensync.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "Enabling kitchensync.service..."
sudo systemctl daemon-reload
sudo systemctl enable kitchensync.service

echo "-------------------------------------------------------"
echo "Setup Complete! Please REBOOT for changes to take effect."
echo "Upon reboot, the Pi will automatically:"
echo " 1. Start X11/Openbox"
echo " 2. Search for ksync.ini on USB root"
echo " 3. Assume the configured Role (Leader/Collaborator/Bystander)"
echo "-------------------------------------------------------"
