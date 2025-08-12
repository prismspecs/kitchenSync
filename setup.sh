#!/bin/bash
# KitchenSync Setup Script

set -e  # Exit on any error

echo "=== KitchenSync Setup ==="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ Don't run as root. Use: sudo ./setup.sh"
   exit 1
fi

# Check for Raspberry Pi OS
if ! grep -q "Raspberry Pi OS" /etc/os-release 2>/dev/null; then
    echo "⚠️  This script is designed for Raspberry Pi OS"
    echo "Continuing anyway..."
fi

# Fix APT cache if needed
echo "🔍 Checking APT cache..."
if ! sudo apt update 2>/dev/null; then
    echo "🛠️  Fixing APT cache..."
    sudo rm -rf /var/lib/apt/lists/*
    sudo apt update
fi

# Install packages in one go
echo "📦 Installing packages..."
sudo apt install -y \
    vlc \
    libvlc-dev \
    python3-vlc \
    python3-pip \
    python3-dev \
    libasound2-dev \
    alsa-utils \
    udisks2 \
    usbutils \
    libdbus-1-dev \
    libglib2.0-dev \
    wmctrl

# Install Python packages
echo "🐍 Installing Python packages..."
sudo pip3 install --break-system-packages \
    python-rtmidi \
    dbus-python \
    python-vlc

# Setup USB mount points
echo "💾 Setting up USB mount points..."
sudo mkdir -p /media/usb{0..3}
sudo chown $USER:$USER /media/usb*

# Add user to groups
echo "👤 Configuring permissions..."
sudo usermod -a -G plugdev,disk $USER

# Safe OS Optimizations (Desktop Environment Preserved)
echo "⚡ Applying safe OS optimizations..."

# Only disable clearly safe services
echo "Disabling Bluetooth (safe to disable)..."
sudo systemctl disable bluetooth.service hciuart.service 2>/dev/null || true

# Automatically disable additional services for performance
echo "Disabling additional services for performance..."
sudo systemctl disable cups.service 2>/dev/null || true
sudo systemctl disable triggerhappy.service 2>/dev/null || true
sudo systemctl disable avahi-daemon.service 2>/dev/null || true
echo "⚠️  Desktop environment may not work properly after reboot!"

# Automatically remove unused packages
echo "Removing unused packages..."
sudo apt purge -y wolfram-engine sonic-pi scratch nuscratch smartsim libreoffice* 2>/dev/null || true

echo "Running apt autoremove for cleanup..."
sudo apt autoremove -y
echo "⚠️  If desktop doesn't work after reboot, run:"
echo "   sudo apt install --reinstall raspberrypi-ui-mods"

sudo apt clean

# Safe boot optimizations
echo "Applying safe boot optimizations..."
if ! grep -q "disable_splash=1" /boot/config.txt; then
    echo "disable_splash=1" | sudo tee -a /boot/config.txt >/dev/null 2>&1 || true
fi
if ! grep -q "boot_delay=0" /boot/config.txt; then
    echo "boot_delay=0" | sudo tee -a /boot/config.txt >/dev/null 2>&1 || true
fi

# Install systemd service
echo "🚀 Setting up auto-start service..."
sudo cp kitchensync.service /etc/systemd/system/
sudo sed -i "s/kitchensync/$USER/g" /etc/systemd/system/kitchensync.service
sudo sed -i "s|/home/kitchensync/kitchenSync|$(pwd)|g" /etc/systemd/system/kitchensync.service
sudo systemctl daemon-reload
sudo systemctl enable kitchensync.service

# Test imports
echo "🧪 Testing imports..."
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

try:
    from networking import SyncBroadcaster, CommandManager
    print('✅ Leader networking: OK')
except Exception as e:
    print(f'❌ Leader networking: {e}')

try:
    from networking import SyncReceiver, CommandListener  
    print('✅ Collaborator networking: OK')
except Exception as e:
    print(f'❌ Collaborator networking: {e}')
"

echo ""
echo "✅ Setup Complete!"
