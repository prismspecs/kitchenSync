# GEMINI.md - Context & Developer Guide

## 1. Project Overview
**KitchenSync** is a distributed system for synchronized video playback and MIDI output across multiple Raspberry Pi nodes.
- **Goal:** Play video and trigger MIDI events (via Arduino) in perfect sync across a local network.
- **Deployment:** "Plug-and-play" using USB drives for configuration (`kitchensync.ini`) and content (`.mp4`, `schedule.json`).
- **Roles:**
    - **Leader:** Plays video, broadcasts time sync (UDP 5005), manages the schedule, and coordinates collaborators.
    - **Collaborator:** Receives time sync, adjusts video playback (drift correction), and manages local MIDI output.

## 2. Architecture & Core Components

### Entry Points
- **`kitchensync.py`**: The main boot-time entry point (systemd service). Detects role and launches appropriate script.
- **`leader.py`**: Uses `src.video` for playback, broadcasts master clock, hosts debug UI.
- **`collaborator.py`**: Listens for sync, adjusts playback to match leader, drives MIDI.

### Module Structure (`src/`)
- **`src/config/`**: USB detection, ini parsing.
- **`src/core/`**: Shared logic (logging, system state, scheduling).
- **`src/midi/`**: Arduino serial communication.
- **`src/networking/`**: UDP broadcast/listen logic.
- **`src/video/`**: Abstracted video player. Currently VLC-based (deprecated), moving to GStreamer.
- **`src/ui/`**: CLI/Terminal interface.
- **`src/debug/`**: HTML overlay for status.

### Hardware
- **Raspberry Pi 4/5**: Main compute nodes.
- **Arduino**: USB Serial MIDI controller (`115200` baud).

## 3. Conventions
- **Language**: Python 3.
- **Style**: PEP 8ish. Robust error handling for network/hardware disconnects.
- **Logging**: Extensive logging to files (`/var/log/kitchensync/` or user home) for headless debugging.
- **Sync Model**: Leader is the master clock. Collaborators drift-correct.

## 4. Current Status
- **Operational:**
    - Basic playback and sync using VLC.
    - USB auto-mounting and role detection.
    - MIDI output via Arduino.
- **Critical Issues:**
    - **Sync Stability:** VLC player struggles with precise seeking and buffering, causing collaborators to "black screen" or lose sync during corrections.
    - **Latency:** "Stop-and-wait" correction method is too disruptive.

## 5. Roadmap
1.  **Video Player Rewrite (High Priority):** Replace `src/video/vlc_player.py` with a low-level, GStreamer-based implementation.
    -   *Goal:* Seamless rate-based sync (speed up/slow down) instead of seek-based sync.
    -   *Tech:* GStreamer (Python GObject bindings) with hardware acceleration (`v4l2h264dec`).
2.  **Web Interface:** Expand schedule editor (Leader-hosted).
3.  **Refactoring:** Decouple `src` modules further.
4.  **Testing:** Networking and MIDI unit tests.