#!/usr/bin/env python3
"""
KitchenSync Network Sync Testing Tool

This tool can:
1. Monitor sync broadcasts from the leader
2. Simulate a collaborator Pi for testing
3. Show real-time sync timing and network communication

Usage:
  python3 test_network_sync.py monitor    # Just monitor sync messages
  python3 test_network_sync.py simulate   # Simulate a collaborator Pi
"""

import argparse
import json
import socket
import threading
import time
from datetime import datetime
from typing import Optional


class SyncMonitor:
    """Monitor sync broadcasts from leader"""
    
    def __init__(self, sync_port: int = 5005, control_port: int = 5006):
        self.sync_port = sync_port
        self.control_port = control_port
        self.running = False
        self.sync_count = 0
        self.last_sync_time = None
        self.leader_id = None
        
    def start_monitoring(self):
        """Start monitoring both sync and control channels"""
        print("🔍 Starting KitchenSync Network Monitor")
        print(f"   Listening on sync port {self.sync_port} and control port {self.control_port}")
        print("   Press Ctrl+C to stop\n")
        
        self.running = True
        
        # Start sync monitor thread
        sync_thread = threading.Thread(target=self._monitor_sync, daemon=True)
        sync_thread.start()
        
        # Start control monitor thread  
        control_thread = threading.Thread(target=self._monitor_control, daemon=True)
        control_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping monitor...")
            self.running = False
            
    def _monitor_sync(self):
        """Monitor sync broadcasts"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("", self.sync_port))
            sock.settimeout(1.0)
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = json.loads(data.decode())
                    
                    if msg.get("type") == "sync":
                        self.sync_count += 1
                        self.last_sync_time = time.time()
                        self.leader_id = msg.get("leader_id", "unknown")
                        leader_time = msg.get("time", 0)
                        
                        # Show sync info every 10 messages to avoid spam
                        if self.sync_count % 10 == 1:
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            print(f"[{timestamp}] 📡 SYNC #{self.sync_count}: Leader={self.leader_id}, Time={leader_time:.2f}s, From={addr[0]}")
                            
                except socket.timeout:
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"❌ Sync monitor error: {e}")
                        
        except Exception as e:
            print(f"❌ Failed to setup sync monitor: {e}")
            
    def _monitor_control(self):
        """Monitor control messages"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("", self.control_port))
            sock.settimeout(1.0)
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = json.loads(data.decode())
                    
                    msg_type = msg.get("type", "unknown")
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    if msg_type == "start":
                        schedule_count = len(msg.get("schedule", []))
                        debug_mode = msg.get("debug_mode", False)
                        print(f"[{timestamp}] 🚀 START command: {schedule_count} cues, debug={debug_mode}")
                        
                    elif msg_type == "stop":
                        print(f"[{timestamp}] 🛑 STOP command")
                        
                    elif msg_type == "register":
                        pi_id = msg.get("pi_id", "unknown")
                        video_file = msg.get("video_file", "unknown")
                        print(f"[{timestamp}] 📝 REGISTER: {pi_id} with video '{video_file}'")
                        
                    elif msg_type == "heartbeat":
                        pi_id = msg.get("pi_id", "unknown")
                        status = msg.get("status", "unknown")
                        # Only show heartbeats occasionally to avoid spam
                        if self.sync_count % 20 == 1:
                            print(f"[{timestamp}] 💓 HEARTBEAT: {pi_id} status={status}")
                        
                    else:
                        print(f"[{timestamp}] 📨 {msg_type.upper()}: {msg}")
                        
                except socket.timeout:
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"❌ Control monitor error: {e}")
                        
        except Exception as e:
            print(f"❌ Failed to setup control monitor: {e}")


