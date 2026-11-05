#!/bin/bash
# setup.sh - Consolidated, idempotent setup for a kSync node.
# Supports Raspberry Pi OS (Pi 4/5) and x86 PCs running Debian 13 (e.g. AMD
# mini PCs). Handles GStreamer, X11 permissions, hardware mapping, and UI polishing.
# Steps marked [PC] run only on non-Pi machines; the Pi path is unchanged by them.

set -e # Exit on error

echo "Starting kSync Setup..."

# 0. Platform Detection
# Raspberry Pis expose a device-tree model string; x86 PCs have no device tree.
if grep -qs "Raspberry Pi" /proc/device-tree/model; then
    PLATFORM=pi
else
    PLATFORM=pc
fi
# AMD GPU (PCI vendor 0x1002) selects the amdgpu-specific [PC] steps.
HAS_AMD_GPU=no
if [ "$PLATFORM" = pc ] && grep -qs 0x1002 /sys/class/drm/card*/device/vendor; then
    HAS_AMD_GPU=yes
fi
echo "Platform: $PLATFORM (AMD GPU: $HAS_AMD_GPU)"

# 1. Install System Dependencies
echo "Installing GStreamer and X11 dependencies..."
sudo apt update

PC_PACKAGES=()
if [ "$PLATFORM" = pc ]; then
    # [PC] Raspberry Pi OS ships these; a minimal Debian install doesn't.
    #  - GStreamer GL/X/ALSA plugins + Mesa GL: glimagesink, xvimagesink, HDMI audio
    #  - mesa-va-drivers + vainfo: hardware decode (vah264dec / vah265dec)
    #  - NetworkManager stack (+ polkitd for its permissions, iptables for the
    #    captive-portal redirect): WiFi provisioning and the leader hotspot;
    #    iw shows whether the WiFi chip supports AP (hotspot) mode
    #  - avahi-daemon: reach the node as <hostname>.local, like the Pis
    #  - python3-venv: the .venv below; ffmpeg: media conversion and ffprobe
    PC_PACKAGES=(
        gstreamer1.0-gl gstreamer1.0-x gstreamer1.0-alsa libgl1-mesa-dri
        mesa-va-drivers vainfo
        network-manager wpasupplicant dnsmasq-base iptables rfkill polkitd iw
        avahi-daemon python3-venv ffmpeg
    )
    if [ "$HAS_AMD_GPU" = yes ]; then
        PC_PACKAGES+=(xserver-xorg-video-amdgpu)
        # GPU firmware is in Debian's non-free-firmware component (enabled by
        # the Debian 12+ installer). Without it amdgpu can't start at all.
        if apt-cache show firmware-amd-graphics >/dev/null 2>&1; then
            PC_PACKAGES+=(firmware-amd-graphics)
        else
            echo "WARNING: firmware-amd-graphics not available. Add 'non-free-firmware' to the"
            echo "         components in /etc/apt/sources.list, then re-run setup.sh."
        fi
    fi
fi

sudo apt install -y --no-install-recommends \
    xserver-xorg xinit openbox x11-xserver-utils xserver-xorg-legacy \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-libav \
    gstreamer1.0-tools python3-gst-1.0 gir1.2-gst-plugins-base-1.0 \
    unclutter wmctrl v4l-utils "${PC_PACKAGES[@]}"

# 2. X Server Permissions & Legacy Mode
echo "Configuring X Server permissions..."
sudo usermod -a -G video,render,tty $USER

# Configure Xwrapper for non-root X
XWRAPPER="/etc/X11/Xwrapper.config"
sudo touch $XWRAPPER
grep -q "allowed_users=anybody" $XWRAPPER || echo "allowed_users=anybody" | sudo tee -a $XWRAPPER
grep -q "needs_root_rights=yes" $XWRAPPER || echo "needs_root_rights=yes" | sudo tee -a $XWRAPPER

# 3. Xorg Hardware Mapping
sudo mkdir -p /etc/X11/xorg.conf.d
if [ "$PLATFORM" = pi ]; then
    # Force card1 for Pi 5
    echo "Applying Xorg hardware mapping for Pi 5..."
    sudo tee /etc/X11/xorg.conf.d/99-vc4.conf <<EOF
