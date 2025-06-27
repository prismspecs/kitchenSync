# KitchenSync Usage Guide

## Quick Start

### 1. Leader Pi Setup
```bash
# Run the leader Pi (provides control interface)
python3 leader.py
```

### 2. Collaborator Pi Setup  
```bash
# Edit config file for each Pi (assign unique IDs and video files)
nano collaborator_config.ini

# Run the collaborator Pi
python3 collaborator.py
```

## Leader Pi Commands

When running `leader.py`, you'll get an interactive command prompt:

- `start` - Start synchronized playback across all Pis
- `stop` - Stop playback on all Pis  
- `status` - Show system status and connected Pis
- `schedule` - Edit the relay cue schedule
- `quit` - Exit the program

## Schedule Editor

The schedule editor allows you to:
- `add` - Add new relay cues (time + relay state)
- `remove <number>` - Remove specific cues
- `clear` - Clear all cues
- `save` - Save schedule and return to main menu

## Configuration

### Collaborator Configuration (collaborator_config.ini)

Each collaborator Pi needs its own config file:

```ini
[DEFAULT]
# Unique identifier (must be different for each Pi)
pi_id = pi-001

# Video file to play (can be different per Pi)
video_file = video.mp4

# GPIO pin for relay control
relay_pin = 18

# Directories to search for video files
video_sources = ./videos/,/media/usb/,/media/usb0/,/media/usb1/
```

### Multiple Collaborator Pis

For multiple Pis, create separate config files:
- `collaborator_config_pi2.ini`
- `collaborator_config_pi3.ini` 
- etc.

Run collaborators with specific configs:
```bash
python3 collaborator.py collaborator_config_pi2.ini
```

## Video File Management

### Local Storage
Place video files in:
- `./videos/` directory
- Same directory as the scripts

### USB Storage
The system automatically searches USB drives:
- `/media/usb/`
- `/media/usb0/` 
- `/media/usb1/`

### Different Videos Per Pi

Each Pi can play a different video file by setting different `video_file` values in their config files:
- Pi 1: `video_file = intro.mp4`
- Pi 2: `video_file = main_show.mp4`  
- Pi 3: `video_file = outro.mp4`

## Relay Control

Relays are controlled via GPIO pin 18 (configurable) based on the schedule:

```json
[
  { "time": 5.0, "relay": 1 },   // Turn relay ON at 5 seconds
  { "time": 10.0, "relay": 0 },  // Turn relay OFF at 10 seconds  
  { "time": 15.0, "relay": 1 }   // Turn relay ON at 15 seconds
]
```

## Network Configuration

- **Sync Port**: 5005 (UDP broadcast for time sync)
- **Control Port**: 5006 (UDP for commands and registration)
- **Network**: All Pis must be on the same network
- **Broadcast**: Uses 255.255.255.255 for discovery

## Troubleshooting

### Pi Not Appearing in Status
- Check network connectivity
- Ensure both leader and collaborator are running
- Verify ports 5005 and 5006 are not blocked

### Video Not Playing
- **On Raspberry Pi**: Check if `omxplayer` is installed: `sudo apt install omxplayer`
- **On other systems (simulation)**: Install a video player: `sudo apt install vlc` or `mpv` or `ffmpeg`
- Verify video file exists in configured locations
- Check video file format (MP4 recommended)

### Simulation Mode
When running on non-Raspberry Pi systems (like Linux Mint, Ubuntu, etc.):
- GPIO operations are simulated and logged to console
- Video playback uses alternative players (VLC, MPV, FFplay, MPlayer)
- `omxplayer` is Raspberry Pi specific and won't work on other systems

### Auto-Discovery
Collaborator Pis automatically register with the leader when started.

### Heartbeat Monitoring  
Leader tracks collaborator Pi status with periodic heartbeats.

### Flexible Video Sources
Supports local files, USB drives, and multiple search directories.
