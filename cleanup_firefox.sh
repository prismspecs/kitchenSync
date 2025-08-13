#!/bin/bash
# KitchenSync Firefox Cleanup Script
# This script cleans up Firefox processes and the clean profile directory

echo "🧹 Cleaning up Firefox processes and profile..."

# Kill any running Firefox processes
echo "Killing Firefox processes..."
pkill -f firefox 2>/dev/null || echo "No Firefox processes found"

# Wait a moment for processes to close
sleep 2

# Clean up the clean profile directory
echo "Cleaning up profile directory..."
if [ -d "/tmp/ff-clean-profile" ]; then
    echo "Removing: /tmp/ff-clean-profile"
    rm -rf "/tmp/ff-clean-profile"
else
    echo "No profile directory found"
fi

# Check if cleanup was successful
if pgrep -f firefox >/dev/null; then
    echo "⚠️  Some Firefox processes are still running. You may need to force kill them:"
    echo "   sudo pkill -9 -f firefox"
else
    echo "✅ Firefox cleanup completed successfully"
fi

echo "Cleanup script finished"
