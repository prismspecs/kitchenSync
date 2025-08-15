#!/bin/bash
# KitchenSync Auto-Start Script
# This script is called by the systemd service to start KitchenSync
# with proper environment variables for display access

set -e  # Exit on any error
set -x  # Enable debug tracing to show each command execution

# Function to archive logs with rotation (max 1000 lines per archive)
archive_log() {
    local current_log="$1"
    local archive_log="$2"
    local max_lines=1000
    
    if [[ -f "$current_log" ]]; then
        echo "$(date): Archiving $current_log -> $archive_log" >> /tmp/kitchensync_startup.log
        
        # If archive exists, combine current + archive, keep only last 1000 lines
        if [[ -f "$archive_log" ]]; then
            # Append current log to archive, then keep only last 1000 lines
            cat "$current_log" >> "$archive_log"
            tail -n "$max_lines" "$archive_log" > "${archive_log}.tmp"
            mv "${archive_log}.tmp" "$archive_log"
        else
            # First time: just move current to archive (but limit to 1000 lines)
            tail -n "$max_lines" "$current_log" > "$archive_log"
        fi
        
        # Remove current log to start fresh
        rm "$current_log"
        echo "$(date): Archived $(wc -l < "$archive_log" 2>/dev/null || echo "0") lines to $archive_log" >> /tmp/kitchensync_startup.log
    fi
}

# Archive existing logs before starting
echo "$(date): KitchenSync startup initiated - archiving old logs" >> /tmp/kitchensync_startup.log

# Archive each log type (system, VLC, debug, stderr/stdout)
archive_log "/tmp/kitchensync_system.log" "/tmp/kitchensync_system_archive.log"
archive_log "/tmp/kitchensync_vlc.log" "/tmp/kitchensync_vlc_archive.log"
archive_log "/tmp/kitchensync_leader_debug.txt" "/tmp/kitchensync_debug_archive.log"
archive_log "/tmp/kitchensync_vlc_stderr.log" "/tmp/kitchensync_vlc_stderr_archive.log"
archive_log "/tmp/kitchensync_vlc_stdout.log" "/tmp/kitchensync_vlc_stdout_archive.log"

echo "$(date): Log archiving complete, starting fresh logs" >> /tmp/kitchensync_startup.log

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
