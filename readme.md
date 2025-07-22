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
- `videos/` — Directory for video files (can also use USB drives)

## 🛠 Setup Instructions

### 1. Install Dependencies

```bash
# Fix APT cache if corrupted (common on Raspberry Pi OS Bookworm)
sudo rm -rf /var/lib/apt/lists/*
sudo apt update

# Install VLC for video playback
sudo apt install -y vlc libvlc-dev python3-vlc

# Install system packages for Python libraries
sudo apt install -y python3-pip python3-venv python3-dev libasound2-dev

# Create a virtual environment for Python packages (recommended for modern systems)
python3 -m venv kitchensync-env
source kitchensync-env/bin/activate

# Install Python dependencies
pip install python-rtmidi dbus-python python-vlc
```

**Note:** Always activate your virtual environment before running the scripts:
```bash
source kitchensync-env/bin/activate
python3 leader.py
# or
python3 collaborator.py
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
  {
    "time": 10.0,
    "note": 64,
    "velocity": 100,
    "channel": 1,
    "type": "note_on"
  },
  { "time": 10.5, "note": 64, "velocity": 0, "channel": 1, "type": "note_off" },
  {
    "time": 15.0,
    "control": 7,
    "value": 127,
    "channel": 1,
    "type": "control_change"
  }
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

### Setup (run once)

```bash
# Run the setup script
chmod +x setup.sh
./setup.sh
```

### Leader Pi

```bash
# Activate virtual environment
source kitchensync-env/bin/activate

python3 leader.py
```

Use the interactive interface to start/stop the system and manage schedules.

### Collaborator Pi

```bash
# Activate virtual environment
source kitchensync-env/bin/activate

# Edit config file first (set unique pi_id, video_file, and midi_port)
nano collaborator_config.ini
python3 collaborator.py
```

## 🖥️ Usage & Commands

When running `leader.py`, you'll get an interactive command prompt:

- `start` - Start synchronized playback across all Pis
- `stop` - Stop playback on all Pis
- `status` - Show system status and connected Pis
- `schedule` - Edit the MIDI cue schedule
- `quit` - Exit the program

### Schedule Editor

- `add` - Add new MIDI cues (note on/off, control changes)
- `remove <number>` - Remove specific cues
- `clear` - Clear all cues
- `save` - Save schedule and return to main menu

## 📝 Collaborator Configuration

Each collaborator Pi needs its own config file:

```ini
[DEFAULT]
# Unique identifier (must be different for each Pi)
pi_id = pi-001

# Video file to play (can be different per Pi)
video_file = video.mp4

# MIDI port for output (0 = first available port)
midi_port = 0

# Directories to search for video files
video_sources = ./videos/,/media/usb/,/media/usb0/,/media/usb1/

# Video sync correction settings
sync_tolerance = 1.0              # Deprecated - kept for compatibility
sync_check_interval = 5.0         # How often to check sync (seconds)

