#!/usr/bin/env python3
"""
Test script to verify networking components start without blocking
This helps diagnose Firefox startup delays
"""

import sys
import time
import threading
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_network_startup():
    """Test networking component startup timing"""
    print("🧪 Testing KitchenSync networking startup...")
    
    try:
        from networking import SyncBroadcaster, CommandManager, SyncReceiver, CommandListener
        
        print("✓ Imports successful")
        
        # Test 1: SyncBroadcaster startup
        print("\n1. Testing SyncBroadcaster startup...")
        start_time = time.time()
        
        broadcaster = SyncBroadcaster()
        broadcaster.setup_socket()
        
        # Start broadcasting in background
        broadcaster.start_broadcasting(time.time())
        
        setup_time = time.time() - start_time
        print(f"   ✓ Setup time: {setup_time:.3f}s")
        
        # Test 2: CommandManager startup
        print("\n2. Testing CommandManager startup...")
        start_time = time.time()
        
        cmd_manager = CommandManager()
        cmd_manager.setup_socket()
        
        # Start listening in background
        cmd_manager.start_listening()
        
        setup_time = time.time() - start_time
        print(f"   ✓ Setup time: {setup_time:.3f}s")
        
        # Test 3: SyncReceiver startup
        print("\n3. Testing SyncReceiver startup...")
        start_time = time.time()
        
        sync_receiver = SyncReceiver()
        sync_receiver.setup_socket()
        
        # Start listening in background
        sync_receiver.start_listening()
        
        setup_time = time.time() - start_time
        print(f"   ✓ Setup time: {setup_time:.3f}s")
        
        # Test 4: CommandListener startup
        print("\n4. Testing CommandListener startup...")
        start_time = time.time()
        
        cmd_listener = CommandListener()
        cmd_listener.setup_socket()
        
        # Start listening in background
        cmd_listener.start_listening()
        
        setup_time = time.time() - start_time
        print(f"   ✓ Setup time: {setup_time:.3f}s")
        
        # Let components run for a few seconds
        print("\n5. Running components for 5 seconds...")
        time.sleep(5)
        
        # Cleanup
        print("\n6. Cleaning up...")
        broadcaster.stop_broadcasting()
        cmd_manager.stop_listening()
        sync_receiver.stop_listening()
        cmd_listener.stop_listening()
        
        print("\n✅ All networking components started successfully without blocking!")
        print("   This should resolve Firefox startup delays.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_port_availability():
    """Test if network ports are available"""
    print("\n🔌 Testing network port availability...")
    
    try:
        import socket
        
        ports_to_test = [5005, 5006]
        
        for port in ports_to_test:
            try:
                # Try to bind to the port
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                test_sock.bind(("", port))
                test_sock.close()
                print(f"   ✓ Port {port} is available")
            except OSError as e:
                print(f"   ❌ Port {port} is in use: {e}")
                return False
        
        print("   ✅ All required ports are available")
        return True
        
    except Exception as e:
        print(f"   ❌ Port test failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("KitchenSync Network Startup Test")
    print("=" * 50)
    
    # Test 1: Port availability
    if not test_port_availability():
        print("\n⚠️  Some ports are in use. This could cause startup delays.")
        print("   Consider restarting the system or checking for other services.")
    
    # Test 2: Component startup
    print("\n" + "=" * 50)
    success = test_network_startup()
    
    if success:
        print("\n🎉 Network startup test PASSED!")
        print("   Firefox should now start much faster on reboot.")
    else:
        print("\n💥 Network startup test FAILED!")
        print("   There may still be issues causing Firefox delays.")
    
    print("\n" + "=" * 50)
