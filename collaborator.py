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
            # Create VLC instance with appropriate options for fullscreen video
            vlc_args = [
                '--fullscreen',             # Start in fullscreen
                '--no-video-title-show',    # Don't show title
                '--no-osd',                 # No on-screen display
                '--quiet',                  # Reduce log output
                '--mouse-hide-timeout=0',   # Hide mouse immediately
            ]
            
            self.vlc_instance = vlc.Instance(' '.join(vlc_args))
            self.vlc_player = self.vlc_instance.media_player_new()
            
            # Set fullscreen
            self.vlc_player.set_fullscreen(True)
            
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
            result = self.vlc_player.play()
            self.start_time = time.time()
            self.using_python_vlc = True
            
            print(f"✓ Started VLC Python playback: {video_path} (volume: {vlc_volume}%)")
            print(f"✓ VLC play result: {result}")
            print(f"✓ Fullscreen mode enabled")
            
            # Wait a moment for VLC to initialize
            time.sleep(1)
            
            # Check if video is actually playing
            state = self.vlc_player.get_state()
            print(f"✓ VLC player state: {state}")
            
            return True
            
        except Exception as e:
            print(f"Error starting VLC Python player: {e}")
            return False
    
    def _start_with_command_line_vlc(self, video_path, volume):
        """Start video using VLC command line (fallback method)"""
        try:
            # Build VLC command for fullscreen playback
            cmd = [
                'vlc',
                '--fullscreen',             # Start in fullscreen
                '--no-video-title-show',    # Don't show title
                '--no-osd',                 # No on-screen display
                '--play-and-exit',          # Exit when done
                '--quiet',                  # Reduce log output
                '--mouse-hide-timeout=0',   # Hide mouse immediately
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

class DebugOverlay:
    """
    Debug overlay system that displays Pi ID, video info, and time on screen
    Supports both pygame (preferred) and text-based (fallback) modes
    """
    
    def __init__(self, pi_id, video_file, use_pygame=False):
        self.pi_id = pi_id
        self.video_file = os.path.basename(video_file) if video_file else "No Video"
        self.use_pygame = use_pygame
        self.overlay_active = False
        
        if self.use_pygame:
            try:
                import pygame
                self.pygame = pygame
                self._init_pygame_overlay()
            except ImportError:
                print("Pygame not available, falling back to text debug mode")
                self.use_pygame = False
    
    def _init_pygame_overlay(self):
        """Initialize pygame overlay for visual debug display"""
        try:
            import os
            # Set pygame window properties for staying on top
            os.environ['SDL_WINDOWID'] = ''
            
            self.pygame.init()
            
            # Get display info
            info = self.pygame.display.Info()
            self.screen_width = info.current_w
            self.screen_height = info.current_h
            
            # Create overlay surface (small window for debug info)
            self.overlay_width = 400
            self.overlay_height = 240
            
            # Position overlay in top-right corner
            self.overlay_x = self.screen_width - self.overlay_width - 20
            self.overlay_y = 20
            
            # Set window position
            os.environ['SDL_VIDEO_WINDOW_POS'] = f'{self.overlay_x},{self.overlay_y}'
            
            # Create a small window with ALWAYS_ON_TOP flag
            flags = self.pygame.NOFRAME
            try:
                # Try to set always on top flag if available
                flags |= getattr(self.pygame, 'HWSURFACE', 0)
            except:
                pass
                
            self.screen = self.pygame.display.set_mode((self.overlay_width, self.overlay_height), flags)
            self.pygame.display.set_caption("KitchenSync Debug")
            
            # Multiple attempts to force window on top
            try:
                import subprocess
                import time
                
                # Method 1: Use wmctrl to set always on top
                subprocess.run(['wmctrl', '-r', 'KitchenSync Debug', '-b', 'add,above'], 
                              capture_output=True, timeout=2)
                
                # Method 2: Use xdotool to raise window repeatedly
                subprocess.run(['xdotool', 'search', '--name', 'KitchenSync Debug', 'windowraise'], 
                              capture_output=True, timeout=2)
                
                # Method 3: Set window as sticky (appears on all workspaces)
                subprocess.run(['wmctrl', '-r', 'KitchenSync Debug', '-b', 'add,sticky'], 
                              capture_output=True, timeout=2)
                
            except:
                pass  # Tools not available, continue anyway
            
            # Start a thread to periodically raise the window
            import threading
            self.keep_on_top = True
            def raise_window_periodically():
                while self.keep_on_top:
                    try:
                        # Raise window every 2 seconds
                        subprocess.run(['wmctrl', '-r', 'KitchenSync Debug', '-b', 'add,above'], 
                                      capture_output=True, timeout=1)
                        time.sleep(2)
                    except:
                        time.sleep(2)
            
            self.raise_thread = threading.Thread(target=raise_window_periodically, daemon=True)
            self.raise_thread.start()
            
            # Create fonts (monospace for consistent layout)
            try:
                self.font_large = self.pygame.font.Font(None, 36)  # For Pi ID
                self.font_medium = self.pygame.font.Font(None, 24)  # For video name
                self.font_small = self.pygame.font.Font(None, 18)   # For time and details
            except:
                # Fallback to default font
                self.font_large = self.pygame.font.Font(None, 36)
                self.font_medium = self.pygame.font.Font(None, 24)
                self.font_small = self.pygame.font.Font(None, 18)
            
            # Colors
            self.color_bg = (0, 0, 0, 180)      # Semi-transparent black
            self.color_pi_id = (255, 255, 255)   # White for Pi ID
            self.color_video = (200, 200, 255)   # Light blue for video name
            self.color_time = (255, 255, 0)      # Yellow for time
            self.color_text = (220, 220, 220)    # Light gray for other text
            
            print("✓ Pygame debug overlay initialized")
            
        except Exception as e:
            print(f"Error initializing pygame overlay: {e}")
            self.use_pygame = False
    
    def update_display(self, current_time=0, total_time=0, additional_info=None):
        """Update the debug overlay display"""
        if self.use_pygame:
            self._update_pygame_display(current_time, total_time, additional_info)
        else:
            self._update_text_display(current_time, total_time, additional_info)
    
    def _update_pygame_display(self, current_time, total_time, additional_info):
        """Update pygame-based visual overlay"""
        try:
            # Clear the entire window with semi-transparent background
            self.screen.fill((0, 0, 0))  # Black background for small window
            
            y_pos = 10
            
            # Pi ID (large, prominent)
            pi_text = self.font_large.render(f"Pi: {self.pi_id}", True, self.color_pi_id)
            self.screen.blit(pi_text, (10, y_pos))
            y_pos += 40
            
            # Video file name (truncate if too long)
            video_name = self.video_file
            if len(video_name) > 25:
                video_name = video_name[:22] + "..."
            video_text = self.font_medium.render(f"Video: {video_name}", True, self.color_video)
            self.screen.blit(video_text, (10, y_pos))
            y_pos += 30
            
            # Time display (MM:SS / MM:SS format)
            current_min = int(current_time // 60)
            current_sec = int(current_time % 60)
            total_min = int(total_time // 60)
            total_sec = int(total_time % 60)
            
            time_str = f"{current_min:02d}:{current_sec:02d}/{total_min:02d}:{total_sec:02d}"
            time_text = self.font_medium.render(time_str, True, self.color_time)
            self.screen.blit(time_text, (10, y_pos))
            y_pos += 30
            
            # Additional info (if provided) - limit to fit in window
            if additional_info:
                for info_line in additional_info[:4]:  # Limit to 4 lines
                    # Truncate long lines
                    info_str = str(info_line)
                    if len(info_str) > 40:
                        info_str = info_str[:37] + "..."
                    info_text = self.font_small.render(info_str, True, self.color_text)
                    self.screen.blit(info_text, (10, y_pos))
                    y_pos += 20
            
            # Update the display
            self.pygame.display.flip()
            
        except Exception as e:
            print(f"Error updating pygame display: {e}")
    
    def _update_text_display(self, current_time, total_time, additional_info):
        """Update text-based debug display (fallback)"""
        # Format time
        current_min = int(current_time // 60)
        current_sec = int(current_time % 60)
        total_min = int(total_time // 60)
        total_sec = int(total_time % 60)
        
        time_str = f"{current_min:02d}:{current_sec:02d}/{total_min:02d}:{total_sec:02d}"
        
        # Print debug info to console (every 5 seconds to avoid spam)
        if int(current_time) % 5 == 0 and current_time > 0:
            print(f"🐛 DEBUG | Pi: {self.pi_id} | Video: {self.video_file} | Time: {time_str}")
            if additional_info:
                for info in additional_info[:2]:
                    print(f"🐛        | {info}")
    
    def cleanup(self):
        """Clean up overlay resources"""
        if self.use_pygame:
            try:
                # Stop the window raising thread
                if hasattr(self, 'keep_on_top'):
                    self.keep_on_top = False
                if hasattr(self, 'raise_thread'):
                    self.raise_thread.join(timeout=1)
                
                self.pygame.quit()
            except:
                pass

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
        
        # Build video sources list - prioritize USB mount point from auto-start
        usb_mount_point = self.config.get('usb_mount_point', '').strip()
        if usb_mount_point:
            # USB mount point identified by auto-start script gets highest priority
            self.video_sources = [usb_mount_point]
            print(f"✓ Using USB mount point from auto-start: {usb_mount_point}")
        else:
            # Fallback to configured video_sources or defaults
            configured_sources = self.config.get('video_sources', './videos/,/media/usb/,/media/usb0/,/media/usb1/')
            if isinstance(configured_sources, str):
                self.video_sources = [s.strip() for s in configured_sources.split(',') if s.strip()]
            else:
                self.video_sources = configured_sources
            print(f"⚠️  No USB mount point from auto-start, using fallback sources: {self.video_sources}")
        
        # Debug mode configuration
        self.debug_mode = self.config.get('debug', 'false').lower() == 'true'
        if self.debug_mode:
            print("🐛 DEBUG MODE ENABLED")
            # Initialize debug overlay components
            self.debug_overlay = None
            try:
                import pygame
                self.pygame_available = True
                print("✓ Pygame available for debug overlay")
            except ImportError:
                self.pygame_available = False
                print("⚠️ Pygame not available, debug overlay will be text-based")
        else:
            self.pygame_available = False
        
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
        
        # Test USB detection on startup
        if "--test-usb" in sys.argv:
            self.test_usb_detection()
            sys.exit(0)
        
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
    
    def mount_usb_drives(self):
        """Automatically detect and mount USB drives"""
        import subprocess
        import glob
        
        mounted_drives = []
        
        try:
            # First, check for already mounted USB drives in /media/
            mount_result = subprocess.run(['mount'], capture_output=True, text=True)
            if mount_result.returncode == 0:
                for line in mount_result.stdout.split('\n'):
                    if '/media/' in line and ('usb' in line.lower() or 'sd' in line or 'mmc' in line):
                        # Extract mount point from mount output
                        parts = line.split(' on ')
                        if len(parts) >= 2:
                            mount_point = parts[1].split(' type ')[0]
                            if os.path.exists(mount_point) and os.path.isdir(mount_point):
                                mounted_drives.append(mount_point)
                                print(f"✓ Found mounted USB drive: {mount_point}")
            
            # If we found already-mounted drives, return them
            if mounted_drives:
                return mounted_drives
            
            # Otherwise, try to detect and mount USB devices manually
            usb_devices = []
            
            # Check for USB storage devices
            for device in glob.glob('/sys/block/*/device'):
                try:
                    with open(f"{device}/uevent", 'r') as f:
                        content = f.read()
                        if 'usb' in content.lower():
                            block_device = device.split('/')[-2]
                            # Look for partitions
                            for partition in glob.glob(f'/sys/block/{block_device}/{block_device}*'):
                                partition_name = partition.split('/')[-1]
                                if partition_name != block_device:  # It's a partition
                                    usb_devices.append(f'/dev/{partition_name}')
                            
                            # If no partitions, use the whole device
                            if not any(f'/dev/{block_device}' in d for d in usb_devices):
                                usb_devices.append(f'/dev/{block_device}')
                except:
                    continue
            
            # Mount each USB device
            for device in usb_devices:
                device_name = device.split('/')[-1]
                mount_point = f'/media/usb-{device_name}'
                
                # Create mount point if it doesn't exist
                os.makedirs(mount_point, exist_ok=True)
                
                # Check if already mounted
                result = subprocess.run(['mountpoint', '-q', mount_point], 
                                      capture_output=True)
                
                if result.returncode != 0:  # Not mounted
                    try:
                        # Try to mount
                        mount_result = subprocess.run([
                            'sudo', 'mount', '-o', 'uid=1000,gid=1000', 
                            device, mount_point
                        ], capture_output=True, text=True, timeout=10)
                        
                        if mount_result.returncode == 0:
                            mounted_drives.append(mount_point)
                            print(f"✓ Mounted USB drive: {device} -> {mount_point}")
                        else:
                            print(f"✗ Failed to mount {device}: {mount_result.stderr}")
                    except subprocess.TimeoutExpired:
                        print(f"✗ Timeout mounting {device}")
                    except Exception as e:
                        print(f"✗ Error mounting {device}: {e}")
                else:
                    mounted_drives.append(mount_point)
                    print(f"✓ USB drive already mounted: {mount_point}")
        
        except Exception as e:
            print(f"Error detecting USB drives: {e}")
        
        return mounted_drives

    def find_video_files_on_usb(self, mount_point):
        """Find video files at the root of a USB drive"""
        video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.m4v', '.wmv', '.flv', '.webm']
        video_files = []
        
        try:
            if os.path.exists(mount_point):
                # Only look at root level files
                for item in os.listdir(mount_point):
                    item_path = os.path.join(mount_point, item)
                    if os.path.isfile(item_path):
                        _, ext = os.path.splitext(item.lower())
                        if ext in video_extensions:
                            video_files.append(item_path)
        except Exception as e:
            print(f"Error scanning USB drive {mount_point}: {e}")
        
        return sorted(video_files)

    def find_video_file(self):
        """Find video file with USB mount point priority from auto-start script"""
        
        # Step 1: Check if we have a USB mount point from the auto-start script
        usb_mount_point = self.config.get('usb_mount_point', '').strip()
        if usb_mount_point and os.path.exists(usb_mount_point):
            print(f"✓ Using USB mount point from auto-start script: {usb_mount_point}")
            
            # Look for the specific video file first
            if self.video_file:
                video_path = os.path.join(usb_mount_point, self.video_file)
                if os.path.exists(video_path):
                    print(f"✓ Found configured video file: {video_path}")
                    return video_path
            
            # Look for any video files in the USB mount point
            video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.m4v', '.wmv', '.flv', '.webm']
            usb_videos = []
            
            try:
                for item in os.listdir(usb_mount_point):
                    item_path = os.path.join(usb_mount_point, item)
                    if os.path.isfile(item_path):
                        _, ext = os.path.splitext(item.lower())
                        if ext in video_extensions:
                            usb_videos.append(item_path)
                
                if usb_videos:
                    if len(usb_videos) == 1:
                        print(f"✓ Found video on USB drive: {usb_videos[0]}")
                        return usb_videos[0]
                    else:
                        print("⚠ Multiple video files found on USB drive:")
                        for i, video in enumerate(usb_videos, 1):
                            print(f"   {i}. {os.path.basename(video)}")
                        
                        selected_video = usb_videos[0]
                        print(f"➤ Using first video file: {selected_video}")
                        return selected_video
                        
            except Exception as e:
                print(f"Error scanning USB mount point: {e}")
        
        # Step 2: Fallback to legacy USB scanning (for manual mode or if auto-start failed)
        print("🔍 No USB mount point from auto-start, scanning for USB drives...")
        mounted_drives = self.mount_usb_drives()
        
        # Check USB drives 
        usb_video_files = []
        for mount_point in mounted_drives:
            videos = self.find_video_files_on_usb(mount_point)
            usb_video_files.extend(videos)
        
        if usb_video_files:
            if len(usb_video_files) == 1:
                print(f"✓ Found video on USB drive: {usb_video_files[0]}")
                return usb_video_files[0]
            elif len(usb_video_files) > 1:
                print("⚠ Multiple video files found on USB drives:")
                for i, video in enumerate(usb_video_files, 1):
                    print(f"   {i}. {os.path.basename(video)} ({os.path.dirname(video)})")
                
                selected_video = usb_video_files[0]
                print(f"➤ Using first video file: {selected_video}")
                print("💡 Tip: Use only one video file per USB drive for automatic selection")
                return selected_video
        
        # Step 3: Check if specific video file exists in configured locations
        if os.path.exists(self.video_file):
            print(f"✓ Found configured video file: {self.video_file}")
            return self.video_file
        
        # Check video source directories for the configured file
        for source_dir in self.video_sources:
            video_path = os.path.join(source_dir, self.video_file)
            if os.path.exists(video_path):
                print(f"✓ Found configured video file: {video_path}")
                return video_path
        
        # Step 4: Look for any video files in configured directories
        print(f"⚠ Configured video file '{self.video_file}' not found")
        print("🔍 Searching for alternative video files...")
        
        video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.m4v', '.wmv', '.flv', '.webm']
        found_videos = []
        
        for source_dir in self.video_sources:
            if os.path.exists(source_dir):
                for file in os.listdir(source_dir):
                    file_path = os.path.join(source_dir, file)
                    if os.path.isfile(file_path):
                        _, ext = os.path.splitext(file.lower())
                        if ext in video_extensions:
                            found_videos.append(file_path)
        
        if found_videos:
            if len(found_videos) == 1:
                print(f"✓ Found alternative video: {found_videos[0]}")
                return found_videos[0]
            else:
                print("⚠ Multiple video files found in local directories:")
                for i, video in enumerate(found_videos, 1):
                    print(f"   {i}. {os.path.basename(video)} ({os.path.dirname(video)})")
                
                selected_video = found_videos[0]
                print(f"➤ Using first video file: {selected_video}")
                return selected_video
        
        # Step 5: No video files found anywhere
        self.display_video_error("No video files found")
        return None

    def display_video_error(self, error_message):
        """Display error message for video issues"""
        print("❌ VIDEO ERROR ❌")
        print("=" * 50)
        print(f"Error: {error_message}")
        print("")
        print("Expected locations (in priority order):")
        
        # Check if we have USB mount point from auto-start
        usb_mount_point = self.config.get('usb_mount_point', '').strip()
        if usb_mount_point:
            print(f"  1. USB mount point (from auto-start): {usb_mount_point}")
            if os.path.exists(usb_mount_point):
                print(f"     ✓ {usb_mount_point}/ (accessible)")
            else:
                print(f"     ✗ {usb_mount_point}/ (not accessible)")
        else:
            print("  1. USB drive auto-detection (fallback)")
            for mount_point in ['/media/usb', '/media/usb0', '/media/usb1']:
                if os.path.exists(mount_point):
                    print(f"     ✓ {mount_point}/")
                else:
                    print(f"     ✗ {mount_point}/ (not found)")
        
        print(f"  2. Configured file: {self.video_file}")
        print("  3. Fallback directories:")
        for source_dir in self.video_sources:
            if os.path.exists(source_dir):
                print(f"     ✓ {source_dir}")
            else:
                print(f"     ✗ {source_dir} (not found)")
        
        print("")
        print("Supported formats: MP4, AVI, MKV, MOV, M4V, WMV, FLV, WebM")
        print("💡 For automatic detection, place ONE video file at the root of your USB drive")
        print("=" * 50)

    def test_usb_detection(self):
        """Test USB drive detection and video file finding"""
        print("🧪 USB Drive Detection Test")
        print("=" * 40)
        
        # Test USB mounting
        print("\n1. Testing USB drive detection...")
        mounted_drives = self.mount_usb_drives()
        
        if not mounted_drives:
            print("❌ No USB drives detected")
            print("💡 Connect a USB drive and try again")
            return
        
        # Test video file detection
        print(f"\n2. Testing video file detection...")
        all_videos = []
        for mount_point in mounted_drives:
            videos = self.find_video_files_on_usb(mount_point)
            all_videos.extend(videos)
            print(f"   {mount_point}: {len(videos)} video file(s)")
            for video in videos:
                print(f"     - {os.path.basename(video)}")
        
        # Test overall file finding logic
        print(f"\n3. Testing complete video file selection...")
        selected_video = self.find_video_file()
        
        if selected_video:
            print(f"✅ Selected video: {selected_video}")
        else:
            print("❌ No video file selected")
        
        print("\n" + "=" * 40)
        print("Test complete!")
    
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
        
        # Override debug mode if leader specifies it
        leader_debug_mode = msg.get('debug_mode', False)
        if leader_debug_mode and not self.debug_mode:
            self.debug_mode = True
            print("🐛 Debug mode enabled by leader")
            # Initialize pygame if possible
            try:
                import pygame
                self.pygame_available = True
                print("✓ Pygame available for debug overlay")
            except ImportError:
                self.pygame_available = False
        
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
            
            # Initialize debug overlay if in debug mode
            if self.debug_mode:
                self.debug_overlay = DebugOverlay(self.pi_id, video_path, self.pygame_available)
                # Start debug update thread
                Thread(target=self.debug_update_loop, daemon=True).start()
                print("🐛 Debug overlay initialized")
            
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
        
        # Clean up debug overlay
        if self.debug_mode and hasattr(self, 'debug_overlay') and self.debug_overlay:
            self.debug_overlay.cleanup()
            print("🐛 Debug overlay cleaned up")
        
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
    
    def debug_update_loop(self):
        """Update debug overlay display periodically"""
        while self.is_running and self.debug_mode and hasattr(self, 'debug_overlay'):
            try:
                if self.synced_start is None:
                    time.sleep(0.1)
                    continue
                
                # Get current video time
                current_time = time.time() - self.synced_start
                video_position = self.get_video_position()
                
                # Estimate total video duration (VLC might provide this)
                total_time = 300  # Default 5 minutes, could be improved with VLC duration
                if hasattr(self.video_player, 'vlc_player') and self.video_player.vlc_player:
                    try:
                        duration_ms = self.video_player.vlc_player.get_length()
                        if duration_ms > 0:
                            total_time = duration_ms / 1000.0
                    except:
                        pass
                
                # Prepare additional debug info
                additional_info = [
                    f"Sync: {current_time:.1f}s",
                    f"Video pos: {video_position:.1f}s" if video_position else "Video pos: N/A",
                    f"MIDI cues: {len(self.triggered_cues)}/{len(self.schedule)}"
                ]
                
                # Update debug overlay
                self.debug_overlay.update_display(current_time, total_time, additional_info)
                
                # Update at 10 FPS to avoid overwhelming the system
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Error in debug update loop: {e}")
                time.sleep(1)  # Wait longer on error to avoid spam
    
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
    import argparse
    
    parser = argparse.ArgumentParser(description='KitchenSync Collaborator Pi')
    parser.add_argument('--test-video', action='store_true', help='Test video playback immediately')
    parser.add_argument('--test-usb', action='store_true', help='Test USB drive detection')
    args = parser.parse_args()
    
    collaborator = KitchenSyncCollaborator()
    
    if args.test_usb:
        print("🧪 USB Drive Detection Test")
        print("=" * 40)
        print("\n1. Testing USB drive detection...")
        mounted_drives = collaborator.mount_usb_drives()
        if not mounted_drives:
            print("❌ No USB drives detected")
            print("💡 Connect a USB drive and try again")
            return
        
        print("\n2. Testing video file detection...")
        all_videos = []
        for mount_point in mounted_drives:
            videos = collaborator.find_video_files_on_usb(mount_point)
            print(f"   {mount_point}: {len(videos)} video file(s)")
            for video in videos:
                print(f"     - {video}")
                all_videos.append(os.path.join(mount_point, video))
        
        print("\n3. Testing complete video file selection...")
        selected_video = collaborator.get_video_file_path()
        if selected_video:
            print(f"✅ Selected video: {selected_video}")
        else:
            print("❌ No video selected")
        
        print("\n" + "=" * 40)
        print("Test complete!")
        return
    
    elif args.test_video:
        print("🎬 Testing Video Playback")
        print("=" * 30)
        
        # Get video file
        video_path = collaborator.get_video_file_path()
        if not video_path:
            print("❌ No video file found")
            return
        
        print(f"📹 Playing: {video_path}")
        
        # Start video immediately
        if collaborator.video_player.start_video(video_path):
            print("✅ Video started successfully")
            print("🎬 Video should now be playing in fullscreen")
            print("Press Ctrl+C to stop")
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Stopping video...")
                collaborator.video_player.stop_video()
                print("👋 Test complete!")
        else:
            print("❌ Failed to start video")
        return
    
    # Normal operation
    collaborator.run()

if __name__ == "__main__":
    main()
