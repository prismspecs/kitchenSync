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

# Wait for X server (Xorg or Xwayland) to be fully ready
echo "$(date): Waiting for X server to be ready..." >> /tmp/kitchensync_startup.log
max_wait=60
waited=0
while [ $waited -lt $max_wait ]; do
    # Check if X server is running AND responsive
    if (pgrep -f "Xorg.*:0" > /dev/null || pgrep -f "Xwayland.*:0" > /dev/null) && xset q > /dev/null 2>&1; then
        echo "$(date): X server is ready after ${waited}s" >> /tmp/kitchensync_startup.log
        break
    fi
    sleep 2
    waited=$((waited + 2))
done

if [ $waited -ge $max_wait ]; then
    echo "$(date): WARNING: X server not ready after ${max_wait}s, proceeding anyway" >> /tmp/kitchensync_startup.log
fi

# Wait for window manager to be ready (needed for wmctrl)
echo "$(date): Waiting for window manager to be ready..." >> /tmp/kitchensync_startup.log
wm_wait=30
wm_waited=0
while [ $wm_waited -lt $wm_wait ]; do
    # Check if wmctrl can list windows (window manager is responsive)
    if wmctrl -l > /dev/null 2>&1; then
        echo "$(date): Window manager is ready after ${wm_waited}s" >> /tmp/kitchensync_startup.log
        break
    fi
    sleep 2
    wm_waited=$((wm_waited + 2))
done

if [ $wm_waited -ge $wm_wait ]; then
    echo "$(date): WARNING: Window manager not ready after ${wm_wait}s, proceeding anyway" >> /tmp/kitchensync_startup.log
fi

# Log environment and directory
echo "$(date): Working directory: $(pwd)" >> /tmp/kitchensync_startup.log
echo "$(date): DISPLAY=$DISPLAY" >> /tmp/kitchensync_startup.log
echo "$(date): XAUTHORITY=$XAUTHORITY" >> /tmp/kitchensync_startup.log
echo "$(date): XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR" >> /tmp/kitchensync_startup.log

# Start KitchenSync main script
echo "$(date): Launching kitchensync.py" >> /tmp/kitchensync_startup.log
exec python3 kitchensync.py "$@"
