# KitchenSync Project Plan

## Overview

KitchenSync is a modern, production-ready system for synchronized video playback and MIDI output across multiple Raspberry Pis. The system features plug-and-play USB drive configuration, automatic role detection, VLC-based video playback with advanced drift correction, and systemd auto-start capabilities. One Pi acts as the leader, broadcasting synchronized time via UDP and coordinating the entire system, while collaborator Pis receive time sync and execute precisely timed MIDI events. The system supports different videos per Pi, automatic USB drive detection, and professional deployment workflows.

I am developing this on a separate computer than the one on which it will run. Commands given to the system will be through SSH (for development).

## Technical Stack

- **Language:** Python 3 (system-wide installation, no virtual environment)
- **Media Player:** VLC with Python bindings (consolidated approach for both leader and collaborator)
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

- Video playback with Python VLC bindings (unified approach)
- Time sync broadcasting (UDP port 5005)
- Collaborator Pi registration and heartbeat monitoring
- Interactive user interface with schedule editor
- System control commands (start/stop/status)
- Auto-start mode for production deployment

**collaborator.py** - Collaborator Pi worker

- Time sync reception and drift correction
- Python VLC-based synchronized video playback (same method as leader)
- MIDI output via USB interfaces
- Advanced median filtering for sync accuracy
- Automatic leader discovery and registration
- Heartbeat status reporting
- Simplified mode (current): no start/stop commands; auto-starts playback on first timecode packet and continuously maintains sync from leader broadcasts

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

- Unified Python VLC bindings for all nodes (leader and collaborator)
- Median deviation filtering to eliminate false corrections
- Intelligent pause-during-correction for large deviations
- Configurable thresholds and grace periods
- Real-time position tracking and drift compensation
- Consistent seeking behavior across all Pis

**Network Architecture**

- UDP broadcast for low-latency time sync
- Automatic Pi discovery and registration
- Heartbeat monitoring for connection status
- Command distribution for system control (deprecated for collaborator in simplified mode; collaborator ignores start/stop and follows timecode only)
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
- ✅ Consolidated VLC approach - both leader and collaborator use identical Python VLC method

### Technical Achievements

- **Unified Video Engine**: Consolidated Python VLC approach for all nodes ensures consistent behavior
- **Professional USB Handling**: Enterprise-grade drive detection and mounting
- **Intelligent Sync**: Statistical median filtering prevents false corrections
- **Plug-and-Play Design**: Zero-configuration deployment via USB drives
- **Production Ready**: Systemd integration for reliable auto-start
- **Raspberry Pi OS Bookworm**: Full compatibility with latest Pi OS
- **Simplified Architecture**: Single VLC playback method eliminates complexity and debug/production differences

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

## Firefox Startup Issue - RESOLVED (Jan 2025)

### Problem Description
After system reboot, Firefox takes a very long time to start and the debug overlay window does not get repositioned properly. Manual service restart works fine.

### Root Cause Analysis
The issue occurs because:
1. **Wayland Fallback**: Firefox tries to use Wayland first, fails, then falls back to X11 (causing delays)
2. **Display Environment**: X11 display server may not be fully ready when the systemd service starts
3. **Environment Variables**: Wayland-related environment variables aren't properly cleared in systemd context
4. **Startup Timing**: Desktop environment (Wayfire/Wayland) takes time to fully initialize

### Comprehensive Solution Implemented

**1. Service File Updates (`kitchensync.service`)**
- Added explicit dependency on `display-manager.service`
- Force X11 mode with comprehensive environment variables
- Added X11 readiness check with `xset q` command
- Increased startup delay to ensure full desktop initialization

**2. Start Script Updates (`start_clean.sh`)**
- Force Firefox to use X11 with `MOZ_*` environment variables
- Added X11 display validation before starting KitchenSync
- Comprehensive logging of environment state

**3. Firefox Launch Updates (`src/debug/html_overlay.py`)**
- Force X11 mode with command line arguments (`--disable-wayland`)
- **SIMPLIFIED: Clean profile approach**
  - Simple profile directory (`/tmp/ff-clean-profile`)
  - Remove profile before each launch for guaranteed clean state
  - Basic Firefox arguments: `--no-remote --profile /tmp/ff-clean-profile --new-instance`
  - No complex configuration files or preferences
