# KitchenSync Project Plan

## Overview

KitchenSync is a modern, production-ready system for synchronized video playback and MIDI output across multiple Raspberry Pis. The system features plug-and-play USB drive configuration, automatic role detection, VLC-based video playback with advanced drift correction, and systemd auto-start capabilities. One Pi acts as the leader, broadcasting synchronized time via UDP and coordinating the entire system, while collaborator Pis receive time sync and execute precisely timed MIDI events. The system supports different videos per Pi, automatic USB drive detection, and professional deployment workflows.

I am developing this on a separate computer than the one on which it will run. Commands given to the system will be through SSH (for development).

## Technical Stack

- **Language:** Python 3 (system-wide installation, no virtual environment)
- **Media Player:** VLC with Python bindings for precise control and drift correction
- **MIDI Library:** python-rtmidi for USB MIDI interface communication
- **Networking:** UDP broadcast for time sync and control commands
- **Hardware:** Raspberry Pi 4 (recommended) + USB MIDI interfaces
- **Auto-Start:** systemd service for boot-time initialization
- **Configuration:** USB-based .ini files for automatic role detection
- **Sync Method:** Advanced median filtering with intelligent correction algorithms
- **Video Sources:** Automatic USB drive detection with priority-based file selection
- **User Interface:** Interactive leader Pi control with schedule editor
- **Schedule Format:** JSON-based MIDI event definitions with precise timing
- **Concurrency:** Python threading for non-blocking network operations
- **Display Management:** Proper X11 display context handling for video output
- **Deployment:** Production-ready with comprehensive error handling and status monitoring

## Current Architecture

### Core Components

**kitchensync.py** - Main auto-start script

- USB configuration detection and parsing
- Automatic role determination (leader vs collaborator)
- Subprocess management for launching appropriate mode
- Comprehensive error handling and logging
- Systemd service integration

**leader.py** - Leader Pi coordinator

- Video playbook with VLC Python bindings
- Time sync broadcasting (UDP port 5005)
- Collaborator Pi registration and heartbeat monitoring
- Interactive user interface with schedule editor
- System control commands (start/stop/status)
- Auto-start mode for production deployment

**collaborator.py** - Collaborator Pi worker

- Time sync reception and drift correction
- VLC-based synchronized video playback
- MIDI output via USB interfaces
- Advanced median filtering for sync accuracy
- Automatic leader discovery and registration
- Heartbeat status reporting

**kitchensync.service** - Systemd service

- Automatic startup on boot
- Proper user and directory configuration
- Display environment setup (DISPLAY=:0)
- Service restart policies and error handling

### Advanced Features

**USB Drive Auto-Detection**

- Automatic mounting and drive scanning
- Intelligent video file selection with priority ordering
- Configuration file parsing from USB drives
- Graceful handling of multiple drives and file conflicts

**Video Synchronization Technology**

- Python VLC bindings for programmatic control
- Median deviation filtering to eliminate false corrections
- Intelligent pause-during-correction for large deviations
- Configurable thresholds and grace periods
- Real-time position tracking and drift compensation

**Network Architecture**

- UDP broadcast for low-latency time sync
- Automatic Pi discovery and registration
- Heartbeat monitoring for connection status
- Command distribution for system control
- Robust error handling for network interruptions

**Configuration Management**

- USB-based configuration deployment
- Automatic role detection (leader/collaborator)
- Per-Pi video file specification
- MIDI port and sync parameter configuration
- Schedule file distribution and management

## Development Status ✅

### Completed Features

- ✅ Complete VLC migration from deprecated omxplayer
- ✅ USB drive auto-detection and mounting system
- ✅ Automatic role detection via USB configuration files
- ✅ Video playback functionality in leader script
- ✅ Systemd service configuration and auto-start system
- ✅ Advanced sync algorithms with median filtering
- ✅ Python VLC bindings for drift control capabilities
- ✅ Comprehensive error handling and status reporting
- ✅ Interactive schedule editor and system control interface
- ✅ Production-ready deployment workflow

### Technical Achievements

- **Modern Video Engine**: Migrated to VLC for cross-platform compatibility
- **Professional USB Handling**: Enterprise-grade drive detection and mounting
- **Intelligent Sync**: Statistical median filtering prevents false corrections
- **Plug-and-Play Design**: Zero-configuration deployment via USB drives
- **Production Ready**: Systemd integration for reliable auto-start
- **Raspberry Pi OS Bookworm**: Full compatibility with latest Pi OS

### Performance Characteristics

- **Time Sync Accuracy**: 10-30ms typical on wired LAN
- **Video Sync Tolerance**: 0.5s default (configurable)
- **MIDI Timing Precision**: Sub-50ms for synchronized events
- **Drift Correction**: Real-time compensation with minimal playback disruption
- **Resource Usage**: Optimized for Raspberry Pi 4 hardware
- **Network Efficiency**: UDP broadcast minimizes bandwidth usage

## Production Deployment

### System Requirements

