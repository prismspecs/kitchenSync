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
2. Copy systemd service file and enable auto-start
3. Prepare USB drives with configuration and video files
4. Deploy to Raspberry Pis and power on
5. System auto-starts and begins synchronized playback

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

## Debug Overlay Refactor (2024-06)

- The debug overlay (pygame window) now manages its own update loop and event handling in a dedicated thread.
- The main app (leader/collaborator) no longer runs a debug update thread or loop.
- The main app only calls `set_state` on the overlay to update info (video file, playback time, id, leader status, MIDI info) when state changes (e.g., after each sync tick or playback event).
- Only one overlay and one update loop exist per process, enforced by the overlay class.
- The overlay is non-blocking, thread-safe, and robust against lag or duplicate windows.
- This fixes previous issues with lag, duplicate windows, and missing info in debug mode.

### Debug Overlay API (2024-06)

- `DebugOverlay(pi_id, video_file, use_pygame=True)`
  - Creates and shows the overlay window, starts its own update thread.
- `overlay.set_state(video_file=..., current_time=..., total_time=..., midi_data=..., is_leader=..., pi_id=...)`
  - Updates the overlay's displayed state. Thread-safe.
- `overlay.cleanup()`
  - Closes the overlay and cleans up threads/resources.

### Usage Pattern

- Create the overlay after video file is found/loaded.
- On each sync tick or playback event, call `set_state` with the latest info.
- Do not run a separate debug update loop in the main app.

### Benefits

- No lag or bloat from duplicate overlays or threads.
- Overlay always shows the latest info (video file, time, id, leader status, MIDI info).
- Overlay appears promptly and closes cleanly.

## Diagnostics and Logs (2025-08)

To troubleshoot boot-time display issues (VLC vs. overlay), the system writes diagnostic logs to `/tmp` so they are available both under systemd and desktop sessions:

- System log: `/tmp/kitchensync_system.log`
- VLC (Python/CLI) details:
  - Main: `/tmp/kitchensync_vlc.log` (reserved)
  - Stdout: `/tmp/kitchensync_vlc_stdout.log`
  - Stderr: `/tmp/kitchensync_vlc_stderr.log`
- Overlay (file-based fallback): `/tmp/kitchensync_debug_leader-pi.txt`

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

Notes
- Logs are appended with timestamps; they survive until next reboot or manual cleanup.
- Environment snapshot includes `DISPLAY`, `XDG_SESSION_TYPE`, `XDG_RUNTIME_DIR`, `SDL_VIDEODRIVER`, `WAYLAND_DISPLAY`, `XAUTHORITY`.
