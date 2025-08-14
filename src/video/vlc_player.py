#!/usr/bin/env python3
"""
VLC Video Player Management for KitchenSync
Handles VLC video playback with sync capabilities
"""

import os
import subprocess
import time
import threading
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

    def __init__(
        self,
        debug_mode: bool = False,
        enable_vlc_logging: bool = False,
        vlc_log_level: int = 0,
    ):
        self.debug_mode = debug_mode
        self.enable_vlc_logging = enable_vlc_logging
        self.vlc_log_level = vlc_log_level
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self.video_path = None
        self.is_playing = False
        self.loop_count = 0
        self.enable_looping = True
        self.loop_callback = None
        self.video_output: Optional[str] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop_event: Optional[threading.Event] = None
        self._is_restarting: bool = False
        self._last_time_ms: int = -1
        self._last_time_check: float = 0.0

        # Check VLC availability once at init
        if not VLC_PYTHON_AVAILABLE:
            raise VLCPlayerError(
                "Python VLC bindings not available - required for KitchenSync"
            )

        # Log environment snapshot once when player is constructed (only if VLC logging enabled)
        if enable_vlc_logging:
            snapshot_env()

    def _ms_to_seconds(self, milliseconds: int) -> float:
        """Convert milliseconds to seconds"""
        return milliseconds / 1000.0 if milliseconds > 0 else 0.0

    def _seconds_to_position(self, seconds: float) -> float:
        """Convert seconds to VLC position ratio (0.0-1.0)"""
        if not self.vlc_player:
            return 0.0
        length_ms = self.vlc_player.get_length()
        if length_ms > 0:
            position_ratio = (seconds * 1000.0) / length_ms
            return max(0.0, min(1.0, position_ratio))
        return 0.0

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

        return self._start_with_python_vlc()

    def stop_playback(self) -> None:
        """Stop video playback"""
        try:
            # Stop monitor thread first
            if self._monitor_stop_event is not None:
                try:
                    self._monitor_stop_event.set()
                except Exception:
                    pass
            if self._monitor_thread is not None and self._monitor_thread.is_alive():
                try:
                    self._monitor_thread.join(timeout=1.0)
                except Exception:
                    pass
            self._monitor_thread = None
            self._monitor_stop_event = None

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
        if not self.is_playing or not self.vlc_player:
            return None

        try:
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
        if not self.vlc_player:
            return False
        try:
            position_ratio = self._seconds_to_position(seconds)
            if position_ratio >= 0:
                self.vlc_player.set_position(position_ratio)
                return True
            return False
        except Exception as e:
            log_error(f"Error setting position: {e}", component="vlc")
            return False

    def get_duration(self) -> Optional[float]:
        """Get video duration in seconds"""
        if not self.vlc_player:
            return None
        try:
            length_ms = self.vlc_player.get_length()
            return self._ms_to_seconds(length_ms) if length_ms > 0 else None
        except Exception as e:
            log_error(f"Error getting duration: {e}", component="vlc")
            return None

    def pause(self) -> bool:
        """Pause playback"""
        if not self.vlc_player:
            return False
        try:
            self.vlc_player.pause()
            return True
        except Exception as e:
            log_error(f"Error pausing: {e}", component="vlc")
            return False

    def resume(self) -> bool:
        """Resume playback"""
        if not self.vlc_player:
            return False
        try:
            self.vlc_player.play()
            return True
        except Exception as e:
            log_error(f"Error resuming: {e}", component="vlc")
            return False

    def _restart_loop(self) -> None:
        """Restart video from beginning and notify loop callback."""
        if not self.enable_looping or not self.vlc_player:
            return
        if self._is_restarting:
            return
        self._is_restarting = True
        try:
            # Notify callback first so MIDI and state reset before video resumes
            self.loop_count += 1
            if self.loop_callback:
                try:
                    self.loop_callback(self.loop_count)
                except Exception as e:
                    log_error(f"Error in video loop callback: {e}", component="vlc")

            # Flicker-free restart: avoid stop(); pause → seek → resume
            # If player is in Ended state, re-attach media first
            try:
                if self.vlc_player.get_state() == vlc.State.Ended and self.vlc_media:
                    self.vlc_player.set_media(self.vlc_media)
            except Exception:
                pass

            # Pause before seeking back to 0
            try:
                self.vlc_player.set_pause(1)
            except Exception:
                pass

            # Try to reset to time 0; fallback to position if needed
            reset_ok = False
            try:
                # set_time expects milliseconds
                self.vlc_player.set_time(0)
                reset_ok = True
            except Exception:
                pass
            if not reset_ok:
                try:
                    self.set_position(0.0)
                except Exception:
                    pass

            # Resume playback without tearing
            try:
                self.vlc_player.set_pause(0)
            except Exception:
                try:
                    self.vlc_player.play()
                except Exception:
                    pass

            # Re-assert fullscreen in production (no toggle flicker)
            try:
                if not self.debug_mode:
                    if not self.vlc_player.get_fullscreen():
                        self.vlc_player.set_fullscreen(True)
            except Exception:
                pass

            self.is_playing = True
            log_info(f"Restarted video loop #{self.loop_count}", component="vlc")
        except Exception as e:
            log_error(f"Error restarting loop: {e}", component="vlc")
        finally:
            self._is_restarting = False

    def _start_monitoring(self) -> None:
        """Start a background monitor to enforce reliable looping."""
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return
        self._monitor_stop_event = threading.Event()

                def monitor_loop():
            debug_counter = 0
            while self._monitor_stop_event and not self._monitor_stop_event.is_set():
                try:
                    if not self.vlc_player:
                        break
                    state = self.vlc_player.get_state()
                    # get_position returns 0..1, or -1 if unknown
                    try:
                        pos = float(self.vlc_player.get_position())
                    except Exception:
                        pos = -1.0
                    # Use absolute time as primary end detection
                    try:
                        cur_ms = int(self.vlc_player.get_time())
                    except Exception:
                        cur_ms = -1
                    try:
                        len_ms = int(self.vlc_player.get_length())
                    except Exception:
                        len_ms = -1

                    # Debug output every 50 cycles (~10s at 0.2s intervals)
                    debug_counter += 1
                    if debug_counter % 50 == 0 or debug_counter <= 5:
                        print(f"🔍 VLC DEBUG: state={state}, pos={pos:.3f}, time={cur_ms}ms/{len_ms}ms, last={self._last_time_ms}ms")

                    # Detect natural wrap-around (VLC internal repeat) and invoke callback only
                    if len_ms > 0 and self.enable_looping:
                        # Initialize tracking on first valid time
                        if self._last_time_ms < 0 and cur_ms >= 0:
                            self._last_time_ms = cur_ms
                            self._last_time_check = time.time()
                            print(f"🔍 VLC DEBUG: Initialized tracking at {cur_ms}ms")
                        
                        # Loop edge: previous time was near end and current is near start
                        if (
                            self._last_time_ms >= 0
                            and cur_ms >= 0
                            and self._last_time_ms > (len_ms - 400)
                            and cur_ms < 400
                        ):
                            try:
                                self.loop_count += 1
                                if self.loop_callback:
                                    self.loop_callback(self.loop_count)
                                print(f"🔄 VLC DEBUG: Detected natural loop edge (#{self.loop_count}) - {self._last_time_ms}ms -> {cur_ms}ms")
                                log_info(
                                    f"Detected natural loop edge (#{self.loop_count})",
                                    component="vlc",
                                )
                            except Exception as e:
                                print(f"❌ VLC DEBUG: Loop callback error: {e}")
                                log_error(f"Loop callback error: {e}", component="vlc")

                        # Check for stalls near end
                        if cur_ms >= 0 and len_ms > 0 and cur_ms > (len_ms - 1000):
                            if cur_ms == self._last_time_ms:
                                stall_time = time.time() - self._last_time_check
                                if stall_time > 0.5:
                                    print(f"⚠️ VLC DEBUG: Stalled at {cur_ms}ms for {stall_time:.1f}s (near end)")
                            else:
                                self._last_time_ms = cur_ms
                                self._last_time_check = time.time()
                        else:
                            # Update tracking normally
                            if cur_ms != self._last_time_ms:
                                self._last_time_ms = cur_ms
                                self._last_time_check = time.time()
                except Exception as e:
                    print(f"❌ VLC DEBUG: Monitor exception: {e}")
                time.sleep(0.2)

        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()

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

            # Enable seamless looping in VLC and monitor for loop edges
            if self.enable_looping:
                try:
                    # Loop indefinitely at the media level (seamless)
                    self.vlc_media.add_option(":input-repeat=-1")
                except Exception:
                    pass
                self._start_monitoring()

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
                        log_warning(
                            "Fullscreen not active, trying again", component="vlc"
                        )
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
        """Get optimized VLC arguments for Raspberry Pi hardware acceleration"""
        args = [
            # Essential settings for performance
            "--no-video-title-show",
            # Hardware acceleration for Raspberry Pi performance
            "--avcodec-hw=any",  # Enable hardware decoding (CRITICAL for performance)
            "--codec=avcodec",  # Use avcodec for better hardware support
            # Video output optimization
            "--vout=gl",  # Use OpenGL video output for hardware acceleration
            "--no-audio",  # Disable audio for video-only playback (reduces load)
        ]

        # Add logging only if enabled (default: disabled for performance)
        if self.enable_vlc_logging:
            paths = log_file_paths()
            args.extend(
                [
                    "--file-logging",
                    f"--logfile={paths['vlc_main']}",
                    f"--verbose={self.vlc_log_level}",  # Use configurable log level
                ]
            )
        else:
            # Minimal logging - errors only
            args.extend(
                [
                    "--quiet",  # Suppress most output
                    "--verbose=0",  # Only critical errors
                ]
            )

        # Override video output if explicitly specified
        if self.video_output:
            # Replace the default --vout=gl with specified output
            args = [arg for arg in args if not arg.startswith("--vout")]
            args.extend(["--vout", self.video_output])

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
            "is_playing": self.is_playing,
            "state": "stopped",
            "loop_count": self.loop_count,
            "looping_enabled": self.enable_looping,
        }

        if not self.vlc_player:
            return info

        try:
            # Get current playback time
            current_ms = self.vlc_player.get_time()
            if current_ms >= 0:
                info["current_time"] = self._ms_to_seconds(current_ms)

            # Get total video length
            length_ms = self.vlc_player.get_length()
            if length_ms > 0:
                info["total_time"] = self._ms_to_seconds(length_ms)

            # Get position as percentage (0.0 to 1.0)
            position = self.vlc_player.get_position()
            if position >= 0:
                info["position"] = position

            # Get player state
            state = self.vlc_player.get_state()
            if state:
                info["state"] = str(state).split(".")[-1].lower()
                info["is_playing"] = state == vlc.State.Playing

        except Exception as e:
            log_error(f"Error getting video info: {e}", component="vlc")

        return info
