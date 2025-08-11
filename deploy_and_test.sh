#!/bin/bash
# KitchenSync Deployment and Testing Script
# Run this on the Pi to install service and test logging

echo "🎬 KitchenSync Deployment and Testing"
echo "====================================="

# Check if running as correct user
if [ "$USER" != "kitchensync" ]; then
    echo "⚠️  Warning: Not running as kitchensync user"
    echo "   Current user: $USER"
    echo "   Expected: kitchensync"
    echo "   You may need to run: sudo -u kitchensync bash"
fi

# Check current directory
EXPECTED_DIR="/home/kitchensync/kitchenSync"
CURRENT_DIR="$(pwd)"

if [ "$CURRENT_DIR" != "$EXPECTED_DIR" ]; then
    echo "⚠️  Warning: Not in expected directory"
    echo "   Current: $CURRENT_DIR"
    echo "   Expected: $EXPECTED_DIR"
    echo "   Please cd to $EXPECTED_DIR first"
    exit 1
fi

echo "✅ Running from correct directory: $CURRENT_DIR"

# Step 1: Test basic logging first
echo ""
echo "🔍 Step 1: Testing basic logging..."
python3 test_logging.py

if [ $? -eq 0 ]; then
    echo "✅ Basic logging test passed"
else
    echo "❌ Basic logging test failed - check /tmp/kitchensync_test_failed.log"
    exit 1
fi

# Step 2: Check what logs were created
echo ""
echo "📋 Step 2: Checking created log files..."
ls -la /tmp/kitchensync_* 2>/dev/null || echo "No log files found yet"

# Step 3: Install systemd service
echo ""
echo "📋 Step 3: Installing systemd service..."
sudo cp kitchensync.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kitchensync.service

echo "✅ Service installed and enabled"

# Step 4: Stop any existing instances
echo ""
echo "🛑 Step 4: Stopping existing instances..."
sudo systemctl stop kitchensync.service 2>/dev/null || true
pkill -f 'leader.py|kitchensync.py|collaborator.py|vlc' 2>/dev/null || true
sleep 2

# Step 5: Start service and monitor
echo ""
echo "🚀 Step 5: Starting service and monitoring..."
sudo systemctl start kitchensync.service

# Wait a moment for startup
sleep 5

# Check service status
echo ""
echo "📊 Service status:"
systemctl status kitchensync.service --no-pager

# Step 6: Monitor logs in real-time
echo ""
echo "📝 Step 6: Monitoring logs (Ctrl+C to stop monitoring)..."
echo "Log files to check:"
echo "  - /tmp/kitchensync_startup.log (emergency startup log)"
echo "  - /tmp/kitchensync_system.log (main system log)"
echo "  - /tmp/kitchensync_vlc_stderr.log (VLC errors)"
echo "  - /tmp/kitchensync_vlc_stdout.log (VLC output)"
echo "  - /tmp/kitchensync_debug_leader-pi.txt (overlay fallback)"
echo ""

# Show startup log first
if [ -f "/tmp/kitchensync_startup.log" ]; then
    echo "=== STARTUP LOG ==="
    cat /tmp/kitchensync_startup.log
    echo ""
fi

# Show system log if it exists
if [ -f "/tmp/kitchensync_system.log" ]; then
    echo "=== SYSTEM LOG (last 50 lines) ==="
    tail -n 50 /tmp/kitchensync_system.log
    echo ""
fi

# Show VLC logs if they exist
if [ -f "/tmp/kitchensync_vlc_stderr.log" ]; then
    echo "=== VLC STDERR (last 20 lines) ==="
    tail -n 20 /tmp/kitchensync_vlc_stderr.log
    echo ""
fi

if [ -f "/tmp/kitchensync_vlc_stdout.log" ]; then
    echo "=== VLC STDOUT (last 20 lines) ==="
    tail -n 20 /tmp/kitchensync_vlc_stdout.log
    echo ""
fi

# Show overlay log if it exists
if [ -f "/tmp/kitchensync_debug_leader-pi.txt" ]; then
    echo "=== OVERLAY LOG (last 20 lines) ==="
    tail -n 20 /tmp/kitchensync_debug_leader-pi.txt
    echo ""
fi

echo ""
echo "🎯 Next steps:"
echo "1. Check if VLC window appeared on Pi screen"
echo "2. Check if debug overlay appeared"
echo "3. If issues persist, check logs above for errors"
echo "4. To stop service: sudo systemctl stop kitchensync.service"
echo "5. To restart: sudo systemctl restart kitchensync.service"
echo ""
echo "📋 To monitor logs in real-time:"
echo "  tail -f /tmp/kitchensync_system.log"
echo "  tail -f /tmp/kitchensync_vlc_stderr.log"
echo "  tail -f /tmp/kitchensync_debug_leader-pi.txt"
