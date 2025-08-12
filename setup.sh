#!/bin/bash
# KitchenSync Setup Script

set -euo pipefail
IFS=$'\n\t'

echo "=== KitchenSync Setup ==="

# Ensure sudo credentials are cached upfront
sudo -v || true

# Resolve absolute project path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
cd "$PROJECT_DIR"

# Refresh APT metadata; repair list corruption if needed
echo "Checking APT cache integrity..."
if ! sudo apt-get update >/dev/null 2>&1; then
    echo "APT cache issue detected, refreshing lists..."
    sudo rm -rf /var/lib/apt/lists/*
    sudo apt-get update
else
    echo "APT cache is healthy"
fi

# Install system dependencies (non-interactive)
echo "Installing system dependencies..."
export DEBIAN_FRONTEND=noninteractive
sudo apt-get install -y --no-install-recommends \
    vlc \
    python3-pip python3-venv python3-dev \
    libasound2-dev alsa-utils \
    udisks2 usbutils \
    libdbus-1-dev libglib2.0-dev \
    wmctrl

# Create media directories for USB mounting
echo "Setting up USB mount points..."
sudo mkdir -p /media/usb /media/usb0 /media/usb1
sudo chown -R "$USER":"$USER" /media/usb* 2>/dev/null || true

# Add user to necessary groups for USB access
echo "Configuring USB access permissions..."
sudo usermod -a -G plugdev "$USER" 2>/dev/null || true

# Install Python dependencies system-wide from requirements
echo "Installing Python packages (requirements.txt)..."
sudo -H pip3 install --break-system-packages -r "$PROJECT_DIR/requirements.txt"

# Setup auto-start user service
echo "Setting up auto-start service..."
mkdir -p "$HOME/.config/systemd/user"
cp "$PROJECT_DIR/kitchensync.service" "$HOME/.config/systemd/user/kitchensync.service"

# Adapt service for user mode and current paths
sed -i "s|/home/kitchensync/kitchenSync|$PROJECT_DIR|g" "$HOME/.config/systemd/user/kitchensync.service"
sed -i "s|/home/kitchensync|$HOME|g" "$HOME/.config/systemd/user/kitchensync.service"
# User units run as the calling user; drop explicit User/Group if present
sed -i "s/^User=.*$//g" "$HOME/.config/systemd/user/kitchensync.service"
sed -i "s/^Group=.*$//g" "$HOME/.config/systemd/user/kitchensync.service"

systemctl --user daemon-reload
systemctl --user enable kitchensync.service

echo "Auto-start service installed. KitchenSync will start automatically on boot."

# Test networking imports after cleanup
echo ""
echo "🔍 Testing networking imports..."
python3 - <<'PYTEST'
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
PYTEST

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Video player: VLC"
echo "Python packages installed from requirements.txt"
echo "🔄 Auto-start service: ENABLED (user)"
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
echo "- Test service: systemctl --user start kitchensync.service"
echo "- Manual leader: python3 leader.py"
echo "- Manual collaborator: python3 collaborator.py"
echo ""
echo "🎵 MIDI Setup:"
echo "1. Connect USB MIDI interface to collaborator Pis"
echo "2. Test connection: aconnect -l or amidi -l"
echo ""
echo "🛠️ Service Management:"
echo "- Check status: systemctl --user status kitchensync.service"
echo "- View logs: journalctl --user -u kitchensync -f"
echo "- Disable auto-start: systemctl --user disable kitchensync.service"
echo ""
echo "Note: If this is your first time joining groups, you may need to log out and back in for permissions to take effect."
echo ""
echo "💡 READY FOR DEPLOYMENT! Just plug in USB drive and power on!"
echo ""