# KitchenSync Project

## Overview
KitchenSync enables synchronized video playback and MIDI output across multiple Raspberry Pis on a local network. One Pi acts as the leader, broadcasting synchronized time via UDP and serving as a user interface for control and configuration. Collaborator Pis use this signal to start video playback with VLC and output MIDI data at pre-defined timecodes via USB MIDI interfaces. Each Pi has a unique ID and can play different videos (or the same video as needed). Videos can be stored locally on each device or played from USB drives. The system uses lightweight UDP time sync and Python threading for concurrency. MIDI data is timecoded to the video timeline, ensuring perfect synchronization between audio-visual elements.

## Stack
- **Language:** Python 3
- **Media Player:** VLC (with Python bindings for precise control)
- **MIDI Library:** python-rtmidi
- **Networking:** UDP broadcast (Python `socket` module)
- **Hardware:** Raspberry Pi + USB MIDI interface
- **Sync Method:** Leader Pi broadcasts time; collaborator Pis offset their clocks with advanced median filtering
- **Device Management:** Each Pi has unique ID; can play different or identical videos
- **Video Sources:** Local storage or USB drives
- **User Interface:** Leader Pi provides control interface for configuration and file management
- **Schedule Format:** JSON with MIDI event definitions (note_on, note_off, control_change, etc.)
- **Concurrency:** `threading.Thread` for non-blocking network listening
- **MIDI Output:** Timecoded MIDI events synchronized to video playback
- **Video Control:** VLC Python API for precise seeking, position tracking, and playback control