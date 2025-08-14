# Command Line Debug Flag Support

## Problem Fixed
The `--debug` command line flag was being applied after the components were already initialized, which meant:
- Logging configuration didn't see the debug setting
- VLC player initialization used the config file value instead of command line override
- Debug overlay wasn't created when using `--debug` flag

## Solution Implemented

### 1. Modified Constructors
**CollaboratorPi:**
- Added `debug_override: bool = False` parameter
- Applies debug setting before logging and VLC initialization

**LeaderPi:**
- Added `debug_override: bool = False` parameter  
- Applies debug setting before logging, VLC, and HTML overlay creation

### 2. Updated Main Functions
**Both `collaborator.py` and `leader.py`:**
- Pass `debug_override=args.debug` to constructors
- Removed redundant post-initialization debug setting

### 3. Initialization Order
```python
# OLD (broken):
instance = CollaboratorPi()  # Uses config file values
if args.debug:
    instance.config.debug = True  # Too late!

# NEW (working):
instance = CollaboratorPi(debug_override=args.debug)  # Applied immediately
```

## Usage

**Collaborator:**
```bash
python3 collaborator.py --debug                    # Enable debug mode
python3 collaborator.py config.ini --debug         # With custom config + debug
```

**Leader:**
```bash
python3 leader.py --debug                          # Enable debug mode  
python3 leader.py --auto --debug                   # Auto-start + debug mode
```

## What Gets Enabled with --debug

**Collaborator:**
- ✅ Detailed sync logging with deviation info
- ✅ VLC debug logging (if configured)
- ✅ Real-time sync monitoring every 5th sample
- ✅ Verbose sync correction details

**Leader:**
- ✅ HTML debug overlay creation
- ✅ VLC debug logging (if configured)  
- ✅ Detailed system logging
- ✅ Video/MIDI sync monitoring

## Files Modified
- `collaborator.py` - Constructor and main function
- `leader.py` - Constructor and main function
- `test_debug_flag.py` - Test script to verify functionality

## Testing
Run the test script to verify the flag works:
```bash
python3 test_debug_flag.py
```

The command line debug flag now properly enables debug mode from startup, ensuring all components see the debug setting during initialization.
