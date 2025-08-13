#!/usr/bin/env python3
"""
Simple KitchenSync Network Test
Just shows leader sync messages
"""

import json
import socket
import time

def main():
    print("🎯 KitchenSync Network Test - Monitoring Leader")
    print("=" * 50)
    print("Listening for sync messages on port 5005...")
    print("Press Ctrl+C to stop\n")
    
    # Create UDP socket to listen for sync broadcasts
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", 5005))
    sock.settimeout(1.0)
    
    packet_count = 0
    start_time = time.time()
    
    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                packet_count += 1
                current_time = time.time()
                
                try:
                    msg = json.loads(data.decode())
                    
                    if msg.get("type") == "sync":
                        leader_time = msg.get('time', 0)
                        leader_id = msg.get('leader_id', 'unknown')
                        
                        print(f"📡 Sync #{packet_count} from {addr[0]}")
                        print(f"   Leader: {leader_id}")
                        print(f"   Time: {leader_time:.3f}s")
                        print(f"   Received at: {current_time:.3f}s")
                        print(f"   Uptime: {current_time - start_time:.1f}s")
                        print("   " + "-" * 40)
                    
                except json.JSONDecodeError:
                    print(f"⚠️  Invalid JSON from {addr[0]}")
            
            except socket.timeout:
                # No packets received, just continue
                continue
                
    except KeyboardInterrupt:
        print(f"\n📊 Test completed!")
        print(f"   Total packets received: {packet_count}")
        print(f"   Test duration: {time.time() - start_time:.1f}s")
    
    finally:
        sock.close()

if __name__ == "__main__":
    main()

