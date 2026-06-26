#!/bin/bash
# Setup chrony NTP sync between Pi 5 (leader) and Pi 4 (collaborator)
# Temporarily takes eth0 down so internet-bound traffic routes through WiFi.
#
# Usage:
#   On Pi 5 (leader):  bash ntp-setup.sh leader
#   On Pi 4 (collab):  bash ntp-setup.sh collaborator 192.168.0.165

set -e

ROLE="${1:-}"
LEADER_IP="${2:-192.168.0.165}"
ETH_IFACE="${3:-eth0}"

if [ -z "$ROLE" ]; then
    echo "Usage: $0 <leader|collaborator> [leader_ip] [eth_iface]"
    exit 1
fi

# Check if eth0 is up — if so, we need to temporarily take it down so
# apt-get can route through WiFi (ethernet has no internet on our setup).
ETH_WAS_UP=false
if ip link show "$ETH_IFACE" 2>/dev/null | grep -q "state UP"; then
    echo "==> $ETH_IFACE is up — taking it down temporarily for internet access..."
    ETH_WAS_UP=true
    sudo ip link set "$ETH_IFACE" down
    # Wait for route to switch to WiFi
    sleep 2
fi

cleanup() {
    if [ "$ETH_WAS_UP" = true ]; then
        echo "==> Restoring $ETH_IFACE..."
        sudo ip link set "$ETH_IFACE" up
        sleep 1
    fi
}
trap cleanup EXIT

echo "==> Installing chrony..."
sudo apt-get install -y chrony

if [ "$ROLE" = "leader" ]; then
    echo "==> Configuring Pi 5 as NTP server..."
    echo "" | sudo tee -a /etc/chrony/chrony.conf
    echo "# Serve time to kSync peers on local network" | sudo tee -a /etc/chrony/chrony.conf
    echo "allow 192.168.0.0/24" | sudo tee -a /etc/chrony/chrony.conf
    echo "local stratum 10" | sudo tee -a /etc/chrony/chrony.conf

elif [ "$ROLE" = "collaborator" ]; then
    echo "==> Configuring Pi 4 to sync from leader at $LEADER_IP..."
    echo "" | sudo tee -a /etc/chrony/chrony.conf
    echo "# kSync leader (Pi 5) as primary time source" | sudo tee -a /etc/chrony/chrony.conf
    echo "server $LEADER_IP iburst prefer" | sudo tee -a /etc/chrony/chrony.conf
    echo "minpoll 2" | sudo tee -a /etc/chrony/chrony.conf
    echo "maxpoll 4" | sudo tee -a /etc/chrony/chrony.conf
fi

echo "==> Restarting chrony..."
sudo systemctl restart chrony

echo "==> Waiting 5 seconds for initial sync..."
sleep 5

echo "==> Checking sync status..."
chronyc tracking | grep -E "Reference ID|Stratum|Last offset|RMS offset"

echo ""
echo "Done! Run 'chronyc tracking' anytime to check sync accuracy."
