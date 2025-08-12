#!/bin/bash
# KitchenSync Setup Script - Minimal Raspberry Pi OS Lite Version

set -e  # Exit on any error

echo "=== KitchenSync Minimal Setup (Raspberry Pi OS Lite) ==="

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

# Install minimal packages for KitchenSync on Raspberry Pi OS Lite
echo "📦 Installing minimal packages for Raspberry Pi OS Lite..."
sudo apt install --no-install-recommends -y \
    xserver-xorg \
    openbox \
    vlc \
    python3-vlc \
    python3-pip \
    python3-dev \
    libasound2-dev \
    alsa-utils \
    udisks2 \
    usbutils \
    libdbus-1-dev \
    libglib2.0-dev \
    wmctrl \
    xterm \
    xinit \
    x11-xserver-utils

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

# Create minimal Openbox configuration for KitchenSync
echo "🪟 Setting up Openbox configuration..."
mkdir -p ~/.config/openbox
cat > ~/.config/openbox/autostart << 'EOF'
#!/bin/bash
# KitchenSync autostart script
cd /home/pi/kitchenSync
python3 kitchensync.py
EOF

chmod +x ~/.config/openbox/autostart

# Create .xinitrc to start Openbox automatically
echo "🚀 Setting up auto-start with X11..."
cat > ~/.xinitrc << 'EOF'
#!/bin/bash
# Start Openbox window manager
exec openbox-session
EOF

chmod +x ~/.xinitrc

# Create systemd service for auto-login and X11 start
echo "🔧 Setting up systemd auto-login service..."
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf > /dev/null << 'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I $TERM
Type=idle
EOF

# Create .bash_profile to auto-start X11
echo "📱 Setting up auto-start X11 on login..."
cat >> ~/.bash_profile << 'EOF'

# Auto-start X11 if not already running
if [[ -z $DISPLAY ]] && [[ $(tty) = /dev/tty1 ]]; then
    startx
fi
EOF

# Disable unnecessary services for minimal setup
echo "⚡ Disabling unnecessary services..."
sudo systemctl disable bluetooth.service hciuart.service 2>/dev/null || true
sudo systemctl disable cups.service 2>/dev/null || true
sudo systemctl disable triggerhappy.service 2>/dev/null || true
sudo systemctl disable avahi-daemon.service 2>/dev/null || true
sudo systemctl disable lightdm.service 2>/dev/null || true
sudo systemctl disable gdm.service 2>/dev/null || true

# Remove any existing desktop environment packages if they exist
echo "🧹 Cleaning up any existing desktop packages..."
sudo apt purge -y raspberrypi-ui-mods lxde* gnome* kde* xfce* 2>/dev/null || true

# Clean up package cache
sudo apt autoremove -y
sudo apt clean

# Safe boot optimizations
echo "Applying safe boot optimizations..."
if ! grep -q "disable_splash=1" /boot/config.txt; then
    echo "disable_splash=1" | sudo tee -a /boot/config.txt >/dev/null 2>&1 || true
fi
if ! grep -q "boot_delay=0" /boot/config.txt; then
    echo "boot_delay=0" | sudo tee -a /boot/config.txt >/dev/null 2>&1 || true
fi

# Install KitchenSync systemd service
echo "🚀 Setting up KitchenSync auto-start service..."
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
echo "✅ Minimal Setup Complete!"
echo ""
echo "📋 What was installed:"
echo "   - X11 server (graphics foundation)"
echo "   - Openbox (lightweight window manager)"
echo "   - VLC media player"
echo "   - Essential Python packages"
echo "   - USB and audio support"
echo ""
echo "🚀 System will now:"
echo "   - Boot directly to command line"
echo "   - Auto-login as $USER"
echo "   - Start X11 automatically"
echo "   - Launch KitchenSync in Openbox"
echo ""
echo "⚠️  Note: This is a minimal setup without full desktop environment."
echo "   If you need a full desktop, run: sudo apt install raspberrypi-ui-mods"