Section "Device"
    Identifier "VC4"
    Driver "modesetting"
    Option "kmsdev" "/dev/dri/card1"
EndSection

Section "Screen"
    Identifier "Default Screen"
    Device "VC4"
EndSection
EOF
else
    # [PC] The Pi mapping points X at the Pi's display device. Remove it in
    # case an older setup.sh wrote it on this machine.
    sudo rm -f /etc/X11/xorg.conf.d/99-vc4.conf
    if [ "$HAS_AMD_GPU" = yes ]; then
        # TearFree stops video tearing under Openbox (no compositor).
        echo "Configuring amdgpu (TearFree)..."
        sudo tee /etc/X11/xorg.conf.d/20-amdgpu.conf >/dev/null <<EOF
Section "Device"
    Identifier "AMD"
    Driver "amdgpu"
    Option "TearFree" "true"
EndSection
EOF
    fi
    # [PC] Keep the screens on. Xorg blanks after 10 idle minutes by default
    # and video playback doesn't count as activity.
    echo "Disabling screen blanking..."
    sudo tee /etc/X11/xorg.conf.d/10-ksync-noblank.conf >/dev/null <<EOF
Section "ServerFlags"
    Option "BlankTime" "0"
    Option "StandbyTime" "0"
    Option "SuspendTime" "0"
    Option "OffTime" "0"
EndSection
EOF
fi

# 4. Openbox UI Polishing (Borderless & Fullscreen)
echo "Configuring Openbox for borderless operation..."
mkdir -p ~/.config/openbox
if [ ! -f ~/.config/openbox/rc.xml ]; then
    cp /etc/xdg/openbox/rc.xml ~/.config/openbox/rc.xml
fi

# Use Python to idempotently insert the borderless rule
python3 - <<EOF
import os
config_path = os.path.expanduser("~/.config/openbox/rc.xml")
with open(config_path, 'r') as f:
    lines = f.readlines()

new_rule = [
    '  <application class="*">\n',
    '    <decor>no</decor>\n',
    '    <fullscreen>yes</fullscreen>\n',
    '  </application>\n'
]

content = "".join(lines)
if '<decor>no</decor>' not in content:
    with open(config_path, 'w') as f:
        for line in lines:
            if '</applications>' in line:
                f.writelines(new_rule)
            f.write(line)
EOF

# 5. Autostart Configuration (Mouse hiding)
echo "Configuring autostart..."
mkdir -p ~/.config/openbox
AUTOSTART=~/.config/openbox/autostart
# Fix ownership in case it was created as root by mistake
sudo chown -R $USER:$USER ~/.config/openbox
touch $AUTOSTART
grep -q "unclutter" $AUTOSTART || echo "unclutter -idle 0.1 -root &" >> $AUTOSTART

# 6. Python Virtual Environment
echo "Setting up Python virtual environment..."
VENV_DIR="$PWD/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
    echo "Virtual environment created at $VENV_DIR"
fi

echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

# 7. Systemd Service Configuration
# NOTE: the unit generated below is the ONLY source of truth for the service.
# (A stale kitchensync.service was once tracked in the repo and misled people.)
echo "Configuring systemd service..."
CURRENT_USER=$(whoami)
INSTALL_DIR=$(pwd)
VENV_PYTHON="$VENV_DIR/bin/python3"

# Create a clean service file with dynamic paths
sudo tee /etc/systemd/system/kitchensync.service <<EOF
[Unit]
Description=kSync Universal Node
After=network.target
# We don't depend on graphical.target because we start our own X session if needed

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR/src
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$CURRENT_USER/.Xauthority
# Ensure the node can start X if it's not already running
ExecStartPre=$INSTALL_DIR/tools/start_x.sh
# Launch the universal bootstrapper
ExecStart=$VENV_PYTHON kitchensync.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "Enabling kitchensync.service..."
sudo systemctl daemon-reload
sudo systemctl enable kitchensync.service

# 8. WiFi Provisioning Prerequisites (see docs/WIFI_PROVISIONING.md)
echo "Configuring WiFi provisioning prerequisites..."
# netdev membership lets the service user drive NetworkManager via nmcli.
# (A minimal Debian install may not have the group yet.)
getent group netdev >/dev/null || sudo groupadd --system netdev
sudo usermod -a -G netdev $USER
if [ "$PLATFORM" = pc ]; then
    # [PC] Debian's own NetworkManager rule only covers a user signed in at the
    # desktop. The kSync service runs with no session, so grant netdev directly.
    sudo mkdir -p /etc/polkit-1/rules.d
    sudo tee /etc/polkit-1/rules.d/50-ksync-networkmanager.rules >/dev/null <<'EOF'