class CollaboratorSimulator:
    """Simulate a collaborator Pi for testing"""
    
    def __init__(self, pi_id: str = "test-pi", sync_port: int = 5005, control_port: int = 5006):
        self.pi_id = pi_id
        self.sync_port = sync_port
        self.control_port = control_port
        self.running = False
        self.synced = False
        self.last_sync_time = 0
        self.leader_time = 0
        self.sync_count = 0
        
    def start_simulation(self):
        """Start simulating a collaborator"""
        print(f"🤖 Starting Collaborator Simulator: {self.pi_id}")
        print(f"   Listening for sync on port {self.sync_port}")
        print(f"   Listening for commands on port {self.control_port}")
        print("   Press Ctrl+C to stop\n")
        
        self.running = True
        
        # Start sync receiver
        sync_thread = threading.Thread(target=self._receive_sync, daemon=True)
        sync_thread.start()
        
        # Start command listener
        command_thread = threading.Thread(target=self._listen_commands, daemon=True)
        command_thread.start()
        
        # Start status updates
        status_thread = threading.Thread(target=self._status_updates, daemon=True)
        status_thread.start()
        
        # Send initial registration
        time.sleep(1)  # Wait a moment for threads to start
        self._send_registration()
        
        # Start heartbeat
        heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        heartbeat_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n🛑 Stopping {self.pi_id} simulator...")
            self.running = False
            
    def _receive_sync(self):
        """Receive sync broadcasts"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("", self.sync_port))
            sock.settimeout(1.0)
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = json.loads(data.decode())
                    
                    if msg.get("type") == "sync":
                        self.sync_count += 1
                        self.last_sync_time = time.time()
                        self.leader_time = msg.get("time", 0)
                        self.synced = True
                        
                except socket.timeout:
                    # Check if sync is stale
                    if self.synced and (time.time() - self.last_sync_time) > 5.0:
                        self.synced = False
                        print(f"⚠️  {self.pi_id}: Lost sync with leader")
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"❌ {self.pi_id} sync error: {e}")
                        
        except Exception as e:
            print(f"❌ {self.pi_id} failed to setup sync receiver: {e}")
            
    def _listen_commands(self):
        """Listen for leader commands"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("", self.control_port))
            sock.settimeout(1.0)
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = json.loads(data.decode())
                    
                    msg_type = msg.get("type")
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    if msg_type == "start":
                        schedule_count = len(msg.get("schedule", []))
                        print(f"[{timestamp}] 🚀 {self.pi_id}: Received START command ({schedule_count} cues)")
                        print(f"   Waiting for sync...")
                        
                        # Simulate waiting for sync
                        wait_start = time.time()
                        while not self.synced and (time.time() - wait_start) < 10:
                            time.sleep(0.1)
                            
                        if self.synced:
                            print(f"   ✅ {self.pi_id}: Sync established, starting playback")
                        else:
                            print(f"   ⚠️  {self.pi_id}: Starting without sync (timeout)")
                            
                    elif msg_type == "stop":
                        print(f"[{timestamp}] 🛑 {self.pi_id}: Received STOP command")
                        
                    elif msg_type == "update_schedule":
                        schedule_count = len(msg.get("schedule", []))
                        print(f"[{timestamp}] 📝 {self.pi_id}: Schedule updated ({schedule_count} cues)")
                        
                except socket.timeout:
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"❌ {self.pi_id} command error: {e}")
                        
        except Exception as e:
            print(f"❌ {self.pi_id} failed to setup command listener: {e}")
            
    def _send_registration(self):
        """Send registration to leader"""
        registration = {
            "type": "register",
            "pi_id": self.pi_id,
            "status": "ready",
            "video_file": "test_video.mp4"
        }
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(
                json.dumps(registration).encode(),
                ("255.255.255.255", self.control_port)
            )
            sock.close()
            print(f"📝 {self.pi_id}: Registered with leader")
        except Exception as e:
            print(f"❌ {self.pi_id} registration failed: {e}")
            
    def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self.running:
            try:
                heartbeat = {
                    "type": "heartbeat",
                    "pi_id": self.pi_id,
                    "status": "ready"
                }
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(
                    json.dumps(heartbeat).encode(),
                    ("255.255.255.255", self.control_port)
                )
                sock.close()
                
                time.sleep(2)  # Heartbeat every 2 seconds
                
            except Exception as e:
                if self.running:
                    print(f"❌ {self.pi_id} heartbeat error: {e}")
                time.sleep(2)
                
    def _status_updates(self):
        """Show periodic status updates"""
        while self.running:
            try:
                time.sleep(10)  # Update every 10 seconds
                if self.running:
                    sync_status = "✅ SYNCED" if self.synced else "❌ NO SYNC"
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] 📊 {self.pi_id}: {sync_status}, Syncs received: {self.sync_count}, Leader time: {self.leader_time:.1f}s")
                    
            except Exception as e:
                if self.running:
                    print(f"❌ {self.pi_id} status error: {e}")


def main():
    parser = argparse.ArgumentParser(description="KitchenSync Network Testing Tool")
    parser.add_argument("mode", choices=["monitor", "simulate"], 
                       help="monitor: Watch network traffic, simulate: Act as collaborator")
    parser.add_argument("--pi-id", default="test-pi", 
                       help="Pi ID for simulation mode (default: test-pi)")
    parser.add_argument("--sync-port", type=int, default=5005,
                       help="Sync port (default: 5005)")
    parser.add_argument("--control-port", type=int, default=5006,
                       help="Control port (default: 5006)")
    
    args = parser.parse_args()
    
    try:
        if args.mode == "monitor":
            monitor = SyncMonitor(args.sync_port, args.control_port)
            monitor.start_monitoring()
        elif args.mode == "simulate":
            simulator = CollaboratorSimulator(args.pi_id, args.sync_port, args.control_port)
            simulator.start_simulation()
            
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()