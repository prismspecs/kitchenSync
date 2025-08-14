# Collaborator Sync Logging Changes

## Changes Made

### 1. Conditional Sync Logging
All sync-related log messages are now conditional on `debug_mode`:

**Startup sync messages:**
- "Waiting for time sync..."
- "Starting without sync (timeout)" 
- "Sync established"

**Real-time sync monitoring:**
- Video position check warnings
- Sync correction notifications  
- Pause/seek operation details
- Wait-for-sync state messages

### 2. Enhanced Debug Information
When debug mode is enabled, sync logs now include:

**Deviation details:**
- Raw deviation value alongside median deviation
- Current video position vs expected position
- Real-time sync monitoring (every 5th sample)
- Sample count for median filtering

**Example debug output:**
```
Sync monitor: video=45.230s, expected=45.180s, deviation=0.050s, samples=15
Sync correction needed: deviation=-0.250s (raw=-0.245s, threshold=0.200s)
```

### 3. Production Mode Behavior
When `debug_mode=false` (production):
- ✅ Sync corrections still happen normally  
- ✅ Essential error messages still appear
- ❌ Verbose sync monitoring is suppressed
- ❌ Real-time deviation info is hidden

Only the visual "🔄 Sync correction" print statement remains for user feedback.

### 4. Files Modified
- `collaborator.py` - Updated sync logging throughout `_handle_sync()` and `_check_video_sync()` methods

## Usage

**Enable verbose sync logging:**
```ini
[KITCHENSYNC]
debug = true
```

**Production mode (quiet sync):**
```ini  
[KITCHENSYNC]
debug = false
```

## Result
- **Production**: Clean, minimal output with essential corrections only
- **Debug**: Detailed sync analysis with deviation tracking and timing information
- **Maintains**: All sync functionality regardless of debug setting
