#!/bin/bash
# KitchenSync Setup Script

echo "=== KitchenSync Setup ==="

# Check for Raspberry Pi OS version
PI_VERSION=$(grep VERSION_CODENAME /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')

# Fix APT cache corruption if it exists
echo "Checking APT cache integrity..."
if ! sudo apt update 2>/dev/null; then
    echo "APT cache corruption detected, fixing..."
    sudo rm -rf /var/lib/apt/lists/*
    echo "Updating package lists..."
    sudo apt update
else
    echo "APT cache is healthy"
fi

# Install VLC and dependencies
echo "Installing VLC and dependencies..."
sudo apt install -y vlc libvlc-dev python3-vlc python3-pip python3-dev libasound2-dev alsa-utils

# Install USB mounting utilities
echo "Installing USB mounting utilities..."
sudo apt install -y udisks2 usbutils

# Install dbus development libraries (needed for dbus-python)
echo "Installing dbus development libraries..."
sudo apt install -y libdbus-1-dev libglib2.0-dev

# Install required packages
sudo apt-get update
sudo apt-get install -y python3-pip python3-vlc vlc
sudo apt-get install -y wmctrl  # For window management

# Create media directories for USB mounting
echo "Setting up USB mount points..."
sudo mkdir -p /media/usb /media/usb0 /media/usb1
sudo chown -R $USER:$USER /media/usb* 2>/dev/null || true

# Add user to necessary groups for USB access
echo "Configuring USB access permissions..."
sudo usermod -a -G plugdev,disk $USER

# Install Python packages system-wide
echo "Installing Python packages system-wide..."
sudo pip install python-rtmidi dbus-python python-vlc --break-system-packages

# --- OS Optimizations ---
echo "Applying OS optimizations..."

# Disable unnecessary services
echo "Disabling unused services (Bluetooth, CUPS, etc.)..."
sudo systemctl disable bluetooth.service hciuart.service > /dev/null 2>&1 || true
sudo systemctl disable cups.service > /dev/null 2>&1 || true
sudo systemctl disable triggerhappy.service > /dev/null 2>&1 || true
sudo systemctl disable avahi-daemon.service > /dev/null 2>&1 || true

# Remove unused software packages
echo "Removing unnecessary software (Wolfram, LibreOffice, etc.)..."
sudo apt-get purge -y wolfram-engine sonic-pi scratch nuscratch smartsim libreoffice* > /dev/null 2>&1
sudo apt-get autoremove -y > /dev/null 2>&1
sudo apt-get clean > /dev/null 2>&1

# Optimize boot configuration
echo "Optimizing boot configuration..."
if ! grep -q "disable_splash=1" /boot/config.txt; then
    echo "disable_splash=1" | sudo tee -a /boot/config.txt
fi
if ! grep -q "boot_delay=0" /boot/config.txt; then
    echo "boot_delay=0" | sudo tee -a /boot/config.txt
fi
# --- End OS Optimizations ---

# --- Desktop Environment Configuration ---
echo "Configuring desktop environment (disabling panel, desktop icons, setting black background)..."

# ---- disable panel & desktop and force black background ----
# create autostart override dir
mkdir -p "$HOME/.config/autostart" "$HOME/.config/lxsession/LXDE-pi"

# create per-user autostart overrides to block system autostarts
cat > "$HOME/.config/autostart/lxpanel.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=lxpanel
Hidden=true
X-GNOME-Autostart-enabled=false
EOF

cat > "$HOME/.config/autostart/pcmanfm.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=pcmanfm
Hidden=true
X-GNOME-Autostart-enabled=false
EOF

# copy system autostart if present, then remove the lines to be safe
if [ -f /etc/xdg/lxsession/LXDE-pi/autostart ]; then
    cp /etc/xdg/lxsession/LXDE-pi/autostart "$HOME/.config/lxsession/LXDE-pi/autostart"
fi

# remove pcmanfm and lxpanel entries (safe even if not present)
sed -i '/@pcmanfm --desktop/d' "$HOME/.config/lxsession/LXDE-pi/autostart" 2>/dev/null || true
sed -i '/@lxpanel --profile LXDE-pi/d' "$HOME/.config/lxsession/LXDE-pi/autostart" 2>/dev/null || true

# ensure black background is set on session start
grep -qxF '@xsetroot -solid black' "$HOME/.config/lxsession/LXDE-pi/autostart" 2>/dev/null \
  || echo '@xsetroot -solid black' >> "$HOME/.config/lxsession/LXDE-pi/autostart"

# create minimal pcmanfm desktop-settings disable (extra safety)
mkdir -p "$HOME/.config/pcmanfm/LXDE-pi"
cat > "$HOME/.config/pcmanfm/LXDE-pi/desktop-items-0.conf" <<'EOF'
[*]
show_desktop=0
EOF

echo "Desktop environment configured for minimal display"
echo "Changes will take effect after reboot or logout/login"

# Immediate test (if running with display access)
if [ -n "$DISPLAY" ] || [ "$DISPLAY" = ":0" ]; then
    echo "Testing desktop changes immediately..."
    
    # Set environment variables for X access
    export DISPLAY=${DISPLAY:-:0}
    export XAUTHORITY="$HOME/.Xauthority"
    
    # Stop currently running desktop processes
    pkill -f lxpanel 2>/dev/null || true
    pkill -f pcmanfm 2>/dev/null || true
    sleep 0.5
    
    # Set black root background for current X session
    DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY xsetroot -solid black 2>/dev/null || true
    
    # Verify processes are gone
    if ! pgrep -a lxpanel >/dev/null 2>&1; then
        echo "✅ lxpanel stopped"
    else
        echo "⚠️  lxpanel still running"
    fi
    
    if ! pgrep -a pcmanfm >/dev/null 2>&1; then
        echo "✅ pcmanfm stopped" 
    else
        echo "⚠️  pcmanfm still running"
    fi
    
    echo "Desktop should now show black background with no icons/panel"
else
    echo "No display detected - changes will apply on next graphical login"
fi
# --- End Desktop Environment Configuration ---


# Setup auto-start service
echo "Setting up auto-start service..."
mkdir -p ~/.config/systemd/user
cp kitchensync.service ~/.config/systemd/user/
sed -i "s/kitchensync/$USER/g" ~/.config/systemd/user/kitchensync.service
sed -i "s|/home/kitchensync/kitchenSync|$(pwd)|g" ~/.config/systemd/user/kitchensync.service
systemctl --user daemon-reload
systemctl --user enable kitchensync.service

echo "Auto-start service installed. KitchenSync will start automatically on boot."

# Test networking imports after cleanup
echo ""
echo "🔍 Testing networking imports..."
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

try:
    from networking import SyncBroadcaster, CommandManager
    print('✅ Leader networking imports OK')
except Exception as e:
    print(f'❌ Leader networking imports failed: {e}')

try:
    from networking import SyncReceiver, CommandListener  
    print('✅ Collaborator networking imports OK')
except Exception as e:
    print(f'❌ Collaborator networking imports failed: {e}')
"

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Video player: VLC"
echo "Python packages installed system-wide"
echo "🔄 Auto-start service: ENABLED"
echo "🖥️  Desktop: Hidden (icons, menu bar, black background)"
echo ""
echo "🚀 PLUG-AND-PLAY OPERATION:"
echo "1. Create kitchensync.ini on your USB drive with:"
echo "   - is_leader = true/false (designates leader or collaborator)"
echo "   - pi_id = unique ID for each Pi" 
echo "   - video_file = specific video filename (optional)"
echo "2. Power on the Pi - KitchenSync starts automatically!"
echo ""
echo "📁 USB Drive Contents:"
echo "   - kitchensync.ini (configuration file)"
echo "   - Your video file(s) at the root level"
echo ""
echo "🔧 MANUAL TESTING (Optional):"
echo "- Test auto-detection: python3 kitchensync.py"
echo "- Test with display (SSH): DISPLAY=:0 PULSE_SERVER=unix:/run/user/1000/pulse/native python3 kitchensync.py"
echo "- Test service: sudo systemctl start kitchensync"
echo "- Manual leader: python3 leader.py"
echo "- Manual collaborator: python3 collaborator.py"
echo ""
echo "🎵 MIDI Setup:"
echo "1. Connect USB MIDI interface to collaborator Pis"
echo "2. Test connection: aconnect -l or amidi -l"
echo ""
echo "� Service Management:"
echo "- Check status: sudo systemctl status kitchensync"
echo "- View logs: sudo journalctl -u kitchensync -f"
echo "- Disable auto-start: sudo systemctl disable kitchensync"
echo ""
echo "🖥️  Desktop Configuration:"
echo "- Desktop icons/panel: DISABLED"
echo "- Background: BLACK"
echo "- To restore: rm ~/.config/autostart/{lxpanel,pcmanfm}.desktop && reboot"
echo ""
echo "🔧 Desktop Diagnostics (if issues):"
echo "- Check autostart: cat ~/.config/lxsession/LXDE-pi/autostart"
echo "- Check processes: ps aux | grep -E 'lxpanel|pcmanfm'"
echo "- Manual test: pkill lxpanel pcmanfm; xsetroot -solid black"
echo ""
echo "💡 READY FOR DEPLOYMENT! Just plug in USB drive and power on!"
echo ""

# --- Minimal X Session (Kiosk Mode) Option ---
echo "Configuring Minimal X session (kiosk mode) to avoid LXDE entirely..."

# Install minimal X stack and lightweight WM
sudo apt-get update -y >/dev/null 2>&1 || true
sudo apt-get install -y xorg xinit openbox >/dev/null 2>&1 || true

# Create systemd service to start X on tty1 for the current user
KSYNC_USER="$USER"
KSYNC_HOME="$(eval echo ~${KSYNC_USER})"
KSYNC_APP_DIR="$(pwd)"

KSYNC_SERVICE_PATH="/etc/systemd/system/kitchensync-x.service"
sudo bash -c "cat > ${KSYNC_SERVICE_PATH} <<EOF
[Unit]
Description=KitchenSync X session (kiosk)
After=systemd-user-sessions.service systemd-logind.service getty@tty1.service
Wants=getty@tty1.service systemd-logind.service

[Service]
User=${KSYNC_USER}
Environment=HOME=${KSYNC_HOME}
Environment=XDG_SESSION_TYPE=x11
Environment=XDG_RUNTIME_DIR=/run/user/1000
PAMName=login
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=journal
WorkingDirectory=${KSYNC_APP_DIR}
# Start X using xinit directly with explicit server options on vt1
ExecStart=/usr/bin/xinit ${KSYNC_HOME}/.xinitrc -- :0 -nolisten tcp vt1 -keeptty -verbose 3
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF"

# Write a minimal .xinitrc for the user
cat > "${KSYNC_HOME}/.xinitrc" <<EOF
#!/bin/sh
# Minimal X session for KitchenSync

# make root background black
xsetroot -solid black

# disable DPMS / screen blanking
xset s off
xset -dpms

# Start a tiny window manager (optional)
openbox-session &

# small delay to let WM initialize
sleep 0.5

# Start KitchenSync app
export DISPLAY=:0
exec /usr/bin/python3 ${KSYNC_APP_DIR}/kitchensync.py
EOF

sudo chown ${KSYNC_USER}:${KSYNC_USER} "${KSYNC_HOME}/.xinitrc"
chmod +x "${KSYNC_HOME}/.xinitrc"

# Enable the kiosk X service
sudo systemctl daemon-reload
sudo systemctl enable kitchensync-x.service
sudo systemctl start kitchensync-x.service || true

# Disable the previous user service to avoid double-launch
systemctl --user disable kitchensync.service >/dev/null 2>&1 || true

# Disable LightDM display manager to prevent LXDE from starting (safe for kiosk)
sudo systemctl disable lightdm.service >/dev/null 2>&1 || true

echo "Kiosk X session configured: kitchensync-x.service enabled, LightDM disabled."
echo "If you are at a CLI now, the service should start X shortly (or after reboot)."
echo "Reboot to start in kiosk mode (no LXDE, black background, no panel/icons)."
echo "Rollback (SSH): sudo systemctl disable kitchensync-x && sudo systemctl enable lightdm && sudo reboot"
echo "Debug: sudo systemctl status kitchensync-x.service; journalctl -u kitchensync-x -b -e | tail -n 100"

