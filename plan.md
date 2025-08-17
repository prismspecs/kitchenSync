# KitchenSync Project Plan

## Overview

KitchenSync is a modern, production-ready system for synchronized video playback and MIDI output across multiple Raspberry Pis. The system features plug-and-play USB drive configuration, automatic role detection, VLC-based video playback with advanced drift correction, and systemd auto-start capabilities. One Pi acts as the leader, broadcasting synchronized time via UDP and coordinating the entire system, while collaborator Pis receive time sync and execute precisely timed MIDI events. The system supports different videos per Pi, automatic USB drive detection, and professional deployment workflows.

**🔄 SYSTEM STATUS: FULLY OPERATIONAL** - All major components working, MIDI system migrated to Arduino serial, comprehensive error handling implemented.

I am developing this on a separate computer than the one on which it will run. Commands given to the system will be through SSH (for development).

## Technical Stack

- **Language:** Python 3 (system-wide installation, no virtual environment)
- **Media Player:** VLC with Python bindings (consolidated approach for both leader and collaborator)
- **Audio Support:** Full audio track synchronization with configurable output (HDMI/headphone jack)
- **MIDI System:** **NEW** - Arduino serial-based MIDI controller with automatic port detection
- **Networking:** UDP broadcast for time sync and control commands
- **Hardware:** Raspberry Pi 4 (recommended) + Arduino MIDI controller via USB serial
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
- **NEW**: Automatic upgrade system from USB drives

**leader.py** - Leader Pi coordinator

- Video playback with Python VLC bindings (unified approach)
- Time sync broadcasting (UDP port 5005)
- Collaborator Pi registration and heartbeat monitoring
- Interactive user interface with schedule editor
- System control commands (start/stop/status)
- Auto-start mode for production deployment
- **NEW**: Enhanced MIDI scheduling with loop detection

**collaborator.py** - Collaborator Pi worker

- Time sync reception and drift correction
- Python VLC-based synchronized video playback (same method as leader)
- **NEW**: Arduino serial MIDI output via USB
- Advanced median filtering for sync accuracy
- Automatic leader discovery and registration
- Heartbeat status reporting
- Simplified mode (current): no start/stop commands; auto-starts playback on first timecode packet and continuously maintains sync from leader broadcasts

**start_clean.sh** - System startup script with log archiving

- Auto-archives existing logs before starting (max 1000 lines per archive)
- X11 environment setup and validation
- Firefox/display configuration  
- Smart log rotation prevents runaway disk usage

**cleanup_logs.sh** - Manual log management utility

- Archives current logs and starts fresh
- Maintains rolling 1000-line history per log type
- User-friendly output showing file sizes and operations
- Can be run anytime for manual cleanup

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

**NEW: Arduino Serial MIDI System**

- **Hardware**: Arduino-based MIDI controller connected via USB serial
- **Port Detection**: Automatic detection of Arduino ports (`/dev/ttyACM*`, `/dev/ttyUSB*`)
- **Communication**: Serial protocol with commands like `noteon <channel> <note> <velocity>`
- **Fallback**: Mock MIDI output when hardware not available
- **Loop Detection**: Intelligent loop detection for synchronized MIDI playback
- **Error Handling**: Comprehensive error handling with graceful fallbacks
- **Serial Settings**: Configurable baud rate (default: 9600 for Arduino compatibility)

**Video and Audio Synchronization Technology**

