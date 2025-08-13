#!/bin/bash
# KitchenSync Auto-Start Script
# This script is called by the systemd service to start KitchenSync
# with proper environment variables for display access

set -e  # Exit on any error

# Log startup attempt
echo "$(date): KitchenSync startup initiated" >> /tmp/kitchensync_startup.log

# Set up X11 display environment variables
export DISPLAY=:0
export XAUTHORITY=/home/kitchensync/.Xauthority
export XDG_RUNTIME_DIR=/run/user/1000

# SDL video driver settings for pygame/overlay
export SDL_VIDEODRIVER=x11

# Force X11 mode (disable Wayland)
export GDK_BACKEND=x11
export QT_QPA_PLATFORM=xcb
export WAYLAND_DISPLAY=

# Ensure we're in the right directory
cd /home/kitchensync/kitchenSync

# Wait for X11 desktop to be ready
echo "$(date): Waiting for X11 desktop to be ready..." >> /tmp/kitchensync_startup.log
desktop_wait=20
desktop_waited=0
while [ $desktop_waited -lt $desktop_wait ]; do
    # Simple check: X server running and wmctrl works
    if pgrep -f "Xorg.*:0" > /dev/null && wmctrl -l > /dev/null 2>&1; then
        echo "$(date): X11 desktop ready after ${desktop_waited}s" >> /tmp/kitchensync_startup.log
        break
    fi
    sleep 2
    desktop_waited=$((desktop_waited + 2))
done

if [ $desktop_waited -ge $desktop_wait ]; then
    echo "$(date): WARNING: X11 desktop not ready after ${desktop_wait}s, proceeding anyway" >> /tmp/kitchensync_startup.log
fi

# Log environment and directory
echo "$(date): Working directory: $(pwd)" >> /tmp/kitchensync_startup.log
echo "$(date): DISPLAY=$DISPLAY" >> /tmp/kitchensync_startup.log
echo "$(date): XAUTHORITY=$XAUTHORITY" >> /tmp/kitchensync_startup.log
echo "$(date): XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR" >> /tmp/kitchensync_startup.log

# Start KitchenSync main script
echo "$(date): Launching kitchensync.py" >> /tmp/kitchensync_startup.log
exec python3 kitchensync.py "$@"
