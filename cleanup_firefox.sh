#!/bin/bash
# KitchenSync Firefox Cleanup Script
# This script cleans up any leftover Firefox processes and profile directories
# Run this if you notice Firefox tabs accumulating or if the service doesn't start cleanly

echo "🧹 Cleaning up Firefox processes and profiles..."

# Kill any running Firefox processes
echo "Killing Firefox processes..."
pkill -f firefox 2>/dev/null || echo "No Firefox processes found"

# Wait a moment for processes to close
sleep 2

# Clean up profile directories
echo "Cleaning up profile directories..."
for profile_dir in /tmp/firefox-debug-profile*; do
    if [ -d "$profile_dir" ]; then
        echo "Removing: $profile_dir"
        rm -rf "$profile_dir"
    fi
done

# Clean up any other temporary Firefox files
echo "Cleaning up temporary Firefox files..."
find /tmp -name "*firefox*" -type d -exec rm -rf {} + 2>/dev/null || true
find /tmp -name "*firefox*" -type f -delete 2>/dev/null || true

# Check if cleanup was successful
if pgrep -f firefox >/dev/null; then
    echo "⚠️  Some Firefox processes are still running. You may need to force kill them:"
    echo "   sudo pkill -9 -f firefox"
else
    echo "✅ Firefox cleanup completed successfully"
fi

echo "Cleanup script finished"
