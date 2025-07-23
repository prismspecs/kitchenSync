#!/bin/bash
# KitchenSync Deployment Script for Raspberry Pi
# Run this on the Pi after copying files

echo "🎬 KitchenSync Deployment Setup"
echo "================================"

# Check if running as correct user
if [ "$USER" != "kitchensync" ]; then
    echo "⚠️  Warning: Not running as kitchensync user"
    echo "   Current user: $USER"
    echo "   Expected: kitchensync"
fi

# Check current directory
EXPECTED_DIR="/home/kitchensync/kitchenSync"
CURRENT_DIR="$(pwd)"

if [ "$CURRENT_DIR" != "$EXPECTED_DIR" ]; then
    echo "⚠️  Warning: Not in expected directory"
    echo "   Current: $CURRENT_DIR"
    echo "   Expected: $EXPECTED_DIR"
fi

# Copy systemd service file
echo "📋 Installing systemd service..."
sudo cp kitchensync.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kitchensync.service

# Test imports
echo "🔍 Testing Python imports..."
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

try:
    from networking import SyncBroadcaster, CommandManager
    print('✅ Leader imports OK')
except Exception as e:
    print(f'❌ Leader imports failed: {e}')

try:
    from networking import SyncReceiver, CommandListener  
    print('✅ Collaborator imports OK')
except Exception as e:
    print(f'❌ Collaborator imports failed: {e}')
"

# Check for USB drives
echo "💾 Checking USB drives..."
if ls /media/kitchensync/ 2>/dev/null | grep -q .; then
    echo "✅ USB drives detected:"
    ls /media/kitchensync/
else
    echo "⚠️  No USB drives found in /media/kitchensync/"
fi

# Check VLC
echo "🎬 Checking VLC installation..."
if command -v vlc &> /dev/null; then
    echo "✅ VLC command available"
else
    echo "❌ VLC not found - install with: sudo apt install vlc"
fi

# Check python-vlc
python3 -c "
try:
    import vlc
    print('✅ python-vlc module available')
except ImportError:
    print('❌ python-vlc not found - install with: pip3 install python-vlc')
"

echo ""
echo "🚀 Ready to test!"
echo "   Manual test: python3 kitchensync.py"
echo "   Service test: sudo systemctl start kitchensync.service"
echo "   Check status: sudo systemctl status kitchensync.service"
