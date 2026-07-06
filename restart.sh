#!/bin/bash
# kSync Quick Update & Restart Utility
# Performs git pull, restarts kitchensync service, and shows logs.

set -e

# Change directory to the script's directory (repo root)
cd "$(dirname "$0")"

echo "==> Pulling latest changes from Git..."
git pull

echo "==> Restarting kitchensync service..."
sudo systemctl restart kitchensync.service

echo "==> Service restarted successfully! Showing last 10 lines of logs:"
echo "------------------------------------------------------------------"
sudo journalctl -u kitchensync.service -n 10 --no-pager
echo "------------------------------------------------------------------"
echo "To monitor logs in real-time, run: journalctl -u kitchensync.service -f"
