#!/usr/bin/env python3
"""
KitchenSync Leader Pi
Broadcasts time sync and provides user interface for system control
"""

import socket
import time
import json
import threading
import os
import sys
from pathlib import Path

class KitchenSyncLeader:
    def __init__(self):
        self.BROADCAST_IP = '255.255.255.255'
        self.SYNC_PORT = 5005
        self.CONTROL_PORT = 5006
        self.TICK_INTERVAL = 0.1  # seconds
        
        # System state
        self.start_time = None
        self.is_running = False
        self.collaborator_pis = {}  # Track connected Pis
        self.system_schedule = self.load_schedule()
        
        # Sockets
        self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sync_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.control_sock.bind(('', self.CONTROL_PORT))
        
    def load_schedule(self):
        """Load schedule from JSON file"""
        try:
            with open('schedule.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print("schedule.json not found, using empty schedule")
            return []
        except json.JSONDecodeError:
            print("Error parsing schedule.json")
            return []
    
    def save_schedule(self):
        """Save current schedule to JSON file"""
        with open('schedule.json', 'w') as f:
            json.dump(self.system_schedule, f, indent=2)
    
    def broadcast_sync(self):
        """Continuously broadcast time sync"""
        while self.is_running:
            if self.start_time:
                now = time.time() - self.start_time
                payload = json.dumps({
                    'type': 'sync',
                    'time': now,
                    'leader_id': 'leader-001'
                })
                try:
                    self.sync_sock.sendto(payload.encode(), (self.BROADCAST_IP, self.SYNC_PORT))
                except Exception as e:
                    print(f"Error broadcasting sync: {e}")
            time.sleep(self.TICK_INTERVAL)
    
    def listen_for_collaborators(self):
        """Listen for messages from collaborator Pis"""
        while self.is_running:
            try:
                data, addr = self.control_sock.recvfrom(1024)
                msg = json.loads(data.decode())
                
                if msg.get('type') == 'register':
                    pi_id = msg.get('pi_id')
                    if pi_id:
                        self.collaborator_pis[pi_id] = {
                            'ip': addr[0],
                            'last_seen': time.time(),
                            'status': msg.get('status', 'unknown')
                        }
                        print(f"Registered Pi: {pi_id} at {addr[0]}")
                        
                elif msg.get('type') == 'heartbeat':
                    pi_id = msg.get('pi_id')
                    if pi_id in self.collaborator_pis:
                        self.collaborator_pis[pi_id]['last_seen'] = time.time()
                        
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Error in collaborator listener: {e}")
    
    def send_command(self, command, target_pi=None):
        """Send command to collaborator Pi(s)"""
        payload = json.dumps(command)
        
        if target_pi and target_pi in self.collaborator_pis:
            # Send to specific Pi
            ip = self.collaborator_pis[target_pi]['ip']
            try:
                self.control_sock.sendto(payload.encode(), (ip, self.CONTROL_PORT))
                print(f"Sent command to {target_pi}: {command['type']}")
            except Exception as e:
                print(f"Error sending command to {target_pi}: {e}")
        else:
            # Broadcast to all Pis
            try:
                self.control_sock.sendto(payload.encode(), (self.BROADCAST_IP, self.CONTROL_PORT))
                print(f"Broadcast command: {command['type']}")
            except Exception as e:
                print(f"Error broadcasting command: {e}")
    
    def start_system(self):
        """Start the synchronized playback system"""
        if self.is_running:
            print("System is already running")
            return
            
        self.start_time = time.time()
        self.is_running = True
        
        # Start background threads
        threading.Thread(target=self.broadcast_sync, daemon=True).start()
        threading.Thread(target=self.listen_for_collaborators, daemon=True).start()
        
        # Send start command to all collaborators
        self.send_command({
            'type': 'start',
            'schedule': self.system_schedule,
            'start_time': self.start_time
        })
        
        print("System started! Broadcasting time sync...")
    
    def stop_system(self):
        """Stop the synchronized playback system"""
        if not self.is_running:
            print("System is not running")
            return
            
        self.is_running = False
        self.start_time = None
        
        # Send stop command to all collaborators
        self.send_command({'type': 'stop'})
        
        print("System stopped")
    
    def show_status(self):
        """Display system status"""
        print("\n=== KitchenSync Leader Status ===")
        print(f"System running: {self.is_running}")
        if self.start_time:
            elapsed = time.time() - self.start_time
            print(f"Elapsed time: {elapsed:.2f} seconds")
        
        print(f"\nConnected Collaborator Pis: {len(self.collaborator_pis)}")
        for pi_id, info in self.collaborator_pis.items():
            last_seen = time.time() - info['last_seen']
            status = "ONLINE" if last_seen < 5 else "OFFLINE"
            print(f"  {pi_id}: {info['ip']} - {status} (last seen {last_seen:.1f}s ago)")
        
        print(f"\nSchedule: {len(self.system_schedule)} cues")
        for i, cue in enumerate(self.system_schedule):
            print(f"  {i+1}. Time {cue['time']}s - Relay {cue['relay']}")
    
    def user_interface(self):
        """Simple command-line interface"""
        print("\n=== KitchenSync Leader Control ===")
        print("Commands:")
        print("  start - Start synchronized playback")
        print("  stop - Stop playback")
        print("  status - Show system status")
        print("  schedule - Edit schedule")
        print("  quit - Exit program")
        
        while True:
            try:
                cmd = input("\nkitchensync> ").strip().lower()
                
                if cmd == 'start':
                    self.start_system()
                elif cmd == 'stop':
                    self.stop_system()
                elif cmd == 'status':
                    self.show_status()
                elif cmd == 'schedule':
                    self.edit_schedule()
                elif cmd in ['quit', 'exit', 'q']:
                    if self.is_running:
                        self.stop_system()
                    print("Goodbye!")
                    break
                elif cmd == 'help':
                    self.user_interface()
                else:
                    print("Unknown command. Type 'help' for available commands.")
                    
            except KeyboardInterrupt:
                if self.is_running:
                    self.stop_system()
                print("\nGoodbye!")
                break
    
    def edit_schedule(self):
        """Simple schedule editor"""
        print("\n=== Schedule Editor ===")
        print("Current schedule:")
        for i, cue in enumerate(self.system_schedule):
            print(f"  {i+1}. Time {cue['time']}s - Relay {cue['relay']}")
        
        print("\nOptions:")
        print("  add - Add new cue")
        print("  remove <number> - Remove cue")
        print("  clear - Clear all cues")
        print("  save - Save and return")
        
        while True:
            cmd = input("schedule> ").strip().lower()
            
            if cmd == 'add':
                try:
                    time_val = float(input("Enter time (seconds): "))
                    relay_val = int(input("Enter relay state (0 or 1): "))
                    if relay_val not in [0, 1]:
                        print("Relay state must be 0 or 1")
                        continue
                    self.system_schedule.append({"time": time_val, "relay": relay_val})
                    self.system_schedule.sort(key=lambda x: x['time'])
                    print(f"Added cue: {time_val}s -> relay {relay_val}")
                except ValueError:
                    print("Invalid input")
                    
            elif cmd.startswith('remove '):
                try:
                    num = int(cmd.split()[1]) - 1
                    if 0 <= num < len(self.system_schedule):
                        removed = self.system_schedule.pop(num)
                        print(f"Removed cue: {removed['time']}s -> relay {removed['relay']}")
                    else:
                        print("Invalid cue number")
                except (IndexError, ValueError):
                    print("Usage: remove <number>")
                    
            elif cmd == 'clear':
                self.system_schedule.clear()
                print("Schedule cleared")
                
            elif cmd == 'save':
                self.save_schedule()
                print("Schedule saved")
                break
                
            else:
                print("Unknown command")

def main():
    leader = KitchenSyncLeader()
    leader.user_interface()

if __name__ == "__main__":
    main()
