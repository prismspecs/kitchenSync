# GEMINI.md - Context & Developer Guide

## 1. Project Overview
**KitchenSync** is a distributed system for synchronized video playback and MIDI output across multiple Raspberry Pi nodes.
- **Goal:** Play video and trigger MIDI events (via Arduino) in perfect sync across a local network.
- **Deployment:** "Plug-and-play" using USB drives for configuration (`kitchensync.ini`) and content (`.mp4`, `schedule.json`).
- **Roles:**
    - **Leader:** Plays video, broadcasts time sync (UDP 5005), manages the schedule, and coordinates collaborators.
    - **Collaborator:** Receives time sync, adjusts video playback (drift correction), and handles local MIDI output if configured.

## 2. Architecture & Core Components

### Entry Points
- **`kitchensync.py`**: The main boot-time entry point (systemd service).
    - Detects USB configuration.
    - Determines role (Leader vs. Collaborator).
    - Launches the appropriate script (`leader.py` or `collaborator.py`).
- **`leader.py`**:
    - Uses `src.video.vlc_player` for playback.
    - Broadcasts master clock time.
    - Hosts a debug/status interface (HTML/CLI).
- **`collaborator.py`**:
    - Listens for sync packets.
    - Adjusts playback speed/position to match leader.
    - manages `src.midi.manager` for local hardware control.

### Module Structure (`src/`)
- **`src/config/`**: USB detection, parsing `kitchensync.ini`, config validation.
- **`src/core/`**: Shared logic (logging, system state, scheduling data structures).
- **`src/midi/`**: Arduino serial communication (`MidiManager`), event scheduling.
- **`src/networking/`**: UDP broadcast/listen logic.
- **`src/video/`**: VLC bindings wrapper, file management.
- **`src/ui/`**: CLI/Terminal interface helpers.
- **`src/debug/`**: HTML overlay generation for status display.

### External Hardware
- **Arduino**: Connected via USB. Controlled via Serial (115200 baud).
    - Protocol: `noteon <ch> <note> <vel>`, `noteoff <ch> <note> 0`.
    - Code: `arduino/midi_controller/`.

## 3. Conventions & Standards
- **Language**: Python 3 (System-wide).
- **Dependencies**: Uses system packages where possible (e.g., `python3-vlc`).
- **Style**: PEP 8ish. Explicit error handling is critical (network failures, USB disconnects).
- **Logging**: Extensive logging to stdout/files for debugging headless Pis.
- **State Management**: Leader is the source of truth for *time*. Collaborators are the source of truth for their *local configuration*.

## 4. Current Status (from Plan.md)
- **Operational**:
    - VLC-based video playback.
    - UDP Time Sync.
    - USB Role Auto-detection.
    - Arduino MIDI Serial control.
    - Systemd auto-start (`kitchensync.service`).
- **In Progress / Maintenance**:
    - Web interface for easier scheduling.
    - Precision improvements for sync (aiming for sub-frame accuracy).

## 5. Roadmap & Tasks
1.  **Web Interface**: Expand the schedule editor to be fully web-based (served by Leader).
2.  **Mobile App**: Future goal for management.
3.  **Refactoring**: Ensure `src/` modules are strictly decoupled where possible.
4.  **Testing**: Add more unit tests for `src/networking` and `src/midi`.

## 6. Key Commands
- **Run (Auto)**: `python3 kitchensync.py`
- **Run (Leader)**: `python3 leader.py`
- **Run (Collaborator)**: `python3 collaborator.py`
- **Test MIDI**: `python3 -c "from src.midi.manager import MidiManager; m = MidiManager(use_serial=True); print('MIDI OK')"`
