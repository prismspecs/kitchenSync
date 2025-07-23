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

# Setup auto-start service
echo "Setting up auto-start service..."
sudo cp kitchensync.service /etc/systemd/system/
sudo sed -i "s/kitchensync/$USER/g" /etc/systemd/system/kitchensync.service
sudo sed -i "s|/home/kitchensync/kitchenSync|$(pwd)|g" /etc/systemd/system/kitchensync.service
sudo systemctl daemon-reload
sudo systemctl enable kitchensync.service

echo "Auto-start service installed. KitchenSync will start automatically on boot."

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
