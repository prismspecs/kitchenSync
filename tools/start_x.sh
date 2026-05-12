#!/bin/bash
# Helper script to start the graphical environment manually for testing.
# Run this from an SSH session to trigger the Pi's local display.

echo "Starting X11 + Openbox on local display (using sudo)..."
# Start X in the background with sudo
sudo nohup startx /usr/bin/openbox-session > /tmp/xstart.log 2>&1 &

echo "Waiting for X server to initialize..."
for i in {1..10}; do
    if DISPLAY=:0 xset q > /dev/null 2>&1; then
        echo "✓ X server is ready on :0"
        exit 0
    fi
    sleep 1
done

echo "✗ X server failed to start. Check /tmp/xstart.log"
exit 1
