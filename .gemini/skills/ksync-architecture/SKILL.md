---
name: ksync-architecture
description: >
  Just-in-time architecture context loader for kSync. Provides a structured overview
  of the entire system — module map, entry points, data flow, config structure, and
  cross-references to documentation. Any agent can invoke this skill to rapidly
  orient on the kSync codebase without reading every file.
---

# kSync Architecture Context

Load this skill when you need rapid orientation on the kSync codebase. This provides
the complete system map, data flows, and cross-references that all domain agents share.

## System Identity

**kSync** is a distributed system for synchronized video playback and multi-protocol
control output across multiple Raspberry Pi nodes. Branding: always **kSync**.

## Entry Points

| File | Role | How Invoked |
|------|------|-------------|
| `kitchensync.py` | Universal Bootstrapper | systemd → `python3 kitchensync.py` |
| `leader.py` | Leader process | `os.execv()` from bootstrapper |
| `collaborator.py` | Collaborator/Bystander | `os.execv()` from bootstrapper |
| `src/remote/controller.py` | Web UI server | `python3 -m remote.controller` or embedded |

## Module Map

```
kitchenSync/
├── kitchensync.py          # Boot: USB detect → role assign → os.execv()
├── leader.py               # Leader: broadcast sync, manage cluster
├── collaborator.py         # Collaborator: receive sync, adjust rate
├── src/
│   ├── config/
│   │   ├── manager.py      # ConfigManager, USBConfigLoader
│   │   │                   # CONFIG_ROLE_SECTIONS, EDITABLE_CONFIG_FIELDS
│   │   └── __init__.py
│   ├── core/
│   │   ├── logger.py       # log_info/warning/error with component tags
│   │   ├── system_state.py # SystemState (is_running, start_time, current_time)
│   │   ├── schedule.py     # Schedule class (JSON + .mid cue loading)
│   │   ├── ntp_check.py    # NTP synchronization status
│   │   └── __init__.py
│   ├── networking/
│   │   ├── communication.py  # SyncBroadcaster, SyncReceiver,
│   │   │                     # CommandManager, CommandListener
│   │   └── __init__.py
│   ├── protocols/
│   │   ├── midi_handler.py   # MidiManager, MidiScheduler, SerialMidiOut
│   │   ├── osc_handler.py    # OscHandler (minimal, planned expansion)
│   │   └── __init__.py
│   ├── video/
│   │   ├── driver.py         # VideoDriver ABC, PlayerState enum
│   │   ├── drivers/
│   │   │   ├── gst_driver.py   # GstDriver (38K, HW accel, rate control)
│   │   │   └── mock_driver.py  # MockVideoDriver (wall-clock based)
│   │   ├── file_manager.py   # VideoFileManager (discovery, metadata, upload)
│   │   └── __init__.py       # get_video_driver() factory
│   ├── ui/
│   │   ├── interface.py      # CommandInterface, StatusDisplay (CLI)
│   │   ├── window_manager.py # hide_mouse_cursor, display management
│   │   └── assets/           # Desktop background, icons
│   └── remote/
│       ├── controller.py     # Web UI HTTP server (969 lines)
│       ├── templates/        # HTML templates
│       └── schedule_editor/  # Visual schedule editor
├── tests/                    # 6 test files, ~34K total
├── tools/                    # Simulator, GStreamer verifier, NTP setup
├── docs/                     # Deployment, testing, MIDI, roadmap docs
├── arduino/                  # Arduino MIDI controller sketch
└── .gemini/                  # Agents and skills (this directory)
```

## Data Flow: Sync Cycle

```
Leader                          Network                    Collaborator
──────                          ───────                    ────────────
get_position() ──┐
                 ├─→ SyncBroadcaster ──UDP:5005──→ SyncReceiver
                 │   {time, leader_id,              │
                 │    source, sent_at,              ├─→ _handle_sync()
                 │    position_read_time}           │   (non-blocking, stores in _sync_lock)
                 │                                  │
                 │                                  ├─→ _sync_processor_loop() [100Hz thread]
                 │                                  │   ├── Adjust for latency
                 │                                  │   ├── Calculate deviation
                 │                                  │   ├── Median filter
                 │                                  │   └── Apply: seek or set_speed()
```

## Data Flow: Command Cycle

```
Web UI ──HTTP──→ controller.py ──UDP:5006──→ Leader/Collaborator
                                             │
Browser polls ←──JSON──────────────────────  │
                                             ├─→ Heartbeat every 2s
                                             ├─→ Config request/update
                                             ├─→ Media management
                                             └─→ Device update (git pull + reboot)
```

## Configuration Priority Chain

```
1. USB root: /media/*/ksync.ini
2. USB subdirs (depth ≤ 1)
3. Local: ./ksync.ini
4. USB video auto-detect → auto-configure collaborator
5. No config → Bystander mode
```

## Key Documentation

| Document | Path | Content |
|----------|------|---------|
| Project guide | `GEMINI.md` | Architecture overview, principles, conventions |
| Deployment | `docs/DEPLOYMENT_CHECKLIST.md` | Pi setup checklist |
| Testing | `docs/TESTING.md` | Three-tier test strategy |
| MIDI control | `docs/MIDI_CONTROL.md` | Complete MIDI relay documentation |
| Roadmap | `docs/ROADMAP.md` | PTP, OSC, OverlayFS, kmssink plans |
| TODO | `TODO.md` | Current backlog items |
| Changelog | `CHANGELOG.md` | Version history |

## Agent Routing Guide

When you need a domain expert, route to:

| Question About | Route To |
|----------------|----------|
| P-controller tuning, deviation, loop sync | `sync-specialist` |
| GStreamer pipeline, HW accel, video sinks | `gstreamer-expert` |
| USB boot, systemd, setup.sh, role detection | `deployment-ops` |
| MIDI cues, Arduino, OSC, schedule format | `protocol-engineer` |
| UDP packets, broadcast, latency, heartbeat | `network-engineer` |
| Web UI, HTTP API, DOM updates, media mgmt | `webui-reviewer` |
| System design, new subsystems, trade-offs | `architect` |
| Feature planning, phased implementation | `planner` |
