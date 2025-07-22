#!/usr/bin/env python3
"""
KitchenSync Collaborator Pi
Receives time sync and commands from leader, plays videos and outputs MIDI data
Now uses VLC as the primary video player (omxplayer is deprecated in Raspberry Pi OS Bookworm)
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
from collections import deque
import statistics

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

# Try to import VLC Python bindings, fall back to command line if not available
try:
    import vlc
    VLC_PYTHON_AVAILABLE = True
    print("VLC Python bindings available - using advanced video control")
except ImportError:
    print("python-vlc not available, falling back to VLC command line interface")
    VLC_PYTHON_AVAILABLE = False

# DBus is no longer needed since we're using VLC instead of omxplayer
# But we'll keep the import for backward compatibility
try:
    import dbus
    DBUS_AVAILABLE = True
except ImportError:
    print("python-dbus not available (not needed for VLC mode)")
    DBUS_AVAILABLE = False

class VLCVideoPlayer:
    """
    VLC-based video player with precise control and synchronization capabilities
    Supports both VLC Python bindings and command-line interface
    """
    
    def __init__(self):
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self.command_process = None
        self.start_time = None
        self.video_path = None
        self.using_python_vlc = False
        
    def start_video(self, video_path, volume=-2000):
        """Start video playback with VLC"""
        self.video_path = video_path
        
        if VLC_PYTHON_AVAILABLE:
            return self._start_with_python_vlc(video_path, volume)
        else:
            return self._start_with_command_line_vlc(video_path, volume)
    
    def _start_with_python_vlc(self, video_path, volume):
        """Start video using VLC Python bindings (preferred method)"""
        try:
            # Create VLC instance with appropriate options
            vlc_args = [
                '--intf', 'dummy',          # No interface
                '--no-video-title-show',    # Don't show title
                '--no-osd',                 # No on-screen display
                '--quiet',                  # Reduce log output
            ]
            
            self.vlc_instance = vlc.Instance(' '.join(vlc_args))
            self.vlc_player = self.vlc_instance.media_player_new()
            
            # Load media
            self.vlc_media = self.vlc_instance.media_new(video_path)
            self.vlc_player.set_media(self.vlc_media)
            
            # Set volume (VLC uses 0-100 scale, convert from omxplayer-style values)
            if volume < 0:
                # Convert from omxplayer millibel to VLC percentage
                # omxplayer -2000 (very quiet) -> VLC ~20%
                vlc_volume = max(0, min(100, int(100 * pow(10, volume/4000))))
            else:
                vlc_volume = min(100, volume)
            
            self.vlc_player.audio_set_volume(vlc_volume)
            
            # Start playback
            self.vlc_player.play()
            self.start_time = time.time()
            self.using_python_vlc = True
            
            print(f"Started VLC Python playback: {video_path} (volume: {vlc_volume}%)")
            return True
            
        except Exception as e:
            print(f"Error starting VLC Python player: {e}")
            return False
    
    def _start_with_command_line_vlc(self, video_path, volume):
        """Start video using VLC command line (fallback method)"""
        try:
            # Build VLC command
            cmd = [
                'vlc',
                '--intf', 'dummy',          # No interface
                '--no-video-title-show',    # Don't show title
                '--no-osd',                 # No on-screen display
                '--play-and-exit',          # Exit when done
                '--quiet',                  # Reduce log output
            ]
            
            # Add volume if specified
            if volume < 0:
                # Convert from omxplayer millibel to VLC gain
                vlc_gain = max(-20, volume/100)  # Rough conversion
                cmd.extend(['--gain', str(vlc_gain)])
            
            cmd.append(video_path)
            
            # Start VLC process
            self.command_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.start_time = time.time()
            self.using_python_vlc = False
            
            print(f"Started VLC command line playback: {video_path}")
            return True
            
        except FileNotFoundError:
            print("Error: VLC not found. Install with: sudo apt install vlc")
            return False
        except Exception as e:
            print(f"Error starting VLC command line: {e}")
            return False
    
    def get_position(self):
        """Get current playback position in seconds"""
        if self.using_python_vlc and self.vlc_player:
            try:
                # VLC returns position as fraction (0.0-1.0) of total duration
                position_fraction = self.vlc_player.get_position()
                length_ms = self.vlc_player.get_length()
                
                if position_fraction >= 0 and length_ms > 0:
                    return (position_fraction * length_ms) / 1000.0
                else:
                    # Fallback to elapsed time if position unavailable
                    return time.time() - self.start_time if self.start_time else 0
            except Exception as e:
                print(f"Error getting VLC position: {e}")
                return time.time() - self.start_time if self.start_time else 0
        else:
            # For command line VLC, estimate based on elapsed time
            return time.time() - self.start_time if self.start_time else 0
    
    def seek_to(self, position_seconds):
        """Seek to specific position in seconds"""
        if self.using_python_vlc and self.vlc_player:
            try:
                length_ms = self.vlc_player.get_length()
                if length_ms > 0:
                    # Convert seconds to fraction of total duration
                    position_fraction = min(1.0, max(0.0, (position_seconds * 1000.0) / length_ms))
                    self.vlc_player.set_position(position_fraction)
                    print(f"VLC seeked to {position_seconds:.2f}s ({position_fraction:.3f})")
                    return True
                else:
                    print("Cannot seek: video length unknown")
                    return False
            except Exception as e:
                print(f"Error seeking VLC player: {e}")
                return False
        else:
            print("Seeking not available with VLC command line interface")
            return False
    
    def pause(self):
        """Pause playback"""
        if self.using_python_vlc and self.vlc_player:
            try:
                self.vlc_player.pause()
                print("VLC playback paused")
                return True
            except Exception as e:
                print(f"Error pausing VLC: {e}")
                return False
        else:
            print("Pause not available with VLC command line interface")
            return False
    
    def resume(self):
        """Resume playback"""
        if self.using_python_vlc and self.vlc_player:
            try:
                if self.vlc_player.is_playing():
                    print("VLC is already playing")
                else:
                    self.vlc_player.play()
                    print("VLC playback resumed")
                return True
            except Exception as e:
                print(f"Error resuming VLC: {e}")
                return False
        else:
            print("Resume not available with VLC command line interface")
            return False
    
    def stop(self):
        """Stop playback and cleanup"""
        if self.using_python_vlc:
            try:
                if self.vlc_player:
                    self.vlc_player.stop()
                if self.vlc_instance:
                    self.vlc_instance.release()
                print("VLC Python player stopped")
            except Exception as e:
                print(f"Error stopping VLC Python player: {e}")
        
        if self.command_process:
            try:
                self.command_process.terminate()
                self.command_process.wait(timeout=5)
                print("VLC command line player stopped")
            except Exception as e:
                print(f"Error stopping VLC command line: {e}")
        
        # Reset state
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self.command_process = None
        self.start_time = None
        self.using_python_vlc = False
    
    def is_playing(self):
        """Check if video is currently playing"""
        if self.using_python_vlc and self.vlc_player:
            try:
                return self.vlc_player.is_playing()
            except:
                return False
        elif self.command_process:
            return self.command_process.poll() is None
        else:
            return False

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
        self.video_player = VLCVideoPlayer()  # Use new VLC video player
        self.schedule = []
        self.triggered_cues = set()
        self.video_start_time = None
        self.last_sync_check = 0
        
        # Video sync settings
        self.sync_tolerance = self.config.get('sync_tolerance', 1.0)  # seconds
        self.sync_check_interval = self.config.get('sync_check_interval', 5.0)  # seconds
        
        # Advanced sync settings (originally from omxplayer-sync, now adapted for VLC)
        self.deviation_threshold = self.config.get('deviation_threshold', 0.5)  # seconds
        self.max_deviation_samples = int(self.config.get('max_deviation_samples', 10))
        self.pause_threshold = self.config.get('pause_threshold', 2.0)  # seconds for pausing during large corrections
        self.sync_grace_time = self.config.get('sync_grace_time', 3.0)  # seconds to wait after sync before checking again
        
        # Deviation tracking for median filtering
        self.deviation_samples = deque(maxlen=self.max_deviation_samples)
        self.last_correction_time = 0
        
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
        if 'sync_tolerance' in settings:
            settings['sync_tolerance'] = float(settings['sync_tolerance'])
        if 'sync_check_interval' in settings:
            settings['sync_check_interval'] = float(settings['sync_check_interval'])
        if 'deviation_threshold' in settings:
            settings['deviation_threshold'] = float(settings['deviation_threshold'])
        if 'max_deviation_samples' in settings:
            settings['max_deviation_samples'] = int(settings['max_deviation_samples'])
        if 'pause_threshold' in settings:
            settings['pause_threshold'] = float(settings['pause_threshold'])
        if 'sync_grace_time' in settings:
            settings['sync_grace_time'] = float(settings['sync_grace_time'])
        
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
        """Start video playback with VLC"""
        video_path = self.find_video_file()
        
        if not video_path:
            print(f"Error: Video file '{self.video_file}' not found")
            return False
        
        # Use VLC video player (works on both Raspberry Pi and other systems)
        success = self.video_player.start_video(video_path, volume=-2000)
        
        if success:
            self.video_start_time = time.time()
            print(f"Started VLC video playback: {video_path}")
            return True
        else:
            print("Failed to start video playback")
            return False
    
    def get_video_position(self):
        """Get current video position in seconds"""
        return self.video_player.get_position()
    
    def seek_video_position(self, target_seconds):
        """Seek video to specific position"""
        return self.video_player.seek_to(target_seconds)
    
    def check_video_sync(self, leader_time):
        """Check if video needs sync correction using median deviation filtering"""
        if not self.video_start_time or not self.synced_start:
            return
            
        # Only check sync periodically to avoid overhead
        now = time.time()
        if now - self.last_sync_check < self.sync_check_interval:
            return
        self.last_sync_check = now
        
        # Don't check sync too soon after a correction (grace period)
        if now - self.last_correction_time < self.sync_grace_time:
            return
        
        # Get current video position
        video_position = self.get_video_position()
        if video_position is None:
            return
            
        # Calculate expected position based on leader time
        expected_position = leader_time
        
        # Calculate deviation (positive = video ahead, negative = video behind)
        deviation = video_position - expected_position
        
        # Add deviation to our sample collection for median filtering
        self.deviation_samples.append(deviation)
        
        # Only act on sync if we have enough samples
        if len(self.deviation_samples) < 3:
            return
            
        # Calculate median deviation to filter out outliers
        median_deviation = statistics.median(self.deviation_samples)
        abs_median_deviation = abs(median_deviation)
        
        # Check if median deviation exceeds our threshold
        if abs_median_deviation > self.deviation_threshold:
            print(f"Video sync drift detected: median deviation {median_deviation:.2f}s")
            print(f"Video position: {video_position:.2f}s, Expected: {expected_position:.2f}s")
            
            # For large deviations, pause video during correction to avoid glitches
            if abs_median_deviation > self.pause_threshold:
                print(f"Large deviation ({abs_median_deviation:.2f}s), pausing during correction")
                self.pause_video()
                time.sleep(0.1)  # Brief pause to ensure pause takes effect
            
            # Perform the correction
            corrected_position = expected_position
            if self.seek_video_position(corrected_position):
                self.last_correction_time = now
                # Clear deviation samples after successful correction
                self.deviation_samples.clear()
                
                # Resume video if we paused it
                if abs_median_deviation > self.pause_threshold:
                    time.sleep(0.1)  # Brief delay before resuming
                    self.resume_video()
                    print("Video resumed after correction")
            else:
                print("Failed to correct video position")
    
    def pause_video(self):
        """Pause video playback"""
        return self.video_player.pause()
    
    def resume_video(self):
        """Resume video playback"""
        return self.video_player.resume()
    
    def stop_playback(self):
        """Stop video playback and reset state"""
        self.is_running = False
        
        # Stop VLC video player
        self.video_player.stop()
        
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
            
            # Check video sync correction
            self.check_video_sync(current_time)
            
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
