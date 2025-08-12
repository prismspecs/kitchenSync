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

# --- Desktop Configuration for Wayfire/Wayland ---
echo "Configuring desktop appearance for Wayfire (hide icons, black background)..."

# Configure wf-shell for black background (Wayfire's desktop shell)
echo "Configuring wf-shell for black background..."
mkdir -p ~/.config
if [ -f ~/.config/wf-shell.ini ]; then
    # Check if background section exists
    if grep -q "^\[background\]" ~/.config/wf-shell.ini; then
        # Update existing background color
        sed -i 's|color = .*|color = \\#000000|g' ~/.config/wf-shell.ini
    else
        # Add background section
        echo "" >> ~/.config/wf-shell.ini
        echo "[background]" >> ~/.config/wf-shell.ini
        echo "color = \\#000000" >> ~/.config/wf-shell.ini
    fi
else
    # Create new wf-shell.ini with black background
    cat > ~/.config/wf-shell.ini << 'EOF'
[background]
color = \#000000
EOF
fi

# Configure pcmanfm to not show desktop icons (if it's being used)
echo "Disabling desktop icons in pcmanfm..."
mkdir -p ~/.config/pcmanfm/default
if [ -f ~/.config/pcmanfm/default/pcmanfm.conf ]; then
    # Check if desktop section exists and modify it
    if grep -q "^\[desktop\]" ~/.config/pcmanfm/default/pcmanfm.conf; then
        sed -i '/^\[desktop\]/,/^\[/{s/show_desktop=1/show_desktop=0/g;}' ~/.config/pcmanfm/default/pcmanfm.conf
    else
        # Add desktop section
        echo "" >> ~/.config/pcmanfm/default/pcmanfm.conf
        echo "[desktop]" >> ~/.config/pcmanfm/default/pcmanfm.conf
        echo "show_desktop=0" >> ~/.config/pcmanfm/default/pcmanfm.conf
    fi
else
    # Create new pcmanfm.conf with desktop icons disabled
    cat > ~/.config/pcmanfm/default/pcmanfm.conf << 'EOF'
[config]
bm_open_method=0

[desktop]
show_desktop=0
EOF
fi

# Install swaybg as fallback/alternative background setter
echo "Installing swaybg as fallback background setter..."
sudo apt install -y swaybg

# Create fallback black background script using swaybg
cat > ~/set_black_background_fallback.sh << 'EOF'
#!/bin/bash
# Fallback black background using swaybg
pkill swaybg 2>/dev/null || true
swaybg -c '#000000' &
EOF
chmod +x ~/set_black_background_fallback.sh

# Configure Wayfire autostart for fallback background (if wf-shell doesn't work)
echo "Configuring Wayfire autostart fallback..."
mkdir -p ~/.config
if [ -f ~/.config/wayfire.ini ]; then
    # Check if autostart section exists
    if grep -q "^\[autostart\]" ~/.config/wayfire.ini; then
        # Add fallback background if not already present
        if ! grep -q "fallback_bg=" ~/.config/wayfire.ini; then
            sed -i '/^\[autostart\]/a fallback_bg=~/set_black_background_fallback.sh' ~/.config/wayfire.ini
        fi
    else
        # Add entire autostart section with fallback
        echo "" >> ~/.config/wayfire.ini
        echo "[autostart]" >> ~/.config/wayfire.ini
        echo "fallback_bg=~/set_black_background_fallback.sh" >> ~/.config/wayfire.ini
    fi
else
    # Create new wayfire.ini with autostart fallback
    cat > ~/.config/wayfire.ini << 'EOF'
[autostart]
fallback_bg=~/set_black_background_fallback.sh
EOF
fi

# Apply desktop configuration immediately if in Wayland session
if [ -n "$WAYLAND_DISPLAY" ]; then
    echo "Applying Wayfire desktop configuration immediately..."
    # Kill any existing desktop icon managers
    pkill pcmanfm 2>/dev/null || true
    # Start fallback background
    ~/set_black_background_fallback.sh
    echo "Wayfire desktop configuration applied (black background set, desktop icons disabled)"
else
    echo "Desktop configuration will be applied on next Wayfire session"
fi

echo "Wayfire desktop configuration complete"
# --- End Desktop Configuration ---

# Setup auto-start service
echo "Setting up auto-start service..."
mkdir -p ~/.config/systemd/user
cp kitchensync.service ~/.config/systemd/user/
sed -i "s/kitchensync/$USER/g" ~/.config/systemd/user/kitchensync.service
sed -i "s|/home/kitchensync/kitchenSync|$(pwd)|g" ~/.config/systemd/user/kitchensync.service
systemctl --user daemon-reload
systemctl --user enable kitchensync.service

echo "Auto-start service installed. KitchenSync will start automatically on boot."

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
echo "💡 READY FOR DEPLOYMENT! Just plug in USB drive and power on!"
echo ""
