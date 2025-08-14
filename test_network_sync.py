#!/usr/bin/env python3
"""
Simple KitchenSync Network Test

Just run this script to see if the leader is sending sync messages.
It will listen for UDP broadcasts and show you what's happening.

Usage:
  python3 test_network_sync.py
"""

import json
import socket
import time
from datetime import datetime


def monitor_leader():
    """Simple monitor for leader sync broadcasts"""
    sync_port = 5005

    print("🔍 KitchenSync Network Test")
    print("=" * 40)
    print(f"Listening for leader broadcasts on port {sync_port}")
    print("Make sure the leader is running!")
    print("Press Ctrl+C to stop\n")

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", sync_port))
    sock.settimeout(1.0)

    packet_count = 0
    start_time = time.time()

    try:
        while True:
            try:
                # Wait for data
                data, addr = sock.recvfrom(1024)
                packet_count += 1
                current_time = time.time()

                # Parse the message
                try:
                    msg = json.loads(data.decode())
                    msg_type = msg.get("type", "unknown")

                    # Show what we received
                    print(f"📡 Packet #{packet_count} from {addr[0]}")
                    print(f"   Type: {msg_type}")
                    print(f"   Time: {datetime.now().strftime('%H:%M:%S')}")

                    if msg_type == "sync":
                        leader_time = msg.get("time", 0)
                        leader_id = msg.get("leader_id", "unknown")
                        print(f"   Leader ID: {leader_id}")
                        print(f"   Leader time: {leader_time:.3f}s")

                        # Show timing info
                        uptime = current_time - start_time
                        print(f"   Uptime: {uptime:.1f}s")
                        print(f"   Packets received: {packet_count}")

                    print("   " + "-" * 30)

                except json.JSONDecodeError:
                    print(f"⚠️  Invalid JSON from {addr[0]}")
                    print(f"   Raw data: {data[:100]}...")
                    print("   " + "-" * 30)

            except socket.timeout:
                # No data received, show status every 5 seconds
                if int(time.time()) % 5 == 0:
                    uptime = time.time() - start_time
                    print(
                        f"⏳ Waiting... (uptime: {uptime:.0f}s, packets: {packet_count})"
                    )

            except Exception as e:
                print(f"❌ Error: {e}")
                break

    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
    finally:
        sock.close()
        print(f"\n📊 Final stats:")
        print(f"   Total packets: {packet_count}")
        uptime = time.time() - start_time
        print(f"   Total time: {uptime:.1f}s")
        if packet_count > 0:
            print(f"   Avg rate: {packet_count/uptime:.2f} packets/sec")


if __name__ == "__main__":
    monitor_leader()
