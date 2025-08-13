#!/usr/bin/env python3
"""
KitchenSync Network Sync Test Script

This script tests the network synchronization functionality by:
1. Monitoring sync broadcasts from the leader Pi
2. Simulating a collaborator Pi for testing
3. Providing network diagnostics and timing analysis

Usage:
  python3 test_network_sync.py --monitor    # Monitor leader broadcasts
  python3 test_network_sync.py --simulate   # Simulate a collaborator
  python3 test_network_sync.py --both       # Run both monitor and simulator
"""

import argparse
import json
import socket
import threading
import time
from collections import deque
from typing import Optional, Dict, Any
import statistics


class SyncMonitor:
    """Monitors sync broadcasts from leader Pi"""
    
    def __init__(self, sync_port: int = 5005):
        self.sync_port = sync_port
        self.is_running = False
        self.sync_sock = None
        self.stats = {
            'packets_received': 0,
            'last_packet_time': None,
            'leader_id': None,
            'timing_intervals': deque(maxlen=50),
            'sync_times': deque(maxlen=10),
            'start_time': time.time()
        }
    
    def start_monitoring(self) -> None:
        """Start monitoring sync broadcasts"""
        print("🔍 Starting sync broadcast monitor...")
        print(f"   Listening on UDP port {self.sync_port}")
        print("   Press Ctrl+C to stop\n")
        
        try:
            self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sync_sock.bind(("", self.sync_port))
            self.sync_sock.settimeout(1.0)
            self.is_running = True
            
            last_packet_time = None
            
            while self.is_running:
                try:
                    data, addr = self.sync_sock.recvfrom(1024)
                    current_time = time.time()
                    
                    try:
                        msg = json.loads(data.decode())
                        
                        if msg.get("type") == "sync":
                            self.stats['packets_received'] += 1
                            self.stats['last_packet_time'] = current_time
                            self.stats['leader_id'] = msg.get('leader_id', 'unknown')
                            
                            leader_time = msg.get('time', 0)
                            self.stats['sync_times'].append(leader_time)
                            
                            # Calculate timing interval
                            if last_packet_time:
                                interval = current_time - last_packet_time
                                self.stats['timing_intervals'].append(interval)
                            
                            last_packet_time = current_time
                            
                            # Print status every 10 packets
                            if self.stats['packets_received'] % 10 == 0:
                                self._print_status(addr[0], leader_time)
                    
                    except json.JSONDecodeError:
                        print(f"⚠️  Invalid JSON from {addr[0]}")
                
                except socket.timeout:
                    # Check for timeout (no packets received)
                    if (self.stats['last_packet_time'] and 
                        time.time() - self.stats['last_packet_time'] > 5.0):
                        print("⚠️  No sync packets received for 5+ seconds")
                        self.stats['last_packet_time'] = None
                
                except Exception as e:
                    print(f"❌ Monitor error: {e}")
                    break
        
        except Exception as e:
            print(f"❌ Failed to start monitor: {e}")
        finally:
            self._cleanup()
    
    def _print_status(self, leader_ip: str, leader_time: float) -> None:
        """Print current sync status"""
        uptime = time.time() - self.stats['start_time']
        
        # Calculate timing statistics
        avg_interval = 0.0
        jitter = 0.0
        if len(self.stats['timing_intervals']) > 1:
            intervals = list(self.stats['timing_intervals'])
            avg_interval = statistics.mean(intervals)
            jitter = statistics.stdev(intervals) if len(intervals) > 1 else 0.0
        
        print(f"📡 Sync Status (uptime: {uptime:.1f}s)")
        print(f"   Leader: {self.stats['leader_id']} @ {leader_ip}")
        print(f"   Packets: {self.stats['packets_received']}")
        print(f"   Leader time: {leader_time:.3f}s")
        print(f"   Avg interval: {avg_interval*1000:.1f}ms (target: 100ms)")
        print(f"   Jitter: {jitter*1000:.2f}ms")
        print("   " + "-" * 40)
    
    def stop_monitoring(self) -> None:
        """Stop monitoring"""
        self.is_running = False
    
    def _cleanup(self) -> None:
        """Clean up resources"""
        if self.sync_sock:
            try:
                self.sync_sock.close()
            except:
                pass
        print("\n📊 Final Statistics:")
        print(f"   Total packets: {self.stats['packets_received']}")
        if self.stats['timing_intervals']:
            intervals = list(self.stats['timing_intervals'])
            print(f"   Avg interval: {statistics.mean(intervals)*1000:.1f}ms")
            print(f"   Min interval: {min(intervals)*1000:.1f}ms")
            print(f"   Max interval: {max(intervals)*1000:.1f}ms")


