#!/usr/bin/env python3
"""
Simple test script for debug overlay functionality
"""

import sys
import os
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from debug import DebugManager

def test_debug_overlay():
    """Test the debug overlay with simulated playback"""
    print("Testing debug overlay...")
    
    # Create debug manager
    video_file = "/media/kitchensync/MicroBoi/test_video.mp4"
    debug_mgr = DebugManager("test-pi", video_file, debug_mode=True)
    
    if not debug_mgr.overlay:
        print("❌ Failed to create debug overlay")
        return False
    
    print("✅ Debug overlay created successfully")
    
    # Test initial state
    debug_mgr.overlay.set_state(
        video_file=video_file,
        current_time=0.0,
        total_time=180.0,
        midi_data={'recent': [], 'current': None, 'upcoming': []},
        is_leader=True,
        pi_id="test-pi"
    )
    
    print("✅ Initial state set")
    
    # Simulate playback for 10 seconds
    print("Simulating 10 seconds of playback...")
    for i in range(10):
        current_time = float(i)
        
        # Simulate some MIDI events
        midi_data = {
            'recent': [
                {'type': 'note_on', 'channel': 1, 'note': 60, 'time': max(0, current_time-2)},
            ] if i > 2 else [],
            'current': {
                'type': 'note_on', 'channel': 1, 'note': 64, 'time': current_time
            } if i == 5 else None,
            'upcoming': [
                {'type': 'note_off', 'channel': 1, 'note': 60, 'time': current_time+3},
                {'type': 'control_change', 'channel': 1, 'control': 7, 'value': 100, 'time': current_time+5}
            ] if i < 7 else []
        }
        
        debug_mgr.overlay.set_state(
            current_time=current_time,
            total_time=180.0,
            midi_data=midi_data
        )
        
        print(f"  Time: {i:02d}:00 / 03:00")
        time.sleep(1)
    
    print("✅ Playback simulation completed")
    
    # Cleanup
    debug_mgr.cleanup()
    print("✅ Cleanup completed")
    
    return True

if __name__ == "__main__":
    try:
        success = test_debug_overlay()
        if success:
            print("\n🎉 Debug overlay test PASSED!")
        else:
            print("\n❌ Debug overlay test FAILED!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted")
    except Exception as e:
        print(f"\n💥 Test error: {e}")
        sys.exit(1) 