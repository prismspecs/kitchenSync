# KitchenSync MIDI Relay Control

This document explains how to use KitchenSync's MIDI functionality for relay control.

## Overview

KitchenSync can send precisely-timed MIDI messages synchronized to video playback. This is perfect for controlling external relays that respond to MIDI signals.

## How It Works

1. **Leader Pi** loads a MIDI schedule (JSON file) from USB drive or local storage
2. **Video plays** and the system tracks the current playback time  
3. **MIDI messages** are sent at specified times in the schedule
4. **External hardware** (MIDI-to-relay interface) receives messages and controls relays
5. **Collaborator Pis** receive sync data but don't send MIDI (unless configured)

## MIDI Message Format

For relay control, we use **MIDI Note On/Off** messages with **note-based addressing**:

- **Note On** (0x90 + channel): Turn relay ON
- **Note Off** (0x80 + channel): Turn relay OFF  
- **Note Numbers 60-71**: Map to relay outputs 1-12
  - Note 60 (C4) = Output 1
  - Note 61 (C#4) = Output 2
  - Note 62 (D4) = Output 3
  - Note 63 (D#4) = Output 4
  - Note 64 (E4) = Output 5
  - Note 65 (F4) = Output 6
  - Note 66 (F#4) = Output 7
  - Note 67 (G4) = Output 8
  - Note 68 (G#4) = Output 9
  - Note 69 (A4) = Output 10
  - Note 70 (A#4) = Output 11
  - Note 71 (B4) = Output 12
- **MIDI Channel**: Ignored (any channel 1-16 works)
- **Velocity**: Controls output power (0 = OFF, 1-127 = ON with power level)
- **Auto-timeout**: Notes automatically turn OFF after 5 seconds if no new messages

## Schedule File Format

KitchenSync supports **two input formats** for MIDI schedules:

### 1. JSON Format (Recommended for Relay Control)

JSON format provides the most control and is easiest to create/edit:

```json
[
  {
    "time": 5.0,
    "type": "note_on", 
    "channel": 1,
    "note": 60,
    "velocity": 127,
    "description": "Output 1 ON"
  },
  {
    "time": 8.0,
    "type": "note_off",
    "channel": 1, 
    "note": 60,
    "velocity": 0,
    "description": "Output 1 OFF"
  },
  {
    "time": 10.0,
    "type": "note_on",
    "channel": 1,
    "note": 61,
    "velocity": 100,
    "description": "Output 2 ON (Medium power)"
  }
]
```

#### JSON Properties

- **time**: Time in video (seconds) when event should trigger
- **type**: "note_on" or "note_off"
- **channel**: MIDI channel (1-16, ignored by hardware but useful for organization)
- **note**: MIDI note number (60-71 for outputs 1-12)
- **velocity**: Power level (0 = OFF, 1-127 = ON with power control)
- **description**: Optional human-readable description

### 2. Standard MIDI Files (.mid/.midi)

You can also use standard MIDI files created in any DAW or MIDI sequencer:

- **Automatic conversion**: MIDI events are automatically converted to schedule format
- **Multi-track support**: All tracks are processed and combined
- **Timing preservation**: Original MIDI timing is maintained
- **Channel mapping**: MIDI channels 1-16 map directly to relay channels

#### MIDI File Requirements

- **Note On/Off events**: Converted to relay ON/OFF commands
- **Control Change events**: Supported for advanced control
- **Timing**: Based on MIDI file tempo and tick resolution
- **Channels**: Standard MIDI channels 1-16

### Format Conversion

Use the built-in conversion tools to switch between formats:

```bash
# Convert MIDI file to JSON (for editing)
python3 tools/midi_tools.py convert-to-json my_schedule.mid

# Convert JSON to MIDI file (for DAW compatibility)  
python3 tools/midi_tools.py convert-to-midi my_schedule.json

# Inspect either format
python3 tools/midi_tools.py inspect my_schedule.json
python3 tools/midi_tools.py inspect my_schedule.mid
```

## USB Drive Setup

### USB Directory Structure

```
📁 USB Drive (Leader Pi)
├── kitchensync.ini          # Main configuration
├── video_file.mp4           # Video to play
├── schedule.json            # MIDI relay schedule
└── desktop-background.png   # Optional background
```

### Supported Schedule Files

The system automatically searches for these files on USB drives:

- `schedule.json` (preferred JSON format)
- `midi_schedule.json` (alternative JSON name)
- `relay_schedule.json` (relay-specific JSON name)
- `schedule.mid` (standard MIDI file)
- `*.mid` or `*.midi` (any MIDI file)

**Priority Order**: JSON files are checked first, then MIDI files.

### MIDI File Requirements

To use MIDI files, install the `mido` library:

```bash
# On Raspberry Pi or Linux systems:
pip3 install mido

# This is already included in requirements.txt
```

Without `mido`, only JSON format is supported (which covers 99% of use cases).

## Creating Schedules

### Method 1: Manual JSON Creation

Create a `schedule.json` file manually:

```json
[
  {
    "time": 10.0,
    "type": "note_on",
    "channel": 1,
    "note": 60, 
    "velocity": 127,
    "description": "Turn on spotlight"
  },
  {
    "time": 15.0,
    "type": "note_off", 
    "channel": 1,
    "note": 60,
    "velocity": 0,
    "description": "Turn off spotlight"
  }
]
```

### Method 2: Programmatic Creation

Use the built-in Schedule class:

```python
from core.schedule import Schedule

# Create new schedule
schedule = Schedule('my_schedule.json')
schedule.clear_schedule()

# Add relay events using helper methods
schedule.add_relay_on(5.0, relay_channel=1)    # Relay 1 ON at 5s
schedule.add_relay_off(10.0, relay_channel=1)  # Relay 1 OFF at 10s
schedule.add_relay_pulse(15.0, relay_channel=2, duration=0.5)  # 0.5s pulse

# Save to file
schedule.save_schedule()
```

### Method 3: Interactive Editor

Use the built-in schedule editor (when running leader interactively):

```bash
python3 leader.py
# Type "schedule" to enter the schedule editor
```

### Method 4: Using a DAW or MIDI Sequencer

Create schedules using familiar music software:

1. **Open your DAW** (Logic Pro, Ableton Live, GarageBand, etc.)
2. **Create MIDI tracks** - one for each relay channel  
3. **Set track channels** to 1-16 (corresponding to relay numbers)
4. **Place MIDI notes** at desired times (note 60 recommended)
5. **Export as MIDI file** (.mid format)
6. **Copy to USB drive** alongside video and config

#### DAW Workflow Tips

- **Use click track** to align with video timing
- **Import video** if your DAW supports it for visual reference
- **Channel organization**: Channel 1 = Relay 1, Channel 2 = Relay 2, etc.
- **Note duration**: Doesn't matter - only Note On/Off timing is used
- **Velocity**: Use 127 for maximum compatibility

#### Popular DAW Examples

**Logic Pro X:**
1. Create Software Instrument track
2. Set MIDI channel in Track Inspector
3. Record or draw MIDI notes in Piano Roll
4. File → Export → Selection as MIDI File

**Ableton Live:**
1. Create MIDI track
2. Set MIDI To: channel number
3. Draw notes in MIDI Editor  
4. File → Export → Export MIDI Clip

**GarageBand:**
1. Create Software Instrument track
2. Record MIDI notes
3. Share → Export Song to Disk → MIDI

## Hardware Requirements

### MIDI Relay Box Specifications

**Your specific MIDI relay box behavior:**

- **8 Outputs**: Controlled by MIDI notes 60-67 (C4 to G4)
- **Note Mapping**: 
  - Note 60 (C4) = Output 1
  - Note 61 (C#4) = Output 2  
  - Note 62 (D4) = Output 3
  - Note 63 (D#4) = Output 4
  - Note 64 (E4) = Output 5
  - Note 65 (F4) = Output 6
  - Note 66 (F#4) = Output 7
  - Note 67 (G4) = Output 8
- **Channel Independence**: MIDI channel is ignored (any channel 1-16 works)
- **Power Control**: Velocity controls output power (0=OFF, 1-127=power level)
- **Auto-Timeout**: Outputs automatically turn OFF after 5 seconds if no new messages
- **Message Types**: Responds to Note On/Off only (not Control Change)
- **Output Type**: Isolated dry contact closures (MOSFET-based, not mechanical relays)

### Connection Setup

```
[Raspberry Pi] → [USB MIDI Interface] → [5-pin DIN MIDI Cable] → [MIDI Relay Box] → [External Devices]
```

## Important Hardware Behavior

### 5-Second Auto-Timeout

**Critical**: Your MIDI box automatically turns OFF any output after 5 seconds if no new MIDI message is received for that note.

**Implications for scheduling:**

1. **Short events** (< 5s): Schedule normally with Note On/Off pairs
2. **Long events** (> 5s): Need to send "keepalive" Note On messages every 4 seconds
3. **Continuous operation**: Send Note On every 4s to maintain output

**Example for long event:**
```json
[
  {"time": 10.0, "type": "note_on", "note": 60, "velocity": 127, "description": "Start long event"},
  {"time": 14.0, "type": "note_on", "note": 60, "velocity": 127, "description": "Keepalive 1"},
  {"time": 18.0, "type": "note_on", "note": 60, "velocity": 127, "description": "Keepalive 2"},
  {"time": 22.0, "type": "note_off", "note": 60, "velocity": 0, "description": "End long event"}
]
```

### Power Control via Velocity

Unlike traditional relays, your box supports **variable power output**:

- **Velocity 127**: Full power output  
- **Velocity 100**: ~78% power output
- **Velocity 64**: ~50% power output
- **Velocity 32**: ~25% power output
- **Velocity 0**: OFF (same as Note Off)

This allows **dimming control** for compatible devices.

### Multiple Output Control

Since MIDI channel is ignored, you can control multiple outputs simultaneously:

```json
[
  {"time": 10.0, "type": "note_on", "note": 60, "velocity": 127, "description": "Output 1 ON"},
  {"time": 10.0, "type": "note_on", "note": 61, "velocity": 100, "description": "Output 2 ON (dimmed)"},
  {"time": 10.0, "type": "note_on", "note": 62, "velocity": 127, "description": "Output 3 ON"}
]
```

## Common Patterns

### Sequential Activation

Turn on relays in sequence:

```json
[
  {"time": 5.0, "type": "note_on", "channel": 1, "note": 60, "velocity": 127},
  {"time": 10.0, "type": "note_on", "channel": 2, "note": 60, "velocity": 127}, 
  {"time": 15.0, "type": "note_on", "channel": 3, "note": 60, "velocity": 127}
]
```

### Timed Pulses

Short duration relay activations:

```json
[
  {"time": 10.0, "type": "note_on", "channel": 1, "note": 60, "velocity": 127},
  {"time": 10.5, "type": "note_off", "channel": 1, "note": 60, "velocity": 0}
]
```

### Multiple Relays Simultaneously

Control multiple relays at once:

```json
[
  {"time": 20.0, "type": "note_on", "channel": 1, "note": 60, "velocity": 127},
  {"time": 20.0, "type": "note_on", "channel": 2, "note": 60, "velocity": 127},
  {"time": 20.0, "type": "note_on", "channel": 3, "note": 60, "velocity": 127}
]
```

## Timing and Synchronization

### Precision

- **MIDI timing precision**: Sub-50ms accuracy
- **Video sync tolerance**: 0.5s default (configurable)
- **Network sync accuracy**: 10-30ms on typical LAN

### Video Looping

If your video loops, MIDI events will repeat automatically:

- Events trigger again when video restarts
- Loop counter available in debug mode
- Can disable looping in MidiScheduler if needed

## Debug Mode

Enable debug mode to see MIDI events in real-time:

```ini
[KITCHENSYNC]
debug = true
```

Debug overlay shows:
- **Recent MIDI events** (last 5, grayed out)
- **Current MIDI event** (yellow highlight)
- **Upcoming events** (next 5, light blue)
- **Video timing** and sync status

## Troubleshooting

### No MIDI Output

1. Check MIDI port configuration in `kitchensync.ini`
2. Verify USB MIDI interface is connected
3. Check `dmesg` for USB device detection
4. Test with `amidi -l` to list MIDI ports

### Schedule Not Loading

1. Verify file is named correctly (`schedule.json`)
2. Check JSON syntax with online validator
3. Ensure file is in USB drive root directory
4. Check startup logs in `/tmp/kitchensync_startup.log`

### Timing Issues

1. Use wired network connection for better sync
2. Reduce `tick_interval` in configuration
3. Check video file performance/encoding
4. Monitor debug overlay for timing drift

### MIDI Hardware Testing

Test MIDI output manually:

```bash
# Send Note On to channel 1
amidi -p hw:1,0 --send-hex="90 3C 7F"

# Send Note Off to channel 1  
amidi -p hw:1,0 --send-hex="80 3C 00"
```

## Example Workflows

### Basic Lighting Control

1. Create `schedule.json` with lighting cues
2. Put on USB drive with video and config
3. Insert USB into Leader Pi
4. Start KitchenSync - lighting follows video automatically

### Complex Multi-Zone Setup

1. Use channels 1-8 for different lighting zones
2. Channel 9-12 for special effects relays
3. Channel 13-16 for audio/projection equipment
4. Create detailed schedule with zone coordination

### Event Synchronization

1. Multiple Leader Pis can run identical schedules
2. Network sync keeps all systems coordinated
3. Central relay control from each Leader Pi
4. Backup systems possible with multiple USB drives

## API Reference

### Schedule Class Methods

```python
# Create events
schedule.add_relay_on(time, relay_channel, note=60, velocity=127)
schedule.add_relay_off(time, relay_channel, note=60) 
schedule.add_relay_pulse(time, relay_channel, duration=0.5)

# Static helpers
Schedule.create_relay_on_cue(time, channel, note, velocity)
Schedule.create_relay_off_cue(time, channel, note)
Schedule.create_relay_pulse_cues(time, channel, duration)

# Management
schedule.save_schedule()
schedule.load_schedule()
schedule.clear_schedule()
schedule.print_schedule()
```

This documentation covers the complete MIDI relay control system. The implementation provides a robust, precise, and easy-to-use system for synchronized relay control in multimedia installations.