# Advanced sync settings (adapted for VLC)
deviation_threshold = 0.5         # Median deviation threshold for correction (seconds)
max_deviation_samples = 10        # Number of samples for median calculation
pause_threshold = 2.0             # Deviation threshold for pause-during-correction (seconds)
sync_grace_time = 3.0             # Wait time after correction before checking again (seconds)
```

#### Sync Parameter Explanation:

- **deviation_threshold**: Minimum median deviation to trigger correction (0.5s default)
- **max_deviation_samples**: Sample size for median filtering (10 samples default)
- **pause_threshold**: Large deviations above this trigger pause-during-correction (2.0s default)
- **sync_grace_time**: Prevents immediate re-checking after correction (3.0s default)

For multiple Pis, create separate config files:

- `collaborator_config_pi2.ini`
- `collaborator_config_pi3.ini`
- etc.

Run collaborators with specific configs:

```bash
python3 collaborator.py collaborator_config_pi2.ini
```

## 🎬 Video File Management

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

## 🎹 MIDI Output

MIDI data is output via USB MIDI interface based on the schedule:

```json
[
  { "time": 5.0, "note": 60, "velocity": 127, "channel": 1, "type": "note_on" },
  { "time": 5.5, "note": 60, "velocity": 0, "channel": 1, "type": "note_off" },
  {
    "time": 10.0,
    "control": 7,
    "value": 127,
    "channel": 1,
    "type": "control_change"
  }
]
```

### MIDI Message Types:

- **note_on**: Trigger a note with specified velocity
- **note_off**: Release a note
- **control_change**: Send control change message (CC)

## 🌐 Network Configuration

- **Sync Port**: 5005 (UDP broadcast for time sync)
- **Control Port**: 5006 (UDP for commands and registration)
- **Network**: All Pis must be on the same network
- **Broadcast**: Uses 255.255.255.255 for discovery

## ⏱ Sync Precision

UDP time sync is accurate to ~10–30ms on a typical LAN. For tighter synchronization, consider wired GPIO triggers or hardware timestamping.

### Advanced Video Sync Technology

KitchenSync incorporates advanced synchronization techniques with VLC:

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

**VLC Integration Benefits:**

- **Cross-Platform Compatibility:** Works on Raspberry Pi OS, desktop Linux, and other systems
- **Python API:** Direct control through VLC Python bindings for precise seeking and position tracking
- **Robust Playback:** VLC's mature media engine handles various video formats reliably
- **Active Development:** VLC is actively maintained and supported

**Why Median Filtering is Superior:**

- **Noise Immunity:** Single bad readings (network lag, CPU spike) don't trigger corrections
- **Stability:** Prevents "correction oscillation" where frequent small adjustments make sync worse
- **Reliability:** Statistical approach ensures corrections only happen for genuine drift
- **Performance:** Reduces unnecessary seek operations that can cause stuttering

**VLC Technical Advantages:**

- **Precise Control:** Python bindings provide accurate position tracking and seeking
- **Format Support:** Handles more video formats and codecs than legacy players
- **Cross-Platform:** Same codebase works on Pi and desktop systems for testing
- **Error Handling:** Better error reporting and recovery mechanisms

## 🧪 Testing

- Monitor video playback with VLC's built-in controls and logging
- Monitor MIDI output with a MIDI monitor or DAW software
- Test with different video files on different Pis to verify individual control
- Verify MIDI interface connectivity with `aconnect -l` or `amidi -l`
- Check VLC installation: `vlc --version`

## 🛠️ Troubleshooting

### Common Setup Issues

**APT Cache Issues:**
```bash
# Fix corrupted package cache (common on some Raspberry Pi systems)
sudo rm -rf /var/lib/apt/lists/*
sudo apt update
```

**Python Environment:**
```bash
# Create and use virtual environment (recommended)
python3 -m venv kitchensync-env
source kitchensync-env/bin/activate
pip install python-rtmidi dbus-python python-vlc

# Always activate before running scripts
source kitchensync-env/bin/activate
python3 leader.py
```

### Pi Not Appearing in Status

- Check network connectivity
- Ensure both leader and collaborator are running
- Verify ports 5005 and 5006 are not blocked

### MIDI Not Working

- Check USB MIDI interface connectivity: `aconnect -l` or `amidi -l`
- Verify MIDI port configuration in `collaborator_config.ini`
- Test with a MIDI monitor or DAW software
- Ensure `python-rtmidi` is installed in your virtual environment

### Video Not Playing

- Check VLC installation: `vlc --version`
- Install VLC if missing: `sudo apt install vlc libvlc-dev python3-vlc`
- Verify video file exists in configured locations
- Check video file format (MP4 recommended)
- Ensure `python-vlc` is installed: `pip install python-vlc`

### Performance Issues

- Use wired network connection for best sync performance
- Ensure all Pis are on the same network segment
- Check CPU usage during playback
- Consider video file resolution and bitrate

### Auto-Discovery

Collaborator Pis automatically register with the leader when started.

### Heartbeat Monitoring

Leader tracks collaborator Pi status with periodic heartbeats.

### Flexible Video Sources

Supports local files, USB drives, and multiple search directories.

## 🏷️ Features

- **Flexible Video Assignment:** Each Pi can play different videos or all play the same
- **Centralized Control:** Leader Pi provides interface for uploading files and configuration
- **Multiple Storage Options:** Videos from local storage or USB drives
- **Unique Pi Identification:** Each device has a configurable unique ID
- **Scalable Architecture:** Add collaborator Pis as needed

## 🗒 Notes

- **Performance:** VLC provides excellent video playback performance on modern Raspberry Pi hardware
- **Compatibility:** VLC works across different operating systems and hardware platforms
- **Time Sync:** Ensure NTP is either disabled or all Pis use the same server to avoid drift
- **Network:** Works on both wired and wireless networks (wired recommended for best sync)
- **File Management:** Leader Pi can manage video files and push updates to collaborator Pis
- **MIDI Timing:** MIDI data is timecoded to the video, ensuring synchronized playback across all devices
- **USB MIDI:** Each Pi requires a USB MIDI interface; class-compliant devices work best
- **Video Sync:** Advanced drift correction with median filtering keeps videos synchronized during playback
- **Sync Tolerance:** Videos are corrected if median deviation exceeds threshold (configurable)
- **Outlier Filtering:** Median deviation filtering prevents false corrections from temporary glitches
- **Smart Corrections:** Large deviations trigger pause-during-correction to avoid playback artifacts