- **NEW: Firefox Welcome Screen Suppression**
  - `user.js` file with preferences to disable Privacy Notice and welcome screens
  - `policies.json` for enterprise-level suppression of first-run pages
  - Ensures Firefox launches completely clean without popups or extra tabs
- Fallback launch mechanism if primary launch fails
- Enhanced error handling and logging

**4. Cleanup and Process Management**
- **NEW: Comprehensive cleanup system**
  - Signal handlers for graceful shutdown (SIGTERM, SIGINT)
  - Automatic Firefox process termination on service stop
  - Profile directory cleanup to prevent accumulation
  - Manual cleanup script (`cleanup_firefox.sh`) for maintenance

### Environment Variables Added
```bash
# Force X11 mode
MOZ_ENABLE_WAYLAND=0
MOZ_DISABLE_WAYLAND=1
MOZ_ENABLE_X11=1
MOZ_X11_EGL=1

# Disable sandboxing delays
MOZ_DISABLE_RDD_SANDBOX=1
MOZ_DISABLE_GMP_SANDBOX=1
MOZ_DISABLE_GPU_SANDBOX=1
MOZ_DISABLE_CONTENT_SANDBOX=1
```

### Firefox Welcome Screen Suppression

The system now creates two configuration files in each Firefox profile to ensure completely clean launches:

**1. `user.js` - User Preferences**
```javascript
// Disable privacy notice tab
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);

// Suppress welcome/onboarding pages
user_pref("trailhead.firstrun.didSeeAboutWelcome", true);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("startup.homepage_welcome_url", "");
user_pref("browser.startup.homepage_override.mstone", "ignore");

// Force clean startup
user_pref("browser.startup.page", 0);
user_pref("browser.startup.homepage", "about:blank");
user_pref("browser.newtabpage.enabled", false);
user_pref("browser.sessionstore.enabled", false);
```

**2. `policies.json` - Enterprise Policies**
```json
{
  "policies": {
    "OverrideFirstRunPage": "",
    "OverridePostUpdatePage": "",
    "DisableTelemetry": true,
    "DisableFirefoxStudies": true,
    "DisablePocket": true
  }
}
```

This dual approach ensures Firefox launches without:
- Privacy Notice tabs
- Welcome/onboarding screens
- Telemetry prompts
- Update splash screens
- Activity stream content

### Testing Results
- **Before**: Firefox startup took 30+ seconds after reboot, window positioning failed
- **After**: Firefox starts in 2-5 seconds, window positioning works reliably
- **Reliability**: Service now works consistently after both reboot and manual restart

### Technical Details
The fix addresses the fundamental issue where Firefox was attempting to use Wayland (which wasn't ready) before falling back to X11. By forcing X11 mode at multiple levels (systemd service, start script, Firefox launch, and Firefox preferences), we eliminate the fallback delay and ensure consistent behavior.

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
- `XAUTHORITY=/home/$USER/.Xauthority` - X11 authentication (dynamic per user)
- `XDG_RUNTIME_DIR=/run/user/1000` - Runtime directory
- User `kitchensync` with proper permissions

### Troubleshooting

1. **Monitor system logs**: `tail -f /tmp/kitchensync_system.log`
2. **Check VLC errors**: `tail -f /tmp/kitchensync_vlc_stderr.log`  
3. **Service status**: `sudo systemctl status kitchensync.service`
4. **Window positioning**: Logs show wmctrl positioning results


## Programming Philosophy & Standards

**CRITICAL DIRECTIVE**: Do not do shallow or superficial edits. Always dive deep and think systemically:
- What other components are affected by this change?
- What are the ripple effects and repercussions?
- Are there hidden dependencies or side effects?
- Does this fix the root cause or just the symptom?
- What edge cases or failure modes need to be considered?

**Example**: When implementing configurable logging, don't just add config flags - trace through EVERY component that logs (HTML overlay, VLC args, config loading, startup sequences, etc.) and ensure ALL respect the configuration.

This is the mark of professional programming vs. superficial patching.

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
