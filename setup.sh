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

# Install required packages
sudo apt-get update
sudo apt-get install -y python3-pip python3-vlc vlc
sudo apt-get install -y wmctrl  # For window management

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

# --- OS Optimizations ---
echo "Applying OS optimizations..."

# Disable unnecessary services
echo "Disabling unused services (Bluetooth, CUPS, etc.)..."
sudo systemctl disable bluetooth.service hciuart.service > /dev/null 2>&1 || true
sudo systemctl disable cups.service > /dev/null 2>&1 || true
sudo systemctl disable triggerhappy.service > /dev/null 2>&1 || true
sudo systemctl disable avahi-daemon.service > /dev/null 2>&1 || true

# Remove unused software packages
echo "Removing unnecessary software (Wolfram, LibreOffice, etc.)..."
sudo apt-get purge -y wolfram-engine sonic-pi scratch nuscratch smartsim libreoffice* > /dev/null 2>&1
sudo apt-get autoremove -y > /dev/null 2>&1
sudo apt-get clean > /dev/null 2>&1

# Optimize boot configuration
echo "Optimizing boot configuration..."
if ! grep -q "disable_splash=1" /boot/config.txt; then
    echo "disable_splash=1" | sudo tee -a /boot/config.txt
fi
if ! grep -q "boot_delay=0" /boot/config.txt; then
    echo "boot_delay=0" | sudo tee -a /boot/config.txt
fi
# --- End OS Optimizations ---

# --- Desktop Environment: Wayfire/Labwc clean kiosk setup ---
echo "Configuring Wayfire for clean kiosk mode (no panels, black background)..."

# Ensure we have the UI packages and LightDM
sudo apt update >/dev/null 2>&1 || true
sudo apt install -y raspberrypi-ui-mods lightdm >/dev/null 2>&1 || true
sudo systemctl enable --now lightdm >/dev/null 2>&1 || true

# Clean previous overrides created by earlier revisions
rm -f "$HOME/.config/autostart/lxpanel.desktop" "$HOME/.config/autostart/pcmanfm.desktop" 2>/dev/null || true
sed -i '/@xsetroot -solid black/d' "$HOME/.config/lxsession/LXDE-pi/autostart" 2>/dev/null || true
rm -f "$HOME/.config/pcmanfm/LXDE-pi/desktop-items-0.conf" 2>/dev/null || true

# Remove kiosk X service if it exists
sudo systemctl disable kitchensync-x.service >/dev/null 2>&1 || true
sudo systemctl stop kitchensync-x.service >/dev/null 2>&1 || true
sudo rm -f /etc/systemd/system/kitchensync-x.service 2>/dev/null || true
sudo systemctl daemon-reload
rm -f "$HOME/.xinitrc" 2>/dev/null || true

# Configure Wayfire for clean kiosk (no panels, black background)
mkdir -p "$HOME/.config"
cat > "$HOME/.config/wayfire.ini" <<'EOF'
[core]
plugins = hide-cursor

[background]
color = 0 0 0
EOF

# Create KitchenSync autostart .desktop file
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/kitchensync.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=KitchenSync
Exec=python3 $(pwd)/kitchensync.py
X-GNOME-Autostart-enabled=true
EOF

# Disable the user systemd service since we're using .desktop autostart
systemctl --user disable kitchensync.service >/dev/null 2>&1 || true

echo "Wayfire configured for kiosk mode with KitchenSync autostart"
# --- End Desktop Environment configuration ---


# Setup backup auto-start service (disabled by default, using .desktop instead)
echo "Setting up backup auto-start service (disabled)..."
mkdir -p ~/.config/systemd/user
cp kitchensync.service ~/.config/systemd/user/
sed -i "s/kitchensync/$USER/g" ~/.config/systemd/user/kitchensync.service
sed -i "s|/home/kitchensync/kitchenSync|$(pwd)|g" ~/.config/systemd/user/kitchensync.service
systemctl --user daemon-reload

echo "Auto-start via .desktop file configured. KitchenSync will start automatically on login."

# Test networking imports after cleanup
echo ""
echo "🔍 Testing networking imports..."
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

try:
    from networking import SyncBroadcaster, CommandManager
    print('✅ Leader networking imports OK')
except Exception as e:
    print(f'❌ Leader networking imports failed: {e}')

try:
    from networking import SyncReceiver, CommandListener  
    print('✅ Collaborator networking imports OK')
except Exception as e:
    print(f'❌ Collaborator networking imports failed: {e}')
"

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Video player: VLC"
echo "Python packages installed system-wide"
echo "🔄 Auto-start service: ENABLED"
echo "🖥️  Desktop: Wayfire kiosk mode (black background, no panels)"
echo ""
echo "🚀 PLUG-AND-PLAY OPERATION:"
echo "1. Create kitchensync.ini on your USB drive with:"
echo "   - is_leader = true/false (designates leader or collaborator)"
echo "   - pi_id = unique ID for each Pi" 
echo "   - video_file = specific video filename (optional)"
echo "2. Power on the Pi - KitchenSync starts automatically!"
echo ""
echo "📁 USB Drive Contents:"
echo "   - kitchensync.ini (configuration file)"
echo "   - Your video file(s) at the root level"
echo ""
echo "🔧 MANUAL TESTING (Optional):"
echo "- Test auto-detection: python3 kitchensync.py"
echo "- Test with display (SSH): DISPLAY=:0 PULSE_SERVER=unix:/run/user/1000/pulse/native python3 kitchensync.py"
echo "- Test service: sudo systemctl start kitchensync"
echo "- Manual leader: python3 leader.py"
echo "- Manual collaborator: python3 collaborator.py"
echo ""
echo "🎵 MIDI Setup:"
echo "1. Connect USB MIDI interface to collaborator Pis"
echo "2. Test connection: aconnect -l or amidi -l"
echo ""
echo "� Service Management:"
echo "- Check status: sudo systemctl status kitchensync"
echo "- View logs: sudo journalctl -u kitchensync -f"
echo "- Disable auto-start: sudo systemctl disable kitchensync"
echo ""
:
echo "💡 READY FOR DEPLOYMENT! Just plug in USB drive and power on!"
echo ""

:

