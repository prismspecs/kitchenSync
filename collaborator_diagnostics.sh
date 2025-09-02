#!/bin/bash
# KitchenSync Collaborator Diagnostics Script
# Run this on a collaborator Pi to gather troubleshooting information
# Usage: bash collaborator_diagnostics.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== KitchenSync Collaborator Diagnostics ===${NC}"
echo "Date: $(date)"
echo "Hostname: $(hostname)"
echo "User: $(whoami)"
echo "Working Directory: $(pwd)"
echo ""

# Function to run command and capture both success/failure
run_check() {
    local description="$1"
    local command="$2"
    local show_output="${3:-true}"
    
    echo -e "${YELLOW}=== $description ===${NC}"
    
    if eval "$command" 2>&1; then
        echo -e "${GREEN}✅ SUCCESS${NC}"
    else
        echo -e "${RED}❌ FAILED (exit code: $?)${NC}"
    fi
    echo ""
}

# Function to show file contents safely
show_file() {
    local description="$1"
    local filepath="$2"
    local lines="${3:-50}"
    
    echo -e "${YELLOW}=== $description ===${NC}"
    if [[ -f "$filepath" ]]; then
        echo "File exists: $filepath ($(wc -l < "$filepath") lines)"
        echo "Last modified: $(stat -c %y "$filepath" 2>/dev/null || stat -f %Sm "$filepath" 2>/dev/null || echo "unknown")"
        echo "--- Content (last $lines lines) ---"
        tail -n "$lines" "$filepath" 2>/dev/null || echo "Could not read file"
    else
        echo -e "${RED}❌ File not found: $filepath${NC}"
    fi
    echo ""
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo -e "${BLUE}=== SYSTEM OVERVIEW ===${NC}"
echo "OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2 2>/dev/null || echo "Unknown")"
echo "Kernel: $(uname -r)"
echo "Architecture: $(uname -m)"
echo "Uptime: $(uptime -p 2>/dev/null || uptime)"
echo "Load: $(uptime | awk -F'load average:' '{print $2}' | xargs)"
echo "Memory: $(free -h | grep Mem | awk '{print $3"/"$2" ("$3/$2*100"%)"}')"
echo "Disk Space: $(df -h / | tail -1 | awk '{print $3"/"$2" ("$5" used)"}')"
echo ""

# 1. Service Status
run_check "Service Status Check" "sudo systemctl status kitchensync.service --no-pager"

# 2. Process Check
echo -e "${YELLOW}=== Process Information ===${NC}"
echo "KitchenSync processes:"
ps aux | grep -E "(kitchensync|collaborator|leader)" | grep -v grep || echo "No KitchenSync processes found"
echo ""
echo "VLC processes:"
ps aux | grep vlc | grep -v grep || echo "No VLC processes found"
echo ""
echo "Python processes:"
ps aux | grep python | grep -v grep | head -5 || echo "No Python processes found"
echo ""

# 3. Log Files
echo -e "${YELLOW}=== Available Log Files ===${NC}"
ls -la /tmp/kitchensync* 2>/dev/null || echo "No KitchenSync log files found in /tmp"
echo ""

# Show main log files
show_file "System Log (Main)" "/tmp/kitchensync_system.log" 50
show_file "VLC Error Log" "/tmp/kitchensync_vlc_stderr.log" 30
show_file "VLC Output Log" "/tmp/kitchensync_vlc_stdout.log" 20

# 4. Service Logs
echo -e "${YELLOW}=== Recent Service Logs (journalctl) ===${NC}"
if command_exists journalctl; then
    sudo journalctl -u kitchensync -n 30 --no-pager 2>/dev/null || echo "Could not access journalctl logs"
else
    echo "journalctl not available"
fi
echo ""

# 5. USB and Storage
echo -e "${YELLOW}=== USB Drive Detection ===${NC}"
echo "Mounted filesystems (USB-related):"
mount | grep -E "(media|mnt|usb)" || echo "No USB-related mounts found"
echo ""

echo "Available media directories:"
ls -la /media/ 2>/dev/null || echo "/media directory not found"
echo ""

echo "USB drive contents:"
find /media/ -maxdepth 2 -type f 2>/dev/null | head -20 || echo "No files found in /media"
echo ""

# 6. Configuration Files
echo -e "${YELLOW}=== Configuration Detection ===${NC}"
echo "Looking for kitchensync.ini files..."
find /media/ -name "kitchensync.ini" -type f 2>/dev/null | while read config_file; do
    echo "Found config: $config_file"
    echo "--- Contents ---"
    cat "$config_file" 2>/dev/null || echo "Could not read config file"
    echo ""
done

# Check local config
if [[ -f "collaborator_config.ini" ]]; then
    echo "Local collaborator_config.ini found:"
    cat collaborator_config.ini
else
    echo "No local collaborator_config.ini found"
fi
echo ""

# 7. Video Files
echo -e "${YELLOW}=== Video File Detection ===${NC}"
echo "Searching for video files..."
video_extensions=("*.mp4" "*.avi" "*.mov" "*.mkv" "*.wmv" "*.flv" "*.webm" "*.m4v")
for ext in "${video_extensions[@]}"; do
    find /media/ -name "$ext" -type f 2>/dev/null | head -5
done | sort | while read video_file; do
    if [[ -n "$video_file" ]]; then
        echo "Found: $video_file"
        ls -lh "$video_file"
        file "$video_file" 2>/dev/null || echo "Could not determine file type"
        echo ""
    fi
done

if [[ ! $(find /media/ -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" 2>/dev/null) ]]; then
    echo "❌ No video files found on USB drives"
fi
echo ""

# 8. Network Configuration
echo -e "${YELLOW}=== Network Configuration ===${NC}"
echo "Network interfaces:"
ip addr show | grep -E "inet |^[0-9]|UP|DOWN" || ifconfig 2>/dev/null | grep -E "inet|flags"
echo ""

echo "Default route:"
ip route show default 2>/dev/null || route -n | grep "^0.0.0.0"
echo ""

echo "DNS configuration:"
cat /etc/resolv.conf 2>/dev/null | grep nameserver || echo "Could not read DNS config"
echo ""

# 9. Network Connectivity Tests
echo -e "${YELLOW}=== Network Connectivity Tests ===${NC}"

# Test basic connectivity
run_check "Internet Connectivity" "ping -c 3 -W 5 8.8.8.8 >/dev/null"

# Test local network (try to find leader)
echo "Scanning for other devices on network..."
network=$(ip route | grep -E "192\.168\.|10\.|172\." | head -1 | awk '{print $1}' 2>/dev/null)
if [[ -n "$network" ]]; then
    echo "Network range: $network"
    # Quick scan for common Pi IPs
    for ip in {1..10}; do
        base_ip=$(echo $network | cut -d'/' -f1 | cut -d'.' -f1-3)
        ping -c 1 -W 1 "$base_ip.$ip" >/dev/null 2>&1 && echo "  Found device: $base_ip.$ip"
    done
else
    echo "Could not determine network range"
fi
echo ""

# 10. Port and Service Tests
echo -e "${YELLOW}=== Port and Service Tests ===${NC}"

# Check if sync/command ports are in use
echo "Checking KitchenSync ports..."
netstat -ulnp 2>/dev/null | grep -E ":5005|:5006" || ss -ulnp | grep -E ":5005|:5006" || echo "No KitchenSync ports active"
echo ""

# Try to listen for sync packets briefly
echo "Testing for sync packets (5 second test)..."
timeout 5 nc -ul 5005 2>/dev/null && echo "Received sync data!" || echo "No sync packets received in 5 seconds"
echo ""

# 11. VLC and Media Tests
echo -e "${YELLOW}=== VLC and Media System Tests ===${NC}"

# VLC version
run_check "VLC Installation" "vlc --version | head -1"

# Python VLC bindings
run_check "Python VLC Bindings" "python3 -c 'import vlc; print(\"VLC bindings version:\", vlc.libvlc_get_version().decode())'"

# Display environment
echo "Display environment:"
echo "DISPLAY=$DISPLAY"
echo "XDG_SESSION_TYPE=$XDG_SESSION_TYPE"
echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-unset}"
echo ""

# X11 test
if [[ -n "$DISPLAY" ]]; then
    run_check "X11 Display Access" "DISPLAY=$DISPLAY xrandr >/dev/null"
fi

# VLC dummy test
run_check "VLC Dummy Interface Test" "vlc --intf dummy --play-and-exit --quiet /dev/null 2>/dev/null"
echo ""

# 12. MIDI/Arduino Tests (if applicable)
echo -e "${YELLOW}=== MIDI/Arduino Tests ===${NC}"
echo "Serial devices:"
ls -la /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || echo "No Arduino/serial devices found"
echo ""

# Test MIDI system if KitchenSync source is available
if [[ -d "src" ]]; then
    run_check "MIDI System Test" "python3 -c 'import sys; sys.path.insert(0, \"./src\"); from midi.manager import MidiManager; m = MidiManager(use_serial=True); print(\"MIDI system initialized successfully\")'"
else
    echo "KitchenSync source directory not found - skipping MIDI test"
fi
echo ""

# 13. Configuration Test
echo -e "${YELLOW}=== Configuration Loading Test ===${NC}"
if [[ -d "src" ]]; then
    echo "Testing configuration loading..."
    python3 -c "
import sys
sys.path.insert(0, './src')
try:
    from config import ConfigManager
    cm = ConfigManager()
    print(f'✅ Configuration loaded successfully')
    print(f'Device ID: {cm.device_id}')
    print(f'Video file: {cm.video_file}')
    print(f'USB mount: {getattr(cm, \"usb_mount_point\", \"Not set\")}')
    print(f'Is leader: {cm.is_leader}')
    print(f'Debug mode: {cm.debug_mode}')
    print(f'Enable system logging: {cm.enable_system_logging}')
except Exception as e:
    print(f'❌ Configuration loading failed: {e}')
    import traceback
    traceback.print_exc()
" 2>&1
else
    echo "KitchenSync source directory not found - skipping config test"
fi
echo ""

# 14. Manual Collaborator Test
echo -e "${YELLOW}=== Manual Collaborator Test ===${NC}"
if [[ -f "collaborator.py" ]]; then
    echo "Testing collaborator startup (5 second test)..."
    timeout 5 python3 collaborator.py --debug 2>&1 | head -20 || echo "Collaborator test completed/timed out"
else
    echo "collaborator.py not found - skipping manual test"
fi
echo ""

# 15. Environment Summary
echo -e "${YELLOW}=== Environment Summary ===${NC}"
echo "Environment variables (relevant):"
env | grep -E "(DISPLAY|XDG|PULSE|PATH|PYTHON)" | sort
echo ""

echo "Python version and path:"
python3 --version
which python3
echo ""

echo "System Python packages (VLC-related):"
python3 -c "import pkg_resources; [print(f'{d.project_name}: {d.version}') for d in pkg_resources.working_set if 'vlc' in d.project_name.lower()]" 2>/dev/null || echo "Could not list Python packages"
echo ""

# 16. Disk Usage and Permissions
echo -e "${YELLOW}=== Disk Usage and Permissions ===${NC}"
echo "Current directory permissions:"
ls -la . | head -10
echo ""

echo "Tmp directory usage:"
du -sh /tmp 2>/dev/null || echo "Could not check /tmp usage"
ls -la /tmp/kitchensync* 2>/dev/null | head -10 || echo "No KitchenSync files in /tmp"
echo ""

# 17. Summary and Recommendations
echo -e "${BLUE}=== DIAGNOSTIC SUMMARY ===${NC}"
echo ""

# Check for obvious issues
issues=()

if ! systemctl is-active --quiet kitchensync.service 2>/dev/null; then
    issues+=("❌ KitchenSync service is not running")
fi

if [[ ! -f "/tmp/kitchensync_system.log" ]]; then
    issues+=("❌ No system log file found")
fi

if ! command_exists vlc; then
    issues+=("❌ VLC is not installed")
fi

if [[ ! $(find /media/ -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" 2>/dev/null) ]]; then
    issues+=("❌ No video files found on USB drives")
fi

if [[ ! $(find /media/ -name "kitchensync.ini" 2>/dev/null) ]]; then
    issues+=("⚠️  No kitchensync.ini found on USB drives")
fi

if [[ ${#issues[@]} -eq 0 ]]; then
    echo -e "${GREEN}✅ No obvious issues detected${NC}"
    echo "If the system still isn't working, check the detailed logs above for specific errors."
else
    echo -e "${RED}Issues detected:${NC}"
    for issue in "${issues[@]}"; do
        echo "  $issue"
    done
fi

echo ""
echo -e "${BLUE}=== END DIAGNOSTICS ===${NC}"
echo "Generated on: $(date)"
echo "Save this output and send it for analysis."
echo ""
echo "Quick commands for further investigation:"
echo "  - View live system log: tail -f /tmp/kitchensync_system.log"
echo "  - Restart service: sudo systemctl restart kitchensync.service"
echo "  - Stop service: sudo systemctl stop kitchensync.service"
echo "  - Manual debug run: python3 collaborator.py --debug --debug_loop"
