# GEMINI.md - Context & Developer Guide

## 1. Project Overview
**KitchenSync** is a distributed system for synchronized video playback and multi-protocol control output across multiple Raspberry Pi nodes.
- **Goal:** Play video and trigger synchronized events (MIDI, OSC, and other common protocols) in perfect sync across a local network.
- **Deployment:** "Plug-and-play" using USB drives for configuration (`kitchensync.ini`) and content (`.mp4`, `schedule.json`).
- **Roles:**
    - **Leader:** Plays video, broadcasts time sync (UDP 5005), manages the schedule, and coordinates collaborators.
    - **Collaborator:** Receives time sync, adjusts video playback (drift correction), and manages local protocol output (MIDI, OSC, etc.).

## 2. Core Development Principles
- **High Organization:** All code must be highly organized and modular. Before adding code, evaluate if it belongs in an existing module or deserves a new file.
- **No Hacks:** Writing "hacks" or "quick fixes" is a last resort. Prioritize robust, idiomatic solutions that address the root cause.
- **Research First:** Always look up existing documentation, best practices, and community solutions online before implementing. Leverage the global knowledge base to ensure technical integrity.
- **Efficiency:** The system must be incredibly efficient, especially regarding network latency, CPU usage on the Pi, and disk I/O.
- **Abstraction:** Design for extensibility. Protocol handlers (MIDI, OSC) should be abstracted so that new protocols can be added with minimal changes to the core sync logic.

## 3. Architecture & Core Components

### Entry Points
- **`kitchensync.py`**: The main boot-time entry point (systemd service). Detects role and launches appropriate script.
- **`leader.py`**: Uses `src.video` for playback, broadcasts master clock, hosts debug UI.
- **`collaborator.py`**: Listens for sync, adjusts playback to match leader, drives control protocols.

### Module Structure (`src/`)
- **`src/config/`**: USB detection, ini parsing.
- **`src/core/`**: Shared logic (logging, system state, scheduling).
- **`src/protocols/`**: (Future) Abstraction layer for MIDI, OSC, etc. Currently `src/midi/`.
- **`src/networking/`**: UDP broadcast/listen logic.
- **`src/video/`**: Abstracted video player. Moving to GStreamer for seamless rate-based sync.
- **`src/ui/`**: CLI/Terminal interface.
- **`src/debug/`**: HTML overlay for status.

## 4. Conventions
- **Language**: Python 3.
- **Style**: PEP 8ish. Robust error handling for network/hardware disconnects.
- **Logging**: Extensive logging for headless debugging; however, minimize logging in performance-critical loops.
- **Sync Model**: Leader is the master clock. Collaborators drift-correct using speed adjustments (GStreamer) rather than disruptive seeks.

## 5. Current Status
- **Operational:** Basic playback and sync using VLC; USB auto-mounting; MIDI output.
- **Critical Issues:** VLC sync is "stop-and-wait" and causes black screens.
- **Roadmap:**
    1. **GStreamer Migration:** Replace VLC for rate-based sync.
    2. **Protocol Abstraction:** Refactor MIDI logic into a generic protocol handler (adding OSC support).
    3. **OS Optimization:** Move to a minimal OS profile (Openbox + X11 on Lite) for better reliability.