// Written by kSync setup.sh: let the netdev group (the kSync service user)
// manage NetworkManager without a desktop session (WiFi setup + hotspot).
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager.") == 0 &&
        subject.isInGroup("netdev")) {
        return polkit.Result.YES;
    }
});
EOF
fi
# WiFi is soft-blocked out of the box on some images
sudo rfkill unblock wifi || true
# AP (hotspot) mode silently fails while the regulatory domain is unset;
# fresh images ship with it unset until the user picks a country.
if command -v raspi-config >/dev/null 2>&1; then
    WIFI_COUNTRY=$(raspi-config nonint get_wifi_country 2>/dev/null || true)
    if [ -z "$WIFI_COUNTRY" ]; then
        echo "WiFi country not set - defaulting to US (change with: sudo raspi-config nonint do_wifi_country <CC>)"
        sudo raspi-config nonint do_wifi_country US || true
    fi
fi

# Captive portal (leader hotspot only):
# 1) resolve every hostname on the hotspot to the leader so joining phones
#    hit the setup page (NetworkManager runs dnsmasq in shared mode);
# 2) redirect the hotspot's port 80 to the portal server (port 8081) —
#    a dispatcher script adds/removes the rule with the hotspot itself.
sudo mkdir -p /etc/NetworkManager/dnsmasq-shared.d
echo "address=/#/10.42.0.1" | sudo tee /etc/NetworkManager/dnsmasq-shared.d/ksync-portal.conf >/dev/null

sudo tee /etc/NetworkManager/dispatcher.d/90-ksync-portal >/dev/null <<'EOF'
#!/bin/bash
# kSync captive portal: redirect hotspot HTTP (80) to the portal (8081).
# Runs as root on every connection event; only acts on the kSync hotspot.
IFACE="$1"; ACTION="$2"
[ "$CONNECTION_ID" = "ksync-hotspot" ] || exit 0
RULE=(-i "$IFACE" -p tcp --dport 80 -j REDIRECT --to-ports 8081)
case "$ACTION" in
    up)
        iptables -t nat -C PREROUTING "${RULE[@]}" 2>/dev/null || \
        iptables -t nat -A PREROUTING "${RULE[@]}"
        ;;
    down)
        iptables -t nat -D PREROUTING "${RULE[@]}" 2>/dev/null || true
        ;;
esac
EOF
sudo chmod 755 /etc/NetworkManager/dispatcher.d/90-ksync-portal

# 9. Sudo Permissions (password-less reboot for remote update)
echo "Setting up sudo permissions..."
echo "$CURRENT_USER ALL=(ALL) NOPASSWD: /sbin/reboot, /usr/sbin/reboot, /sbin/shutdown, /usr/sbin/shutdown, /bin/systemctl, /usr/bin/systemctl" | sudo tee /etc/sudoers.d/ksync-reboot
sudo chmod 440 /etc/sudoers.d/ksync-reboot

# 10. [PC] USB Auto-mount
# kSync looks for ksync.ini and media on USB sticks mounted under /media/.
# A minimal Debian install mounts nothing by itself, so a udev rule mounts
# each USB partition at /media/usb-<name> as it appears. systemd unmounts it
# when the stick is pulled.
if [ "$PLATFORM" = pc ]; then
    echo "Configuring USB auto-mount..."
    sudo tee /usr/local/sbin/ksync-usb-mount >/dev/null <<'EOF'
#!/bin/sh
# Written by kSync setup.sh. udev (90-ksync-usb-automount.rules) runs this for
# each new USB partition and mounts it at /media/usb-<name>.
DEV="/dev/$1"
# Leave alone anything already mounted (e.g. booting from a USB disk).
findmnt -rn --source "$DEV" >/dev/null 2>&1 && exit 0
OPTS="noatime"
TYPE_ARG=""
case "$ID_FS_TYPE" in
    # These filesystems have no file owners: mount them as the kSync user so
    # it can write (media uploads, config saves).
    vfat|exfat) OPTS="$OPTS,uid=@KSYNC_UID@,gid=@KSYNC_GID@,umask=022" ;;
    ntfs) OPTS="$OPTS,uid=@KSYNC_UID@,gid=@KSYNC_GID@,umask=022"; TYPE_ARG="-t ntfs3" ;;