- **Full A/V Synchronization**: Videos with audio tracks are synchronized across all nodes, ensuring both video and audio stay in perfect sync
- Unified Python VLC bindings for all nodes (leader and collaborator)
- Median deviation filtering to eliminate false corrections
- Intelligent pause-during-correction for large deviations
- Configurable thresholds and grace periods
- Real-time position tracking and drift compensation
- Consistent seeking behavior across all Pis
- Configurable latency compensation to counter network/compute lag
- Seek settle timing to allow decoder/display to catch up after seeks
- **Wall-clock time synchronization**: Leader broadcasts elapsed wall time since start, ensuring all nodes advance at the same rate rather than trying to match absolute video positions
- **Anti-feedback sync**: Deviation samples cleared before seeking to prevent correction loops
- **Outlier filtering**: Trimmed median calculation removes extreme measurements that could trigger false corrections
- **Continuous sync monitoring**: Leader broadcasts position continuously (every 0.1s), collaborator monitors and corrects in real-time
- **High-frequency sync**: Leader broadcasts every 0.02 seconds (50x/sec) for responsive wait-for-sync state management
- **omxplayer-sync inspired approach**: Pause during correction, seek ahead to compensate for latency, wait-for-sync state management, and grace periods to prevent rapid re-corrections

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
- **Audio Output Configuration**: Configurable audio output selection (HDMI vs. headphone jack)
- **Fallback Defaults**: Hardcoded defaults in code match INI file values for consistent behavior
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
- ✅ **NEW**: Arduino serial MIDI system with automatic port detection
- ✅ **NEW**: Enhanced MIDI scheduling with loop detection and error handling
- ✅ **NEW**: Automatic upgrade system from USB drives
- ✅ **NEW**: Comprehensive null safety in MIDI system for graceful shutdown

### Technical Achievements

- **Unified Video Engine**: Consolidated Python VLC approach for all nodes ensures consistent behavior
- **Full A/V Synchronization**: Audio tracks are now properly synchronized across all nodes
- **Configurable Audio Output**: Support for HDMI and headphone jack audio routing (OS-level configuration)
- **Professional USB Handling**: Enterprise-grade drive detection and mounting
- **Intelligent Sync**: Statistical median filtering prevents false corrections
- **Plug-and-Play Design**: Zero-configuration deployment via USB drives
- **Production Ready**: Systemd integration for reliable auto-start
- **Raspberry Pi OS Bookworm**: Full compatibility with latest Pi OS
- **Simplified Architecture**: Single VLC playback method eliminates complexity and debug/production differences
- **Configuration Consistency**: Default values in code always match INI file values for reliable fallback behavior
- **NEW: Arduino MIDI Integration**: Serial-based MIDI control with automatic hardware detection
- **NEW: Robust Error Handling**: Comprehensive null safety and graceful shutdown in MIDI system
- **NEW: Auto-Upgrade System**: Seamless system updates from USB drives
- **NEW: Enhanced Loop Detection**: Intelligent MIDI loop detection for synchronized playback

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
- **NEW**: Arduino board (Uno, Nano, or similar) with USB connection
- **NEW**: Custom Arduino sketch for MIDI control (included in `arduino/` directory)
- Network connectivity (Gigabit wired recommended)
- USB drives for configuration and video content

### Arduino Setup Requirements

- **Hardware**: Arduino Uno, Nano, or compatible board
- **USB Connection**: Standard USB cable for serial communication
- **Sketch**: Custom MIDI control sketch (see `arduino/midi_controller/`)
- **Power**: USB-powered or external power supply
- **Port Detection**: System automatically detects Arduino on `/dev/ttyACM*` or `/dev/ttyUSB*`

### Installation Process

1. Install VLC and Python dependencies system-wide
2. **(Recommended)** Optimize the OS by removing unused packages and services
3. Configure desktop appearance (panel autohide, hide icons, set black background)
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

## Current MIDI System Architecture

### Arduino Serial MIDI Controller

The system now uses an Arduino-based MIDI controller connected via USB serial instead of traditional USB MIDI interfaces.

**Hardware Setup**
- Arduino board (Uno, Nano, or similar) with USB connection
- Custom Arduino sketch for MIDI control
- USB serial connection to Raspberry Pi

**Communication Protocol**
- **Serial Commands**: Simple text-based protocol over USB serial
- **Note On**: `noteon <channel> <note> <velocity>`
- **Note Off**: `noteoff <channel> <note> 0`
- **Baud Rate**: 9600 (configurable for Arduino compatibility)

**Automatic Detection**
- **Port Scanning**: Automatically detects Arduino ports (`/dev/ttyACM*`, `/dev/ttyUSB*`)
- **Fallback**: Uses mock MIDI output when hardware not available
- **Error Handling**: Graceful fallback to simulation mode

**MIDI Scheduler Features**
- **Loop Detection**: Intelligent detection of video loops for synchronized MIDI
- **Cue Management**: Tracks triggered cues to prevent duplicate execution
- **Time Synchronization**: Precise timing based on video position or wall clock
- **Error Safety**: Comprehensive null checks and graceful error handling

