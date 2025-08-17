# KitchenSync - Synchronized Video Playback & MIDI Output System
A modern, plug-and-play system for synchronized video playback and MIDI output across multiple Raspberry Pis. Features automatic USB drive detection, VLC-based video playback with drift correction, and **Arduino-based MIDI relay control** with JSON schedule support.
**🔄 SYSTEM STATUS: FULLY OPERATIONAL** - All major components working, MIDI system migrated to Arduino serial, comprehensive error handling implemented.
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
3. **System automatically starts** in correct roles via systemd service
## 📚 Documentation
- **[MIDI Relay Control Guide](docs/MIDI_RELAY_CONTROL.md)** - Complete guide for relay control via MIDI
- **[Troubleshooting](#troubleshooting)** - Common issues and solutions
## 🔄 How It Works - Unified Startup System
**⚠️ IMPORTANT: Every Pi runs the same installation and service!**
### **Single Service, Multiple Roles**
1. **Identical Setup**: All Pis have the same installation with `kitchensync.service` enabled
2. **USB-Drive Configuration**: Each Pi gets its role from a USB drive configuration file
3. **Automatic Detection**: `kitchensync.py` scans for USB drives and reads `kitchensync.ini`
4. **Role Execution**: Based on the config, it automatically starts as leader or collaborator
```bash
# Same systemd service runs on ALL Pis:
sudo systemctl start kitchensync.service
# → Runs: python3 kitchensync.py
# USB drive contains kitchensync.ini:
[KITCHENSYNC]
is_leader = true    # Makes this Pi the leader
device_id = leader-pi   # OR pi-002, pi-003, etc.
debug = false       # Optional debug mode
# kitchensync.py then automatically:
# • If is_leader = true  → Starts leader.py
# • If is_leader = false → Starts collaborator.py
```
## ✨ Key Features
- **🎬 Synchronized Video Playback**: Multiple Pis play videos in perfect sync using VLC with advanced drift correction
- **🎹 Precise MIDI Output**: Timecoded MIDI events via Arduino serial with sub-50ms accuracy
- **🔌 Plug-and-Play USB**: Automatic USB drive detection, mounting, and video file selection
- **🎯 Automatic Role Detection**: USB-based configuration determines leader vs collaborator roles
- **🚀 Auto-Start System**: Systemd service for boot-time initialization and hands-free operation
- **📡 Network Synchronization**: UDP broadcast for real-time time sync across all devices
- **🎛️ Centralized Control**: Leader Pi provides interactive interface for system management
- **🔌 Arduino Integration**: Serial-based MIDI control with automatic hardware detection and fallback
## 🖥️ Hardware Requirements
- Multiple Raspberry Pis (Pi 4 recommended for 4K video)
- **Arduino board** (Uno, Nano, or similar) with USB connection for MIDI control
- USB drives for video storage and configuration
- Network connectivity (wired recommended for best sync)
## 🔌 Arduino MIDI Setup
### **Hardware Requirements**
- **Arduino Board**: Uno, Nano, or compatible board
- **USB Connection**: Standard USB cable for serial communication
- **Power**: USB-powered or external power supply
### **Arduino Sketch**
The system includes a custom Arduino sketch for MIDI control:
```
arduino/midi_controller/midi_controller.ino
```
**Required Arduino Libraries:**
- Standard Arduino libraries only (no external dependencies)
- Serial communication for USB connectivity
- Digital I/O for relay control outputs
**Sketch Features:**
- Serial command parsing for MIDI-like messages
- Relay output control (configurable pin assignments)
- Automatic port detection and communication
- Error handling and status reporting
### **Automatic Detection**
- **Port Scanning**: System automatically detects Arduino on `/dev/ttyACM*` or `/dev/ttyUSB*`
- **Fallback**: Uses mock MIDI output when hardware not available
- **Error Handling**: Graceful fallback to simulation mode
### **Communication Protocol**
- **Serial Commands**: Simple text-based protocol over USB serial
- **Note On**: `noteon <channel> <note> <velocity>`
- **Note Off**: `noteoff <channel> <note> 0`
- **Baud Rate**: 9600 (configurable for Arduino compatibility)
## 📂 Project Structure
- `kitchensync.py` — Main auto-start script with USB configuration detection
- `leader.py` — Leader Pi script with video playbook and system coordination
- `collaborator.py` — Collaborator Pi script for synchronized playback and MIDI output
- `schedule.json` — MIDI cue timings and events (Arduino relay control format)
- `kitchensync.service` — Systemd service for automatic startup
- `requirements.txt` — Python dependencies
- `arduino/` — Arduino sketches and MIDI controller code
## 💾 USB Drive Configuration Examples
### **Leader Pi USB Drive**
```
📁 Leader USB Drive
├── kitchensync.ini
├── leader_video.mp4
└── schedule.json
```
**kitchensync.ini** (Leader):
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
### **Collaborator Pi USB Drive** 
```
📁 Collaborator USB Drive
├── kitchensync.ini
└── collaborator_video.mp4
```
**kitchensync.ini** (Collaborator):
```ini
[KITCHENSYNC]
is_leader = false
device_id = pi-002
debug = false
video_file = collaborator_video.mp4
enable_vlc_logging = false
enable_system_logging = false
vlc_log_level = 0
```
### **Multiple Collaborators**
- Create separate USB drives with unique `device_id` values (pi-002, pi-003, pi-004, etc.)
- Each can have different video files for unique content per Pi
- All will automatically connect to the leader Pi
## 🚀 Complete Deployment Workflow
### **Step-by-Step Deployment (All Pis Get Same Installation)**
#### **1. Install on All Pis (Identical Setup)**
```bash
# Clone repository
git clone https://github.com/prismspecs/kitchenSync.git
cd kitchenSync
# Install dependencies 
sudo apt install -y vlc libvlc-dev python3-vlc python3-pip python3-dev libasound2-dev
sudo pip install python-vlc pygame --break-system-packages
# Enable service on ALL Pis
sudo systemctl enable kitchensync.service
```
#### **2. Prepare USB Drives (Different Configs)**
**Leader USB Drive:**
```
📁 USB Drive
├── kitchensync.ini      (is_leader = true, device_id = leader-pi)
├── test_video.mp4       (main video)
└── schedule.json        (MIDI schedule)
```
**Collaborator USB Drives:** (one per collaborator Pi)
```
📁 USB Drive Pi-002
├── kitchensync.ini      (is_leader = false, device_id = pi-002)
└── video2.mp4           (video for this Pi)
📁 USB Drive Pi-003  
├── kitchensync.ini      (is_leader = false, device_id = pi-003)
└── video3.mp4           (video for this Pi)
```
#### **3. Deploy and Power On**
1. **Plug USB drives** into respective Pis
2. **Power on all Pis** 
3. **Automatic startup** happens via systemd service:
   - `kitchensync.py` scans for USB configuration
   - Determines role from `is_leader` setting
   - Automatically starts `leader.py` or `collaborator.py`
4. **System starts playing** synchronized videos with MIDI output
### **Production Deployment Benefits**
- ✅ **Zero manual configuration** required on each Pi
- ✅ **Same installation** on every Pi - no per-device setup
- ✅ **USB-drive deployment** - just prepare drives and plug in
- ✅ **Automatic role detection** - no manual script selection
- ✅ **Boot-time startup** - no manual intervention needed
- ✅ **Easy reconfiguration** - just swap USB drives to change roles
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
## 🎛️ System Configuration
### USB-Based Configuration (Recommended)
The system automatically detects configuration from USB drives:
**Leader Configuration (kitchensync.ini):**
```ini
[KITCHENSYNC]
is_leader = true
device_id = leader-pi
video_file = presentation.mp4
debug = false
enable_vlc_logging = false
enable_system_logging = false
vlc_log_level = 0
```
**Collaborator Configuration (kitchensync.ini):**
```ini
[KITCHENSYNC]
is_leader = false
device_id = pi-001
video_file = presentation.mp4
debug = false
enable_vlc_logging = false
enable_system_logging = false
vlc_log_level = 0
pause_threshold = 2.0
sync_grace_time = 3.0
```
### MIDI Schedule (schedule.json)
Define precisely timed MIDI events for Arduino relay control:
```json
[
    {
        "time": 2.0,
        "type": "note_on",
        "channel": 1,
        "note": 63,
        "velocity": 127,
        "description": "Output 1 ON - House lights (Note 60)"
    },
    {
        "time": 10.0,
        "type": "note_off",
        "channel": 1,
        "note": 63,
        "velocity": 0,
        "description": "Output 1 OFF - House lights (Note 60)"
    },
    {
        "time": 12.0,
        "type": "note_on",
        "channel": 1,
        "note": 61,
        "velocity": 127,
        "description": "Output 2 ON - Stage lights (Note 61)"
    }
]
```
**Schedule Format Details:**
- **time**: Seconds from video start (float)
- **type**: `note_on` or `note_off` for relay control
- **channel**: MIDI channel (1-16, typically 1 for Arduino)
- **note**: MIDI note number (0-127, maps to Arduino outputs)
- **velocity**: 127 for full power, 0 for off, intermediate values for dimming
- **description**: Human-readable description of the event
## 🎬 Automatic Video Management
### USB Drive Auto-Detection
The system provides professional USB drive handling:
**✅ Automatic Process:**
1. **Detects** connected USB drives on startup
2. **Mounts** drives to accessible directories  
3. **Scans** for video files with intelligent priority
4. **Selects** optimal video file automatically
**📁 USB Drive Structure:**
```
USB Drive Root/
├── kitchensync.ini    # Configuration file
├── video.mp4          # Video file (any supported format)
└── schedule.json      # Optional MIDI schedule
```
**⚡ Supported Formats:**
- MP4, AVI, MKV, MOV, M4V, WMV, FLV, WebM
- H.264 encoding recommended for best compatibility
### Intelligent File Selection
**Priority Order:**
1. USB drive video files (highest priority)
2. Local `./videos/` directory
3. Configured `video_sources` paths
4. Current directory fallback
**Smart Handling:**
- **Single file**: Automatic selection
- **Multiple files**: First file selected with warning
- **No files**: Clear error message with guidance
### Different Videos Per Pi
Each Pi can play unique content:
1. **USB Method**: Different USB drive per Pi (recommended)
2. **Config Method**: Different `video_file` settings
3. **Mixed Mode**: Some Pis use USB, others use local files
## 🎮 Interactive Controls
### Leader Pi Commands
When running `leader.py` interactively:
- `start` - Start synchronized playback across all Pis
- `stop` - Stop playback on all Pis  
- `status` - Show system status and connected Pis
- `schedule` - Edit the MIDI cue schedule
- `quit` - Exit the program
### Schedule Editor
Built-in schedule editor for real-time MIDI programming:
- `add` - Add new MIDI cues (note on/off, control changes)
- `remove <number>` - Remove specific cues
- `clear` - Clear all cues  
- `save` - Save schedule and return to main menu
### Auto-Start Mode
For production deployment:
```bash
# Leader Pi auto-start (no interface)
python3 leader.py --auto
# Or use systemd service
sudo systemctl start kitchensync.service
```
## 🔄 Advanced Synchronization
### VLC-Based Drift Correction
KitchenSync uses advanced algorithms for maintaining perfect sync:
**Median Deviation Filtering:**
- Collects multiple sync measurements over time
- Uses statistical median to filter network glitches
- Only corrects when median deviation exceeds threshold
- Prevents false corrections from temporary issues
**Intelligent Correction Strategy:**
- **Small deviations**: Seamless seeking without interruption
- **Large deviations**: Temporary pause during correction
- **Grace period**: Prevents immediate re-checking
- **Configurable thresholds**: Tune for your network conditions
**Technical Benefits:**
- **Cross-Platform**: Works on Pi and desktop systems
- **Precise Control**: Python VLC bindings for exact positioning
- **Format Support**: Handles all modern video formats
- **Robust Playback**: Mature VLC media engine
## 🎹 MIDI Output & Networking
### MIDI Message Types
```json
[
  { "time": 5.0, "note": 60, "velocity": 127, "channel": 1, "type": "note_on" },
  { "time": 5.5, "note": 60, "velocity": 0, "channel": 1, "type": "note_off" },
  { "time": 10.0, "control": 7, "value": 127, "channel": 1, "type": "control_change" }
]
```
**Supported Events:**
- **note_on**: Trigger note with specified velocity
- **note_off**: Release note
- **control_change**: Send CC messages
### Network Configuration
- **Sync Port**: 5005 (UDP broadcast for time sync)
- **Control Port**: 5006 (UDP for commands and registration)  
- **Discovery**: Automatic Pi detection via broadcast
- **Precision**: ~10-30ms accuracy on typical LAN
## 🔧 Advanced Features
### Debug Mode
**Visual Debugging:**
- **Pi ID Display**: Shows unique identifier prominently on each screen
- **Video Information**: Displays currently playing video filename
- **Time Counter**: Shows current/total time in MM:SS/MM:SS format
- **MIDI Event Tracking**: Real-time display of MIDI events with color coding
  - **Recent events**: Last 5 MIDI events (grayed out)
  - **Current event**: Active MIDI event (yellow highlight)
  - **Upcoming events**: Next 5 scheduled events (light blue)
- **Sync Status**: Current sync time and video position information
**Configuration:**
```ini
# In USB drive configuration (kitchensync.ini)
[KITCHENSYNC]
is_leader = true
debug = true  # Enables debug mode for entire system
```
**Features:**
- Leader Pi enables debug mode for all connected collaborators
- Automatic pygame-based overlay when available
- Fallback to console output when GUI not available
- Monospace font for consistent display formatting
- 10 FPS update rate to minimize performance impact
### Multiple Pi Configurations
**Scaling Up:**
- Add Pis dynamically to existing setup
- Each Pi auto-discovers leader and registers
- Heartbeat monitoring tracks Pi status
- Graceful handling of Pi disconnections
**Content Management:**
- Different videos per Pi supported
- USB-based content deployment
- Centralized schedule management via leader Pi
- Real-time configuration updates
### Synchronization Technology
**Drift Correction:**
- Median filtering eliminates false corrections
- Intelligent pause-during-correction for large deviations
- Configurable thresholds for different environments
- Grace periods prevent correction oscillation
**Technical Specifications:**
- Time sync accuracy: 10-30ms typical
- Video sync tolerance: configurable (0.5s default)
- MIDI timing precision: sub-50ms
- Network protocol: UDP broadcast
- Video engine: VLC with Python bindings
## 🧪 Testing & Validation
### System Status Check
```bash
# Check VLC installation
vlc --version
# Check MIDI interfaces
aconnect -l
# Test USB drive detection
python3 kitchensync.py --test-usb
# Monitor systemd service
sudo systemctl status kitchensync.service
```
### Video Playback Testing
```bash
# Test standalone video playback
python3 test_video_simple.py
# Test leader with auto-start
DISPLAY=:0 python3 leader.py --auto
```
## 🛠️ Troubleshooting
### Common Issues
**System Won't Start:**
```bash
# Check systemd service status
sudo systemctl status kitchensync.service
sudo journalctl -u kitchensync.service -f
# Run manually for debugging
cd /home/kitchensync/kitchenSync
python3 kitchensync.py
```
**Video Not Displaying:**
```bash
# Check display environment
echo $DISPLAY
# Test with manual display setting
DISPLAY=:0 python3 leader.py --auto
# Verify VLC can access display
DISPLAY=:0 vlc --version
```
**USB Drive Not Detected:**
```bash
# Check USB connections
lsusb
lsblk
# Check mount points  
df -h | grep media
# Manual mount if needed
sudo mkdir -p /media/usb-manual
sudo mount /dev/sdb1 /media/usb-manual
```
**MIDI Not Working:**
```bash
# Check MIDI interfaces
aconnect -l
amidi -l
# Test MIDI connectivity
amidi -p hw:1,0 --send-hex="90 60 7F"
```
**Network Sync Issues:**
- Ensure all Pis on same network segment
- Check firewall settings for UDP ports 5005/5006
- Use wired connection for best reliability
- Verify NTP settings consistent across Pis
### Arduino MIDI Not Working
**Hardware Detection:**
```bash
# Check if Arduino is detected
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || echo "No Arduino detected"
# Check USB connections
lsusb | grep -i arduino
# Test serial communication
python3 -c "from src.midi.manager import SerialMidiOut; s = SerialMidiOut(); print(f'Arduino port: {s.port}')"
```
**Serial Communication:**
- Ensure Arduino is connected via USB
- Check Arduino sketch is uploaded and running
- Verify baud rate matches (default: 9600)
- Test with Arduino Serial Monitor
**Fallback Testing:**
```bash
# Test MIDI system without hardware
python3 -c "from src.midi.manager import MidiManager; m = MidiManager(use_mock=True); print('Mock MIDI system OK')"
```
**Common Issues:**
- Arduino not detected: Check USB cable and drivers
- Permission denied: Add user to `dialout` group: `sudo usermod -a -G dialout $USER`
- Wrong port: Check `/dev/ttyACM*` vs `/dev/ttyUSB*` naming
- Baud rate mismatch: Ensure Arduino sketch uses 9600 baud
### Video Not Playing
- Check VLC installation: `vlc --version`
- Install VLC if missing: `sudo apt install vlc libvlc-dev python3-vlc`
- Verify video file exists in configured locations
- Check video file format (MP4 recommended)
- Ensure `python-vlc` is installed: `pip install python-vlc`
### USB Drive Issues
**USB Drive Not Detected:**
```bash
# Check if USB drive is connected
lsusb
lsblk
# Check mount points
df -h | grep media
# Manual mount (if needed)
sudo mkdir -p /media/usb-manual
sudo mount /dev/sdb1 /media/usb-manual
```
**Permission Issues:**
```bash
# Add user to required groups
sudo usermod -a -G plugdev,disk $USER
# Restart session or reboot for group changes to take effect
```
**Multiple Video Files:**
- Place only ONE video file at the root of each USB drive
- Use subdirectories for storage, but not for playback files
- System will warn and use first file if multiple found
**Video Format Issues:**
- Supported: MP4, AVI, MKV, MOV, M4V, WMV, FLV, WebM
- Recommended: MP4 with H.264 codec for best compatibility
- Convert files if needed: `ffmpeg -i input.avi -c:v libx264 output.mp4`
### Performance Issues
- Use wired network connection for best sync performance
- Ensure all Pis are on the same network segment
- Check CPU usage during playback
- Consider video file resolution and bitrate
### Audio Output Configuration
**To switch audio output from a script on your system:**
```bash
# Switch to headphone jack (3.5mm)
pactl set-default-sink alsa_output.platform-fe00b840.mailbox.stereo-fallback
# Switch to HDMI
pactl set-default-sink alsa_output.platform-fef00700.hdmi.hdmi-stereo
```
**In Python:**
```python
import subprocess
def set_audio_output(output_type):
    sinks = {
        'headphone': 'alsa_output.platform-fe00b840.mailbox.stereo-fallback',
        'hdmi': 'alsa_output.platform-fef00700.hdmi.hdmi-stereo'
    }
    
    try:
        subprocess.run(['pactl', 'set-default-sink', sinks[output_type]], check=True)
        print(f"Audio output switched to {output_type}")
    except subprocess.CalledProcessError:
        print(f"Failed to switch to {output_type}")
# Usage
set_audio_output('hdmi')      # Switch to HDMI
set_audio_output('headphone') # Switch to headphone jack
```
**Note:** These sink names are specific to Raspberry Pi hardware. To find the correct sink names for your system, run:
```bash
pactl list short sinks
```
## 📋 Production Deployment
### Complete Setup Checklist
1. **✅ Install Dependencies**: VLC, Python packages, systemd service
2. **✅ Prepare USB Drives**: Config files and video content
3. **✅ Network Setup**: Ensure all Pis on same network
4. **✅ MIDI Hardware**: Connect and test USB MIDI interfaces
5. **✅ Auto-Start**: Enable systemd service on all Pis
6. **✅ Testing**: Verify sync, video playback, and MIDI output
### Deployment Commands
```bash
# Enable auto-start on all Pis
sudo systemctl enable kitchensync.service
# Start system immediately
sudo systemctl start kitchensync.service
# Monitor system status
sudo systemctl status kitchensync.service
```
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
- **Arduino MIDI:** Each Pi uses Arduino serial communication for MIDI control
- **Video Sync:** Advanced drift correction with median filtering keeps videos synchronized during playback
- **Sync Tolerance:** Videos are corrected if median deviation exceeds threshold (configurable)
- **Outlier Filtering:** Median deviation filtering prevents false corrections from temporary glitches
- **Smart Corrections:** Large deviations trigger pause-during-correction to avoid playback artifacts
