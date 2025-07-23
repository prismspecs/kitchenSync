#!/bin/bash
# KitchenSync Setup Script

echo "=== KitchenSync Setup ==="

# Check for Raspberry Pi OS version
PI_VERSION=$(grep VERSION_CODENAME /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')

# Fix APT cache corruption if it exists
echo "Checking APT cache integrity..."
if ! sudo apt update 2>/dev/null; then
    echo "APT cache corruption detected, fixing..."
    sudo rm -rf /var/lib/apt/lists/*
    echo "Updating package lists..."
    sudo apt update
else
    echo "APT cache is healthy"
fi

# Install VLC and dependencies
echo "Installing VLC and dependencies..."
sudo apt install -y vlc libvlc-dev python3-vlc python3-pip python3-venv python3-dev libasound2-dev alsa-utils

# Install USB mounting utilities
echo "Installing USB mounting utilities..."
sudo apt install -y udisks2 usbutils

# Create media directories for USB mounting
echo "Setting up USB mount points..."
sudo mkdir -p /media/usb /media/usb0 /media/usb1
sudo chown -R $USER:$USER /media/usb* 2>/dev/null || true

# Add user to necessary groups for USB access
echo "Configuring USB access permissions..."
sudo usermod -a -G plugdev,disk $USER

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
echo "5. Video files:"
echo "   - USB drive (auto-detected): Place ONE video file at the root of USB drive"
echo "   - Local storage: Place files in ./videos/ directory"
echo "6. Test MIDI connection with: aconnect -l or amidi -l"
echo ""
echo "💡 USB Drive Priority: The system will automatically mount and use video files"
echo "   from USB drives before checking local directories. For best results, use"
echo "   only one video file per USB drive at the root level."
echo ""
