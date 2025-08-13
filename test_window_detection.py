#!/usr/bin/env python3
"""
Test script to debug window detection and test Chromium window visibility
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ui.window_manager import WindowManager
from core.logger import log_info, log_warning, log_error

def test_window_detection():
    """Test window detection capabilities"""
    print("🔍 Testing Window Detection System")
    print("=" * 50)
    
    # Initialize window manager
    wm = WindowManager()
    
    print(f"Window manager type: {'Wayland' if wm.is_wayland else 'X11'}")
    print(f"Window tool: {wm.window_tool}")
    print()
    
    # Test 1: List all windows
    print("📋 Test 1: Listing all windows")
    print("-" * 30)
    windows = wm.list_windows()
    print(f"Total windows found: {len(windows)}")
    for i, window in enumerate(windows):
        if window.strip():
            print(f"  {i}: {window}")
    print()
    
    # Test 2: Search for specific window types
    print("🔍 Test 2: Searching for specific windows")
    print("-" * 30)
    
    search_tests = [
        (["chromium"], "Chromium browser"),
        (["vlc"], "VLC media player"),
        (["firefox"], "Firefox browser"),
        (["kitchensync"], "KitchenSync"),
        (["debug"], "Debug windows"),
        (["terminal"], "Terminal windows"),
    ]
    
    for search_terms, description in search_tests:
        window = wm.find_window(search_terms)
        if window:
            print(f"✅ {description}: {window}")
        else:
            print(f"❌ {description}: Not found")
    print()
    
    # Test 3: Get detailed window information
    print("📊 Test 3: Detailed window information")
    print("-" * 30)
    details = wm.get_window_details()
    print(details)
    print()
    
    # Test 4: Test window waiting
    print("⏳ Test 4: Testing window waiting (5 second timeout)")
    print("-" * 30)
    
    # Try to find a Chromium window
    print("Waiting for Chromium window...")
    start_time = time.time()
    chromium_window = wm.wait_for_window(
        search_terms=["chromium", "debug"],
        exclude_terms=["vlc"],
        timeout=5
    )
    elapsed = time.time() - start_time
    
    if chromium_window:
        print(f"✅ Chromium window found after {elapsed:.1f}s: {chromium_window}")
    else:
        print(f"❌ Chromium window not found within 5 seconds")
    print()
    
    # Test 5: Manual window search debugging
    print("🐛 Test 5: Manual window search debugging")
    print("-" * 30)
    
    # Search for Chromium with detailed debugging
    debug_info = wm.debug_window_search(["chromium"], ["vlc"])
    print(debug_info)
    
    print("=" * 50)
    print("🎯 Test complete!")

def test_chromium_launch():
    """Test launching Chromium manually"""
    print("\n🚀 Testing Chromium Launch")
    print("=" * 50)
    
    try:
        import subprocess
        import os
        
        # Set up environment
        env = os.environ.copy()
        env.update({
            'DISPLAY': ':0',
            'XDG_SESSION_TYPE': 'x11',
            'GDK_BACKEND': 'x11',
        })
        
        print("Launching Chromium with test page...")
        
        # Launch Chromium with a simple test page
        process = subprocess.Popen([
            "chromium-browser",
            "--new-window",
            "--no-first-run",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-background-tabs",
            "--disable-background-mode",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-translate",
            "--disable-web-security",
            "--no-default-browser-check",
            "--disable-features=VizDisplayCompositor",
            "--disable-gpu-sandbox",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            "--disable-ipc-flooding-protection",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-background-timer-throttling",
            "--disable-features=TranslateUI",
            "--disable-features=NetworkService",
            "--disable-features=NetworkServiceLogging",
            "data:text/html,<html><body><h1>KitchenSync Test Page</h1><p>Chromium test window</p></body></html>"
        ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        print("Chromium launched, waiting for window...")
        time.sleep(2)
        
        # Check if process is still running
        if process.poll() is None:
            print("✅ Chromium process is running")
            
            # Now test window detection
            wm = WindowManager()
            print("Searching for Chromium window...")
            
            for i in range(10):  # Try for 5 seconds
                window = wm.find_window(["chromium", "test", "kitchensync"])
                if window:
                    print(f"✅ Chromium window found: {window}")
                    break
                time.sleep(0.5)
                print(f"  Attempt {i+1}/10...")
            else:
                print("❌ Chromium window not detected")
            
            # Clean up
            process.terminate()
            process.wait(timeout=5)
            print("Chromium process terminated")
        else:
            stdout, stderr = process.communicate()
            print(f"❌ Chromium failed to start")
            print(f"Exit code: {process.returncode}")
            print(f"Stdout: {stdout.decode()}")
            print(f"Stderr: {stderr.decode()}")
            
    except Exception as e:
        print(f"❌ Error testing Chromium launch: {e}")

if __name__ == "__main__":
    print("🧪 KitchenSync Window Detection Test")
    print("=" * 50)
    
    try:
        test_window_detection()
        test_chromium_launch()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
