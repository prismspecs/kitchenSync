#!/bin/bash
# SSH Test Script for KitchenSync
# This script sets up the proper environment for testing video playback via SSH

echo "🧪 KitchenSync SSH Test Environment"
echo "=================================="

# Set up environment variables for video/audio
export DISPLAY=:0
export PULSE_SERVER=unix:/run/user/1000/pulse/native
export XDG_RUNTIME_DIR=/run/user/1000

# Check if X11 is running
if ! xset q &>/dev/null; then
    echo "⚠️  X11 display not available - video may not show"
    echo "💡 This is normal when testing via SSH"
    echo "📺 Video will work normally when started via systemd service on boot"
    echo ""
fi

# Check if audio system is available
if ! pulseaudio --check -v &>/dev/null; then
    echo "⚠️  PulseAudio not running - audio may not work"
    echo ""
fi

echo "🚀 Starting KitchenSync with SSH-compatible environment..."
echo "Press Ctrl+C to stop"
echo ""

# Run with proper environment
python3 kitchensync.py
