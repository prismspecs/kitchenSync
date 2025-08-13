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

# Configure system for X11 mode (disable Wayland)
echo "Configuring system for X11 mode..."
# Set X11 as default session for GDM3
if [ -f /etc/gdm3/daemon.conf ]; then
    sudo sed -i 's/#WaylandEnable=false/WaylandEnable=false/' /etc/gdm3/daemon.conf 2>/dev/null || true
fi

# Configure LightDM to use X11 session instead of Wayland (labwc)
if [ -f /etc/lightdm/lightdm.conf ]; then
    echo "Configuring LightDM for X11 mode..."
    sudo sed -i 's/user-session=LXDE-pi-labwc/user-session=LXDE-pi-x/' /etc/lightdm/lightdm.conf
    sudo sed -i 's/autologin-session=LXDE-pi-labwc/autologin-session=LXDE-pi-x/' /etc/lightdm/lightdm.conf
    echo "✓ LightDM configured to use X11 session (LXDE-pi-x) for both user and autologin"
fi

# Add X11 environment variables to user profile
echo "# Force X11 mode for KitchenSync" >> ~/.bashrc
echo "export GDK_BACKEND=x11" >> ~/.bashrc
echo "export QT_QPA_PLATFORM=xcb" >> ~/.bashrc
echo "export WAYLAND_DISPLAY=" >> ~/.bashrc

# Update start_clean.sh to include X11 environment variables
if ! grep -q "GDK_BACKEND=x11" start_clean.sh; then
    sed -i '/export SDL_VIDEODRIVER=x11/a\\n# Force X11 mode (disable Wayland)\nexport GDK_BACKEND=x11\nexport QT_QPA_PLATFORM=xcb\nexport WAYLAND_DISPLAY=' start_clean.sh
fi

# Setup auto-start service
echo "Setting up auto-start service..."
mkdir -p ~/.config/systemd/user
cp kitchensync.service ~/.config/systemd/user/
sed -i "s/kitchensync/$USER/g" ~/.config/systemd/user/kitchensync.service
sed -i "s|/home/kitchensync/kitchenSync|$(pwd)|g" ~/.config/systemd/user/kitchensync.service

# Fix user service compatibility - remove User/Group directives
sed -i '/^User=/d' ~/.config/systemd/user/kitchensync.service
sed -i '/^Group=/d' ~/.config/systemd/user/kitchensync.service

# Change target to default.target for better headless compatibility
sed -i 's/graphical-session.target/default.target/g' ~/.config/systemd/user/kitchensync.service

# Optimize startup delay for X11 mode (reduced from 45 to 30 seconds)
sed -i 's/ExecStartPre=\/bin\/sleep 45/ExecStartPre=\/bin\/sleep 30/' ~/.config/systemd/user/kitchensync.service
sed -i 's/ExecStartPre=\/bin\/sleep 30/ExecStartPre=\/bin\/sleep 30/' ~/.config/systemd/user/kitchensync.service

# Force X11 mode for reliable window management (disable Wayland)
sed -i '/Environment=SDL_VIDEODRIVER=x11/a Environment=GDK_BACKEND=x11' ~/.config/systemd/user/kitchensync.service
sed -i '/Environment=GDK_BACKEND=x11/a Environment=QT_QPA_PLATFORM=xcb' ~/.config/systemd/user/kitchensync.service
sed -i '/Environment=QT_QPA_PLATFORM=xcb/a Environment=WAYLAND_DISPLAY=' ~/.config/systemd/user/kitchensync.service

# Enable lingering so user services start on boot without login
echo "Enabling user service lingering for boot startup..."
sudo loginctl enable-linger $USER

# Reload and enable the service
systemctl --user daemon-reload
systemctl --user enable kitchensync.service

# Verify the service is properly enabled
if systemctl --user is-enabled kitchensync.service >/dev/null 2>&1; then
    echo "✅ Auto-start service enabled successfully"
    echo "🔄 Service will start automatically on boot"
else
    echo "❌ Failed to enable auto-start service"
    echo "⚠️  Manual intervention may be required"
fi

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
echo "- Test service: systemctl --user start kitchensync"
echo "- Manual leader: python3 leader.py"
echo "- Manual collaborator: python3 collaborator.py"
echo ""
echo "🖥️  DISPLAY CONFIGURATION:"
echo "- System configured for X11 mode (Wayland disabled)"
echo "- This ensures reliable window positioning"
echo "- Reboot required for display changes to take effect"
echo ""
echo "🎵 MIDI Setup:"
echo "1. Connect USB MIDI interface to collaborator Pis"
echo "2. Test connection: aconnect -l or amidi -l"
echo ""
echo "🔧 Service Management:"
echo "- Check status: systemctl --user status kitchensync"
echo "- View logs: journalctl --user -u kitchensync -f"
echo "- Disable auto-start: systemctl --user disable kitchensync"
echo "- Stop service: systemctl --user stop kitchensync"
echo ""
echo "💡 READY FOR DEPLOYMENT! Just plug in USB drive and power on!"
echo ""