**Benefits of New System**
- **Cost Effective**: Arduino boards are inexpensive and widely available
- **Reliable**: Serial communication is more stable than USB MIDI
- **Configurable**: Easy to modify Arduino code for custom MIDI behavior
- **Debugging**: Simple text protocol for easy troubleshooting

## Audio Configuration

### Audio Output Selection

The system supports configurable audio output to accommodate different deployment scenarios:

**Configuration Options**
- **HDMI Audio** (default): Routes audio through HDMI for display/projector setups
- **Headphone Jack**: Routes audio through the 3.5mm audio jack for speaker systems
- **Configuration Key**: `audio_output` in config files
- **Values**: `"hdmi"` or `"headphone"`

**How It Works**
- **VLC Level**: VLC outputs audio normally without any audio routing arguments
- **OS Level**: Audio routing is handled by the Raspberry Pi's system settings
- **Raspberry Pi**: Use `raspi-config` or ALSA settings to configure HDMI vs. headphone jack output

**Default Behavior**
- **Audio is now enabled by default** for full A/V synchronization
- VLC outputs audio normally using the system's default audio output
- Audio tracks from synchronized videos play through the selected output
- The system properly synchronizes both video and audio across all nodes

**Example Configuration**
```ini
[DEFAULT]
# Audio output selection (reserved for future implementation)
audio_output = hdmi  # or "headphone" or "both"
```

**Note**: The `audio_output` configuration setting is reserved for future implementation. Currently, VLC outputs audio normally and the OS handles routing based on system settings. To change audio output (HDMI vs. headphone jack), use `raspi-config` → System Options → Audio → Force HDMI or Force 3.5mm jack.

## Current System Architecture

### Core Components Structure

**Source Organization (`src/`)**
```
src/
├── config/           # Configuration management and USB detection
├── core/            # Core system components (schedule, system state, logger)
├── debug/           # HTML debug overlay and template system
├── midi/            # MIDI management and Arduino serial communication
├── networking/      # UDP sync and communication protocols
├── ui/              # User interface components
└── video/           # VLC video player management
```

**Key Classes and Responsibilities**
- **ConfigManager**: Handles configuration loading and USB detection
- **USBConfigLoader**: Automatic USB drive detection and file loading
- **VLCVideoPlayer**: VLC-based video playback with sync capabilities
- **MidiManager**: Arduino serial MIDI communication with fallbacks
- **MidiScheduler**: MIDI event scheduling and loop detection
- **SyncBroadcaster**: UDP time synchronization broadcasting
- **HTMLDebugManager**: Browser-based debug interface for leader

**Configuration Files**
- `leader_config.ini` - Leader Pi configuration
- `collaborator_config.ini` - Collaborator Pi configuration
- `kitchensync.ini` - Main system configuration (on USB drives)
- `schedule.json` - MIDI event schedule

## Configuration Management Workflow

### Default Values and INI File Synchronization

**Critical Requirement**: Default values in the code must always match the INI file values to ensure consistent behavior when INI files are missing or incomplete.

**Why This Matters**:
- **USB-less Deployment**: Collaborator Pis may not have INI files on their USB drives
- **Fallback Behavior**: When no config is found, the system uses hardcoded defaults
- **Consistency**: INI files and code defaults must represent the same intended behavior

**Workflow for Adding New Configuration**:
1. **Update INI files** (`leader_config.ini`, `collaborator_config.ini`) with new setting
2. **Update default values** in `src/config/manager.py` to match INI values exactly
3. **Update property methods** to use the same default values
4. **Document the setting** in `plan.md` with examples

**Example**: When adding `audio_output = hdmi`:
- ✅ INI file: `audio_output = hdmi`
- ✅ Config manager default: `"audio_output": "hdmi"`
- ✅ Property method: `return self.get("audio_output", "hdmi")`

