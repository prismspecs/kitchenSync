#!/bin/bash
# Setup chrony NTP sync between Pi 5 (leader) and Pi 4 (collaborator)
# Run with: bash ntp-setup.sh [leader|collaborator] [leader_ip]
#
# Examples:
#   On Pi 5:  bash ntp-setup.sh leader
#   On Pi 4:  bash ntp-setup.sh collaborator 192.168.0.165

set -e

ROLE="${1:-}"
LEADER_IP="${2:-192.168.0.165}"

if [ -z "$ROLE" ]; then
    echo "Usage: $0 <leader|collaborator> [leader_ip]"
    exit 1
fi

echo "==> Installing chrony..."
sudo apt-get install -y chrony

if [ "$ROLE" = "leader" ]; then
    echo "==> Configuring Pi 5 as NTP server..."
    # Append config to serve time locally
    echo "" | sudo tee -a /etc/chrony/chrony.conf
    echo "# Serve time to kSync peers on local network" | sudo tee -a /etc/chrony/chrony.conf
    echo "allow 192.168.0.0/24" | sudo tee -a /etc/chrony/chrony.conf
    echo "local stratum 10" | sudo tee -a /etc/chrony/chrony.conf

elif [ "$ROLE" = "collaborator" ]; then
    echo "==> Configuring Pi 4 to sync from leader at $LEADER_IP..."
    # Add leader as preferred NTP source
    echo "" | sudo tee -a /etc/chrony/chrony.conf
    echo "# kSync leader (Pi 5) as primary time source" | sudo tee -a /etc/chrony/chrony.conf
    echo "server $LEADER_IP iburst prefer" | sudo tee -a /etc/chrony/chrony.conf
    # Reduce polling interval for faster sync
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