- Raspberry Pi 4 (recommended for 4K video support)
- Raspberry Pi OS Bookworm (latest)
- USB MIDI interfaces (class-compliant devices)
- Network connectivity (Gigabit wired recommended)
- USB drives for configuration and video content

### Installation Process

1. Install VLC and Python dependencies system-wide
2. **(Recommended)** Optimize the OS by removing unused packages and services
3. Configure desktop appearance (hide icons, set black background)
4. Copy systemd service file and enable auto-start
5. Prepare USB drives with configuration and video files
6. Deploy to Raspberry Pis and power on
7. System auto-starts and begins synchronized playback

### Operational Features

- **Zero Configuration**: USB drives provide all necessary configuration
- **Automatic Discovery**: Pis find each other and establish connections
- **Fault Tolerance**: Graceful handling of Pi disconnections and reconnections
- **Real-Time Control**: Interactive interface for live system management
- **Status Monitoring**: Comprehensive system status and Pi health reporting
- **Content Management**: USB-based video and configuration deployment

## Future Enhancement Opportunities

### Potential Improvements

- **Web Interface**: Browser-based control panel for easier management
- **Content Streaming**: Network-based video distribution from leader Pi
- **Hardware Timestamping**: GPIO-based sync for sub-millisecond accuracy
- **Mobile App**: Smartphone control interface for system management
- **Cloud Integration**: Remote monitoring and configuration capabilities
- **Video Effects**: Real-time video processing and effects synchronization

### Scalability Considerations

- **Performance Testing**: Validate with larger Pi deployments (10+ devices)
- **Network Optimization**: Dedicated VLAN and QoS for critical traffic
- **Content Distribution**: Efficient video file distribution mechanisms
- **Monitoring Integration**: Integration with network monitoring systems
- **Configuration Management**: Centralized configuration database

The project has successfully achieved its core objectives and is ready for production deployment with professional-grade reliability and ease of use.

## Debug and Monitoring System (2025-08)

### Clean Architecture Debug System

The system features a clean, consolidated debug architecture:

**Leader Pi (HTML Debug Interface)**
- `HTMLDebugManager` - Manages browser-based debug interface
- `HTMLDebugOverlay` - Live-updating HTML interface with Firefox
- Real-time video timing and system status monitoring
- Professional window management with side-by-side layout
- Component-specific logging integrated throughout
- **Enhanced Layout (Jan 2025)**: Condensed interface with:
  - Smaller font (12px) and reduced padding for better information density
  - Side-by-side Service Status and VLC Status sections
  - Single refresh control section (removed redundant bottom controls)
  - Clean title without emoji decorations
  - Streamlined MIDI Information with comprehensive Recent/Upcoming lists
  - Scrollable MIDI event lists with color-coded indicators
  - Reduced log section heights to prevent scroll overflow
  - Removed redundant Current/Next MIDI fields for cleaner display
  - **Reliability Fix (Jan 2025)**: Enhanced error handling to prevent white pages
    - Content verification before HTML updates
    - Improved JavaScript error handling with retry limits
    - Fallback retention of previous working content
- **Template System (Jan 2025)**: Modular architecture with:
  - Separate HTML templates in `src/debug/templates/`
  - External CSS stylesheets for easier customization
  - External JavaScript files with improved auto-refresh reliability
  - Simple template engine with variable substitution and HTML escaping
  - Automatic static file copying and management
  - Fallback system for template errors
  - Enhanced error handling for OS module scope issues

**Collaborator Pi (Simple Debug Overlay)**
- `SimpleDebugManager` - Lightweight debug overlay system
- File-based fallback for reliable systemd service operation
- Real-time MIDI and video synchronization status
- Minimal resource footprint for Pi deployment

### Architecture Benefits

- **Clean Separation**: Leader uses rich HTML interface, collaborators use simple overlays
- **Consolidated Logging**: All components use standardized `log_info/warning/error` patterns
- **No Debug Print Pollution**: Eliminated print statements in favor of proper logging
- **Production Ready**: Debug systems designed for reliable systemd operation
- **Enhanced UX**: Improved debug window layout maximizes information visibility within viewport
- **Modular Design**: Template system allows easy customization without touching Python code
- **Reliable Auto-refresh**: Enhanced JavaScript with error handling and refresh counting
- **Streamlined Information**: Removed redundant MIDI fields, focusing on comprehensive data display

## Diagnostics and Logs (2025-08)

To troubleshoot boot-time display issues (VLC vs. overlay), the system writes diagnostic logs to `/tmp` so they are available both under systemd and desktop sessions:

- System log: `/tmp/kitchensync_system.log`
- VLC (Python/CLI) details:
  - Main: `/tmp/kitchensync_vlc.log` (reserved)
  - Stdout: `/tmp/kitchensync_vlc_stdout.log`
  - Stderr: `/tmp/kitchensync_vlc_stderr.log`
- Overlay (file-based fallback): `/tmp/kitchensync_debug_leader-pi.txt`
- Emergency startup log: `/tmp/kitchensync_startup.log` (captures import failures)

What to check after reboot:

