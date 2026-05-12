#!/bin/bash
# hide_mouse.sh - Installs and configures unclutter to hide the mouse cursor

echo "Installing unclutter to hide mouse cursor..."
sudo apt update && sudo apt install -y unclutter

# Add to openbox autostart if not already there
mkdir -p ~/.config/openbox
TOUCH_AUTOSTART=~/.config/openbox/autostart

if [ -f "$TOUCH_AUTOSTART" ]; then
    if ! grep -q "unclutter" "$TOUCH_AUTOSTART"; then
        echo "unclutter -idle 0.1 -root &" >> "$TOUCH_AUTOSTART"
        echo "Added unclutter to Openbox autostart."
    fi
else
    echo "unclutter -idle 0.1 -root &" > "$TOUCH_AUTOSTART"
    echo "Created Openbox autostart with unclutter."
fi

# Start it immediately for the current session
DISPLAY=:0 unclutter -idle 0.1 -root &

echo "-----------------------------------------------"
echo "Mouse should hide after 0.1s of inactivity."
echo "-----------------------------------------------"
