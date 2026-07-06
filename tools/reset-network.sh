#!/bin/bash
# kSync OS Network Config Reset Utility
# Resets Ethernet interface back to standard DHCP client settings.

set -e

# Detect OS Codename
OS_CODENAME=$(cat /etc/os-release | grep VERSION_CODENAME | cut -d= -f2 | tr -d '"')
echo "==> Detected OS Codename: $OS_CODENAME"

if which nmcli >/dev/null 2>&1; then
    echo "==> Resetting NetworkManager (nmcli detected)..."
    
    # Find active Ethernet connection
    ETH_CONN=$(nmcli -t -f NAME,TYPE connection show --active | grep ethernet | cut -d: -f1 | head -n 1 || true)
    
    if [ -z "$ETH_CONN" ]; then
        # Fallback to default name if not currently active
        ETH_CONN="Wired connection 1"
    fi
    
    echo "==> Resetting connection '$ETH_CONN' to automatic DHCP..."
    sudo nmcli connection modify "$ETH_CONN" \
        ipv4.method auto \
        ipv4.addresses "" \
        ipv4.gateway "" \
        ipv4.dns "" \
        ipv4.route-metric -1
        
    echo "==> Re-applying network settings..."
    sudo nmcli connection up "$ETH_CONN" || true
    
elif [ -f /etc/dhcpcd.conf ]; then
    echo "==> Resetting dhcpcd (/etc/dhcpcd.conf detected)..."

        # Create a backup of dhcpcd.conf
        sudo cp /etc/dhcpcd.conf /etc/dhcpcd.conf.bak
        echo "==> Created backup at /etc/dhcpcd.conf.bak"
        
        # Remove lines at the end of dhcpcd.conf containing static/nogateway overrides
        # We search for lines starting with 'interface eth0' and remove them plus subsequent configuration lines.
        # Alternatively, we can use sed to comment out the blocks.
        # Let's comment out lines matching the eth0 interface block
        sudo sed -i '/^interface eth0/,/^[a-zA-Z]/ { /^[a-zA-Z]/! s/^/# /; /^interface eth0/ s/^/# / }' /etc/dhcpcd.conf
        
        echo "==> Restarting dhcpcd service..."
        sudo systemctl restart dhcpcd
    else
        echo "❌ Error: /etc/dhcpcd.conf not found."
        exit 1
    fi
else
    echo "❌ Error: Neither NetworkManager (nmcli) nor dhcpcd (/etc/dhcpcd.conf) was detected on this system."
    exit 1
fi

echo "==> Network reset complete. Verifying new routes:"
echo "--------------------------------------------------"
ip route
echo "--------------------------------------------------"
echo "Testing internet connectivity..."
ping -c 3 google.com || echo "⚠️  Warning: Could not ping google.com. Check connection to the router."
