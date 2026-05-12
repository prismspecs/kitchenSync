#!/bin/bash
# fix_x_pi5.sh - Automated Xorg configuration for Raspberry Pi 5

echo "Applying Pi 5 Xorg configuration fix..."

# 1. Ensure X11 config directory exists
sudo mkdir -p /etc/X11/xorg.conf.d

# 2. Create the config file to force the modesetting driver
# This prevents the 'Cannot run in framebuffer mode' error on Pi 5
sudo tee /etc/X11/xorg.conf.d/99-vc4.conf <<EOF
Section "Device"
    Identifier "Video Device"
    Driver "modesetting"
EndSection
EOF

echo "-----------------------------------------------"
echo "Config applied. Now attempting to start X..."
echo "-----------------------------------------------"

# 3. Try to start the X server
chmod +x ./tools/start_x.sh
./tools/start_x.sh
