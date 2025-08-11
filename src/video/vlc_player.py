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
            result = self.vlc_player.play()
            if result != 0:
                raise VLCPlayerError(f"VLC play() failed with code: {result}")

            # Handle window properties for debug mode
            if self.debug_mode:
                self._configure_debug_window()
            else:
                self.vlc_player.set_fullscreen(True)

            self.is_playing = True
            log_info("VLC playback started successfully", component="vlc")
            return True

        except Exception as e:
            log_error(f"Error with VLC Python: {e}", component="vlc")
            log_info("Falling back to command-line VLC", component="vlc")
            return self._start_with_command_vlc()

    def _start_with_command_vlc(self) -> bool:
        """Start video using VLC command line"""
        try:
            log_info("Starting VLC with command line", component="vlc")

            # Try with audio first
            cmd = ["vlc", "--intf", "dummy"]  # No interface
            cmd.extend(self._get_vlc_args())

            if self.debug_mode:
                # Place video on the right leaving space at left/top for overlay
                cmd.extend(
                    [
                        "--no-fullscreen",
                        "--width=1440",
                        "--height=900",
                        "--video-x=460",
                        "--video-y=60",
                        "--no-video-deco",
                    ]
                )
            else:
                cmd.append("--fullscreen")

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

            if self.debug_mode:
                # Place video on the right leaving space at left/top for overlay
                cmd.extend(
                    [
                        "--no-fullscreen",
                        "--width=1440",
                        "--height=900",
                        "--video-x=460",
                        "--video-y=60",
                        "--no-video-deco",
                    ]
                )
            else:
                cmd.append("--fullscreen")

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
            "--no-video-title-show",
            "--no-osd",
            "--mouse-hide-timeout=0",
            "--no-snapshot-preview",
            "--network-caching=0",
            "--file-caching=300",
            # Minimal config - let VLC auto-detect everything for Pi compatibility
            "--aout=alsa",
            "--file-logging",
            f"--logfile={paths['vlc_main']}",
            "--verbose=2",
        ]

    def _get_vlc_args_no_audio(self) -> list[str]:
        """Get VLC command line arguments with audio disabled (fallback)"""
        paths = log_file_paths()
        return [
            "--no-video-title-show",
            "--no-osd",
            "--mouse-hide-timeout=0",
            "--no-snapshot-preview",
            "--network-caching=0",
            "--file-caching=300",
            # Minimal config - let VLC auto-detect everything for Pi compatibility
            "--aout=dummy",  # Use dummy audio to prevent ALSA crashes
            "--no-audio",  # Disable audio output completely
            "--file-logging",
            f"--logfile={paths['vlc_main']}",
            "--verbose=2",
        ]

    def _configure_debug_window(self) -> None:
        """Configure VLC window for debug mode: position to the right side"""
        if not VLC_PYTHON_AVAILABLE or not self.vlc_player:
            return

        try:
            # Wait for window to appear and get XID (X11 only)
            xid = None
            for _ in range(40):  # ~4 seconds max
                try:
                    xid = self.vlc_player.get_xwindow()
                    if xid and xid != 0:
                        break
                except Exception:
                    pass
                time.sleep(0.1)

            if not xid:
                log_warning(
                    "Could not get VLC window ID for debug configuration",
                    component="vlc",
                )
                return

            # Compute a safe region for video (leave left/top margin for overlay)
            video_x = 460
            video_y = 60
            video_w = 1440
            video_h = 900

            # Try xdotool first (most predictable)
            try:
                subprocess.run(
                    ["xdotool", "windowsize", str(xid), str(video_w), str(video_h)],
                    capture_output=True,
                    timeout=1,
                )
                subprocess.run(
                    ["xdotool", "windowmove", str(xid), str(video_x), str(video_y)],
                    capture_output=True,
                    timeout=1,
                )
                log_info(
                    f"Configured debug window via xdotool: xid={xid}", component="vlc"
                )
                return
            except Exception:
                pass

            # Fallback to wmctrl by matching VLC title
            try:
                subprocess.run(
                    [
                        "wmctrl",
                        "-r",
                        "VLC",
                        "-e",
                        f"0,{video_x},{video_y},{video_w},{video_h}",
                    ],
                    capture_output=True,
                    timeout=1,
                )
                log_info("Configured debug window via wmctrl", component="vlc")
            except Exception:
                log_warning(
                    "Could not position VLC window - xdotool/wmctrl not available",
                    component="vlc",
                )
        except Exception as e:
            log_warning(f"Error configuring debug window: {e}", component="vlc")

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
