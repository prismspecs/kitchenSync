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

# Ensure we're in the right directory
cd /home/kitchensync/kitchenSync

# Log environment and directory
echo "$(date): Working directory: $(pwd)" >> /tmp/kitchensync_startup.log
echo "$(date): DISPLAY=$DISPLAY" >> /tmp/kitchensync_startup.log
echo "$(date): XAUTHORITY=$XAUTHORITY" >> /tmp/kitchensync_startup.log
echo "$(date): XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR" >> /tmp/kitchensync_startup.log

# Start KitchenSync main script
echo "$(date): Launching kitchensync.py" >> /tmp/kitchensync_startup.log
exec python3 kitchensync.py "$@"
