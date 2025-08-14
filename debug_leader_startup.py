#!/usr/bin/env python3
"""
Debug script to trace leader startup issues
"""

import sys
import time
import traceback
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test all imports step by step"""
    print("🔍 Testing imports...")
    
    try:
        from config import ConfigManager
        print("✓ ConfigManager imported")
    except Exception as e:
        print(f"✗ ConfigManager failed: {e}")
        return False
    
    try:
        from video import VideoFileManager, VLCVideoPlayer
        print("✓ Video components imported")
    except Exception as e:
        print(f"✗ Video components failed: {e}")
        return False
    
    try:
        from networking import SyncBroadcaster, CommandManager
        print("✓ Networking components imported")
    except Exception as e:
        print(f"✗ Networking components failed: {e}")
        return False
    
    try:
        from midi import MidiScheduler, MidiManager
        print("✓ MIDI components imported")
    except Exception as e:
        print(f"✗ MIDI components failed: {e}")
        return False
    
    try:
        from core import Schedule, ScheduleEditor, SystemState, CollaboratorRegistry
        print("✓ Core components imported")
    except Exception as e:
        print(f"✗ Core components failed: {e}")
        return False
    
    try:
        from ui import CommandInterface, StatusDisplay
        print("✓ UI components imported")
    except Exception as e:
        print(f"✗ UI components failed: {e}")
        return False
    
    try:
        from debug.html_overlay import HTMLDebugManager
        print("✓ Debug overlay imported")
    except Exception as e:
        print(f"✗ Debug overlay failed: {e}")
        return False
    
    try:
        from core.logger import log_info, log_warning, log_error, snapshot_env, log_file_paths, enable_system_logging
        print("✓ Logger imported")
    except Exception as e:
        print(f"✗ Logger failed: {e}")
        return False
    
    return True

def test_config():
    """Test configuration loading"""
    print("\n🔍 Testing configuration...")
    
    try:
        from config import ConfigManager
        config = ConfigManager("leader_config.ini")
        print(f"✓ Config loaded")
        print(f"  - is_leader: {config.is_leader}")
        print(f"  - debug_mode: {config.debug_mode}")
        print(f"  - video_file: {config.video_file}")
        print(f"  - sync_port: {config.getint('sync_port', 5005)}")
        print(f"  - control_port: {config.getint('control_port', 5006)}")
        print(f"  - tick_interval: {config.tick_interval}")
        return config
    except Exception as e:
        print(f"✗ Config failed: {e}")
        traceback.print_exc()
        return None

def test_leader_init():
    """Test LeaderPi initialization"""
    print("\n🔍 Testing LeaderPi initialization...")
    
    try:
        # Import the LeaderPi class
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        # Import leader module
        import leader
        
        print("✓ Leader module imported")
        
        # Try to create LeaderPi instance
        leader_instance = leader.LeaderPi()
        print("✓ LeaderPi instance created")
        
        return leader_instance
        
    except Exception as e:
        print(f"✗ LeaderPi initialization failed: {e}")
        traceback.print_exc()
        return None

def test_networking():
    """Test networking components"""
    print("\n🔍 Testing networking setup...")
    
    try:
        from networking import SyncBroadcaster, CommandManager
        
        # Test SyncBroadcaster
        broadcaster = SyncBroadcaster(sync_port=5005, tick_interval=1.0)
        print("✓ SyncBroadcaster created")
        
        broadcaster.setup_socket()
        print("✓ SyncBroadcaster socket setup")
        
        # Test CommandManager
        cmd_manager = CommandManager(control_port=5006)
        print("✓ CommandManager created")
        
        cmd_manager.setup_socket()
        print("✓ CommandManager socket setup")
        
        # Cleanup
        broadcaster.stop_broadcasting()
        cmd_manager.stop_listening()
        
        return True
        
    except Exception as e:
        print(f"✗ Networking setup failed: {e}")
        traceback.print_exc()
        return False

def main():
    print("🚀 KitchenSync Leader Startup Diagnostics")
    print("=" * 50)
    
    # Test imports
    if not test_imports():
        print("\n❌ Import test failed")
        return
    
    # Test config
    config = test_config()
    if not config:
        print("\n❌ Config test failed")
        return
    
    # Test networking
    if not test_networking():
        print("\n❌ Networking test failed")
        return
    
    # Test full leader initialization
    leader_instance = test_leader_init()
    if not leader_instance:
        print("\n❌ Leader initialization failed")
        return
    
    print("\n✅ All tests passed!")
    print("The leader should be able to start normally.")
    
    # Try a manual start_system call
    print("\n🔍 Testing start_system()...")
    try:
        leader_instance.start_system()
        print("✓ start_system() completed")
        
        # Wait a bit to see if broadcasting starts
        print("Waiting 3 seconds to check broadcasting...")
        time.sleep(3)
        
        # Check if broadcaster is running
        if leader_instance.sync_broadcaster.is_running:
            print("✓ Broadcasting is active")
        else:
            print("✗ Broadcasting is not active")
            
    except Exception as e:
        print(f"✗ start_system() failed: {e}")
        traceback.print_exc()
    finally:
        # Cleanup
        try:
            leader_instance.cleanup()
        except:
            pass

if __name__ == "__main__":
    main()
