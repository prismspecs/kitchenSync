# KitchenSync Project Plan

## Overview

KitchenSync is a distributed video synchronization system for Raspberry Pi clusters. The system provides synchronized video playback and MIDI output across multiple nodes with automatic role detection, USB-based configuration, and systemd auto-start capabilities.

**System Status**: Fully operational with VLC-based video playback, Arduino serial MIDI control, and comprehensive error handling.

## System Architecture

### Core Components

**kitchensync.py** - Main auto-start script
- USB configuration detection and parsing
- Automatic role determination (leader vs collaborator)
- Subprocess management for launching appropriate mode
- Automatic upgrade system from USB drives

**leader.py** - Leader Pi coordinator
- Video playback with Python VLC bindings
- Time sync broadcasting (UDP port 5005)
- Collaborator Pi registration and heartbeat monitoring
- Interactive user interface with schedule editor
- MIDI scheduling with loop detection

**collaborator.py** - Collaborator Pi worker
- Time sync reception and drift correction
- Python VLC-based synchronized video playback
- Arduino serial MIDI output via USB
- Median filtering for sync accuracy

**src/midi/manager.py** - MIDI system core
- Arduino serial communication with automatic port detection
- MIDI event scheduling and loop detection
- Error handling and graceful fallbacks

### Source Organization
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

## Technical Stack

- **Language**: Python 3 (system-wide installation)
- **Media Player**: VLC with Python bindings
- **MIDI System**: Arduino serial-based controller with automatic port detection
- **Hardware**: Raspberry Pi 4 + Arduino board (Uno/Nano)
- **Networking**: UDP broadcast for time sync
- **Auto-Start**: systemd service for boot-time initialization
- **Configuration**: USB-based .ini files for automatic role detection

## Core Features

### Video & Audio Synchronization
- Videos with audio tracks synchronized across all nodes
- Median filtering with intelligent correction algorithms
- Continuous position tracking and drift compensation
- Loop detection for synchronized playback

### Arduino MIDI System
- Hardware: Arduino Uno, Nano, or compatible board
- Communication: Serial protocol over USB (9600 baud)
- Commands: `noteon <channel> <note> <velocity>`, `noteoff <channel> <note> 0`
- Auto-detection: Scans `/dev/ttyACM*` and `/dev/ttyUSB*` ports
- Fallback: Mock MIDI output when hardware unavailable
- Loop detection for synchronized playback

### USB Drive Auto-Detection
- Automatic mounting and detection on startup
- Configuration loading from `kitchensync.ini` for role determination
- Video file selection with priority ordering
- MIDI schedule loading from `schedule.json` files

## Development Status

### Implemented Features
- VLC migration from deprecated omxplayer
- USB drive auto-detection and mounting system
- Automatic role detection via USB configuration files
- Arduino serial MIDI system with automatic port detection
- MIDI scheduling with loop detection and error handling
- Error handling and graceful shutdown
- Systemd service configuration and auto-start system
- HTML debug overlay for leader Pi
- Production deployment workflow

### Technical Implementation
- Unified Python VLC approach for all nodes
- Audio track synchronization across all nodes
- Serial-based MIDI control with automatic hardware detection
- Null safety and graceful shutdown in MIDI system
- Drive detection and mounting
- Statistical median filtering for sync accuracy

## Configuration Files

### kitchensync.ini (USB Drive)
```ini
[KITCHENSYNC]
is_leader = true
device_id = leader-pi
debug = false
video_file = test_video.mp4
enable_vlc_logging = false
enable_system_logging = false
vlc_log_level = 0
```

### schedule.json (MIDI Events)
```json
[
    {
        "time": 2.0,
        "type": "note_on",
        "channel": 1,
        "note": 63,
        "velocity": 127,
        "description": "Output 1 ON - House lights"
    }
]
```

## Production Deployment

### System Requirements
- Raspberry Pi 4 (recommended for 4K video support)
- Raspberry Pi OS Bookworm (latest)
- Arduino board (Uno, Nano, or similar) with USB connection
- Network connectivity (Gigabit wired recommended)
- USB drives for configuration and video content

### Installation Process
1. Install VLC and Python dependencies system-wide
2. Optimize OS by removing unused packages and services
3. Configure desktop appearance for stage deployment
4. Copy systemd service file and enable auto-start
5. Prepare USB drives with configuration and video files
6. Deploy to Raspberry Pis and power on

### Operational Features
- Zero configuration deployment via USB drives
- Automatic node discovery and connection establishment
- Fault tolerance for node disconnections and reconnections
- Interactive interface for live system management
- Comprehensive system status and node health reporting

## Testing and Validation

### Quick Test Procedure
```bash
# Test basic functionality
python3 leader.py --help
python3 collaborator.py --help

# Test MIDI system
python3 -c "from src.midi.manager import MidiManager; m = MidiManager(use_serial=True); print('MIDI system OK')"

# Test Arduino detection
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || echo "No Arduino detected"
```

### Monitoring and Troubleshooting
```bash
# Monitor system logs
tail -f /tmp/kitchensync_system.log
tail -f /tmp/kitchensync_vlc_stderr.log

# Check service status
sudo systemctl status kitchensync.service
```

## Future Enhancements
- Web interface for browser-based control panel
- Mobile app for smartphone system management
- Network-based video distribution from leader Pi
- GPIO-based sync for sub-millisecond accuracy

## Programming Standards

### Critical Directives
- Consider ripple effects and hidden dependencies
- Default values in code must match INI file values
- Implement comprehensive error handling with graceful fallbacks
- Test changes thoroughly before deployment
