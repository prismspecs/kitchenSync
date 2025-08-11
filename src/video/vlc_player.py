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

        if VLC_PYTHON_AVAILABLE:
            return self._start_with_python_vlc()
        else:
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

    def _start_with_python_vlc(self) -> bool:
        """Start video using VLC Python bindings"""
        try:
            log_info("Starting VLC with Python bindings", component="vlc")

            # Create VLC instance with appropriate args
            vlc_args = self._get_vlc_args()
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

            # Start playback
            self.vlc_player.play()

            # Force VLC window positioning after it starts
            self._force_vlc_position()

            log_info("VLC playback started successfully")
            return True

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
            time.sleep(3)

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

            # Try with audio first
            cmd = ["vlc", "--intf", "dummy"]  # No interface
            cmd.extend(self._get_vlc_args())

            # Use consistent positioning - left side for VLC
            cmd.extend(
                [
                    "--no-fullscreen",
                    "--width=1280",
                    "--height=720",
                    "--video-x=0",  # Left side of screen
                    "--video-y=0",  # Top of screen
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
            time.sleep(3)

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

            cmd = ["vlc", "--intf", "dummy"]  # No interface
            cmd.extend(self._get_vlc_args_no_audio())

            # Use consistent positioning - left side for VLC
            cmd.extend(
                [
                    "--no-fullscreen",
                    "--width=1280",
                    "--height=720",
                    "--video-x=0",  # Left side of screen
                    "--video-y=0",  # Top of screen
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
        return [
            # Window positioning - place VLC on left side, leave space for debug overlay
            "--no-fullscreen",
            "--width=1280",
            "--height=720",
            "--video-x=0",  # Left side of screen
            "--video-y=0",  # Top of screen
            "--no-video-deco",  # No window decorations
            # Minimal config - let VLC use defaults
            "--file-logging",
            f"--logfile={paths['vlc_main']}",
            "--verbose=2",
        ]

    def _get_vlc_args_no_audio(self) -> list[str]:
        """Get VLC command line arguments with audio disabled (fallback)"""
        paths = log_file_paths()
        return [
            # Minimal config - let VLC use defaults
            "--aout=dummy",  # Use dummy audio to prevent ALSA crashes
            "--no-audio",  # Disable audio output completely
            "--file-logging",
            f"--logfile={paths['vlc_main']}",
            "--verbose=2",
        ]

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
