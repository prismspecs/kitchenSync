#!/bin/bash
# KitchenSync Setup Script

echo "=== KitchenSync Setup ==="

# Update system
echo "Updating system packages..."
sudo apt update

# Install video player
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "Raspberry Pi detected, installing omxplayer..."
    sudo apt install -y omxplayer
else
    echo "Not running on Raspberry Pi, installing VLC for simulation..."
    sudo apt install -y vlc
    echo "Note: VLC installed for video simulation. Other options: mpv, ffmpeg"
fi

# Install Python GPIO library (Raspberry Pi only)
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "Raspberry Pi detected, installing GPIO library..."
    sudo apt install -y python3-rpi.gpio
else
    echo "Not running on Raspberry Pi, GPIO simulation will be used"
fi

# Create directories
echo "Creating directories..."
mkdir -p videos
mkdir -p /tmp/kitchensync

# Set permissions
chmod +x leader.py
chmod +x collaborator.py

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. For leader Pi: python3 leader.py"
echo "2. For collaborator Pi: Edit collaborator_config.ini, then python3 collaborator.py"
echo "3. Place video files in ./videos/ directory or USB drives"
echo ""
