#!/usr/bin/env python3
"""
KitchenSync Collaborator Pi
Receives time sync and commands from leader, plays videos and outputs MIDI data
"""

import configparser
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread

# Try to import rtmidi, fall back to simulation if not available
try:
    import rtmidi
    MIDI_AVAILABLE = True
except ImportError:
    print("python-rtmidi not available, using simulation mode")
    MIDI_AVAILABLE = False
    
    class MockMidiOut:
        def open_port(self, port=0): 
            print(f"MIDI: Opened mock port {port}")
        def send_message(self, message): 
            print(f"MIDI: {message}")
        def close_port(self): 
            print("MIDI: Closed mock port")
        def get_port_count(self): 
            return 1
        def get_port_name(self, port): 
            return f"Mock MIDI Port {port}"

class KitchenSyncCollaborator:
    def __init__(self, config_file='collaborator_config.ini'):
        # Load configuration
        self.config = self.load_config(config_file)
        
        # Network settings
        self.SYNC_PORT = 5005
        self.CONTROL_PORT = 5006
        
        # Pi identification
        self.pi_id = self.config.get('pi_id', f'pi-{int(time.time()) % 1000:03d}')
        
        # Video settings
        self.video_file = self.config.get('video_file', 'video.mp4')
        self.video_sources = self.config.get('video_sources', ['./videos/', '/media/usb/'])
        
        # MIDI settings
        self.midi_port = int(self.config.get('midi_port', 0))
        
        # System state
        self.synced_start = None
        self.last_sync_received = 0
        self.is_running = False
        self.video_process = None
        self.schedule = []
        self.triggered_cues = set()
        
        # Setup MIDI
        self.setup_midi()
        
        # Setup sockets
        self.sync_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sync_sock.bind(('', self.SYNC_PORT))
        
        self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.control_sock.bind(('', self.CONTROL_PORT))
        
        print(f"KitchenSync Collaborator '{self.pi_id}' initialized")
        print(f"Video file: {self.video_file}")
        print(f"MIDI port: {self.midi_port}")
    
    def setup_midi(self):
        """Initialize MIDI output"""
        if MIDI_AVAILABLE:
            try:
                self.midi_out = rtmidi.MidiOut()
                available_ports = self.midi_out.get_port_count()
                
                if available_ports == 0:
                    print("No MIDI ports available, creating virtual port")
                    self.midi_out.open_virtual_port("KitchenSync")
                elif self.midi_port < available_ports:
                    port_name = self.midi_out.get_port_name(self.midi_port)
                    self.midi_out.open_port(self.midi_port)
                    print(f"Connected to MIDI port {self.midi_port}: {port_name}")
                else:
                    print(f"MIDI port {self.midi_port} not available, using port 0")
                    port_name = self.midi_out.get_port_name(0)
                    self.midi_out.open_port(0)
                    print(f"Connected to MIDI port 0: {port_name}")
                    
            except Exception as e:
                print(f"Error setting up MIDI: {e}")
                print("Falling back to simulation mode")
                self.midi_out = MockMidiOut()
        else:
            self.midi_out = MockMidiOut()
            self.midi_out.open_port(self.midi_port)
    
    def load_config(self, config_file):
        """Load configuration from file or create default"""
        config = configparser.ConfigParser()
        
        if os.path.exists(config_file):
            config.read(config_file)
            settings = dict(config['DEFAULT']) if 'DEFAULT' in config else {}
        else:
            # Create default config
            settings = {
                'pi_id': f'pi-{int(time.time()) % 1000:03d}',
                'video_file': 'video.mp4',
                'midi_port': '0'
            }
            
            config['DEFAULT'] = settings
            with open(config_file, 'w') as f:
                config.write(f)
            print(f"Created default config file: {config_file}")
        
        # Convert numeric values
        if 'midi_port' in settings:
            settings['midi_port'] = int(settings['midi_port'])
        
        return settings
    
    def find_video_file(self):
        """Find video file in configured locations"""
        # Check current directory first
        if os.path.exists(self.video_file):
            return self.video_file
        
        # Check video source directories
        for source_dir in self.video_sources:
            video_path = os.path.join(source_dir, self.video_file)
            if os.path.exists(video_path):
                return video_path
        
        # Look for any video files if specified file not found
        for source_dir in self.video_sources:
            if os.path.exists(source_dir):
                for ext in ['.mp4', '.avi', '.mkv', '.mov']:
                    for file in os.listdir(source_dir):
                        if file.lower().endswith(ext):
                            print(f"Found alternative video: {file}")
                            return os.path.join(source_dir, file)
        
        return None
    
    def listen_sync(self):
        """Listen for time sync broadcasts from leader"""
        while True:
            try:
                data, addr = self.sync_sock.recvfrom(1024)
                msg = json.loads(data.decode())
                
                if msg.get('type') == 'sync':
                    now = time.time()
                    leader_time = msg['time']
                    self.synced_start = now - leader_time
                    self.last_sync_received = now
                    
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Error in sync listener: {e}")
    
    def listen_commands(self):
        """Listen for commands from leader"""
        while True:
            try:
                data, addr = self.control_sock.recvfrom(1024)
                msg = json.loads(data.decode())
                
                if msg.get('type') == 'start':
                    self.handle_start_command(msg)
                elif msg.get('type') == 'stop':
                    self.handle_stop_command()
                elif msg.get('type') == 'update_schedule':
                    self.schedule = msg.get('schedule', [])
                    print(f"Updated schedule: {len(self.schedule)} cues")
                    
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Error in command listener: {e}")
    
    def handle_start_command(self, msg):
        """Handle start command from leader"""
        if self.is_running:
            print("Already running, stopping current session first")
            self.stop_playback()
        
        self.schedule = msg.get('schedule', [])
        self.triggered_cues.clear()
        self.is_running = True
        
        print(f"Received start command with {len(self.schedule)} cues")
        
        # Wait for sync
        print("Waiting for time sync...")
        while self.synced_start is None:
            time.sleep(0.1)
        
        # Start video playback
        self.start_video()
        
        # Start MIDI control loop
        Thread(target=self.midi_control_loop, daemon=True).start()
        
        print("Collaborator started successfully")
    
    def handle_stop_command(self):
        """Handle stop command from leader"""
        self.stop_playback()
        print("Stopped by leader command")
    
    def start_video(self):
        """Start video playback with appropriate player"""
        video_path = self.find_video_file()
        
        if not video_path:
            print(f"Error: Video file '{self.video_file}' not found")
            return False
        
        # Determine which video player to use
        if self.is_raspberry_pi():
            # Use omxplayer on Raspberry Pi
            cmd = [
                'omxplayer',
                '--no-osd',
                '--vol', '-2000',
                video_path
            ]
            player_name = "omxplayer"
        else:
            # Use alternative players for simulation on other systems
            cmd = self.get_fallback_video_command(video_path)
            player_name = cmd[0] if cmd else "no player"
            
        if not cmd:
            print("No suitable video player found for simulation")
            print("Install one of: vlc, mpv, ffplay, or mplayer")
            return False
        
        try:
            self.video_process = subprocess.Popen(cmd, 
                                                stdout=subprocess.DEVNULL, 
                                                stderr=subprocess.DEVNULL)
            print(f"Started video playback with {player_name}: {video_path}")
            return True
            
        except FileNotFoundError:
            print(f"Error: {player_name} not found")
            if self.is_raspberry_pi():
                print("Install with: sudo apt install omxplayer")
            else:
                print("For simulation, install one of: vlc, mpv, ffplay, or mplayer")
            return False
        except Exception as e:
            print(f"Error starting video: {e}")
            return False
    
    def is_raspberry_pi(self):
        """Check if running on Raspberry Pi"""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read()
                return 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
        except:
            return False
    
    def get_fallback_video_command(self, video_path):
        """Get fallback video player command for non-Pi systems"""
        # Try different video players in order of preference
        players = [
            # VLC (common, good for testing)
            ['vlc', '--intf', 'dummy', '--play-and-exit', video_path],
            # MPV (lightweight, good alternative)
            ['mpv', '--no-video-aspect', '--really-quiet', video_path],
            # FFplay (part of ffmpeg, widely available)
            ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', video_path],
            # MPlayer (older but widely available)
            ['mplayer', '-really-quiet', '-vo', 'null', video_path]
        ]
        
        for cmd in players:
            try:
                # Check if the player exists
                subprocess.run(['which', cmd[0]], 
                             check=True, 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL)
                return cmd
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        return None
    
    def stop_playback(self):
        """Stop video playback and reset state"""
        self.is_running = False
        
        if self.video_process:
            try:
                self.video_process.terminate()
                self.video_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.video_process.kill()
            except Exception as e:
                print(f"Error stopping video: {e}")
            finally:
                self.video_process = None
        
        # Send MIDI all notes off
        try:
            for channel in range(16):
                # All notes off (CC 123)
                self.midi_out.send_message([0xB0 + channel, 123, 0])
                # All sound off (CC 120)
                self.midi_out.send_message([0xB0 + channel, 120, 0])
        except Exception as e:
            print(f"Error sending MIDI all notes off: {e}")
        
        self.triggered_cues.clear()
        print("Playback stopped")
    
    def midi_control_loop(self):
        """Main loop for MIDI output based on schedule"""
        while self.is_running:
            if self.synced_start is None:
                time.sleep(0.1)
                continue
            
            current_time = time.time() - self.synced_start
            
            # Check for lost sync
            if time.time() - self.last_sync_received > 5:
                print("Lost sync with leader")
                self.stop_playback()
                break
            
            # Process scheduled cues
            for cue in self.schedule:
                cue_time = cue['time']
                cue_id = f"{cue_time}_{cue.get('type', 'unknown')}"
                
                if (cue_time <= current_time and 
                    cue_id not in self.triggered_cues):
                    
                    # Send MIDI message
                    self.send_midi_message(cue)
                    self.triggered_cues.add(cue_id)
                    
                    print(f"MIDI triggered at {cue_time}s: {cue.get('type', 'unknown')}")
            
            time.sleep(0.01)  # 10ms precision
    
    def send_midi_message(self, cue):
        """Send MIDI message based on cue data"""
        try:
            cue_type = cue.get('type')
            channel = cue.get('channel', 1) - 1  # Convert to 0-15 range
            
            if cue_type == 'note_on':
                note = cue.get('note', 60)
                velocity = cue.get('velocity', 127)
                message = [0x90 + channel, note, velocity]
                
            elif cue_type == 'note_off':
                note = cue.get('note', 60)
                message = [0x80 + channel, note, 0]
                
            elif cue_type == 'control_change':
                control = cue.get('control', 7)
                value = cue.get('value', 127)
                message = [0xB0 + channel, control, value]
                
            else:
                print(f"Unknown MIDI message type: {cue_type}")
                return
            
            self.midi_out.send_message(message)
            
        except Exception as e:
            print(f"Error sending MIDI message: {e}")
    
    def register_with_leader(self):
        """Register this Pi with the leader"""
        registration = {
            'type': 'register',
            'pi_id': self.pi_id,
            'status': 'ready',
            'video_file': self.video_file
        }
        
        # Broadcast registration
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(json.dumps(registration).encode(), ('255.255.255.255', self.CONTROL_PORT))
            sock.close()
            print(f"Registered with leader as '{self.pi_id}'")
        except Exception as e:
            print(f"Error registering with leader: {e}")
    
    def send_heartbeat(self):
        """Send periodic heartbeat to leader"""
        while True:
            heartbeat = {
                'type': 'heartbeat',
                'pi_id': self.pi_id,
                'status': 'running' if self.is_running else 'ready'
            }
            
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(json.dumps(heartbeat).encode(), ('255.255.255.255', self.CONTROL_PORT))
                sock.close()
            except Exception as e:
                print(f"Error sending heartbeat: {e}")
            
            time.sleep(2)  # Heartbeat every 2 seconds
    
    def run(self):
        """Main run loop"""
        print(f"Starting KitchenSync Collaborator '{self.pi_id}'")
        
        # Start background threads
        Thread(target=self.listen_sync, daemon=True).start()
        Thread(target=self.listen_commands, daemon=True).start()
        Thread(target=self.send_heartbeat, daemon=True).start()
        
        # Register with leader
        self.register_with_leader()
        
        print("Collaborator ready. Waiting for commands from leader...")
        print("Press Ctrl+C to exit")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.stop_playback()
            try:
                self.midi_out.close_port()
            except:
                pass

def main():
    collaborator = KitchenSyncCollaborator()
    collaborator.run()

if __name__ == "__main__":
    main()
