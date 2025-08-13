#!/usr/bin/env python3
"""
VLC Video Player Management for KitchenSync
Handles VLC video playback with sync capabilities
"""

import os
import subprocess
import time
from typing import Optional
from core.logger import log_info, log_error, log_warning, snapshot_env, log_file_paths

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
    """VLC-based video player with sync capabilities using Python VLC bindings"""

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self.video_path = None
        self.is_playing = False
        self.loop_count = 0  # Track number of loops completed
        self.enable_looping = True  # Enable continuous looping
        self.loop_callback = None  # Callback function when video loops
        self.video_output: Optional[str] = None  # e.g., "x11", "glx", "xvideo"
        # Log environment snapshot once when player is constructed
        snapshot_env()

    def load_video(self, video_path: str) -> bool:
        """Load a video file"""
        if not os.path.exists(video_path):
            raise VLCPlayerError(f"Video file not found: {video_path}")

        self.video_path = video_path
        log_info(f"Loaded video: {video_path}", component="vlc")
        return True

    def start_playback(self) -> bool:
        """Start video playback using Python VLC bindings"""
        if not self.video_path:
            raise VLCPlayerError("No video loaded")

        # Always use Python VLC for consistent behavior
        if not VLC_PYTHON_AVAILABLE:
            raise VLCPlayerError("Python VLC bindings not available - required for KitchenSync")

        return self._start_with_python_vlc()

    def stop_playback(self) -> None:
        """Stop video playback"""
        try:
            if self.vlc_player:
                self.vlc_player.stop()
                log_info("Stopped VLC Python player", component="vlc")

            # Kill any remaining VLC processes as safety measure
            subprocess.run(["pkill", "vlc"], capture_output=True)

            self.is_playing = False
        except Exception as e:
            log_error(f"Error stopping video: {e}", component="vlc")

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
            log_error(f"Error getting position: {e}", component="vlc")
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
            log_error(f"Error setting position: {e}", component="vlc")
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
            log_error(f"Error getting duration: {e}", component="vlc")
            return None

    def pause(self) -> bool:
        """Pause playback"""
        try:
            if self.vlc_player and VLC_PYTHON_AVAILABLE:
                self.vlc_player.pause()
                return True
            return False
        except Exception as e:
            log_error(f"Error pausing: {e}", component="vlc")
            return False

    def resume(self) -> bool:
        """Resume playback"""
        try:
            if self.vlc_player and VLC_PYTHON_AVAILABLE:
                self.vlc_player.play()
                return True
            return False
        except Exception as e:
            log_error(f"Error resuming: {e}", component="vlc")
            return False

    def _on_video_end(self, event):
        """Handle video end event for looping"""
        if self.enable_looping and self.vlc_player:
            try:
                self.loop_count += 1
                log_info(
                    f"Video ended, starting loop #{self.loop_count}", component="vlc"
                )

                # Notify callback before restarting (for MIDI sync)
                if self.loop_callback:
                    try:
                        self.loop_callback(self.loop_count)
                    except Exception as e:
                        log_error(f"Error in video loop callback: {e}", component="vlc")

                # Reset to beginning and restart
                self.vlc_player.set_position(0.0)
                self.vlc_player.play()

                log_info(f"Video loop #{self.loop_count} started", component="vlc")
            except Exception as e:
                log_error(f"Error restarting video loop: {e}", component="vlc")

    def _start_with_python_vlc(self) -> bool:
        """Start video using VLC Python bindings"""
        try:
            log_info("Starting VLC with Python bindings", component="vlc")

            # Ensure a GUI display exists when launched via SSH
            try:
                if not os.environ.get("DISPLAY"):
                    os.environ["DISPLAY"] = ":0"
                    log_info("DISPLAY not set; forcing DISPLAY=:0 for VLC", component="vlc")
            except Exception:
                pass

            # Create VLC instance with appropriate args
            vlc_args = self._get_python_vlc_args()
            log_info(f"VLC python args: {' '.join(vlc_args)}", component="vlc")

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

            # Set up looping event handler
            if self.enable_looping:
                events = self.vlc_player.event_manager()
                events.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_video_end)
                log_info("Video looping enabled", component="vlc")

            # Start playback
            log_info("Starting VLC playback...", component="vlc")
            result = self.vlc_player.play()
            log_info(f"VLC play() returned: {result}", component="vlc")

            if result != 0:
                raise VLCPlayerError(f"VLC play() failed with code: {result}")

            log_info("VLC playback started successfully", component="vlc")
            self.is_playing = True
            
            # Set fullscreen mode for production or when specifically requested
            try:
                if not self.debug_mode:
                    # Wait a moment for VLC to initialize window
                    time.sleep(0.5)
                    self.vlc_player.set_fullscreen(True)
                    log_info("Enabled fullscreen in production mode", component="vlc")
                    # Double-check fullscreen is enabled
                    time.sleep(0.2)
                    if not self.vlc_player.get_fullscreen():
                        log_warning("Fullscreen not active, trying again", component="vlc")
                        self.vlc_player.set_fullscreen(True)
                else:
                    log_info("Debug mode: running in windowed mode", component="vlc")
            except Exception as e:
                log_warning(f"Failed to set fullscreen mode: {e}", component="vlc")
            
            return True

        except Exception as e:
            log_error(f"Error with VLC Python: {e}", component="vlc")
            raise VLCPlayerError(f"Failed to start VLC: {e}")



    def _get_python_vlc_args(self) -> list[str]:
        """Get VLC arguments for Python VLC instance"""
        paths = log_file_paths()
        args = [
            # Basic logging
            "--file-logging",
            f"--logfile={paths['vlc_main']}",
            "--verbose=2",
            "--no-video-title-show",
        ]

        # Prefer explicit video output plugin if provided
        if self.video_output:
            args.extend(["--vout", self.video_output])

        # For seeking compatibility, use software decoding for reliable position control
        args.extend([
            "--avcodec-hw=none",  # Disable hardware decoding for seeking reliability
        ])

        return args

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
            log_error(f"Error during VLC cleanup: {e}", component="vlc")

        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None

    def get_video_info(self) -> dict:
        """Get current video playback information"""
        info = {
            "current_time": 0.0,
            "total_time": 0.0,
            "position": 0.0,
            "is_playing": False,
            "state": "stopped",
            "loop_count": self.loop_count,
            "looping_enabled": self.enable_looping,
        }

        try:
            if self.vlc_player:
                # Get current playback time in seconds
                current_ms = self.vlc_player.get_time()
                if current_ms >= 0:
                    info["current_time"] = current_ms / 1000.0

                # Get total video length in seconds
                length_ms = self.vlc_player.get_length()
                if length_ms > 0:
                    info["total_time"] = length_ms / 1000.0

                # Get position as percentage (0.0 to 1.0)
                position = self.vlc_player.get_position()
                if position >= 0:
                    info["position"] = position

                # Get player state
                if VLC_PYTHON_AVAILABLE:
                    import vlc

                    state = self.vlc_player.get_state()
                    if state:
                        info["state"] = (
                            str(state).split(".")[-1].lower()
                        )  # Extract state name
                        info["is_playing"] = state == vlc.State.Playing

        except Exception as e:
            log_error(f"Error getting video info: {e}", component="vlc")

        return info
