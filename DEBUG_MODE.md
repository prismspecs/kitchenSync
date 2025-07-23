# KitchenSync Debug Mode Implementation

## Overview

The KitchenSync debug mode provides visual and console-based debugging information to help troubleshoot and monitor synchronized video playback and MIDI output across multiple Raspberry Pis.

## Features

### Visual Overlay (with pygame)
- **Pi ID**: Large, prominent display of the Pi's unique identifier
- **Video File**: Shows the currently playing video filename
- **Time Counter**: Displays current time / total time in MM:SS format
- **Additional Info**: Shows sync status, video position, and MIDI cue counts
- **Transparent Background**: Semi-transparent black overlay that doesn't obstruct video
- **Monospace Font**: Consistent character spacing for clean display

### Console Output (fallback)
- **Periodic Updates**: Debug info printed every 5 seconds to avoid spam
- **Structured Format**: Clear formatting with emoji indicators
- **MIDI Event Tracking**: Real-time display of current and upcoming MIDI events

### Leader Pi MIDI Tracking
- **Event History**: Tracks last 5 triggered MIDI events (grayed out in concept)
- **Current Events**: Highlights MIDI events happening now (yellow highlight)
- **Upcoming Events**: Shows next 5 scheduled events (light blue in concept)
- **Console Display**: Formatted MIDI event information with timing

## Configuration

### USB Drive Setup (Leader)
```ini
[KITCHENSYNC]
is_leader = true
pi_id = leader-pi
debug = true  # Enables debug for entire system
```

### USB Drive Setup (Collaborator)
```ini
[KITCHENSYNC]
is_leader = false
pi_id = pi-002
debug = true  # Can be overridden by leader
video_file = video2.mp4
```

### Local Configuration Files
```ini
[DEFAULT]
pi_id = pi-001
debug = false  # Local setting, overridden by leader
```

## Implementation Details

### Files Modified

1. **leader.py**
   - Added `load_leader_config()` method
   - Added `update_midi_history()` for MIDI event tracking
   - Modified `start_system()` to pass debug mode to collaborators
   - Added MIDI history state variables

2. **collaborator.py**
   - Added `DebugOverlay` class with pygame and text fallback modes
   - Modified `handle_start_command()` to accept debug mode from leader
   - Added `debug_update_loop()` for periodic overlay updates
   - Integrated debug overlay with video playback lifecycle

3. **kitchensync.py**
   - Modified `update_local_config()` to pass debug setting to collaborators

4. **Configuration Files**
   - Added debug options to all collaborator config files
   - Created example USB configuration files with debug enabled

### Debug Overlay Technical Details

- **Update Rate**: 10 FPS (0.1 second intervals) to minimize performance impact
- **Positioning**: Top-right corner overlay (400x200 pixels)
- **Colors**: 
  - White for Pi ID
  - Light blue for video filename
  - Yellow for time display
  - Light gray for additional info
- **Font Sizes**: 
  - Large (36px) for Pi ID
  - Medium (24px) for video name and time
  - Small (18px) for details

### MIDI Event Tracking

- **History Buffer**: Maintains last 5 triggered events
- **Current Detection**: Events within 0.5 seconds of current time
- **Lookahead**: Shows next 5 events within 10 seconds
- **Update Frequency**: Every 3 seconds to avoid console spam

## Dependencies

### Required for Basic Debug (Text Mode)
- No additional dependencies beyond standard KitchenSync requirements

### Optional for Visual Debug (Overlay Mode)
- **pygame>=2.0.0**: For graphical overlay display
- Automatically falls back to text mode if pygame not available

## Usage

### Enable Debug Mode
1. Set `debug = true` in the leader's USB configuration
2. All connected collaborators will automatically enter debug mode
3. Debug overlays appear on each Pi's video output
4. Leader console shows MIDI event tracking

### Disable Debug Mode
1. Set `debug = false` in configuration files
2. Restart the system
3. All debug displays are disabled for clean presentation

## Performance Considerations

- **Minimal Impact**: Debug overlay updates at 10 FPS only
- **Conditional Execution**: Debug code only runs when debug mode is enabled
- **Graceful Fallback**: Automatically switches to text mode if graphics unavailable
- **Memory Efficient**: Small overlay surface (400x200 pixels)
- **Thread Safety**: Debug updates run in separate thread

## Testing

Use the included test script to verify debug overlay functionality:

```bash
python3 test_debug_overlay.py
```

This script tests both pygame visual mode and text fallback mode without requiring full video playback.

## Troubleshooting

### Pygame Not Available
- Install pygame: `sudo pip install pygame --break-system-packages`
- Or system package: `sudo apt install python3-pygame`
- System automatically falls back to text mode if installation fails

### Debug Overlay Not Visible
- Check that `debug = true` in leader configuration
- Verify collaborators receive debug mode in start command
- Check console output for pygame initialization messages
- Ensure DISPLAY environment variable is set for GUI applications

### Performance Issues
- Debug mode adds minimal overhead (~1% CPU typically)
- Reduce update frequency by modifying sleep interval in `debug_update_loop()`
- Disable debug mode for production use

## Future Enhancements

- **Color-coded MIDI Events**: Visual indication of different MIDI message types
- **Network Status**: Display connection quality and latency information
- **Interactive Controls**: Keyboard shortcuts for debug mode toggling
- **Log Export**: Save debug information to files for analysis
- **Remote Debug**: Web-based debug interface for monitoring multiple Pis
