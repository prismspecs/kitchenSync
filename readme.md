# KitchenSync - Synchronized Video Playback & MIDI Output System

A modern, plug-and-play system for synchronized video playbook and MIDI output across multiple Raspberry Pis. Features automatic USB drive detection, VLC-based video playback with drift correction, and Arduino-based MIDI relay control with JSON schedule support.

## 🚀 Quick Start

### 1. Install on All Pis (Identical Setup)
```bash
git clone https://github.com/prismspecs/kitchenSync.git
cd kitchenSync
./setup.sh
sudo reboot
```

### 2. Prepare USB Drives
**Leader USB Drive:**
```
📁 USB Drive
├── kitchensync.ini      (is_leader = true, device_id = leader-pi)
├── test_video.mp4       (main video)
└── schedule.json        (MIDI schedule)
```

**Collaborator USB Drives:**
```
📁 USB Drive Pi-002
├── kitchensync.ini      (is_leader = false, device_id = pi-002)
└── video2.mp4           (video for this Pi)
```

### 3. Deploy and Power On
1. **Plug USB drives** into respective Pis
2. **Power on all Pis** 
3. **System automatically starts** via systemd service

## ✨ Key Features

- **🎬 Synchronized Video Playback**: Multiple Pis play videos in perfect sync using VLC with advanced drift correction
- **🎹 Precise MIDI Output**: Timecoded MIDI events via Arduino serial with sub-50ms accuracy
- **🔌 Plug-and-Play USB**: Automatic USB drive detection, mounting, and video file selection
- **🎯 Automatic Role Detection**: USB-based configuration determines leader vs collaborator roles
- **🚀 Auto-Start System**: Systemd service for boot-time initialization and hands-free operation
- **📡 Network Synchronization**: UDP broadcast for real-time time sync across all devices

## How It Works

Every Pi runs the same installation and service.

1. **Identical Setup**: All Pis have the same installation with `kitchensync.service` enabled
2. **USB-Drive Configuration**: Each Pi gets its role from a USB drive configuration file
3. **Automatic Detection**: `kitchensync.py` scans for USB drives and reads `kitchensync.ini`
4. **Role Execution**: Based on the config, it automatically starts as leader or collaborator

```ini
# USB drive contains kitchensync.ini:
[KITCHENSYNC]
is_leader = true         # Makes this Pi the leader
device_id = leader-pi    # OR pi-002, pi-003, etc.
debug = false           # Optional debug mode
```

## 🖥️ Hardware Requirements

- Multiple Raspberry Pis (Pi 4 recommended for 4K video)
- **Arduino board** (Uno, Nano, or similar) with USB connection for MIDI control
- USB drives for video storage and configuration
- Network connectivity (wired recommended for best sync)

## 🔌 Arduino MIDI Setup

### Hardware Requirements
- **Arduino Board**: Uno, Nano, or compatible board
- **USB Connection**: Standard USB cable for serial communication
- **Arduino Sketch**: `arduino/midi_controller/midi_controller.ino`

### Features
- **Port Scanning**: System automatically detects Arduino on `/dev/ttyACM*` or `/dev/ttyUSB*`
- **Fallback**: Uses mock MIDI output when hardware not available
- **Communication**: Simple text-based protocol over USB serial
  - **Note On**: `noteon <channel> <note> <velocity>`
  - **Note Off**: `noteoff <channel> <note> 0`
  - **Baud Rate**: 9600

## 📂 Project Structure

- `kitchensync.py` — Main auto-start script with USB configuration detection
- `leader.py` — Leader Pi script with video playbook and system coordination
- `collaborator.py` — Collaborator Pi script for synchronized playback and MIDI output
- `schedule.json` — MIDI cue timings and events (Arduino relay control format)
- `kitchensync.service` — Systemd service for automatic startup
- `arduino/` — Arduino sketches and MIDI controller code

## 💾 Configuration Examples

### Leader Pi Configuration
**kitchensync.ini:**
```ini
[KITCHENSYNC]
is_leader = true
device_id = leader-pi
debug = false
video_file = test_video.mp4
```

### Collaborator Pi Configuration
**kitchensync.ini:**
```ini
[KITCHENSYNC]
is_leader = false
device_id = pi-002
debug = false
video_file = collaborator_video.mp4
```

### MIDI Schedule (schedule.json)
```json
[
    {
        "time": 2.0,
        "type": "note_on",
        "channel": 1,
        "note": 63,
        "velocity": 127,
        "description": "Output 1 ON - House lights"
    },
    {
        "time": 10.0,
        "type": "note_off",
        "channel": 1,
        "note": 63,
        "velocity": 0,
        "description": "Output 1 OFF - House lights"
    }
]
```

**Schedule Format:**
- **time**: Seconds from video start (float)
- **type**: `note_on` or `note_off` for relay control
- **channel**: MIDI channel (1-16, typically 1 for Arduino)
- **note**: MIDI note number (0-127, maps to Arduino outputs)
- **velocity**: 127 for full power, 0 for off
- **description**: Human-readable description

## 🎮 Manual Operation

### Leader Pi
```bash
# Interactive mode
python3 leader.py

# Automatic mode (no interface)
python3 leader.py --auto
```

### Collaborator Pi
```bash
python3 collaborator.py [config_file]
```

### Main Script (Auto-Detection)
```bash
# Detects USB config and starts appropriate role
python3 kitchensync.py
```

## 🎮 Interactive Controls

### Leader Pi Commands
- `start` - Start synchronized playback across all Pis
- `stop` - Stop playback on all Pis  
- `status` - Show system status and connected Pis
- `schedule` - Edit the MIDI cue schedule
- `quit` - Exit the program

### Schedule Editor
- `add` - Add new MIDI cues
- `remove <number>` - Remove specific cues
- `clear` - Clear all cues  
- `save` - Save schedule and return to main menu

## 🎬 Video Management

### Supported Formats
- MP4, AVI, MKV, MOV, M4V, WMV, FLV, WebM
- H.264 encoding recommended for best compatibility

### File Selection Priority
1. USB drive video files (highest priority)
2. Local `./videos/` directory
3. Configured `video_sources` paths
4. Current directory fallback

## 🎹 Network Configuration

- **Sync Port**: 5005 (UDP broadcast for time sync)
- **Control Port**: 5006 (UDP for commands and registration)  
- **Discovery**: Automatic Pi detection via broadcast
- **Precision**: ~10-30ms accuracy on typical LAN

## 🚀 Deployment Commands

```bash
# Enable auto-start on all Pis
sudo systemctl enable kitchensync.service

# Start system immediately
sudo systemctl start kitchensync.service

# Monitor system status
sudo systemctl status kitchensync.service
```

## 🙏 Acknowledgments

This project was inspired by and built upon the excellent work of several open-source projects:

- **[omxplayer-sync](https://github.com/turingmachine/omxplayer-sync/)** - Pioneer implementation of synchronized video playback across multiple Raspberry Pis using omxplayer
- **[videowall](https://github.com/reinzor/videowall)** - Modern approach to synchronized video walls with network-based coordination
- **[rpi-video-sync-looper](https://github.com/andrewintw/rpi-video-sync-looper/)** - Raspberry Pi video synchronization with looping capabilities

KitchenSync builds on these concepts while adding VLC-based playback, Arduino MIDI integration, and USB-driven plug-and-play configuration.

## 📚 Documentation

- **[MIDI Relay Control Guide](docs/MIDI_RELAY_CONTROL.md)** - Complete guide for Arduino MIDI relay control
- **[Troubleshooting](#troubleshooting)** - Common issues and solutions