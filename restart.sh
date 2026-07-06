#!/bin/bash
# kSync Quick Update & Restart Utility
# Performs git pull, restarts kitchensync service, and shows logs.

set -e

# Change directory to the script's directory (repo root)
cd "$(dirname "$0")"

ETH_IFACE="eth0"
WIFI_IFACE="wlan0"
IF_DOWN=false

# If on a Pi and both Ethernet and WiFi are active, temporarily drop Ethernet
# to force traffic (like git pull and NTP) over the internet-connected WiFi.
if [ -f /proc/device-tree/model ] && ip link show "$ETH_IFACE" 2>/dev/null | grep -q "state UP" && ip link show "$WIFI_IFACE" 2>/dev/null | grep -q "state UP"; then
    echo "==> Detected Pi with both Ethernet and WiFi active."
    echo "==> Temporarily taking $ETH_IFACE down to route git pull over WiFi..."
    sudo ip link set "$ETH_IFACE" down
    IF_DOWN=true
    sleep 2
fi

echo "==> Pulling latest changes from Git..."
git -c http.sslVerify=false pull

if [ "$IF_DOWN" = true ]; then
    echo "==> Restoring $ETH_IFACE..."
    sudo ip link set "$ETH_IFACE" up
    sleep 1
fi


echo "==> Restarting kitchensync service..."
sudo systemctl restart kitchensync.service

echo "==> Service restarted successfully! Showing last 10 lines of logs:"
echo "------------------------------------------------------------------"
sudo journalctl -u kitchensync.service -n 10 --no-pager
echo "------------------------------------------------------------------"
echo "To monitor logs in real-time, run: journalctl -u kitchensync.service -f"
