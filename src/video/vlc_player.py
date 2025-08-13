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
    """VLC-based video player with sync capabilities"""

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self.video_path = None
        self.is_playing = False
        self.command_process = None  # For command-line VLC
        self.loop_count = 0  # Track number of loops completed
        self.enable_looping = True  # Enable continuous looping
        self.loop_callback = None  # Callback function when video loops
        # Engine/behavior overrides
        self.force_python = False  # Force Python VLC engine regardless of debug mode
        self.force_fullscreen = False  # Force fullscreen even in debug
        self.video_output: Optional[str] = None  # e.g., "x11", "glx", "xvideo"
        self.use_position_seeking = False  # Use position ratio instead of time seeking
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
        """Start video playback"""
        if not self.video_path:
            raise VLCPlayerError("No video loaded")

        # Engine selection
        if self.force_python and VLC_PYTHON_AVAILABLE:
            return self._start_with_python_vlc()

        # Default behavior: CLI in production, Python in debug (if available)
        if not self.debug_mode:
            log_info(
                "Production mode: using command-line VLC for fullscreen",
                component="vlc",
            )
            return self._start_with_command_vlc()
        else:
            if VLC_PYTHON_AVAILABLE:
                return self._start_with_python_vlc()
            return self._start_with_command_vlc()

    def stop_playback(self) -> None:
        """Stop video playback"""
        try:
            if self.vlc_player:
                self.vlc_player.stop()
                log_info("Stopped VLC Python player", component="vlc")

            if self.command_process:
                self.command_process.terminate()
                self.command_process = None
                log_info("Stopped VLC command process", component="vlc")

            # Kill any remaining VLC processes
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
                if self.use_position_seeking:
                    # Position-based seeking (ratio 0.0-1.0)
                    length_ms = self.vlc_player.get_length()
                    if length_ms > 0:
                        position_ratio = (seconds * 1000.0) / length_ms
                        position_ratio = max(0.0, min(1.0, position_ratio))
                        self.vlc_player.set_position(position_ratio)
                        return True
                else:
                    # Time-based seeking (milliseconds)
                    time_ms = int(seconds * 1000)
                    self.vlc_player.set_time(time_ms)
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
                    log_info(
                        "DISPLAY not set; forcing DISPLAY=:0 for VLC", component="vlc"
                    )
            except Exception:
                pass

            # Create VLC instance with appropriate args
            vlc_args = self._get_vlc_args()
            log_info(f"VLC python args: {' '.join(vlc_args)}", component="vlc")

            # Check if VLC Python bindings are available
            if not VLC_PYTHON_AVAILABLE:
                log_warning(
                    "VLC Python bindings not available, falling back to command line",
                    component="vlc",
                )
                return self._start_with_command_vlc()

            self.vlc_instance = vlc.Instance(vlc_args)
            if not self.vlc_instance:
                log_error("Failed to create VLC instance", component="vlc")
                return self._start_with_command_vlc()

            self.vlc_player = self.vlc_instance.media_player_new()
            if not self.vlc_player:
                log_error("Failed to create VLC player", component="vlc")
                return self._start_with_command_vlc()

            # Load media and start playback
            self.vlc_media = self.vlc_instance.media_new(self.video_path)
            if not self.vlc_media:
                log_error("Failed to create VLC media", component="vlc")
                return self._start_with_command_vlc()

            self.vlc_player.set_media(self.vlc_media)

            # Set up looping event handler
            if self.enable_looping:
                events = self.vlc_player.event_manager()
                events.event_attach(
                    vlc.EventType.MediaPlayerEndReached, self._on_video_end
                )
                log_info("Video looping enabled", component="vlc")

            # Start playback
            log_info("Starting VLC playback...", component="vlc")
            result = self.vlc_player.play()
            log_info(f"VLC play() returned: {result}", component="vlc")

            if result == 0:
                log_info("VLC playback started successfully", component="vlc")
                self.is_playing = True
                # Enable fullscreen when requested even in debug mode
                try:
                    if (not self.debug_mode) or self.force_fullscreen:
                        self.vlc_player.set_fullscreen(True)
                        log_info("Enabled fullscreen in Python VLC", component="vlc")
                except Exception as e:
                    log_warning(
                        f"Failed to set fullscreen in Python VLC: {e}", component="vlc"
                    )
                return True
            else:
                log_error(f"VLC play() failed with code: {result}", component="vlc")
                return self._start_with_command_vlc()

        except Exception as e:
            log_error(f"Error with VLC Python: {e}", component="vlc")
            log_info("Falling back to command-line VLC", component="vlc")
            return self._start_with_command_vlc()

    def _force_vlc_position(self):
        """Force VLC window to the left side using wmctrl"""
        try:
            import subprocess
            import time

            # Wait for VLC window to appear
            time.sleep(1)

            # Find VLC windows and force position
            result = subprocess.run(
                ["wmctrl", "-l"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "vlc" in line.lower() or "test_video" in line.lower():
                        parts = line.split()
                        if len(parts) >= 2:
                            window_id = parts[0]
                            # Force VLC to left side: x=0, y=0, width=1280, height=720
                            subprocess.run(
                                ["wmctrl", "-ir", window_id, "-e", "0,0,0,1280,720"],
                                check=False,
                                timeout=5,
                            )
                            log_info(
                                f"Forced VLC window {window_id} to left side (0,0,1280,720)"
                            )

                            # Bring to front
                            subprocess.run(
                                ["wmctrl", "-ia", window_id], check=False, timeout=5
                            )

        except Exception as e:
            log_warning(f"Failed to force VLC window position: {e}")

    def _start_with_command_vlc(self) -> bool:
        """Start video using VLC command line"""
        try:
            log_info("Starting VLC with command line", component="vlc")
            # Ensure DISPLAY for GUI output when invoked via SSH
            try:
                if not os.environ.get("DISPLAY"):
                    os.environ["DISPLAY"] = ":0"
                    log_info(
                        "DISPLAY not set; forcing DISPLAY=:0 for CLI VLC",
                        component="vlc",
                    )
            except Exception:
                pass

            # Try with audio first
            cmd = ["vlc", "--intf", "dummy"]  # No interface
            cmd.extend(self._get_vlc_args())

            # Add looping if enabled
            if self.enable_looping:
                cmd.append("--repeat")  # Loop indefinitely
                log_info("Command-line VLC looping enabled", component="vlc")

            # Window configuration based on debug mode
            if self.debug_mode:
                # Debug mode: windowed on left side for overlay
                cmd.extend(
                    [
                        "--no-fullscreen",
                        "--width=1280",
                        "--height=1080",
                        "--video-x=0",  # Left side of screen
                        "--video-y=0",  # Top of screen
                        "--no-video-deco",
                    ]
                )
            else:
                # Production mode: fullscreen
                cmd.extend(
                    [
                        "--fullscreen",
                        "--no-video-deco",
                    ]
                )

            cmd.append(self.video_path)

            # Capture stdout/stderr to files for diagnostics
            paths = log_file_paths()
            stdout_path = paths["vlc_stdout"]
            stderr_path = paths["vlc_stderr"]
            self.command_process = subprocess.Popen(
                cmd,
                stdout=open(stdout_path, "wb"),
                stderr=open(stderr_path, "wb"),
            )
            log_info(f"Launched VLC with audio: {' '.join(cmd)}", component="vlc")

            # Give VLC time to start
            time.sleep(1)

            if self.command_process.poll() is None:
                self.is_playing = True
                log_info("VLC command started successfully with audio", component="vlc")
                return True
            else:
                log_warning(
                    "VLC with audio failed, trying without audio", component="vlc"
                )
                return self._start_with_command_vlc_no_audio()

        except Exception as e:
            log_error(f"Error with VLC command: {e}", component="vlc")
            log_warning("Trying VLC without audio as last resort", component="vlc")
            return self._start_with_command_vlc_no_audio()

    def _start_with_command_vlc_no_audio(self) -> bool:
        """Start video using VLC command line without audio (fallback)"""
        try:
            log_info("Starting VLC without audio (fallback)", component="vlc")
            # Ensure DISPLAY for GUI output when invoked via SSH
            try:
                if not os.environ.get("DISPLAY"):
                    os.environ["DISPLAY"] = ":0"
                    log_info(
                        "DISPLAY not set; forcing DISPLAY=:0 for CLI VLC (no audio)",
                        component="vlc",
                    )
            except Exception:
                pass

            cmd = ["vlc", "--intf", "dummy"]  # No interface
            cmd.extend(self._get_vlc_args_no_audio())

            # Add looping if enabled
            if self.enable_looping:
                cmd.append("--repeat")  # Loop indefinitely
                log_info("Command-line VLC looping enabled (no audio)", component="vlc")

            # Window configuration based on debug mode
            if self.debug_mode:
                # Debug mode: windowed on left side for overlay
                cmd.extend(
                    [
                        "--no-fullscreen",
                        "--width=1280",
                        "--height=1080",
                        "--video-x=0",  # Left side of screen
                        "--video-y=0",  # Top of screen
                        "--no-video-deco",
                    ]
                )
            else:
                # Production mode: fullscreen
                cmd.extend(
                    [
                        "--fullscreen",
                        "--no-video-deco",
                    ]
                )

            cmd.append(self.video_path)

            # Capture stdout/stderr to files for diagnostics
            paths = log_file_paths()
            stdout_path = paths["vlc_stdout"]
            stderr_path = paths["vlc_stderr"]
            self.command_process = subprocess.Popen(
                cmd,
                stdout=open(stdout_path, "wb"),
                stderr=open(stderr_path, "wb"),
            )
            log_info(f"Launched VLC without audio: {' '.join(cmd)}", component="vlc")

            # Give VLC time to start
            time.sleep(3)

            if self.command_process.poll() is None:
                self.is_playing = True
                log_info(
                    "VLC command started successfully without audio", component="vlc"
                )
                return True
            else:
                log_error(
                    "VLC command process failed even without audio", component="vlc"
                )
                return False

        except Exception as e:
            log_error(f"Error with VLC command (no audio): {e}", component="vlc")
            return False

    def _get_vlc_args(self) -> list[str]:
        """Get VLC command line arguments"""
        paths = log_file_paths()
        args = [
            # Simple, working VLC configuration
            "--file-logging",
            f"--logfile={paths['vlc_main']}",
            "--verbose=2",
            "--no-video-title-show",
        ]

        # Prefer explicit video output plugin if provided
        if self.video_output:
            args.extend(["--vout", self.video_output])

        # Keep hardware acceleration enabled for performance

        # Add fullscreen for production mode
        if not self.debug_mode:
            args.extend(
                [
                    "--fullscreen",
                    "--no-video-deco",
                ]
            )

        return args

    def _get_vlc_args_no_audio(self) -> list[str]:
        """Get VLC command line arguments with audio disabled (fallback)"""
        paths = log_file_paths()
        args = [
            # Minimal config - let VLC use defaults
            "--aout=dummy",  # Use dummy audio to prevent ALSA crashes
            "--no-audio",  # Disable audio output completely
            "--file-logging",
            f"--logfile={paths['vlc_main']}",
            "--verbose=2",
            "--no-video-title-show",
        ]

        # Prefer explicit video output plugin if provided
        if self.video_output:
            args.extend(["--vout", self.video_output])

        # Add fullscreen for production mode
        if not self.debug_mode:
            args.extend(
                [
                    "--fullscreen",
                    "--no-video-deco",
                ]
            )

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
