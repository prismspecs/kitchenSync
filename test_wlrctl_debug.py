#!/usr/bin/env python3
"""
Debug script to test wlrctl window detection
"""

import subprocess
import os

def test_wlrctl():
    """Test wlrctl window detection"""
    print("🔍 Testing wlrctl Window Detection")
    print("=" * 50)
    
    # Check if wlrctl is available
    try:
        result = subprocess.run(["which", "wlrctl"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ wlrctl found at: {result.stdout.strip()}")
        else:
            print("❌ wlrctl not found")
            return
    except Exception as e:
        print(f"❌ Error checking wlrctl: {e}")
        return
    
    # Test wlrctl toplevel list
    print("\n📋 Testing 'wlrctl toplevel list'")
    print("-" * 30)
    try:
        result = subprocess.run(
            ["wlrctl", "toplevel", "list"], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        if result.returncode == 0:
            print("✅ wlrctl toplevel list successful")
            print("Output:")
            lines = result.stdout.strip().split('\n')
            for i, line in enumerate(lines):
                if line.strip():
                    print(f"  {i}: '{line}'")
                    
                    # Parse the line to see the format
                    parts = line.strip().split(None, 1)
                    if len(parts) >= 2:
                        print(f"    App ID: '{parts[0]}'")
                        print(f"    Title: '{parts[1]}'")
                    else:
                        print(f"    Single part: '{parts[0]}'")
        else:
            print(f"❌ wlrctl toplevel list failed: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        print("❌ wlrctl toplevel list timed out")
    except Exception as e:
        print(f"❌ Error running wlrctl: {e}")
    
    # Test environment variables
    print("\n🌍 Environment Variables")
    print("-" * 30)
    env_vars = ['WAYLAND_DISPLAY', 'XDG_SESSION_TYPE', 'DISPLAY', 'XDG_RUNTIME_DIR']
    for var in env_vars:
        value = os.environ.get(var, 'Not set')
        print(f"{var}: {value}")
    
    # Test if we can see any processes
    print("\n🔍 Running Processes")
    print("-" * 30)
    try:
        result = subprocess.run(
            ["ps", "aux"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            chromium_lines = [line for line in lines if 'chromium' in line.lower()]
            wayland_lines = [line for line in lines if 'wayland' in line.lower() or 'wayfire' in line.lower()]
            
            print(f"Found {len(chromium_lines)} Chromium processes")
            print(f"Found {len(wayland_lines)} Wayland-related processes")
            
            if chromium_lines:
                print("\nChromium processes:")
                for line in chromium_lines[:3]:  # Show first 3
                    print(f"  {line}")
                    
        else:
            print(f"❌ ps command failed: {result.stderr}")
            
    except Exception as e:
        print(f"❌ Error checking processes: {e}")

if __name__ == "__main__":
    test_wlrctl()
