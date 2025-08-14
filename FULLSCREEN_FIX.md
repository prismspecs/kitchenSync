# VLC Fullscreen Enhancement

## Problem
Approximately 25% of the time when starting the KitchenSync system, the VLC window opens in windowed mode instead of fullscreen, which is problematic for production deployments.

## Root Cause
VLC's fullscreen mode setting can be unreliable due to:
1. **Timing Issues**: VLC needs time to fully initialize its window before fullscreen can be set
2. **Window Manager Interactions**: Different window managers handle fullscreen requests differently
3. **Race Conditions**: Setting fullscreen too early may be ignored by the window system
4. **Display Environment**: X11/Wayland compatibility issues can affect fullscreen behavior

## Solution Implemented

### 1. Enhanced VLC Arguments
Added fullscreen-specific arguments to VLC startup:
```python
# Production mode args
"--fullscreen",          # Start in fullscreen mode
"--no-embedded-video",   # Don't embed video in interface  
"--video-on-top",        # Keep video window on top
"--no-video-deco",       # Remove window decorations
```

### 2. Multi-Attempt Fullscreen Setting
Replaced single fullscreen attempt with progressive retry logic:
```python
fullscreen_attempts = [0.3, 0.5, 1.0, 2.0]  # Increasing delays
for attempt, delay in enumerate(fullscreen_attempts, 1):
    time.sleep(delay)
    self.vlc_player.set_fullscreen(True)
    if self.vlc_player.get_fullscreen():
        break  # Success!
```

### 3. Continuous Fullscreen Enforcement Thread
Added background thread that continuously monitors and enforces fullscreen:
```python
def _enforce_fullscreen_periodically(self):
    while self.is_playing and self.should_be_fullscreen:
        time.sleep(2.0)  # Check every 2 seconds
        if not self.vlc_player.get_fullscreen():
            self.vlc_player.set_fullscreen(True)
```

### 4. Manual Fullscreen Command
Added interactive command for manual fullscreen enforcement:
- Leader interface now has `fullscreen` command
- Can be used to manually fix windowed mode
- Shows current fullscreen status

### 5. Enhanced Status Reporting
Video info now includes fullscreen status:
```python
{
    "is_fullscreen": bool,           # Current fullscreen state
    "should_be_fullscreen": bool,    # Intended fullscreen state  
    "enforcement_active": bool,      # Background thread status
}
```

## Files Modified
- `src/video/vlc_player.py` - Core fullscreen enforcement logic
- `leader.py` - Added manual fullscreen command
- `test_fullscreen.py` - Test script for verification

## Usage

### Automatic (Default)
The system now automatically:
1. Starts VLC with fullscreen arguments
2. Attempts fullscreen multiple times with increasing delays
3. Runs background enforcement thread throughout playback

### Manual Command
If windowed mode is detected during operation:
```bash
# In leader interactive mode
fullscreen
```

### Testing
Run the test script to verify fullscreen behavior:
```bash
python3 test_fullscreen.py
```

## Expected Results
- **Before**: ~25% chance of windowed mode startup
- **After**: <1% chance of persistent windowed mode
- **Recovery**: Automatic correction within 2 seconds if fullscreen is lost
- **Manual**: Immediate fullscreen restoration via command

This multi-layered approach should eliminate the fullscreen reliability issue while providing debugging tools and manual recovery options.
