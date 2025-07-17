# KitchenSync - Synchronized Video Playback & MIDI Output System

This project enables multiple Raspberry Pis to:
- Play videos simultaneously (same or different videos per Pi)
- Output MIDI data at specific timecodes via USB MIDI interface
- Stay synchronized via UDP broadcast over LAN/Wi-Fi
- Provide centralized control and configuration through the leader Pi

## 📦 Components
- Multiple Raspberry Pis (each with unique ID)
- USB MIDI interface connected to each Pi
- Video files stored locally or on USB drives
- Schedule file (`schedule.json`) defining MIDI cue timings
- Leader Pi with user interface for system control

## 📂 Files
- `leader.py` — Runs on leader Pi, broadcasts time sync and provides user interface
- `collaborator.py` — Runs on each collaborator Pi, receives time sync, starts video, outputs MIDI data
- `schedule.json` — List of MIDI cues by timecode (note, velocity, channel, etc.)
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

# Install Python MIDI library
pip3 install python-rtmidi

# Install Python DBus library for video sync correction
pip3 install dbus-python
```

### 2. Configuration

#### Assign Unique IDs
Each Pi should be assigned a unique ID for identification and configuration.

#### Connect Hardware
- Connect USB MIDI interface to each Raspberry Pi
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
  { "time": 5.0, "note": 60, "velocity": 127, "channel": 1, "type": "note_on" },
  { "time": 5.5, "note": 60, "velocity": 0, "channel": 1, "type": "note_off" },
  { "time": 10.0, "note": 64, "velocity": 100, "channel": 1, "type": "note_on" },
  { "time": 10.5, "note": 64, "velocity": 0, "channel": 1, "type": "note_off" },
  { "time": 15.0, "control": 7, "value": 127, "channel": 1, "type": "control_change" }
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

Each collaborator Pi will wait for time sync from the leader, then begin playback and execute MIDI output based on the shared clock.

## 🚀 Quick Start

### Leader Pi
```bash
python3 leader.py
```
Use the interactive interface to start/stop the system and manage schedules.

### Collaborator Pi  
```bash
# Edit config file first (set unique pi_id, video_file, and midi_port)
nano collaborator_config.ini
python3 collaborator.py
```

See `USAGE.md` for detailed instructions and troubleshooting.

## ⏱ Sync Precision

UDP time sync is accurate to ~10–30ms on a typical LAN. For tighter synchronization, consider wired GPIO triggers or hardware timestamping.

### Advanced Video Sync Technology

KitchenSync incorporates advanced synchronization techniques inspired by omxplayer-sync:

**Median Deviation Filtering:**
- Collects multiple sync measurements over time (configurable sample size)
- Uses statistical median to filter out temporary glitches and network hiccups
- Only triggers corrections when median deviation consistently exceeds threshold
- Prevents false corrections from momentary position reading errors

**Intelligent Correction Strategy:**
- Small deviations: Seamless seeking without interrupting playback
- Large deviations (>2s): Temporarily pauses video during correction to prevent audio/video artifacts
- Grace period after corrections prevents immediate re-checking
- Configurable thresholds allow tuning for different network conditions

**Why Median Filtering is Superior:**
- **Noise Immunity:** Single bad readings (network lag, CPU spike) don't trigger corrections
- **Stability:** Prevents "correction oscillation" where frequent small adjustments make sync worse  
- **Reliability:** Statistical approach ensures corrections only happen for genuine drift
- **Performance:** Reduces unnecessary seek operations that can cause stuttering

## 🧪 Testing

- Use `omxplayer` flags like `--no-osd` and `--vol` for clean output
- Monitor MIDI output with a MIDI monitor or DAW software
- Test with different video files on different Pis to verify individual control
- Verify MIDI interface connectivity with `aconnect -l` or `amidi -l`

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
- **MIDI Timing:** MIDI data is timecoded to the video, ensuring synchronized playback across all devices
- **USB MIDI:** Each Pi requires a USB MIDI interface; class-compliant devices work best
- **Video Sync:** Advanced drift correction with median filtering keeps videos synchronized during playback (requires DBus)
- **Sync Tolerance:** Videos are corrected if median deviation exceeds threshold (configurable)
- **Outlier Filtering:** Median deviation filtering prevents false corrections from temporary glitches
- **Smart Corrections:** Large deviations trigger pause-during-correction to avoid playback artifacts