#!/bin/bash
# Clean startup script for KitchenSync
# Ensures clean environment regardless of how service is started

echo "🧹 Cleaning environment for KitchenSync..."

# Unset SSH-related variables that can interfere
unset SSH_CLIENT
unset SSH_CONNECTION
unset SSH_TTY
unset SSH_AUTH_SOCK
unset SSH_AGENT_PID

# Set clean display environment
export DISPLAY=:0
export XAUTHORITY=/home/kitchensync/.Xauthority
export XDG_RUNTIME_DIR=/run/user/1000
export HOME=/home/kitchensync
export USER=kitchensync
export LOGNAME=kitchensync

# Clear any conflicting environment
unset SDL_VIDEODRIVER
unset SDL_VIDEO_GL
unset SDL_VIDEO_OPENGL

echo "✅ Environment cleaned"
echo "   DISPLAY: $DISPLAY"
echo "   XAUTHORITY: $XAUTHORITY"
echo "   USER: $USER"

# Start the actual service
exec /usr/bin/python3 /home/kitchensync/kitchenSync/kitchensync.py "$@"
