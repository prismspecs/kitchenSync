#!/usr/bin/env python3
"""
Simple debug output for KitchenSync - bypasses all the complex overlay code
"""

import time
import os
import sys
from pathlib import Path

def write_debug_info():
    """Write debug info to a simple file"""
    debug_file = "/tmp/kitchensync_simple_debug.txt"
    
    try:
        with open(debug_file, 'a') as f:
            timestamp = time.strftime('%H:%M:%S')
            elapsed = time.time() - start_time if 'start_time' in globals() else 0
            
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            
            f.write(f"[{timestamp}] KitchenSync LEADER - Time: {mins:02d}:{secs:02d}\n")
            f.flush()
    except Exception as e:
        print(f"Debug write error: {e}")

if __name__ == "__main__":
    debug_file = "/tmp/kitchensync_simple_debug.txt"
    
    # Initialize file
    with open(debug_file, 'w') as f:
        f.write("KitchenSync Simple Debug\n")
        f.write("=" * 30 + "\n")
        f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 30 + "\n")
    
    start_time = time.time()
    
    print(f"Simple debug running - monitor with:")
    print(f"ssh kitchensync@192.168.178.59 'tail -f {debug_file}'")
    
    try:
        while True:
            write_debug_info()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Debug stopped") 