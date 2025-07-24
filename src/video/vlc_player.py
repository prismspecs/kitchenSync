#!/usr/bin/env python3
"""
VLC Video Player Management for KitchenSync
Handles VLC video playback with sync capabilities
"""

import os
import subprocess
import time
from typing import Optional

# Try to import VLC Python bindings
try:
    import vlc
    VLC_PYTHON_AVAILABLE = True
except ImportError:
    VLC_PYTHON_AVAILABLE = False


class VLCPlayerError(Exception):
    """Raised when VLC player operations fail"""
    pass


class VLCVideoPlayer:
    """VLC-based video player with sync capabilities"""
    
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self.video_path = None
        self.is_playing = False
        self.command_process = None  # For command-line VLC
    
    def load_video(self, video_path: str) -> bool:
        """Load a video file"""
        if not os.path.exists(video_path):
            raise VLCPlayerError(f"Video file not found: {video_path}")
        
        self.video_path = video_path
        print(f"Loaded video: {video_path}")
        return True
    
    def start_playback(self) -> bool:
        """Start video playback"""
        if not self.video_path:
            raise VLCPlayerError("No video loaded")
        
        if VLC_PYTHON_AVAILABLE:
            return self._start_with_python_vlc()
        else:
            return self._start_with_command_vlc()
    
    def stop_playback(self) -> None:
        """Stop video playback"""
        try:
            if self.vlc_player:
                self.vlc_player.stop()
                print("🛑 Stopped VLC Python player")
            
            if self.command_process:
                self.command_process.terminate()
                self.command_process = None
                print("🛑 Stopped VLC command process")
            
            # Kill any remaining VLC processes
            subprocess.run(['pkill', 'vlc'], capture_output=True)
            
            self.is_playing = False
        except Exception as e:
            print(f"Error stopping video: {e}")
    
    def get_position(self) -> Optional[float]:
        """Get current playback position in seconds"""
        if not self.is_playing:
            return None
        
        try:
            if self.vlc_player and VLC_PYTHON_AVAILABLE:
                # VLC position is 0.0 to 1.0, convert to seconds
                position_ratio = self.vlc_player.get_position()
                length_ms = self.vlc_player.get_length()
                if position_ratio >= 0 and length_ms > 0:
                    return (position_ratio * length_ms) / 1000.0
            return None
        except Exception as e:
            print(f"Error getting position: {e}")
            return None
    
    def set_position(self, seconds: float) -> bool:
        """Set playback position"""
        try:
            if self.vlc_player and VLC_PYTHON_AVAILABLE:
                length_ms = self.vlc_player.get_length()
                if length_ms > 0:
                    position_ratio = (seconds * 1000.0) / length_ms
                    position_ratio = max(0.0, min(1.0, position_ratio))
                    self.vlc_player.set_position(position_ratio)
                    return True
            return False
        except Exception as e:
            print(f"Error setting position: {e}")
            return False
    
    def get_duration(self) -> Optional[float]:
        """Get video duration in seconds"""
        try:
            if self.vlc_player and VLC_PYTHON_AVAILABLE:
                length_ms = self.vlc_player.get_length()
                if length_ms > 0:
                    return length_ms / 1000.0
            return None
        except Exception as e:
            print(f"Error getting duration: {e}")
            return None
    
    def pause(self) -> bool:
        """Pause playback"""
        try:
            if self.vlc_player and VLC_PYTHON_AVAILABLE:
                self.vlc_player.pause()
                return True
            return False
        except Exception as e:
            print(f"Error pausing: {e}")
            return False
    
    def resume(self) -> bool:
        """Resume playback"""
        try:
            if self.vlc_player and VLC_PYTHON_AVAILABLE:
                self.vlc_player.play()
                return True
            return False
        except Exception as e:
            print(f"Error resuming: {e}")
            return False
    
    def _start_with_python_vlc(self) -> bool:
        """Start video using VLC Python bindings"""
        try:
            print("Starting VLC with Python bindings")
            
            # Create VLC instance with appropriate args
            vlc_args = self._get_vlc_args()
            self.vlc_instance = vlc.Instance(vlc_args)
            if not self.vlc_instance:
                raise VLCPlayerError("Failed to create VLC instance")
            
            self.vlc_player = self.vlc_instance.media_player_new()
            if not self.vlc_player:
                raise VLCPlayerError("Failed to create VLC player")
            
            # Load media and start playback
            self.vlc_media = self.vlc_instance.media_new(self.video_path)
            if not self.vlc_media:
                raise VLCPlayerError("Failed to create VLC media")
            
            self.vlc_player.set_media(self.vlc_media)
            
            # Start playback
            result = self.vlc_player.play()
            if result != 0:
                raise VLCPlayerError(f"VLC play() failed with code: {result}")
            
            # Handle window properties for debug mode
            if self.debug_mode:
                self._configure_debug_window()
            else:
                self.vlc_player.set_fullscreen(True)
            
            self.is_playing = True
            print("VLC playback started successfully")
            return True
            
        except Exception as e:
            print(f"Error with VLC Python: {e}")
            return False
    
    def _configure_debug_window(self) -> None:
        """Configure VLC window for debug mode - position on right side"""
        try:
            # Give VLC time to initialize window
            time.sleep(1)
            
            # Position video window on the right side
            # Debug overlay is on left (50, 50, 500x400)
            # Video should be on right side
            import subprocess
            
            # Try to set window position using wmctrl
            try:
                # Wait a bit more for VLC window to appear
                time.sleep(1)
                subprocess.run(['wmctrl', '-r', 'VLC', '-e', '0,600,50,1000,700'], 
                              capture_output=True, timeout=2)
                print("Positioned VLC window on right side")
            except Exception:
                # Fallback: try with xdotool
                try:
                    subprocess.run(['xdotool', 'search', '--name', 'VLC', 
                                   'windowmove', '600', '50', 
                                   'windowsize', '1000', '700'], 
                                  capture_output=True, timeout=2)
                    print("Positioned VLC window with xdotool")
                except Exception:
                    print("Could not position VLC window - tools not available")
                    
        except Exception as e:
            print(f"Error configuring debug window: {e}")
            
            self.is_playing = True
            print("✅ VLC playback started successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error with VLC Python: {e}")
            return False
    
    def _start_with_command_vlc(self) -> bool:
        """Start video using VLC command line"""
        try:
            print("Starting VLC with command line")
            
            cmd = ['vlc', '--intf', 'dummy']  # No interface
            cmd.extend(self._get_vlc_args())
            
            if self.debug_mode:
                cmd.extend([
                    '--no-fullscreen',
                    '--width=1000',
                    '--height=700',
                    '--video-x=600',
                    '--video-y=50',
                    '--no-video-deco',
                ])
            else:
                cmd.append('--fullscreen')
            
            cmd.append(self.video_path)
            
            self.command_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            
            # Give VLC time to start
            time.sleep(2)
            
            if self.command_process.poll() is None:
                self.is_playing = True
                print("✅ VLC command started successfully")
                return True
            else:
                stdout, stderr = self.command_process.communicate()
                print(f"❌ VLC process exited: {stdout.decode()}")
                if stderr:
                    print(f"❌ VLC stderr: {stderr.decode()}")
                return False
                
        except Exception as e:
            print(f"❌ Error with VLC command: {e}")
            return False
    
    def _get_vlc_args(self) -> list[str]:
        """Get VLC command line arguments"""
        return [
            '--no-video-title-show',
            '--no-osd',
            '--mouse-hide-timeout=0',
            '--no-snapshot-preview',
            '--network-caching=0',
            '--file-caching=300',
            '--vout=x11',
            '--aout=alsa',
            '--x11-display=:0',
        ]
    
    def _configure_debug_window(self) -> None:
        """Configure VLC window for debug mode"""
        if not VLC_PYTHON_AVAILABLE or not self.vlc_player:
            return
        
        try:
            # Wait for window to appear
            xid = None
            for attempt in range(30):  # 3 seconds max
                try:
                    xid = self.vlc_player.get_xwindow()
                    if xid and xid != 0:
                        break
                except:
                    pass
                time.sleep(0.1)
            
            if xid and xid != 0:
                # Use xdotool to resize and position window
                subprocess.run(['xdotool', 'windowsize', str(xid), '1520', '1080'])
                subprocess.run(['xdotool', 'windowmove', str(xid), '0', '0'])
                print(f"✅ Configured debug window: {xid}")
            else:
                print("⚠️ Could not get VLC window ID for debug configuration")
                
        except Exception as e:
            print(f"⚠️ Error configuring debug window: {e}")
    
    def cleanup(self) -> None:
        """Clean up resources"""
        self.stop_playback()
        
        try:
            if self.vlc_media:
                self.vlc_media.release()
            if self.vlc_player:
                self.vlc_player.release()
            if self.vlc_instance:
                self.vlc_instance.release()
        except Exception as e:
            print(f"Error during VLC cleanup: {e}")
        
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
