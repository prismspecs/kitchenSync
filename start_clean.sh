#!/bin/bash
# KitchenSync Auto-Start Script
# This script is called by the systemd service to start KitchenSync
# with proper environment variables for display access

set -e  # Exit on any error

# Log startup attempt
echo "$(date): KitchenSync startup initiated" >> /tmp/kitchensync_startup.log

# Set up X11 display environment variables
export DISPLAY=:0
export XAUTHORITY=/home/$USER/.Xauthority
export XDG_RUNTIME_DIR=/run/user/$(id -u)

# SDL video driver settings for pygame/overlay
export SDL_VIDEODRIVER=x11

# Force X11 mode (disable Wayland) - CRITICAL for Firefox
export GDK_BACKEND=x11
export QT_QPA_PLATFORM=xcb
export WAYLAND_DISPLAY=

# Force Firefox to use X11 (prevent Wayland fallback)
export MOZ_ENABLE_WAYLAND=0
export MOZ_DISABLE_WAYLAND=1
export MOZ_ENABLE_X11=1
export MOZ_DISABLE_RDD_SANDBOX=1
export MOZ_DISABLE_GMP_SANDBOX=1
export MOZ_X11_EGL=1
export MOZ_ACCELERATED=1

# Ensure we're in the right directory
cd /home/$USER/kitchenSync

# Log environment and directory
echo "$(date): Working directory: $(pwd)" >> /tmp/kitchensync_startup.log
echo "$(date): DISPLAY=$DISPLAY" >> /tmp/kitchensync_startup.log
echo "$(date): XAUTHORITY=$XAUTHORITY" >> /tmp/kitchensync_startup.log
echo "$(date): XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR" >> /tmp/kitchensync_startup.log
echo "$(date): WAYLAND_DISPLAY=$WAYLAND_DISPLAY" >> /tmp/kitchensync_startup.log
echo "$(date): MOZ_ENABLE_WAYLAND=$MOZ_ENABLE_WAYLAND" >> /tmp/kitchensync_startup.log

# Verify X11 display is working before proceeding
echo "$(date): Verifying X11 display..." >> /tmp/kitchensync_startup.log
if ! xset q >/dev/null 2>&1; then
    echo "$(date): ERROR: X11 display not ready, waiting..." >> /tmp/kitchensync_startup.log
    # Wait up to 30 seconds for X11 to be ready
    for i in {1..30}; do
        if xset q >/dev/null 2>&1; then
            echo "$(date): X11 display ready after ${i}s" >> /tmp/kitchensync_startup.log
            break
        fi
        sleep 1
    done
    
    if ! xset q >/dev/null 2>&1; then
        echo "$(date): FATAL: X11 display never became ready" >> /tmp/kitchensync_startup.log
        exit 1
    fi
fi

# Start KitchenSync main script
echo "$(date): Launching kitchensync.py" >> /tmp/kitchensync_startup.log
exec python3 kitchensync.py "$@"