class CollaboratorSimulator:
    """Simulates a collaborator Pi for testing"""
    
    def __init__(self, sync_port: int = 5005, control_port: int = 5006, pi_id: str = "test-collaborator"):
        self.sync_port = sync_port
        self.control_port = control_port
        self.pi_id = pi_id
        self.is_running = False
        self.sync_sock = None
        self.control_sock = None
        
        self.stats = {
            'sync_packets': 0,
            'last_sync_time': None,
            'leader_time_offset': None,
            'sync_history': deque(maxlen=20),
            'registered': False,
            'heartbeat_count': 0
        }
    
    def start_simulation(self) -> None:
        """Start simulating a collaborator"""
        print(f"🤖 Starting collaborator simulator: {self.pi_id}")
        print(f"   Sync port: {self.sync_port}")
        print(f"   Control port: {self.control_port}")
        print("   Press Ctrl+C to stop\n")
        
        self.is_running = True
        
        # Start sync listener
        sync_thread = threading.Thread(target=self._sync_listener, daemon=True)
        sync_thread.start()
        
        # Start command listener  
        command_thread = threading.Thread(target=self._command_listener, daemon=True)
        command_thread.start()
        
        # Start heartbeat sender
        heartbeat_thread = threading.Thread(target=self._heartbeat_sender, daemon=True)
        heartbeat_thread.start()
        
        # Send initial registration
        self._send_registration()
        
        # Main status loop
        try:
            while self.is_running:
                time.sleep(5)
                self._print_status()
        except KeyboardInterrupt:
            print("\n🛑 Stopping simulator...")
        finally:
            self.stop_simulation()
    
    def _sync_listener(self) -> None:
        """Listen for sync broadcasts"""
        try:
            self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sync_sock.bind(("", self.sync_port))
            self.sync_sock.settimeout(1.0)
            
            while self.is_running:
                try:
                    data, addr = self.sync_sock.recvfrom(1024)
                    local_time = time.time()
                    
                    try:
                        msg = json.loads(data.decode())
                        
                        if msg.get("type") == "sync":
                            leader_time = msg.get('time', 0)
                            self.stats['sync_packets'] += 1
                            self.stats['last_sync_time'] = local_time
                            
                            # Calculate time offset
                            self.stats['leader_time_offset'] = leader_time
                            
                            # Store sync history for analysis
                            self.stats['sync_history'].append({
                                'local_time': local_time,
                                'leader_time': leader_time,
                                'leader_id': msg.get('leader_id', 'unknown')
                            })
                    
                    except json.JSONDecodeError:
                        pass
                
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.is_running:
                        print(f"⚠️  Sync listener error: {e}")
        
        except Exception as e:
            print(f"❌ Failed to start sync listener: {e}")
    
    def _command_listener(self) -> None:
        """Listen for commands from leader"""
        try:
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_sock.bind(("", self.control_port))
            self.control_sock.settimeout(1.0)
            
            while self.is_running:
                try:
                    data, addr = self.control_sock.recvfrom(1024)
                    
                    try:
                        msg = json.loads(data.decode())
                        msg_type = msg.get("type")
                        
                        if msg_type == "start":
                            print(f"📥 Received START command from {addr[0]}")
                            schedule = msg.get("schedule", [])
                            print(f"   Schedule has {len(schedule)} cues")
                        
                        elif msg_type == "stop":
                            print(f"📥 Received STOP command from {addr[0]}")
                        
                        else:
                            print(f"📥 Received {msg_type} command from {addr[0]}")
                    
                    except json.JSONDecodeError:
                        pass
                
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.is_running:
                        print(f"⚠️  Command listener error: {e}")
        
        except Exception as e:
            print(f"❌ Failed to start command listener: {e}")
    
    def _send_registration(self) -> None:
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
            self.stats['registered'] = True
            print(f"📤 Sent registration as '{self.pi_id}'")
        except Exception as e:
            print(f"❌ Failed to send registration: {e}")
    
    def _heartbeat_sender(self) -> None:
        """Send periodic heartbeats"""
        while self.is_running:
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
                
                self.stats['heartbeat_count'] += 1
                time.sleep(2)  # Send heartbeat every 2 seconds
                
            except Exception as e:
                if self.is_running:
                    print(f"⚠️  Heartbeat error: {e}")
                time.sleep(2)
    
    def _print_status(self) -> None:
        """Print current status"""
        sync_active = (self.stats['last_sync_time'] and 
                      time.time() - self.stats['last_sync_time'] < 5.0)
        
        print(f"🤖 Collaborator Status: {self.pi_id}")
        print(f"   Registered: {'✅' if self.stats['registered'] else '❌'}")
        print(f"   Sync active: {'✅' if sync_active else '❌'}")
        print(f"   Sync packets: {self.stats['sync_packets']}")
        print(f"   Heartbeats sent: {self.stats['heartbeat_count']}")
        
        if self.stats['leader_time_offset'] is not None:
            print(f"   Leader time: {self.stats['leader_time_offset']:.3f}s")
        
        print("   " + "-" * 40)
    
    def stop_simulation(self) -> None:
        """Stop simulation"""
        self.is_running = False
        
        if self.sync_sock:
            try:
                self.sync_sock.close()
            except:
                pass
        
        if self.control_sock:
            try:
                self.control_sock.close()
            except:
                pass


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="KitchenSync Network Sync Test")
    parser.add_argument("--monitor", action="store_true", 
                       help="Monitor sync broadcasts from leader")
    parser.add_argument("--simulate", action="store_true",
                       help="Simulate a collaborator Pi")
    parser.add_argument("--both", action="store_true",
                       help="Run both monitor and simulator")
    parser.add_argument("--sync-port", type=int, default=5005,
                       help="Sync port (default: 5005)")
    parser.add_argument("--control-port", type=int, default=5006,
                       help="Control port (default: 5006)")
    parser.add_argument("--pi-id", default="test-collaborator",
                       help="Pi ID for simulator (default: test-collaborator)")
    
    args = parser.parse_args()
    
    if not any([args.monitor, args.simulate, args.both]):
        parser.print_help()
        print("\n❌ Please specify --monitor, --simulate, or --both")
        return
    
    print("🎯 KitchenSync Network Sync Test")
    print("=" * 50)
    
    try:
        if args.both:
            # Run both monitor and simulator
            print("🚀 Starting both monitor and simulator...\n")
            
            monitor = SyncMonitor(args.sync_port)
            simulator = CollaboratorSimulator(args.sync_port, args.control_port, args.pi_id)
            
            # Start monitor in separate thread
            monitor_thread = threading.Thread(target=monitor.start_monitoring, daemon=True)
            monitor_thread.start()
            
            # Start simulator in main thread
            simulator.start_simulation()
            
        elif args.monitor:
            # Monitor only
            monitor = SyncMonitor(args.sync_port)
            monitor.start_monitoring()
            
        elif args.simulate:
            # Simulate only
            simulator = CollaboratorSimulator(args.sync_port, args.control_port, args.pi_id)
            simulator.start_simulation()
    
    except KeyboardInterrupt:
        print("\n👋 Test completed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")


if __name__ == "__main__":
    main()

