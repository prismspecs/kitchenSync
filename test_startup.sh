#!/bin/bash
# Test script to verify KitchenSync startup components
# Run this on the Pi to test if everything is set up correctly

echo "=== KitchenSync Startup Test ==="
echo

# Test 1: Check if start_clean.sh exists and is executable
echo "1. Checking start_clean.sh..."
if [ -f "start_clean.sh" ] && [ -x "start_clean.sh" ]; then
    echo "   ✓ start_clean.sh exists and is executable"
else
    echo "   ✗ start_clean.sh is missing or not executable"
    echo "   Run: chmod +x start_clean.sh"
fi

# Test 2: Check if kitchensync.py exists
echo "2. Checking kitchensync.py..."
if [ -f "kitchensync.py" ]; then
    echo "   ✓ kitchensync.py exists"
else
    echo "   ✗ kitchensync.py is missing"
fi

# Test 3: Check Python dependencies
echo "3. Checking Python dependencies..."
python3 -c "
try:
    import vlc
    print('   ✓ python-vlc available')
except ImportError:
    print('   ✗ python-vlc not available')

try:
    import rtmidi
    print('   ✓ python-rtmidi available')
except ImportError:
    print('   ✗ python-rtmidi not available')

"

# Test 4: Check systemd service
echo "4. Checking systemd service..."
if [ -f "/etc/systemd/system/kitchensync.service" ]; then
    echo "   ✓ kitchensync.service is installed"
    if systemctl is-enabled kitchensync.service >/dev/null 2>&1; then
        echo "   ✓ kitchensync.service is enabled"
    else
        echo "   ✗ kitchensync.service is not enabled"
        echo "   Run: sudo systemctl enable kitchensync.service"
    fi
else
    echo "   ✗ kitchensync.service is not installed"
    echo "   Run: sudo cp kitchensync.service /etc/systemd/system/"
fi

# Test 5: Check display environment
echo "5. Checking display environment..."
if [ -n "$DISPLAY" ]; then
    echo "   ✓ DISPLAY is set: $DISPLAY"
else
    echo "   ⚠ DISPLAY is not set (normal if running via SSH)"
fi

if [ -f "$HOME/.Xauthority" ]; then
    echo "   ✓ .Xauthority exists"
else
    echo "   ⚠ .Xauthority not found (may need to run from desktop session)"
fi

# Test 6: Check log directory
echo "6. Checking log files..."
if [ -d "/tmp" ]; then
    echo "   ✓ /tmp directory exists for logs"
    ls -la /tmp/kitchensync*.log 2>/dev/null && echo "   ✓ Previous logs found" || echo "   ℹ No previous logs (normal on first run)"
else
    echo "   ✗ /tmp directory not accessible"
fi

echo
echo "=== Test Complete ==="
echo "To test the startup script manually:"
echo "  ./start_clean.sh"
echo
echo "To test the systemd service:"
echo "  sudo systemctl start kitchensync.service"
echo "  sudo systemctl status kitchensync.service"
echo "  tail -f /tmp/kitchensync_system.log"
