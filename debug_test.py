#!/usr/bin/env python3
"""
Simple test to verify debug overlay behavior
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from debug.overlay import DebugManager
import time

def test_collaborator_debug():
    """Test collaborator debug initialization"""
    print("Testing collaborator debug initialization...")
    
    # Create debug manager for collaborator
    debug_mgr = DebugManager(
        pi_id="pi-001", 
        video_file="/home/test/video.mp4", 
        debug_mode=True
    )
    
    print(f"Debug manager created:")
    print(f"  - overlay: {debug_mgr.overlay}")
    print(f"  - terminal_debugger: {debug_mgr.terminal_debugger}")
    
    # Test update
    if debug_mgr.overlay or debug_mgr.terminal_debugger:
        midi_data = {
            'recent': [
                {'type': 'note_on', 'channel': 1, 'note': 60, 'velocity': 127, 'time': 10.5},
                {'type': 'note_off', 'channel': 1, 'note': 60, 'time': 11.0}
            ],
            'current': {'type': 'note_on', 'channel': 2, 'note': 64, 'velocity': 100, 'time': 15.2},
            'upcoming': [
                {'type': 'note_on', 'channel': 1, 'note': 67, 'velocity': 110, 'time': 20.0},
                {'type': 'control_change', 'channel': 1, 'control': 7, 'value': 80, 'time': 25.5}
            ]
        }
        
        print("Updating debug display...")
        debug_mgr.update_display(current_time=16.0, total_time=180.0, midi_data=midi_data)
        
        # Keep running for a bit to see the window
        print("Debug window should be visible. Press Ctrl+C to exit.")
        try:
            while True:
                debug_mgr.update_display(current_time=16.0, total_time=180.0, midi_data=midi_data)
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nCleaning up...")
            debug_mgr.cleanup()
    else:
        print("No debug display was created!")

if __name__ == "__main__":
    test_collaborator_debug()
