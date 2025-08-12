#!/usr/bin/env python3
"""
KitchenSync Test Listener
A simple script to test synchronization between leader and collaborator devices.
Run this on any device to listen for KitchenSync leader broadcasts.

Usage:
    python3 test_sync_listener.py
"""

import json
import socket
import time
import threading
from datetime import datetime


class KitchenSyncTestListener:
    """Test listener for KitchenSync leader broadcasts"""

    def __init__(self, sync_port=5005, control_port=5006):
        self.sync_port = sync_port
        self.control_port = control_port
        self.is_running = False

        # Statistics
        self.sync_count = 0
        self.command_count = 0
        self.last_sync_time = None
        self.last_command_time = None

        # Sockets
        self.sync_sock = None
        self.control_sock = None

    def setup_sockets(self):
        """Initialize UDP sockets for listening"""
        try:
            # Time sync socket
            self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sync_sock.bind(("", self.sync_port))
            self.sync_sock.settimeout(1.0)

            # Control command socket
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_sock.bind(("", self.control_port))
            self.control_sock.settimeout(1.0)

            print(
                f"✅ Listening on ports {self.sync_port} (sync) and {self.control_port} (control)"
            )
            print(f"📍 Local IP: {self.get_local_ip()}")
            print("🔍 Waiting for KitchenSync leader broadcasts...\n")

        except Exception as e:
            print(f"❌ Failed to setup sockets: {e}")
            raise

    def get_local_ip(self):
        """Get local IP address"""
        try:
            # Connect to a remote address to determine local IP
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
            sock.close()
            return local_ip
        except:
            return "unknown"

    def start_listening(self):
        """Start listening for broadcasts"""
        self.is_running = True

        if not self.sync_sock or not self.control_sock:
            self.setup_sockets()

        # Start sync listener thread
        sync_thread = threading.Thread(target=self._sync_listener, daemon=True)
        sync_thread.start()

        # Start control listener thread
        control_thread = threading.Thread(target=self._control_listener, daemon=True)
        control_thread.start()

        # Start status display thread
        status_thread = threading.Thread(target=self._status_display, daemon=True)
        status_thread.start()

        print("🚀 Started listening for KitchenSync broadcasts")
        print("Press Ctrl+C to stop\n")

        try:
            while self.is_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping listener...")
            self.stop_listening()

    def _sync_listener(self):
        """Listen for time sync broadcasts"""
        while self.is_running:
            try:
                data, addr = self.sync_sock.recvfrom(1024)
                self._handle_sync_message(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"⚠️  Sync listener error: {e}")

    def _control_listener(self):
        """Listen for control command broadcasts"""
        while self.is_running:
            try:
                data, addr = self.control_sock.recvfrom(1024)
                self._handle_control_message(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"⚠️  Control listener error: {e}")

    def _handle_sync_message(self, data, addr):
        """Handle time sync messages"""
        try:
            msg = json.loads(data.decode())

            if msg.get("type") == "sync":
                self.sync_count += 1
                self.last_sync_time = time.time()

                leader_time = msg.get("time", 0)
                leader_id = msg.get("leader_id", "unknown")

                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(
                    f"⏰ [{timestamp}] SYNC from {addr[0]}:{addr[1]} (Leader: {leader_id})"
                )
                print(f"   🕐 Leader time: {leader_time:.3f}s")
                print(f"   📊 Total sync messages: {self.sync_count}")
                print()

        except json.JSONDecodeError:
            print(f"⚠️  Invalid JSON from {addr[0]}:{addr[1]}")
        except Exception as e:
            print(f"⚠️  Error handling sync message: {e}")

    def _handle_control_message(self, data, addr):
        """Handle control command messages"""
        try:
            msg = json.loads(data.decode())

            self.command_count += 1
            self.last_command_time = time.time()

            msg_type = msg.get("type", "unknown")
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            print(f"🎮 [{timestamp}] COMMAND from {addr[0]}:{addr[1]}")
            print(f"   📝 Type: {msg_type}")
            print(f"   📊 Total commands: {self.command_count}")

            # Display message content (excluding sensitive data)
            for key, value in msg.items():
                if key not in ["type"]:
                    print(f"   🔑 {key}: {value}")
            print()

        except json.JSONDecodeError:
            print(f"⚠️  Invalid JSON from {addr[0]}:{addr[1]}")
        except Exception as e:
            print(f"⚠️  Error handling control message: {e}")

    def _status_display(self):
        """Display periodic status updates"""
        while self.is_running:
            time.sleep(10)  # Update every 10 seconds

            if self.is_running:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(
                    f"📊 [{timestamp}] STATUS: Sync: {self.sync_count}, Commands: {self.command_count}"
                )

                if self.last_sync_time:
                    time_since_sync = time.time() - self.last_sync_time
                    if time_since_sync > 5:
                        print(f"   ⚠️  No sync for {time_since_sync:.1f}s")
                    else:
                        print(f"   ✅ Sync active ({time_since_sync:.1f}s ago)")

                if self.last_command_time:
                    time_since_cmd = time.time() - self.last_command_time
                    print(f"   📡 Last command: {time_since_cmd:.1f}s ago")

                print()

    def stop_listening(self):
        """Stop listening and cleanup"""
        self.is_running = False

        if self.sync_sock:
            self.sync_sock.close()
        if self.control_sock:
            self.control_sock.close()

        print(f"📊 Final Statistics:")
        print(f"   ⏰ Total sync messages: {self.sync_count}")
        print(f"   🎮 Total commands: {self.command_count}")
        print("👋 Listener stopped")


def main():
    """Main function"""
    print("🎯 KitchenSync Test Listener")
    print("=" * 40)
    print("This script listens for KitchenSync leader broadcasts")
    print("to test synchronization between devices.")
    print()

    try:
        listener = KitchenSyncTestListener()
        listener.start_listening()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
