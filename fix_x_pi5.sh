#!/bin/bash
# fix_x_pi5.sh - Refined Xorg configuration for Raspberry Pi 5

echo "Applying refined Pi 5 Xorg configuration fix..."

# 1. Clean up old locks
sudo rm -f /tmp/.X0-lock /tmp/.X11-unix/X0

# 2. Force Xorg to use the VC4 display controller (card1 on Pi 5)
# We use the 'modesetting' driver and explicitly point to the DRM device
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

# 3. Ensure permissions are set for non-root X
# Using anybody/yes for Xwrapper is the standard 'headless' fix
echo "allowed_users=anybody" | sudo tee /etc/X11/Xwrapper.config
echo "needs_root_rights=yes" | sudo tee -a /etc/X11/Xwrapper.config

echo "-----------------------------------------------"
echo "Config applied. Now attempting to start X..."
echo "-----------------------------------------------"

# 4. Trigger the start script
chmod +x ./tools/start_x.sh
./tools/start_x.sh
