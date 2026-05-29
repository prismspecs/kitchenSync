# kSync.md - Context & Developer Guide

## 1. Project Overview
**kSync** is a distributed system for synchronized video playback and multi-protocol control output across multiple Raspberry Pi nodes.
- **Goal:** Play video and trigger synchronized events (MIDI, OSC, and other common protocols) in perfect sync across a local network.
- **Deployment:** "Plug-and-play" using USB drives for configuration (`ksync.ini`) and content (`.mp4`, `schedule.json`).
- **Universal Node:** Every node starts as a "Universal Node". It detects its role (Leader, Collaborator, or Bystander) from the configuration and boots into the appropriate state.

## 2. Core Development Principles
- **Universal Architecture:** A single codebase powers all roles. Nodes pivot between roles using `os.execv` to ensure a clean state transition.
- **Robust Discovery:** Video discovery is hardened using absolute path resolution across USB, local `videos/` folders, and the project root.
- **Surgical UI:** The Web UI utilizes a custom DOM reconciliation strategy to allow real-time status updates without disrupting user input or focus.
- **Stable Identity:** Device IDs are derived from hardware serial numbers to ensure consistent identification across restarts without manual configuration.

## 3. Architecture & Core Components

### Entry Points
- **`kitchensync.py`**: The Universal Bootstrapper. Handles USB config detection, software upgrades, and role-switching.
- **`leader.py`**: The master node. Coordinates playback, broadcasts time sync, and manages collaborators.
- **`collaborator.py`**: The playback node. Handles both `collaborator` (syncing) and `bystander` (idle) modes.

### Module Structure (`src/`)
- **`src/config/`**: Unified configuration management and USB detection.
- **`src/core/`**: Shared logic (logging, system state, scheduling).
- **`src/protocols/`**: Abstraction layer for MIDI and OSC output.
- **`src/networking/`**: High-precision UDP sync and command management.
- **`src/video/`**: GStreamer-based video driver with rate-based synchronization.
- **`src/ui/`**: CLI/Terminal interface and window management.

## 4. Conventions
- **Language**: Python 3.
- **Sync Model**: Leader broadcasts a master clock. Collaborators use a P-controller to adjust playback speed via GStreamer for seamless correction.
- **Media Management**: Centralized via Web UI. Leader acts as the hub; Collaborators pull media via HTTP.
- **Branding**: Consistently referred to as **kSync**.

## 5. Current Status
- **Operational:** High-performance GStreamer sync; surgical Web UI for cluster management; stable hardware-based IDs.
- **Recently Implemented:**
    - [x] Unified "Universal Node" boot sequence.
    - [x] Surgical DOM reconciliation (Boss UI).
    - [x] Hardened video discovery (Case-insensitive & Multi-path).
    - [x] Automated systemd service generation.
    - [x] "Bystander" idle state for provisioning.