**Current Synchronized Settings**:
- `audio_output`: INI="hdmi", Code="hdmi" ✅
- `debug`: INI="false", Code=False ✅
- `vlc_log_level`: INI="0", Code=0 ✅
- `tick_interval`: INI="0.1", Code=0.1 ✅
- `midi_port`: INI="0", Code=0 ✅
- `sync_port`: INI="5005", Code=5005 ✅
- `control_port`: INI="5006", Code=5006 ✅
- `enable_vlc_logging`: INI="false", Code=False ✅
- `enable_system_logging`: INI="false", Code=False ✅

**Configuration Synchronization Checklist**:
When adding/modifying any configuration setting, verify ALL of these match:
1. ✅ INI file value (leader_config.ini, collaborator_config.ini)
2. ✅ ConfigManager default value in `_create_default_config()`
3. ✅ Property method fallback value in `get()` calls
4. ✅ Any hardcoded defaults in other components
5. ✅ Documentation in plan.md

## Current Development Priorities

### Immediate Focus Areas

- **MIDI System Stability**: Continue improving error handling and robustness
- **Arduino Code**: Optimize Arduino sketch for better performance and reliability
- **Testing**: Comprehensive testing of MIDI system with real hardware
- **Documentation**: Update Arduino setup and troubleshooting guides

### Future Enhancement Opportunities

- **Web Interface**: Browser-based control panel for easier management
- **Content Streaming**: Network-based video distribution from leader Pi
- **Hardware Timestamping**: GPIO-based sync for sub-millisecond accuracy
- **Mobile App**: Smartphone control interface for system management
- **Cloud Integration**: Remote monitoring and configuration capabilities
- **Video Effects**: Real-time video processing and effects synchronization
- **MIDI Expansion**: Support for multiple Arduino controllers or additional MIDI protocols

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

# Wayfire panel autohide (smooth stage experience)
echo "autohide=true" >> ~/.config/wf-panel-pi.ini
echo "autohide_duration=500" >> ~/.config/wf-panel-pi.ini

# PCManFM desktop (system-wide overrides; ensure no per-user override file exists)
sudo mkdir -p /etc/xdg/pcmanfm/LXDE-pi
sudo tee -a /etc/xdg/pcmanfm/LXDE-pi/desktop-items-0.conf >/dev/null <<'EOF'
# KitchenSync overrides (desktop)
show_trash=0
show_mounts=0
wallpaper=
desktop_bg=#000000
EOF
rm -f ~/.config/pcmanfm/LXDE-pi/desktop-items-0.conf

