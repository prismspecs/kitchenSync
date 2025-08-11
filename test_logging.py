#!/usr/bin/env python3
"""
Simple test script to verify logging works at boot
"""

import os
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from core.logger import (
        log_info,
        log_warning,
        log_error,
        snapshot_env,
        log_file_paths,
    )

    # Test basic logging
    log_info("=== LOGGING TEST STARTED ===", component="test")
    log_info(f"PID: {os.getpid()}", component="test")
    log_info(f"User: {os.getenv('USER', 'unknown')}", component="test")
    log_info(f"Working dir: {os.getcwd()}", component="test")

    # Snapshot environment
    env = snapshot_env()
    log_info(f"Environment captured: {len(env)} variables", component="test")

    # Show log paths
    paths = log_file_paths()
    log_info("Log paths available:", component="test")
    for name, path in paths.items():
        log_info(f"  {name}: {path}", component="test")

    # Test file creation
    test_file = "/tmp/kitchensync_test.log"
    with open(test_file, "w") as f:
        f.write(f"Test file created at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"PID: {os.getpid()}\n")
        f.write(f"User: {os.getenv('USER', 'unknown')}\n")

    log_info(f"Test file created: {test_file}", component="test")

    # Test VLC environment
    log_info("Testing VLC environment...", component="test")
    vlc_test_file = "/tmp/kitchensync_vlc_test.log"
    with open(vlc_test_file, "w") as f:
        f.write(f"VLC test at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"DISPLAY: {os.getenv('DISPLAY', 'unset')}\n")
        f.write(f"XAUTHORITY: {os.getenv('XAUTHORITY', 'unset')}\n")
        f.write(f"XDG_RUNTIME_DIR: {os.getenv('XDG_RUNTIME_DIR', 'unset')}\n")
        f.write(f"WAYLAND_DISPLAY: {os.getenv('WAYLAND_DISPLAY', 'unset')}\n")

    log_info("=== LOGGING TEST COMPLETED ===", component="test")
    print("✅ Logging test completed successfully!")
    print(f"Check logs in: /tmp/kitchensync_system.log")
    print(f"Test files: /tmp/kitchensync_test.log, /tmp/kitchensync_vlc_test.log")

except Exception as e:
    print(f"❌ Logging test failed: {e}")
    # Fallback logging
    with open("/tmp/kitchensync_test_failed.log", "w") as f:
        f.write(f"Test failed at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Error: {e}\n")
        f.write(f"PID: {os.getpid()}\n")
        f.write(f"User: {os.getenv('USER', 'unknown')}\n")
    print(f"Fallback log written to: /tmp/kitchensync_test_failed.log")