1) Tail system log for environment and startup sequence
   - `tail -n 200 -f /tmp/kitchensync_system.log`
   - Confirms DISPLAY/Wayland/XDG variables and whether VLC/overlay initialized

2) If VLC window is missing
   - `tail -n 200 /tmp/kitchensync_vlc_stderr.log`
   - Look for `vout` errors, display backend problems, or codec init failures

3) If overlay is blank
   - `tail -n 200 /tmp/kitchensync_debug_leader-pi.txt`
   - Confirms overlay updates, current time, MIDI info; indicates pygame/display fallbacks

4) If no logs appear at all
   - Check emergency startup log: `cat /tmp/kitchensync_startup.log`
   - This captures import failures and path issues before main logging starts

Notes
- Logs are appended with timestamps; they survive until next reboot or manual cleanup.
- Environment snapshot includes `DISPLAY`, `XDG_SESSION_TYPE`, `XDG_RUNTIME_DIR`, `SDL_VIDEODRIVER`, `WAYLAND_DISPLAY`, `XAUTHORITY`.
- Emergency logging ensures startup issues are captured even if main logging fails.

## Testing and Deployment (2025-08)

### OS Optimization (Recommended)

To improve boot time and free up system resources, it is recommended to perform the following optimizations on the Raspberry Pi:

**1. Disable Unnecessary Services**
```bash
# Disable Bluetooth, printing, and other unused services
sudo systemctl disable bluetooth.service hciuart.service
sudo systemctl disable cups.service triggerhappy.service
sudo systemctl disable avahi-daemon.service
```

**2. Remove Unused Software**
```bash
# Remove large, non-essential packages
sudo apt purge -y wolfram-engine sonic-pi scratch nuscratch smartsim libreoffice*
sudo apt autoremove -y && sudo apt clean
```

**3. Optimize Boot Configuration**
Add the following to `/boot/config.txt` to speed up the boot sequence:
```ini
disable_splash=1
boot_delay=0
```

**4. Desktop Configuration (Pi Bookworm/Wayfire)**
Configure a clean desktop appearance for stage deployment:
```bash
# Set black background using wf-shell (Wayfire's desktop shell)
mkdir -p ~/.config
echo "[background]" > ~/.config/wf-shell.ini
echo "color = \\#000000" >> ~/.config/wf-shell.ini

# Disable desktop icons in pcmanfm (if used)
mkdir -p ~/.config/pcmanfm/default
echo "[desktop]" >> ~/.config/pcmanfm/default/pcmanfm.conf
echo "show_desktop=0" >> ~/.config/pcmanfm/default/pcmanfm.conf

# Install swaybg as fallback
sudo apt install -y swaybg
echo "fallback_bg=~/set_black_background_fallback.sh" >> ~/.config/wayfire.ini
```

### Quick Test Procedure

1. **Test logging first** (ensures system works):
   ```bash
   python3 test_logging.py
   ```

2. **Deploy and test service**:
   ```bash
   ./deploy_and_test.sh
   ```

3. **Monitor logs in real-time**:
   ```bash
   tail -f /tmp/kitchensync_system.log
   tail -f /tmp/kitchensync_vlc_stderr.log
   tail -f /tmp/kitchensync_debug_leader-pi.txt
   ```

### Current System Status

The KitchenSync leader system is fully operational with:

- **VLC video playback**: Stable playback with window positioning on left side
- **HTML debug overlay**: Live-updating interface positioned on right side  
- **Real-time monitoring**: Video timing, VLC status, and system health
- **Systemd auto-start**: Reliable boot-time initialization
- **Window management**: Proper side-by-side layout using wmctrl
- **Error handling**: Comprehensive logging and graceful fallbacks

### Service Configuration

The systemd service includes proper environment variables:
- `DISPLAY=:0` - X11 display access
- `XAUTHORITY=/home/kitchensync/.Xauthority` - X11 authentication
- `XDG_RUNTIME_DIR=/run/user/1000` - Runtime directory
- User `kitchensync` with proper permissions

### Troubleshooting

1. **Monitor system logs**: `tail -f /tmp/kitchensync_system.log`
2. **Check VLC errors**: `tail -f /tmp/kitchensync_vlc_stderr.log`  
3. **Service status**: `systemctl --user status kitchensync.service`
4. **Window positioning**: Logs show wmctrl positioning results


## future necessities

+ Remove desktop environment, etc. just have a totally slimmed down OS
+ Read only root filesystem to prevent disk errors, etc.
+ Remote management
+ Ensure total hardware acceleration
+ Custom OS build: Base on a lightweight Linux (Yocto, Buildroot, or optimized Debian variant) tuned for fast boot, stable VLC playback, and real-time scheduling
+ Network resilience: Robust UDP multicast/broadcast handling, auto-recovery from network drops
+ Systemd integration: Auto-start is mandatory; add watchdog timers to auto-restart on failure Logging & diagnostics: multi-log approach is solid; consider remote log aggregation and alerting for commercial use
+ Ensure wide codec compatibility
+ Secure SSH and network channels; disable unused services to minimize attack surface