esac
exec systemd-mount --no-block --collect $TYPE_ARG -o "$OPTS" "$DEV" "/media/usb-$1"
EOF
    sudo sed -i "s/@KSYNC_UID@/$(id -u)/g; s/@KSYNC_GID@/$(id -g)/g" /usr/local/sbin/ksync-usb-mount
    sudo chmod 755 /usr/local/sbin/ksync-usb-mount
    sudo tee /etc/udev/rules.d/90-ksync-usb-automount.rules >/dev/null <<'EOF'
# Written by kSync setup.sh: auto-mount USB partitions under /media/usb-<name>.
ACTION=="add", SUBSYSTEM=="block", ENV{ID_BUS}=="usb", ENV{ID_FS_USAGE}=="filesystem", RUN+="/usr/local/sbin/ksync-usb-mount %k"
EOF
    sudo udevadm control --reload-rules
fi

# 11. [PC] Hand Networking to NetworkManager
# The Debian installer sets up the network with ifupdown (/etc/network/interfaces)
# and NetworkManager ignores every interface listed there. kSync's WiFi
# provisioning needs NetworkManager to own them. This takes effect on the next
# reboot, so an SSH session running this script stays up.
IFACES=/etc/network/interfaces
# The installer makes this file root-only when it holds a WiFi password.
IFACES_TEXT=""
if [ "$PLATFORM" = pc ] && [ -f "$IFACES" ]; then
    IFACES_TEXT=$(sudo cat "$IFACES")
fi
if printf '%s\n' "$IFACES_TEXT" | grep -E '^[[:space:]]*iface[[:space:]]' | \
   grep -qvE '^[[:space:]]*iface[[:space:]]+lo[[:space:]]'; then
    echo "Handing network interfaces from ifupdown to NetworkManager..."
    [ -e "$IFACES.ksync-bak" ] || sudo cp -p "$IFACES" "$IFACES.ksync-bak"
    # Carry over WiFi credentials entered in the installer.
    WIFI_SSID=$(printf '%s\n' "$IFACES_TEXT" | awk '$1=="wpa-ssid"{$1=""; sub(/^[ \t]+/,""); gsub(/^"|"$/,""); print; exit}')
    WIFI_PSK=$(printf '%s\n' "$IFACES_TEXT" | awk '$1=="wpa-psk"{$1=""; sub(/^[ \t]+/,""); gsub(/^"|"$/,""); print; exit}')
    if [ -n "$WIFI_SSID" ] && ! nmcli -t -f NAME connection show | grep -qxF "$WIFI_SSID"; then
        NM_ARGS=(type wifi con-name "$WIFI_SSID" ssid "$WIFI_SSID")
        if [ -n "$WIFI_PSK" ]; then
            NM_ARGS+=(wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$WIFI_PSK")
        fi
        sudo nmcli connection add "${NM_ARGS[@]}" >/dev/null
        echo "Moved WiFi network '$WIFI_SSID' to NetworkManager."
    fi
    sudo tee "$IFACES" >/dev/null <<'EOF'
# kSync setup.sh: networking is managed by NetworkManager.
# The installer's original file is saved as /etc/network/interfaces.ksync-bak.
source /etc/network/interfaces.d/*

auto lo
iface lo inet loopback
EOF
    echo "NOTE: after the reboot this machine may get a new IP address."
    echo "      Reach it as $(hostname).local, or check your router."
fi

echo "-------------------------------------------------------"
echo "Setup Complete! Please REBOOT for changes to take effect."
echo "Upon reboot, the node will automatically:"
echo " 1. Start X11/Openbox"
echo " 2. Search for ksync.ini on USB root"
echo " 3. Assume the configured Role (Leader/Collaborator/Bystander)"
if [ "$PLATFORM" = pc ]; then
    echo "Check hardware decode after the reboot with: vainfo"
fi
echo "-------------------------------------------------------"
