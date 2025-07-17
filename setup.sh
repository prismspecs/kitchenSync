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

# Install Python MIDI library
echo "Installing Python MIDI library..."
pip3 install python-rtmidi

# Install Python DBus library for video sync control
echo "Installing Python DBus library..."
pip3 install dbus-python

# Install system MIDI tools (optional, for debugging)
echo "Installing MIDI system tools..."
sudo apt install -y alsa-utils

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Connect USB MIDI interface to each Pi"
echo "2. For leader Pi: python3 leader.py"
echo "3. For collaborator Pi: Edit collaborator_config.ini, then python3 collaborator.py"
echo "4. Place video files in ./videos/ directory or USB drives"
echo "5. Test MIDI connection with: aconnect -l or amidi -l"
echo ""
