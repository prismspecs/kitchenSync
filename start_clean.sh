#!/bin/bash
# KitchenSync Auto-Start Script
# This script is called by the systemd service to start KitchenSync
# with proper environment variables for display access

set -e  # Exit on any error

# Log startup attempt
echo "$(date): KitchenSync startup initiated" >> /tmp/kitchensync_startup.log

# Set up X11 display environment variables
export DISPLAY=:0
export XDG_RUNTIME_DIR=/run/user/1000

# Find the correct XAUTHORITY file (may vary by user)
if [ -f "/home/$USER/.Xauthority" ]; then
    export XAUTHORITY="/home/$USER/.Xauthority"
elif [ -f "/home/kitchensync/.Xauthority" ]; then
    export XAUTHORITY="/home/kitchensync/.Xauthority"
else
    echo "$(date): Warning: No .Xauthority file found" >> /tmp/kitchensync_startup.log
fi

# SDL video driver settings for pygame/overlay
export SDL_VIDEODRIVER=x11

# Force X11 mode (disable Wayland)
export GDK_BACKEND=x11
export QT_QPA_PLATFORM=xcb
export WAYLAND_DISPLAY=

# Ensure we're in the right directory
cd /home/kitchensync/kitchenSync

# Wait for desktop environment to be fully ready
echo "$(date): Waiting for desktop environment..." >> /tmp/kitchensync_startup.log

# Check if X11 is running and window manager is available
for i in {1..30}; do
    if xset q >/dev/null 2>&1 && wmctrl -l >/dev/null 2>&1; then
        echo "$(date): Desktop environment ready (attempt $i)" >> /tmp/kitchensync_startup.log
        break
    fi
    echo "$(date): Desktop not ready, waiting... (attempt $i/30)" >> /tmp/kitchensync_startup.log
    sleep 2
done

# Additional wait for window manager to stabilize
sleep 5

# Log environment and directory
echo "$(date): Working directory: $(pwd)" >> /tmp/kitchensync_startup.log
echo "$(date): DISPLAY=$DISPLAY" >> /tmp/kitchensync_startup.log
echo "$(date): XAUTHORITY=$XAUTHORITY" >> /tmp/kitchensync_startup.log
echo "$(date): XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR" >> /tmp/kitchensync_startup.log

# Start KitchenSync main script
echo "$(date): Launching kitchensync.py" >> /tmp/kitchensync_startup.log
exec python3 kitchensync.py "$@"
