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
import os
import glob
import subprocess
from pathlib import Path

# VLC video player support
try:
    import vlc
    VLC_PYTHON_AVAILABLE = True
except ImportError:
    VLC_PYTHON_AVAILABLE = False

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
        
        # Debug configuration
        self.debug_mode = False
        self.load_leader_config()
        
        # System state
        self.start_time = None
        self.is_running = False
        self.collaborator_pis = {}  # Track connected Pis
        self.system_schedule = self.load_schedule()
        
        # Debug state for MIDI history
        self.midi_history = []  # List of recent MIDI events
        self.upcoming_midi = []  # Upcoming MIDI events
        
        # Video player state
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self.video_path = None
        
        # Initialize sockets
        self._setup_sockets()
        
        # Initialize video player
        self._setup_video_player()
    
    def load_leader_config(self):
        """Load leader configuration including debug mode"""
        import configparser
        
        # Try to load from USB drive first (same as collaborator pattern)
        usb_config_path = None
        try:
            mount_result = subprocess.run(['mount'], capture_output=True, text=True)
            if mount_result.returncode == 0:
                for line in mount_result.stdout.split('\n'):
                    if '/media/' in line and ('usb' in line.lower() or 'sd' in line or 'mmc' in line):
                        parts = line.split(' on ')
                        if len(parts) >= 2:
                            mount_point = parts[1].split(' type ')[0]
                            if os.path.exists(mount_point) and os.path.isdir(mount_point):
                                config_path = os.path.join(mount_point, 'kitchensync.ini')
                                if os.path.exists(config_path):
                                    usb_config_path = config_path
                                    break
        except Exception as e:
            print(f"Error checking USB drives for config: {e}")
        
        # Load configuration
        config = configparser.ConfigParser()
        if usb_config_path:
            config.read(usb_config_path)
            print(f"✓ Loaded leader config from USB: {usb_config_path}")
        elif os.path.exists('leader_config.ini'):
            config.read('leader_config.ini')
            print("✓ Loaded leader config from leader_config.ini")
        else:
            # Create default leader config
            config['KITCHENSYNC'] = {
                'is_leader': 'true',
                'debug': 'false',
                'pi_id': 'leader-pi'
            }
            with open('leader_config.ini', 'w') as f:
                config.write(f)
            print("✓ Created default leader config")
        
        # Parse debug setting
        if 'KITCHENSYNC' in config:
            self.debug_mode = config.getboolean('KITCHENSYNC', 'debug', fallback=False)
            print(f"✓ Debug mode: {'ENABLED' if self.debug_mode else 'DISABLED'}")
        else:
            self.debug_mode = False
    
    def _setup_video_player(self):
        """Initialize video player and find video file"""
        try:
            # Find video file from USB drive
            self.video_path = self._find_video_file()
            if self.video_path:
                print(f"🎬 Found video: {self.video_path}")
            else:
                print("⚠️ No video file found")
        except Exception as e:
            print(f"Error setting up video player: {e}")
    
    def _find_video_file(self):
        """Find video file on USB drives or local directory"""
        # Check USB drives first
        mount_result = subprocess.run(['mount'], capture_output=True, text=True)
        if mount_result.returncode == 0:
            for line in mount_result.stdout.split('\n'):
                if '/media/' in line:
                    parts = line.split(' on ')
                    if len(parts) >= 2:
                        mount_point = parts[1].split(' type ')[0]
                        if os.path.exists(mount_point) and os.path.isdir(mount_point):
                            # Look for video files
                            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv']
                            for ext in video_extensions:
                                videos = glob.glob(os.path.join(mount_point, f'*{ext}'))
                                if videos:
                                    return videos[0]
        
        # Check local videos directory
        if os.path.exists('./videos'):
            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv']
            for ext in video_extensions:
                videos = glob.glob(f'./videos/*{ext}')
                if videos:
                    return videos[0]
        
        return None
    
    def _play_video(self):
        """Start video playback using VLC"""
        if not self.video_path:
            print("❌ No video file to play")
            return False
        
        print(f"🎬 Starting video playback: {self.video_path}")
        
        # Use Python VLC for programmatic control needed for drift correction
        if VLC_PYTHON_AVAILABLE:
            return self._play_with_python_vlc()
        else:
            return self._play_with_command_vlc()
    
    def _play_with_python_vlc(self):
        """Play video using VLC Python bindings"""
        try:
            # Create VLC instance for fullscreen playbook
            vlc_args = [
                '--fullscreen',
                '--no-video-title-show',
                '--no-osd',
                '--quiet',
                '--mouse-hide-timeout=0',
            ]
            
            self.vlc_instance = vlc.Instance(' '.join(vlc_args))
            if not self.vlc_instance:
                print("❌ Failed to create VLC instance")
                return False
                
            self.vlc_player = self.vlc_instance.media_player_new()
            if not self.vlc_player:
                print("❌ Failed to create VLC player")
                return False
            
            # Set fullscreen
            self.vlc_player.set_fullscreen(True)
            
            # Load and play media
            self.vlc_media = self.vlc_instance.media_new(self.video_path)
            if not self.vlc_media:
                print("❌ Failed to create VLC media")
                return False
                
            self.vlc_player.set_media(self.vlc_media)
            
            result = self.vlc_player.play()
            print(f"✅ VLC play result: {result}")
            print("🎬 Video should now be playing in fullscreen")
            
            # Wait for VLC to initialize and then trigger play again
            time.sleep(2)
            
            # Check if video is actually playing and trigger play again if needed
            state = self.vlc_player.get_state()
            print(f"📊 VLC player state: {state}")
            
            if state != vlc.State.Playing:
                print("🔄 Video not playing, triggering play again...")
                self.vlc_player.play()
                time.sleep(1)
                state = self.vlc_player.get_state()
                print(f"📊 VLC player state after retry: {state}")
            
            # Set position to start and play again to ensure it's not stuck
            self.vlc_player.set_position(0.0)
            self.vlc_player.play()
            
            return True
            
        except Exception as e:
            print(f"❌ Error with VLC Python: {e}")
            return False
    
    def _play_with_command_vlc(self):
        """Play video using VLC command line"""
        try:
            cmd = [
                'vlc',
                '--intf', 'dummy',  # No interface
                '--fullscreen',
                '--no-video-title-show',
                '--no-osd',
                '--quiet',
                '--mouse-hide-timeout=0',
                '--no-loop',
                '--start-time=0',   # Start from beginning
                self.video_path
            ]
            
            print(f"🔧 Running: {' '.join(cmd)}")
            process = subprocess.Popen(cmd)
            print(f"✅ VLC command started with PID: {process.pid}")
            
            # Give VLC a moment to start
            time.sleep(3)
            
            # Check if process is still running
            if process.poll() is None:
                print("✅ VLC process is running")
            else:
                print(f"❌ VLC process exited with code: {process.returncode}")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ Error with VLC command: {e}")
            return False
    
    def _stop_video(self):
        """Stop video playback"""
        try:
            if self.vlc_player:
                self.vlc_player.stop()
                print("🛑 Stopped VLC Python player")
            
            # Also kill any VLC processes
            subprocess.run(['pkill', 'vlc'], capture_output=True)
            print("🛑 Killed VLC processes")
        except Exception as e:
            print(f"Error stopping video: {e}")
    
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
    
    def update_midi_history(self):
        """Update MIDI history for debug display"""
        if not self.debug_mode or not self.is_running or not self.start_time:
            return
        
        current_time = time.time() - self.start_time
        
        # Find recently triggered MIDI events (last 5 seconds)
        recent_events = []
        for cue in self.system_schedule:
            cue_time = cue.get('time', 0)
            if current_time - 5 <= cue_time <= current_time:
                recent_events.append({
                    'time': cue_time,
                    'type': cue.get('type', 'unknown'),
                    'note': cue.get('note', ''),
                    'channel': cue.get('channel', ''),
                    'status': 'triggered'
                })
        
        # Find current MIDI event (within 0.5 seconds)
        current_events = []
        for cue in self.system_schedule:
            cue_time = cue.get('time', 0)
            if abs(current_time - cue_time) <= 0.5:
                current_events.append({
                    'time': cue_time,
                    'type': cue.get('type', 'unknown'),
                    'note': cue.get('note', ''),
                    'channel': cue.get('channel', ''),
                    'status': 'current'
                })
        
        # Find upcoming MIDI events (next 10 seconds)
        upcoming_events = []
        for cue in self.system_schedule:
            cue_time = cue.get('time', 0)
            if current_time < cue_time <= current_time + 10:
                upcoming_events.append({
                    'time': cue_time,
                    'type': cue.get('type', 'unknown'),
                    'note': cue.get('note', ''),
                    'channel': cue.get('channel', ''),
                    'status': 'upcoming'
                })
        
        # Update history lists (keep last 5 recent events)
        self.midi_history = sorted(recent_events, key=lambda x: x['time'])[-5:]
        self.upcoming_midi = sorted(upcoming_events, key=lambda x: x['time'])[:5]
        
        # Print debug info to console (every few seconds)
        if int(current_time) % 3 == 0:
            print(f"\n🐛 MIDI DEBUG | Time: {current_time:.1f}s")
            if current_events:
                for event in current_events:
                    print(f"🐛 ▶️  CURRENT: {event['type']} Ch:{event['channel']} Note:{event['note']} @{event['time']:.1f}s")
            if upcoming_events:
                next_event = upcoming_events[0]
                print(f"🐛 ⏭️  NEXT: {next_event['type']} Ch:{next_event['channel']} Note:{next_event['note']} @{next_event['time']:.1f}s")
    
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
                
                # Update MIDI history for debug mode
                if self.debug_mode:
                    self.update_midi_history()
                    
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
        
        # Start video playback on leader Pi
        print("🎬 Starting video playback on leader Pi...")
        self._play_video()
        
        # Start background threads
        threading.Thread(target=self.broadcast_sync, daemon=True).start()
        threading.Thread(target=self.listen_for_collaborators, daemon=True).start()
        
        # Send start command to all collaborators
        self.send_command({
            'type': 'start',
            'schedule': self.system_schedule,
            'start_time': self.start_time,
            'debug_mode': self.debug_mode  # Pass debug mode to collaborators
        })
        
        print("System started! Broadcasting time sync...")
    
    def stop_system(self):
        """Stop the synchronized playback system"""
        if not self.is_running:
            print("System is not running")
            return
            
        print("Stopping system...")
        self.is_running = False
        
        # Stop video playback on leader Pi
        print("🛑 Stopping video playback on leader Pi...")
        self._stop_video()
        
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
            if cue.get('type') == 'note_on':
                print(f"  {i+1}. Time {cue['time']}s - Note {cue['note']} ON (vel:{cue['velocity']}, ch:{cue['channel']})")
            elif cue.get('type') == 'note_off':
                print(f"  {i+1}. Time {cue['time']}s - Note {cue['note']} OFF (ch:{cue['channel']})")
            elif cue.get('type') == 'control_change':
                print(f"  {i+1}. Time {cue['time']}s - CC {cue['control']}={cue['value']} (ch:{cue['channel']})")
            else:
                print(f"  {i+1}. Time {cue['time']}s - Unknown type: {cue.get('type', 'N/A')}")
    
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
                if cue.get('type') == 'note_on':
                    print(f"  {i+1}. Time {cue['time']}s - Note {cue['note']} ON (vel:{cue['velocity']}, ch:{cue['channel']})")
                elif cue.get('type') == 'note_off':
                    print(f"  {i+1}. Time {cue['time']}s - Note {cue['note']} OFF (ch:{cue['channel']})")
                elif cue.get('type') == 'control_change':
                    print(f"  {i+1}. Time {cue['time']}s - CC {cue['control']}={cue['value']} (ch:{cue['channel']})")
                else:
                    print(f"  {i+1}. Time {cue['time']}s - Unknown type: {cue.get('type', 'N/A')}")
    
    def _add_schedule_cue(self):
        """Add a new cue to the schedule"""
        try:
            time_val = float(input("Enter time (seconds): "))
            
            print("\nMIDI Event Types:")
            print("  1. Note On")
            print("  2. Note Off") 
            print("  3. Control Change")
            event_type = input("Select event type (1-3): ").strip()
            
            if event_type == '1':
                note = int(input("Enter MIDI note (0-127): "))
                velocity = int(input("Enter velocity (0-127): "))
                channel = int(input("Enter MIDI channel (1-16): "))
                if not (0 <= note <= 127 and 0 <= velocity <= 127 and 1 <= channel <= 16):
                    print("Invalid MIDI values")
                    return
                cue = {"time": time_val, "note": note, "velocity": velocity, "channel": channel, "type": "note_on"}
                
            elif event_type == '2':
                note = int(input("Enter MIDI note (0-127): "))
                channel = int(input("Enter MIDI channel (1-16): "))
                if not (0 <= note <= 127 and 1 <= channel <= 16):
                    print("Invalid MIDI values")
                    return
                cue = {"time": time_val, "note": note, "velocity": 0, "channel": channel, "type": "note_off"}
                
            elif event_type == '3':
                control = int(input("Enter control number (0-127): "))
                value = int(input("Enter control value (0-127): "))
                channel = int(input("Enter MIDI channel (1-16): "))
                if not (0 <= control <= 127 and 0 <= value <= 127 and 1 <= channel <= 16):
                    print("Invalid MIDI values")
                    return
                cue = {"time": time_val, "control": control, "value": value, "channel": channel, "type": "control_change"}
                
            else:
                print("Invalid event type")
                return
                
            self.system_schedule.append(cue)
            self.system_schedule.sort(key=lambda x: x['time'])
            print(f"Added MIDI cue at {time_val}s")
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
                cue_desc = f"MIDI {removed.get('type', 'unknown')} at {removed['time']}s"
                print(f"Removed cue: {cue_desc}")
                self._print_schedule()
            else:
                print("Invalid cue number")
        except (IndexError, ValueError):
            print("Usage: remove <number>")

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='KitchenSync Leader Pi')
    parser.add_argument('--auto', action='store_true', help='Start automatically without interactive interface')
    args = parser.parse_args()
    
    try:
        leader = KitchenSyncLeader()
        
        if args.auto:
            print("🎯 Leader Pi starting in automatic mode...")
            print("System will auto-start playback and run continuously.")
            print("Press Ctrl+C to stop.\n")
            
            # Auto-start the system
            leader.start_system()
            
            # Keep running until interrupted
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Stopping system...")
                leader.stop_system()
        else:
            leader.user_interface()
            
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
