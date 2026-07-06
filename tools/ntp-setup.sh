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

# Installing chrony


echo "==> Installing chrony..."
sudo apt-get install -y chrony

if [ "$ROLE" = "leader" ]; then
    echo "==> Cleaning up any legacy config in /etc/chrony/chrony.conf..."
    sudo sed -i '/# Serve time to kSync peers/d' /etc/chrony/chrony.conf
    sudo sed -i '/allow 192.168.0.0\/24/d' /etc/chrony/chrony.conf
    sudo sed -i '/local stratum 10/d' /etc/chrony/chrony.conf

    echo "==> Configuring Pi 5 as NTP server via drop-in config..."
    sudo mkdir -p /etc/chrony/conf.d
    sudo tee /etc/chrony/conf.d/ksync.conf <<EOF
# Serve time to kSync peers on local network
allow 192.168.0.0/24
local stratum 10
EOF

    echo "==> Disabling chrony seccomp filter on leader..."
    if [ -f /etc/default/chrony ]; then
        if grep -q "DAEMON_OPTS" /etc/default/chrony; then
            # Add -F 0 if not already present
            if ! grep -q -- "-F 0" /etc/default/chrony; then
                sudo sed -i 's/DAEMON_OPTS="\(.*\)"/DAEMON_OPTS="\1 -F 0"/' /etc/default/chrony
            fi
        else
            echo 'DAEMON_OPTS="-F 0"' | sudo tee -a /etc/default/chrony
        fi
    fi

elif [ "$ROLE" = "collaborator" ]; then
    echo "==> Cleaning up any legacy config in /etc/chrony/chrony.conf..."
    sudo sed -i '/# kSync leader/d' /etc/chrony/chrony.conf
    sudo sed -i '/server .* iburst prefer/d' /etc/chrony/chrony.conf
    sudo sed -i '/minpoll 2/d' /etc/chrony/chrony.conf
    sudo sed -i '/maxpoll 4/d' /etc/chrony/chrony.conf

    echo "==> Configuring Pi 4 to sync from leader at $LEADER_IP via drop-in config..."
    sudo mkdir -p /etc/chrony/conf.d
    sudo tee /etc/chrony/conf.d/ksync.conf <<EOF
# kSync leader (Pi 5) as primary time source
server $LEADER_IP iburst prefer minpoll 2 maxpoll 4
EOF
fi



echo "==> Restarting chrony..."
sudo systemctl restart chrony

echo "==> Waiting 5 seconds for initial sync..."
sleep 5

echo "==> Checking sync status..."
chronyc tracking | grep -E "Reference ID|Stratum|Last offset|RMS offset"

echo ""
echo "Done! Run 'chronyc tracking' anytime to check sync accuracy."
