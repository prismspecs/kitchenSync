#!/usr/bin/env python3
"""
Debug script to test wmctrl window detection
"""

import subprocess
import os

def test_wmctrl():
    """Test wmctrl window detection"""
    print("🔍 Testing wmctrl Window Detection")
    print("=" * 50)
    
    # Check if wmctrl is available
    try:
        result = subprocess.run(["which", "wmctrl"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ wmctrl found at: {result.stdout.strip()}")
        else:
            print("❌ wmctrl not found")
            return
    except Exception as e:
        print(f"❌ Error checking wmctrl: {e}")
        return
    
    # Test wmctrl -l (list windows)
    print("\n📋 Testing 'wmctrl -l'")
    print("-" * 30)
    try:
        result = subprocess.run(
            ["wmctrl", "-l"], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        if result.returncode == 0:
            print("✅ wmctrl -l successful")
            print("Output:")
            lines = result.stdout.strip().split('\n')
            for i, line in enumerate(lines):
                if line.strip():
                    print(f"  {i}: '{line}'")
                    
                    # Parse the line to see the format
                    parts = line.split(None, 4)
                    if len(parts) >= 5:
                        print(f"    Window ID: '{parts[0]}'")
                        print(f"    Desktop: '{parts[1]}'")
                        print(f"    Class: '{parts[2]}'")
                        print(f"    Host: '{parts[3]}'")
                        print(f"    Title: '{parts[4]}'")
                    else:
                        print(f"    Parts: {parts}")
        else:
            print(f"❌ wmctrl -l failed: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        print("❌ wmctrl -l timed out")
    except Exception as e:
        print(f"❌ Error running wmctrl: {e}")
    
    # Test wmctrl -lG (list windows with geometry)
    print("\n📐 Testing 'wmctrl -lG'")
    print("-" * 30)
    try:
        result = subprocess.run(
            ["wmctrl", "-lG"], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        if result.returncode == 0:
            print("✅ wmctrl -lG successful")
            print("Output:")
            lines = result.stdout.strip().split('\n')
            for i, line in enumerate(lines):
                if line.strip():
                    print(f"  {i}: '{line}'")
                    
                    # Parse the line to see the format
                    parts = line.split()
                    if len(parts) >= 7:
                        print(f"    Window ID: '{parts[0]}'")
                        print(f"    Desktop: '{parts[1]}'")
                        print(f"    X: '{parts[2]}'")
                        print(f"    Y: '{parts[3]}'")
                        print(f"    Width: '{parts[4]}'")
                        print(f"    Height: '{parts[5]}'")
                        print(f"    Class: '{parts[6]}'")
                        if len(parts) > 7:
                            print(f"    Title: '{' '.join(parts[7:])}'")
                    else:
                        print(f"    Parts: {parts}")
        else:
            print(f"❌ wmctrl -lG failed: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        print("❌ wmctrl -lG timed out")
    except Exception as e:
        print(f"❌ Error running wmctrl -lG: {e}")
    
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
    test_wmctrl()
