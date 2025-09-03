#!/usr/bin/env python3
"""
Test script to diagnose broadcast issues
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from networking.communication import (
        _get_broadcast_address,
        SyncBroadcaster,
        CommandManager,
    )

    print("Testing broadcast address detection...")
    broadcast_addr = _get_broadcast_address()
    print(f"Detected broadcast address: {broadcast_addr}")

    print("\nTesting SyncBroadcaster initialization...")
    try:
        sync_broadcaster = SyncBroadcaster()
        print(
            f"SyncBroadcaster created successfully, using: {sync_broadcaster.broadcast_ip}"
        )
    except Exception as e:
        print(f"SyncBroadcaster failed: {e}")

    print("\nTesting CommandManager initialization...")
    try:
        command_manager = CommandManager()
        print(
            f"CommandManager created successfully, using: {command_manager.broadcast_ip}"
        )
    except Exception as e:
        print(f"CommandManager failed: {e}")

    print("\nTesting socket creation...")
    try:
        sync_broadcaster.setup_socket()
        print("Sync socket created successfully")
        sync_broadcaster.sync_sock.close()
    except Exception as e:
        print(f"Sync socket failed: {e}")

    try:
        command_manager.setup_socket()
        print("Command socket created successfully")
        command_manager.control_sock.close()
    except Exception as e:
        print(f"Command socket failed: {e}")

except Exception as e:
    print(f"Import or general error: {e}")
    import traceback

    traceback.print_exc()

