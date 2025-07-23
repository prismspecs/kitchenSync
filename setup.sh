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
sudo apt install -y vlc libvlc-dev python3-vlc python3-pip python3-dev libasound2-dev alsa-utils

# Install USB mounting utilities
echo "Installing USB mounting utilities..."
sudo apt install -y udisks2 usbutils

# Install dbus development libraries (needed for dbus-python)
echo "Installing dbus development libraries..."
sudo apt install -y libdbus-1-dev libglib2.0-dev

# Create media directories for USB mounting
echo "Setting up USB mount points..."
sudo mkdir -p /media/usb /media/usb0 /media/usb1
sudo chown -R $USER:$USER /media/usb* 2>/dev/null || true

# Add user to necessary groups for USB access
echo "Configuring USB access permissions..."
sudo usermod -a -G plugdev,disk $USER

# Install Python packages system-wide
echo "Installing Python packages system-wide..."
sudo pip install python-rtmidi dbus-python python-vlc --break-system-packages

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Video player: VLC"
echo "Python packages installed system-wide"
echo ""
echo "Next steps:"
echo "1. Connect USB MIDI interface to each Pi"
echo "2. For leader Pi: python3 leader.py"
echo "3. For collaborator Pi: Edit collaborator_config.ini, then python3 collaborator.py"
echo "4. Video files:"
echo "   - USB drive (auto-detected): Place ONE video file at the root of USB drive"
echo "   - Local storage: Place files in ./videos/ directory"
echo "5. Test MIDI connection with: aconnect -l or amidi -l"
echo ""
echo "💡 USB Drive Priority: The system will automatically mount and use video files"
echo "   from USB drives before checking local directories. For best results, use"
echo "   only one video file per USB drive at the root level."
echo ""
