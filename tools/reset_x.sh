#!/bin/bash
# Reset script to clear any hanging X11 or Openbox processes.
# Use this when the screen stays black or reports 'Permission Denied'.

echo "Stopping any existing X11 or KitchenSync processes..."
sudo killall -9 Xorg xinit openbox python3 collaborator.py leader.py 2>/dev/null

# Clean up lock files
sudo rm -rf /tmp/.X*-lock /tmp/.X11-unix/X*

echo "X11 state has been reset."
echo "You can now run ./tools/start_x.sh to start a fresh graphical session."