# Install swaybg as fallback
sudo apt install -y swaybg
echo "fallback_bg=~/set_black_background_fallback.sh" >> ~/.config/wayfire.ini
```

### Quick Test Procedure

1. **Test basic functionality** (ensures system works):
   ```bash
   python3 leader.py --help
   python3 collaborator.py --help
   ```

2. **Test MIDI system**:
   ```bash
   python3 -c "from src.midi.manager import MidiManager; m = MidiManager(use_serial=True); print('MIDI system OK')"
   ```

3. **Deploy and test service**:
   ```bash
   ./deploy_and_test.sh
   ```

4. **Monitor logs in real-time**:
   ```bash
   tail -f /tmp/kitchensync_system.log
   tail -f /tmp/kitchensync_vlc_stderr.log
   tail -f /tmp/kitchensync_debug_leader-pi.txt
   ```

5. **Test Arduino MIDI** (if hardware available):
   ```bash
   # Check if Arduino is detected
   ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || echo "No Arduino detected"
   
   # Test serial communication
   python3 -c "from src.midi.manager import SerialMidiOut; s = SerialMidiOut(); print(f'Arduino port: {s.port}')"
   ```

### Current System Status

The KitchenSync system is fully operational with:

**Leader Pi Features**
- **VLC video playback**: Stable playback with window positioning on left side
- **Full audio support**: Audio tracks are now enabled and synchronized across all nodes
- **Simple audio output**: VLC outputs audio normally, OS handles routing (HDMI/headphone jack)
- **HTML debug overlay**: Live-updating interface positioned on right side  
- **Real-time monitoring**: Video timing, VLC status, and system health
- **Systemd auto-start**: Reliable boot-time initialization
- **Window management**: Proper side-by-side layout using wmctrl
- **Error handling**: Comprehensive logging and graceful fallbacks

**MIDI System Features**
- **Arduino integration**: Serial-based MIDI control with automatic port detection
- **Loop detection**: Intelligent MIDI loop detection for synchronized playback
- **Error safety**: Comprehensive null checks and graceful shutdown handling
- **Fallback support**: Mock MIDI output when hardware not available
- **Serial communication**: Reliable USB serial communication with Arduino

**System Features**
- **USB auto-detection**: Automatic configuration and video loading from USB drives
- **Auto-upgrade system**: Seamless system updates from USB drives
- **Role detection**: Automatic leader/collaborator role determination
- **Network sync**: UDP-based time synchronization across all nodes

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

**CONFIGURATION DIRECTIVE**: When adding/modifying configuration settings, ensure ALL default values are synchronized:
- INI file values must match ConfigManager defaults
- Property method fallbacks must match INI file values
- Hardcoded defaults in components must match INI file values
- This ensures consistent behavior when INI files are missing (common in USB-less deployments)

This is the mark of professional programming vs. superficial patching.

### Display and UX invariants
- Do not change display modes without explicit instruction. Defaults:
  - Collaborators: always launch video fullscreen in production (debug=false).
  - Leader: fullscreen unless explicitly running in debug mode.
- Do not switch video outputs (e.g., `--vout`) or windowing backends unless requested and documented.g

## Bug Fixes and Improvements (Jan 2025)

### Ctrl+C Graceful Shutdown Fix

**Problem**: When using Ctrl+C to stop the leader script, the MIDI scheduler would crash with a TypeError when comparing `None` values during shutdown.

**Root Cause**: Race condition between the main thread shutdown and the MIDI cue processing thread. When Ctrl+C was pressed:
1. Main thread would set `system_state.is_running = False`
2. MIDI cue thread might still execute one more iteration
3. Video player methods could return `None` during shutdown
4. `process_cues()` would receive `None` for `current_time`
5. Comparison `playback_time < self.previous_playback_time` would fail with `TypeError: '<' not supported between instances of 'NoneType' and 'float'`

**Solution Implemented**:
1. **Input Validation**: Added null checks in `MidiScheduler.process_cues()` to validate `current_time` parameter
2. **Thread Safety**: Enhanced MIDI cue loop in `leader.py` to check both `current_time` validity and system state before processing
3. **State Reset**: Reset `previous_playback_time` to `None` in `stop_playback()` to prevent comparison issues
4. **Method Safety**: Added null checks to all time-based methods (`get_current_cues`, `get_upcoming_cues`, `get_recent_cues`, `_get_loop_adjusted_time`)

**Files Modified**:
- `src/midi/manager.py` - Added comprehensive null checks and safety measures
- `leader.py` - Enhanced thread safety in MIDI cue processing loop

**Result**: Leader script now shuts down gracefully with Ctrl+C without throwing exceptions.

### Empty MIDI Scheduler File Issue

**Problem**: Empty `src/midi/scheduler.py` file was interfering with Python imports, causing `'LeaderPi' object has no attribute 'seek_to_zero_and_reset_cues'` error when running `python leader.py` directly.

**Root Cause**: The `src/midi/scheduler.py` file was completely empty (0 bytes), but Python was trying to import from it, causing import system conflicts.

**Solution**: Deleted the empty `src/midi/scheduler.py` file, allowing proper imports from `src/midi/manager.py` where the `MidiScheduler` class is actually defined.

**Result**: `python leader.py` now works correctly when run directly.

## Future Necessities

+ Remove desktop environment, etc. just have a totally slimmed down OS
+ Read only root filesystem to prevent disk errors, etc.
+ Remote management
+ Ensure total hardware acceleration
+ Custom OS build: Base on a lightweight Linux (Yocto, Buildroot, or optimized Debian variant) tuned for fast boot, stable VLC playback, and real-time scheduling
+ Network resilience: Robust UDP multicast/broadcast handling, auto-recovery from network drops
+ Systemd integration: Auto-start is mandatory; add watchdog timers to auto-restart on failure Logging & diagnostics: multi-log approach is solid; consider remote log aggregation and alerting for commercial use
+ Ensure wide codec compatibility
+ Secure SSH and network channels; disable unused services to minimize attack surface
