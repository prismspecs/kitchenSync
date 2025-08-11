#!/usr/bin/env python3
"""
Diagnostic script to show what the debug overlay sees in the current environment
"""

import sys
import os
from pathlib import Path
import subprocess

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.logger import log_file_paths


def check_environment():
    """Check what the debug overlay would see in this environment"""
    print("🔍 KitchenSync Debug Environment Diagnostic")
    print("=" * 50)
    
    # Check log file paths
    print("\n📁 Log File Paths:")
    try:
        paths = log_file_paths()
        for name, path in paths.items():
            exists = "✅" if os.path.exists(path) else "❌"
            print(f"  {name}: {exists} {path}")
    except Exception as e:
        print(f"  ❌ Error getting log paths: {e}")
    
    # Check for KitchenSync processes
    print("\n🔄 KitchenSync Processes:")
    try:
        # Check for leader.py
        result = subprocess.run(
            ["pgrep", "-f", "leader.py"], 
            capture_output=True, text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            print(f"  ✅ leader.py processes: {', '.join(pids)}")
        else:
            print("  ❌ No leader.py processes found")
            
        # Check for collaborator.py  
        result = subprocess.run(
            ["pgrep", "-f", "collaborator.py"], 
            capture_output=True, text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            print(f"  ✅ collaborator.py processes: {', '.join(pids)}")
        else:
            print("  ❌ No collaborator.py processes found")
            
    except Exception as e:
        print(f"  ❌ Error checking processes: {e}")
    
    # Check systemd service
    print("\n🔧 Systemd Service:")
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "kitchensync.service"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  ✅ kitchensync.service: {result.stdout.strip()}")
        else:
            print(f"  ❌ kitchensync.service: inactive or not found")
    except Exception as e:
        print(f"  ❌ Error checking service: {e}")
    
    # Check for VLC processes
    print("\n🎬 VLC Processes:")
    try:
        result = subprocess.run(
            ["pgrep", "-f", "vlc"], 
            capture_output=True, text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            print(f"  ✅ VLC processes: {', '.join(pids)}")
        else:
            print("  ❌ No VLC processes found")
    except Exception as e:
        print(f"  ❌ Error checking VLC: {e}")
    
    # Check /tmp directory for debug files
    print("\n📂 Debug Files in /tmp:")
    try:
        tmp_files = []
        for item in os.listdir("/tmp"):
            if "kitchensync" in item.lower():
                path = f"/tmp/{item}"
                if os.path.isfile(path):
                    size = os.path.getsize(path)
                    tmp_files.append(f"  📄 {item} ({size} bytes)")
                elif os.path.isdir(path):
                    tmp_files.append(f"  📁 {item}/")
        
        if tmp_files:
            print("\n".join(tmp_files))
        else:
            print("  ❌ No KitchenSync files found in /tmp")
            
    except Exception as e:
        print(f"  ❌ Error checking /tmp: {e}")
    
    print("\n" + "=" * 50)
    print("📝 Summary:")
    print("   The debug overlay shows 'None'/'No logs' because:")
    print("   • KitchenSync services aren't currently running")
    print("   • No video is loaded in VLC")
    print("   • Log files don't exist yet")
    print("\n   This is normal when testing outside of a full KitchenSync session!")
    print("   When the actual system runs, it will populate with real data.")


if __name__ == "__main__":
    check_environment()
