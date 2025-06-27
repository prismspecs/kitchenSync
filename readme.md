# KitchenSync - Synchronized Video Playback & Relay Control System

This project enables multiple Raspberry Pis to:
- Play videos simultaneously (same or different videos per Pi)
- Trigger relays at specific timecodes
- Stay synchronized via UDP broadcast over LAN/Wi-Fi
- Provide centralized control and configuration through the leader Pi

## 📦 Components
- Multiple Raspberry Pis (each with unique ID)
- Relay modules connected to GPIO (default: GPIO18)
- Video files stored locally or on USB drives
- Schedule file (`schedule.json`) defining cue timings
- Leader Pi with user interface for system control

## 📂 Files
- `leader.py` — Runs on leader Pi, broadcasts time sync and provides user interface
- `collaborator.py` — Runs on each collaborator Pi, receives time sync, starts video, triggers relays
- `schedule.json` — List of relay cues by timecode
- `collaborator_config.ini` — Configuration file for collaborator Pis (unique per Pi)
- `setup.sh` — Installation script for Raspberry Pi setup
- `requirements.txt` — Python dependencies
- `USAGE.md` — Detailed usage guide and troubleshooting
- `videos/` — Directory for video files (can also use USB drives)

## 🛠 Setup Instructions

### 1. Install Dependencies
```bash
sudo apt update
sudo apt install omxplayer
```

### 2. Configuration

#### Assign Unique IDs
Each Pi should be assigned a unique ID for identification and configuration.

#### Connect Hardware
- Connect relay module to GPIO18 (or modify pin in `collaborator.py`)
- Power and network each Raspberry Pi
- Connect USB drives if using external video storage

### 3. Prepare Files

**On each collaborator Pi:**
- `collaborator.py`
- `schedule.json`
- Video files (locally or on USB drive)

**On the leader Pi:**
- `leader.py`
- User interface files for system control and configuration

### 4. Define Schedule

Example `schedule.json`:
```json
[
  { "time": 5.0, "relay": 1 },
  { "time": 10.0, "relay": 0 },
  { "time": 15.0, "relay": 1 }
]
```

### 5. Run the System

**On Leader Pi:**
```bash
python3 leader.py
```

**On Each Collaborator Pi:**
```bash
python3 collaborator.py
```

Each collaborator Pi will wait for time sync from the leader, then begin playback and execute relay triggers based on the shared clock.

## 🚀 Quick Start

### Leader Pi
```bash
python3 leader.py
```
Use the interactive interface to start/stop the system and manage schedules.

### Collaborator Pi  
```bash
# Edit config file first (set unique pi_id and video_file)
nano collaborator_config.ini
python3 collaborator.py
```

See `USAGE.md` for detailed instructions and troubleshooting.

## ⏱ Sync Precision

UDP time sync is accurate to ~10–30ms on a typical LAN. For tighter synchronization, consider wired GPIO triggers or hardware timestamping.

## 🧪 Testing

- Use `omxplayer` flags like `--no-osd` and `--vol` for clean output
- Monitor relay switching with a multimeter or LED
- Test with different video files on different Pis to verify individual control

## � Features

- **Flexible Video Assignment:** Each Pi can play different videos or all play the same
- **Centralized Control:** Leader Pi provides interface for uploading files and configuration
- **Multiple Storage Options:** Videos from local storage or USB drives
- **Unique Pi Identification:** Each device has a configurable unique ID
- **Scalable Architecture:** Add collaborator Pis as needed

## 🗒 Notes

- **Performance:** `omxplayer` offers lower latency and better Pi performance than VLC
- **Time Sync:** Ensure NTP is either disabled or all Pis use the same server to avoid drift
- **Network:** Works on both wired and wireless networks (wired recommended for best sync)
- **File Management:** Leader Pi can manage video files and push updates to collaborator Pis