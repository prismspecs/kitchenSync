# KitchenSync Schedule Format Examples

This directory contains example schedules in both supported formats.

## JSON Format Examples

### Basic Relay Control (`basic_relay_example.json`)
Simple on/off relay control for lighting or effects.

### Advanced Multi-Zone (`multi_zone_example.json`)  
Complex schedule controlling multiple zones with timing coordination.

### Theater Show (`theater_example.json`)
Real-world example for a theater production with lighting and effects cues.

## MIDI File Examples

### DAW Created (`daw_example.mid`)
Example MIDI file created in a Digital Audio Workstation.

### Converted Schedule (`converted_example.mid`)
JSON schedule exported to MIDI format for DAW editing.

## Testing Examples

Use these files to test KitchenSync functionality:

```bash
# Test JSON loading
python3 tools/midi_tools.py inspect examples/basic_relay_example.json

# Test format conversion  
python3 tools/midi_tools.py convert-to-midi examples/basic_relay_example.json

# Test MIDI loading (requires mido library)
python3 tools/midi_tools.py inspect examples/daw_example.mid
```

## USB Drive Usage

Copy any of these files to your USB drive as:
- `schedule.json` (for JSON format)
- `schedule.mid` (for MIDI format)

KitchenSync will automatically detect and load the appropriate format.
