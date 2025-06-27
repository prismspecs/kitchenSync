#!/usr/bin/env python3
"""
KitchenSync Leader Pi
Broadcasts time sync and provides user interface for system control
"""

import json
import socket
import sys
import threading
import time
from pathlib import Path

class KitchenSyncLeader:
    """
    Leader Pi that orchestrates synchronized playback across multiple collaborator Pis.
    Handles time sync broadcasting, command distribution, and user interface.
    """
    
    def __init__(self):
        # Network configuration
        self.BROADCAST_IP = '255.255.255.255'
        self.SYNC_PORT = 5005
        self.CONTROL_PORT = 5006
        self.TICK_INTERVAL = 0.1  # seconds
        
        # System state
        self.start_time = None
        self.is_running = False
        self.collaborator_pis = {}  # Track connected Pis
        self.system_schedule = self.load_schedule()
        
        # Initialize sockets
        self._setup_sockets()
    
    def _setup_sockets(self):
        """Initialize UDP sockets for sync and control communication"""
        try:
            # Sync socket for broadcasting time sync
            self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sync_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # Control socket for commands and responses
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_sock.bind(('', self.CONTROL_PORT))
            self.control_sock.settimeout(1.0)  # Add timeout for non-blocking operations
            
        except Exception as e:
            print(f"Error setting up sockets: {e}")
            sys.exit(1)
    
    def cleanup(self):
        """Clean up resources"""
        try:
            if hasattr(self, 'sync_sock'):
                self.sync_sock.close()
            if hasattr(self, 'control_sock'):
                self.control_sock.close()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        
    def load_schedule(self):
        """Load schedule from JSON file"""
        schedule_file = Path('schedule.json')
        try:
            if schedule_file.exists():
                with open(schedule_file, 'r') as f:
                    return json.load(f)
            else:
                print("schedule.json not found, using empty schedule")
                return []
        except json.JSONDecodeError as e:
            print(f"Error parsing schedule.json: {e}")
            return []
        except Exception as e:
            print(f"Error loading schedule: {e}")
            return []
    
    def save_schedule(self):
        """Save current schedule to JSON file"""
        try:
            with open('schedule.json', 'w') as f:
                json.dump(self.system_schedule, f, indent=2)
            print("Schedule saved successfully")
        except Exception as e:
            print(f"Error saving schedule: {e}")
    
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
                        
            except socket.timeout:
                # Expected timeout, continue loop
                continue
            except json.JSONDecodeError:
                print("Received invalid JSON from collaborator")
                continue
            except Exception as e:
                if self.is_running:  # Only log if we're supposed to be running
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
            
        print("Stopping system...")
        self.is_running = False
        
        # Send stop command to all collaborators
        self.send_command({'type': 'stop'})
        
        # Reset system state
        self.start_time = None
        
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
        print("  start    - Start synchronized playback")
        print("  stop     - Stop playback")
        print("  status   - Show system status")
        print("  schedule - Edit schedule")
        print("  quit     - Exit program")
        
        try:
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
                        break
                    elif cmd == 'help':
                        # Re-show the help text
                        print("Commands:")
                        print("  start    - Start synchronized playback")
                        print("  stop     - Stop playback")
                        print("  status   - Show system status")
                        print("  schedule - Edit schedule")
                        print("  quit     - Exit program")
                    else:
                        print("Unknown command. Type 'help' for available commands.")
                        
                except EOFError:
                    break
                    
        except KeyboardInterrupt:
            pass
        finally:
            if self.is_running:
                self.stop_system()
            self.cleanup()
            print("\nGoodbye!")
    
    def edit_schedule(self):
        """Simple schedule editor"""
        print("\n=== Schedule Editor ===")
        self._print_schedule()
        
        print("\nOptions:")
        print("  add             - Add new cue")
        print("  remove <number> - Remove cue")
        print("  clear           - Clear all cues")
        print("  save            - Save and return")
        
        while True:
            try:
                cmd = input("schedule> ").strip().lower()
                
                if cmd == 'add':
                    self._add_schedule_cue()
                elif cmd.startswith('remove '):
                    self._remove_schedule_cue(cmd)
                elif cmd == 'clear':
                    self.system_schedule.clear()
                    print("Schedule cleared")
                    self._print_schedule()
                elif cmd == 'save':
                    self.save_schedule()
                    break
                elif cmd == 'help':
                    print("\nOptions:")
                    print("  add             - Add new cue")
                    print("  remove <number> - Remove cue") 
                    print("  clear           - Clear all cues")
                    print("  save            - Save and return")
                else:
                    print("Unknown command. Type 'help' for options.")
            except (KeyboardInterrupt, EOFError):
                break
    
    def _print_schedule(self):
        """Print the current schedule"""
        if not self.system_schedule:
            print("  (empty)")
        else:
            for i, cue in enumerate(self.system_schedule):
                print(f"  {i+1}. Time {cue['time']}s - Relay {cue['relay']}")
    
    def _add_schedule_cue(self):
        """Add a new cue to the schedule"""
        try:
            time_val = float(input("Enter time (seconds): "))
            relay_val = int(input("Enter relay state (0 or 1): "))
            if relay_val not in [0, 1]:
                print("Relay state must be 0 or 1")
                return
            self.system_schedule.append({"time": time_val, "relay": relay_val})
            self.system_schedule.sort(key=lambda x: x['time'])
            print(f"Added cue: {time_val}s -> relay {relay_val}")
            self._print_schedule()
        except ValueError:
            print("Invalid input. Please enter numeric values.")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled")
    
    def _remove_schedule_cue(self, cmd):
        """Remove a cue from the schedule"""
        try:
            num = int(cmd.split()[1]) - 1
            if 0 <= num < len(self.system_schedule):
                removed = self.system_schedule.pop(num)
                print(f"Removed cue: {removed['time']}s -> relay {removed['relay']}")
                self._print_schedule()
            else:
                print("Invalid cue number")
        except (IndexError, ValueError):
            print("Usage: remove <number>")

def main():
    """Main entry point"""
    try:
        leader = KitchenSyncLeader()
        leader.user_interface()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
