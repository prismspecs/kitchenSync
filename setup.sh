#!/bin/bash
# KitchenSync Setup Script

echo "=== KitchenSync Setup ==="

# Check for Raspberry Pi OS version
PI_VERSION=$(grep VERSION_CODENAME /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')

# Fix APT cache corruption if it exists
if ! sudo apt list >/dev/null 2>&1; then
    echo "Fixing corrupted APT cache..."
    sudo rm -rf /var/lib/apt/lists/*
fi

# Update system
echo "Updating system packages..."
sudo apt update

# Install VLC and dependencies
echo "Installing VLC and dependencies..."
sudo apt install -y vlc libvlc-dev python3-vlc python3-pip python3-venv python3-dev libasound2-dev alsa-utils

# Create virtual environment
echo "Creating Python virtual environment..."
if [ -d "kitchensync-env" ]; then
    echo "Removing existing virtual environment..."
    rm -rf kitchensync-env
fi

python3 -m venv kitchensync-env
source kitchensync-env/bin/activate

# Install Python packages in virtual environment
echo "Installing Python packages..."
pip install python-rtmidi dbus-python python-vlc

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Video player: VLC"
echo "Python virtual environment created: kitchensync-env"
echo ""
echo "Next steps:"
echo "1. Connect USB MIDI interface to each Pi"
echo "2. Activate virtual environment: source kitchensync-env/bin/activate"
echo "3. For leader Pi: python3 leader.py"
echo "4. For collaborator Pi: Edit collaborator_config.ini, then python3 collaborator.py"
echo "5. Place video files in ./videos/ directory or USB drives"
echo "6. Test MIDI connection with: aconnect -l or amidi -l"
echo ""
