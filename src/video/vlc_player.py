#!/usr/bin/env python3
"""
VLC Video Player Management for KitchenSync
Handles VLC video playback with sync capabilities
"""

import os
import threading
import subprocess
import time
from typing import Optional
from core.logger import log_info, log_error, log_warning, snapshot_env, log_file_paths
from enum import Enum

# Try to import VLC Python bindings
try:
    import vlc

    VLC_PYTHON_AVAILABLE = True
except ImportError:
    VLC_PYTHON_AVAILABLE = False


class LoopStrategy(Enum):
    """Enum for VLC loop strategies"""

    NATURAL = "natural"  # Use VLC's built-in :input-repeat
    MANUAL = "manual"  # Use event handler to restart video


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
        enable_fullscreen_enforcement: bool = True,
        enable_looping: bool = True,
        loop_strategy: LoopStrategy = LoopStrategy.NATURAL,
    ):
        self.debug_mode = debug_mode
        self.enable_vlc_logging = enable_vlc_logging
        self.vlc_log_level = vlc_log_level
        self.enable_fullscreen_enforcement = enable_fullscreen_enforcement
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self.video_path = None
        self.is_playing = False
        self.loop_count = 0
        self.enable_looping = enable_looping
        self.loop_strategy = loop_strategy
        self.loop_callback = None
        self.video_output: Optional[str] = None
        self.fullscreen_enforcement_thread = None
        self.should_be_fullscreen = False
        self.debug_mode = debug_mode
        self.enable_vlc_logging = enable_vlc_logging
        self.vlc_log_level = vlc_log_level
        self.enable_fullscreen_enforcement = enable_fullscreen_enforcement
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self.video_path = None
        self.is_playing = False
        self.loop_count = 0
        self.enable_looping = enable_looping
        self.loop_strategy = loop_strategy
        self.loop_callback = None
        self.video_output: Optional[str] = None
        self.fullscreen_enforcement_thread = None
        self.should_be_fullscreen = False

        # Check VLC availability once at init
        if not VLC_PYTHON_AVAILABLE:
            raise VLCPlayerError(
                "Python VLC bindings not available - required for KitchenSync"
            )

        # Log environment snapshot once when player is constructed (only if VLC logging enabled)
        if enable_vlc_logging:
            snapshot_env()

    def _enforce_fullscreen_periodically(self) -> None:
        """Periodically check and enforce fullscreen mode - optimized for minimal overhead"""
        check_count = 0
        while self.is_playing and self.should_be_fullscreen and self.vlc_player:
            try:
                # Adaptive checking: More frequent checks initially, then back off
                if check_count < 5:
                    # First 10 seconds: check every 2 seconds
                    time.sleep(2.0)
                elif check_count < 15:
                    # Next 20 seconds: check every 4 seconds
                    time.sleep(4.0)
                else:
                    # After 30 seconds: check every 10 seconds (very low overhead)
                    time.sleep(10.0)

                check_count += 1

                if not self.is_playing or not self.should_be_fullscreen:
                    break

                # Quick, lightweight check
                try:
                    is_fullscreen = self.vlc_player.get_fullscreen()
                except Exception:
                    # If we can't check, assume it's fine to avoid errors
                    continue

                if not is_fullscreen:
                    log_warning(
                        "VLC window not in fullscreen, re-enabling", component="vlc"
                    )
                    self.vlc_player.set_fullscreen(True)

                    # Quick verification without extra delay
                    time.sleep(0.05)  # Reduced from 0.1s
                    try:
                        if self.vlc_player.get_fullscreen():
                            log_info(
                                "Successfully restored fullscreen mode", component="vlc"
                            )
                        else:
                            log_error(
                                "Failed to restore fullscreen mode", component="vlc"
                            )
                    except Exception:
                        pass  # Don't crash on verification failure

            except Exception as e:
                log_error(f"Error in fullscreen enforcement: {e}", component="vlc")
                break

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
            # Stop fullscreen enforcement first
            self.should_be_fullscreen = False
            self.is_playing = False

            if self.vlc_player:
                self.vlc_player.stop()
                log_info("Stopped VLC Python player", component="vlc")

            # Kill any remaining VLC processes as safety measure
            subprocess.run(["pkill", "vlc"], capture_output=True)

        except Exception as e:
            log_error(f"Error stopping video: {e}", component="vlc")

    def get_position(self) -> Optional[float]:
        """Get current playback position in seconds"""
        if not self.is_playing or not self.vlc_player:
            return None

        try:
            # Prefer millisecond time for precision
            current_ms = self.vlc_player.get_time()
            if current_ms >= 0:
                return self._ms_to_seconds(current_ms)
            # Fallback to ratio if time is unavailable
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
            # Prefer millisecond time seek for precision
            target_ms = int(max(0.0, seconds) * 1000.0)
            # set_time returns int (0 on success in some versions). We'll treat no-exception as success.
            self.vlc_player.set_time(target_ms)
            return True
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

    def force_fullscreen(self) -> bool:
        """Manually force fullscreen mode"""
        if not self.vlc_player or self.debug_mode:
            return False

        try:
            log_info("Manually forcing fullscreen mode", component="vlc")
            self.vlc_player.set_fullscreen(True)
            time.sleep(0.1)

            success = self.vlc_player.get_fullscreen()
            if success:
                log_info("Manual fullscreen enforcement successful", component="vlc")
            else:
                log_warning("Manual fullscreen enforcement failed", component="vlc")
            return success
        except Exception as e:
            log_error(f"Error forcing fullscreen: {e}", component="vlc")
            return False

    def is_fullscreen(self) -> bool:
        """Check if VLC is currently in fullscreen mode"""
        if not self.vlc_player:
            return False
        try:
            return self.vlc_player.get_fullscreen()
        except Exception:
            return False

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

                # Restart playback from the beginning on a background thread
                def restart():
                    try:
                        if not self.vlc_player:
                            return
                        # Stop to clear end state, then play and seek to 0 for reliability
                        self.vlc_player.stop()
                        time.sleep(0.05)
                        self.vlc_player.play()
                        time.sleep(0.05)
                        self.vlc_player.set_time(0)
                        log_info(
                            f"Video loop #{self.loop_count} started", component="vlc"
                        )
                    except Exception as e:
                        log_error(
                            f"Error during loop restart thread: {e}", component="vlc"
                        )

                threading.Thread(target=restart, daemon=True).start()
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

            # Use ONLY VLC's built-in repeat option for consistent looping behavior
            # This ensures identical loop timing between leader and collaborator
            if self.enable_looping and self.loop_strategy == LoopStrategy.NATURAL:
                try:
                    # Repeat the item many times (practically infinite)
                    # Using a high number for broad compatibility
                    self.vlc_media.add_option(":input-repeat=65535")
                    log_info(
                        "VLC media repeat option set for looping (natural strategy)",
                        component="vlc",
                    )
                except Exception as e:
                    log_warning(
                        f"Failed to set media repeat option: {e}", component="vlc"
                    )

            self.vlc_player.set_media(self.vlc_media)

            # Use event handler ONLY for manual looping strategy
            if self.enable_looping and self.loop_strategy == LoopStrategy.MANUAL:
                log_info(
                    "Video looping enabled via manual event handler", component="vlc"
                )
                event_manager = self.vlc_player.event_manager()
                event_manager.event_attach(
                    vlc.EventType.MediaPlayerEndReached, self._on_video_end
                )
            elif self.enable_looping:
                log_info(
                    "Video looping enabled via VLC repeat option (natural strategy)",
                    component="vlc",
                )

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
                    self.should_be_fullscreen = True

                    # Multiple attempts with increasing delays for reliability
                    fullscreen_attempts = [0.3, 0.5, 1.0, 2.0]
                    fullscreen_success = False

                    for attempt, delay in enumerate(fullscreen_attempts, 1):
                        time.sleep(delay)
                        log_info(
                            f"Fullscreen attempt #{attempt} (after {delay}s delay)",
                            component="vlc",
                        )
                        self.vlc_player.set_fullscreen(True)

                        # Check if it worked
                        time.sleep(0.2)
                        if self.vlc_player.get_fullscreen():
                            log_info(
                                f"Fullscreen enabled successfully on attempt #{attempt}",
                                component="vlc",
                            )
                            fullscreen_success = True
                            break
                        else:
                            log_warning(
                                f"Fullscreen attempt #{attempt} failed", component="vlc"
                            )

                    if not fullscreen_success:
                        log_error(
                            "All fullscreen attempts failed - will use enforcement thread",
                            component="vlc",
                        )

                    # Start fullscreen enforcement thread only if enabled
                    if self.enable_fullscreen_enforcement:
                        self.fullscreen_enforcement_thread = threading.Thread(
                            target=self._enforce_fullscreen_periodically, daemon=True
                        )
                        self.fullscreen_enforcement_thread.start()
                        log_info(
                            "Started fullscreen enforcement thread", component="vlc"
                        )
                    else:
                        log_info("Fullscreen enforcement disabled", component="vlc")
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
        ]

        # Add fullscreen-specific args for production mode
        if not self.debug_mode:
            args.extend(
                [
                    "--fullscreen",  # Start in fullscreen mode
                    "--no-embedded-video",  # Don't embed video in interface
                    "--video-on-top",  # Keep video window on top
                    "--no-video-deco",  # Remove window decorations
                ]
            )
        else:
            args.extend(
                [
                    "--no-fullscreen",  # Explicitly disable fullscreen in debug mode
                ]
            )

        # VLC outputs audio normally - no audio routing arguments needed
        # Audio will be synchronized across all nodes using the system's default audio output
        pass

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
            "loop_strategy": self.loop_strategy.value,
            "is_fullscreen": False,
            "should_be_fullscreen": self.should_be_fullscreen,
            "enforcement_active": self.fullscreen_enforcement_thread is not None
            and self.fullscreen_enforcement_thread.is_alive(),
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

            # Get fullscreen status
            info["is_fullscreen"] = self.vlc_player.get_fullscreen()

        except Exception as e:
            log_error(f"Error getting video info: {e}", component="vlc")

        return info

        def set_playback_rate(self, rate: float) -> bool:
            """Set playback rate (speed)"""
            if not self.vlc_player:
                return False
            try:
                self.vlc_player.set_rate(rate)
                log_info(f"Set playback rate to {rate}", component="vlc")
                return True
            except Exception as e:
                log_error(f"Error setting playback rate: {e}", component="vlc")
                return False

        def get_playback_rate(self) -> Optional[float]:
            """Get current playback rate"""
            if not self.vlc_player:
                return None
            try:
                return self.vlc_player.get_rate()
            except Exception as e:
                log_error(f"Error getting playback rate: {e}", component="vlc")
                return None
