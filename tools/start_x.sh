#!/bin/bash
# Helper script to start the graphical environment manually for testing.
# Run this from an SSH session to trigger the Pi's local display.
#
# NOTE: Must be run as the target user (gsync), NOT with sudo.
# Running startx as root creates an X server root owns, causing
# "Authorization required" errors for VLC/GStreamer.

echo "Starting X11 + Openbox on local display (as $(whoami))..."

# Check if X is already running and ready on :0
if DISPLAY=:0 xset q > /dev/null 2>&1; then
    echo "✓ X server is already running and ready on :0"
    exit 0
fi

# Kill any existing X session on :0
pkill -f "Xorg :0" 2>/dev/null
sleep 1

# Start X as current user in the background
# xinit is lower-level than startx and doesn't require a .xinitrc
nohup xinit /usr/bin/openbox-session -- :0 vt7 > /tmp/xstart.log 2>&1 &

echo "Waiting for X server to initialize..."
for i in {1..15}; do
    if DISPLAY=:0 xset q > /dev/null 2>&1; then
        echo "✓ X server is ready on :0"
        # Make sure XAUTHORITY is accessible to this user
        echo "✓ XAUTHORITY: ${XAUTHORITY:-~/.Xauthority}"
        exit 0
    fi
    sleep 1
done

echo "✗ X server failed to start. Check /tmp/xstart.log"
exit 1
