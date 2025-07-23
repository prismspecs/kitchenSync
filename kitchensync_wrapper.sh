#!/bin/bash
# KitchenSync Service Wrapper
# Ensures proper environment for VLC and audio

# Wait for X11 display to be available
echo "Waiting for X11 display..."
for i in {1..30}; do
    if xset q >/dev/null 2>&1; then
        echo "✅ X11 display ready"
        break
    fi
    sleep 1
done

# Wait for PulseAudio to be ready
echo "Waiting for PulseAudio..."
for i in {1..30}; do
    if pulseaudio --check >/dev/null 2>&1 || pactl info >/dev/null 2>&1; then
        echo "✅ PulseAudio ready"
        break
    fi
    sleep 1
done

# Wait for USB drives to be mounted
echo "Waiting for USB drives..."
sleep 5

# Set up audio environment
export PULSE_SERVER="unix:/run/user/1000/pulse/native"

# Ensure VLC can access the display
xhost +local: 2>/dev/null || true

echo "🎬 Starting KitchenSync..."
cd /home/kitchensync/kitchenSync
exec python3 kitchensync.py
