#!/usr/bin/env python3
"""
Optimized KitchenSync Collaborator Pi
Clean, modular implementation with improved architecture
"""

import argparse
import sys
import threading
import time
from collections import deque
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import ConfigManager
from video import VideoFileManager, VLCVideoPlayer, LoopStrategy
from networking import CommandListener, SyncReceiver
from midi import MidiManager, MidiScheduler
from core import SystemState, Schedule, SyncTracker
from core.logger import log_info, log_warning, log_error, enable_system_logging


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================


@dataclass
class SyncConfig:
    """Centralized sync configuration"""

    # Core sync behavior
    deviation_samples_maxlen: int = 20
    initial_sync_wait_seconds: float = 2.0
    sync_timeout_seconds: float = 10.0
    sync_deviation_threshold_resume: float = 0.1
    heartbeat_interval_seconds: float = 2.0
    reregister_interval_seconds: float = 60.0

    # Tunable sync parameters (can be overridden in config)
    sync_check_interval: float = 5.0
    deviation_threshold: float = 0.3
    sync_jump_ahead: float = 3.0
    latency_compensation: float = 0.0  # DISABLED - may cause issues
    seek_settle_time: float = 0.1
    post_loop_sync_delay: float = 5.0
    no_sync_after_loop: bool = False

    # Debug settings
    debug_log_interval: float = 0.2
    critical_window_start_threshold: float = 5.0
    critical_window_end_threshold: float = 5.0
    critical_window_log_interval: float = 0.05


class SyncState(Enum):
    """Video sync states for cleaner state management"""

    IDLE = "idle"
    WAITING_FOR_SYNC = "waiting"
    IN_GRACE_PERIOD = "grace"
    SYNCED = "synced"
    NO_SYNC_MODE = "no_sync"


class VideoSyncManager:
    """Handles all video synchronization logic"""

    def __init__(self, config: SyncConfig, video_player: VLCVideoPlayer):
        self.config = config
        self.video_player = video_player

        # Sync state
        self.state = SyncState.IDLE
        self.deviation_samples = deque(maxlen=config.deviation_samples_maxlen)
        self.last_correction_time = 0
        self.last_video_position: Optional[float] = None
        self.loop_time = 0
        self.sync_timer = 0

        # Debug state
        self.in_critical_window = False
        self.last_debug_log_time = 0

    def reset(self):
        """Reset sync state"""
        self.state = SyncState.IDLE
        self.deviation_samples.clear()
        self.last_video_position = None
        self.in_critical_window = False

    def handle_video_loop(self, video_position: float) -> bool:
        """
        Detect and handle video loops
        Returns True if loop was detected
        """
        if self.last_video_position is not None:
            # Large backward jump indicates a loop
            if self.last_video_position > video_position + 1.0:
                log_info(
                    f"Loop detected! Position: {self.last_video_position:.3f}s → {video_position:.3f}s",
                    component="sync",
                )
                self.deviation_samples.clear()

                if self.config.no_sync_after_loop:
                    self.state = SyncState.NO_SYNC_MODE
                    log_info(
                        "NO_SYNC_AFTER_LOOP: Blocking all future corrections",
                        component="sync",
                    )
                else:
                    self.state = SyncState.IN_GRACE_PERIOD
                    self.loop_time = time.time()

                self.last_video_position = video_position
                return True

        self.last_video_position = video_position
        return False

    def should_skip_correction(self, leader_time: float) -> tuple[bool, str]:
        """
        Check if sync correction should be skipped
        Returns (should_skip, reason)
        """
        # Check state-based blocks
        if self.state == SyncState.NO_SYNC_MODE:
            return True, "NO_SYNC_AFTER_LOOP active"

        if self.state == SyncState.IN_GRACE_PERIOD:
            if time.time() - self.loop_time < self.config.post_loop_sync_delay:
                remaining = self.config.post_loop_sync_delay - (
                    time.time() - self.loop_time
                )
                return True, f"Grace period ({remaining:.1f}s remaining)"
            else:
                self.state = SyncState.SYNCED

        # Check if near video end (safe zone)
        video_position = self.video_player.get_position()
        duration = self.video_player.get_duration()
        if duration and video_position is not None:
            time_to_end = duration - video_position
            if time_to_end < 2.0:
                return True, f"Loop safe zone ({time_to_end:.2f}s to end)"

        # Rate limiting
        if time.time() - self.last_correction_time < self.config.sync_check_interval:
            remaining = self.config.sync_check_interval - (
                time.time() - self.last_correction_time
            )
            return True, f"Rate limited ({remaining:.1f}s remaining)"

        return False, ""

    def calculate_median_deviation(self, samples: deque) -> float:
        """Calculate median with outlier filtering"""
        if not samples:
            return 0.0

        sorted_samples = sorted(samples)
        trim_count = max(1, len(sorted_samples) // 5)

        if len(sorted_samples) > 2 * trim_count:
            trimmed = sorted_samples[trim_count:-trim_count]
        else:
            trimmed = sorted_samples

        if not trimmed:
            return 0.0
        elif len(trimmed) % 2 == 0:
            mid1, mid2 = trimmed[len(trimmed) // 2 - 1], trimmed[len(trimmed) // 2]
            return (mid1 + mid2) / 2.0
        else:
            return trimmed[len(trimmed) // 2]

    def perform_sync_correction(
        self, leader_time: float, median_deviation: float
    ) -> bool:
        """
        Perform the actual sync correction
        Returns True if correction was successful
        """
        duration = self.video_player.get_duration()

        # Calculate target position
        expected_position = (
            (leader_time + self.config.latency_compensation) % duration
            if duration
            else leader_time
        )
        correction_offset = (
            -self.config.latency_compensation
            if median_deviation > 0
            else self.config.latency_compensation
        )
        target_position = (
            (expected_position + correction_offset) % duration
            if duration
            else expected_position + correction_offset
        )

        # Clear samples before correction
        self.deviation_samples.clear()

        # Pause and seek
        if not self.video_player.pause():
            log_warning("Failed to pause for correction", component="sync")
            return False

        time.sleep(0.1)  # VLC settle time

        # Seek with jump-ahead
        seek_position = (
            (target_position + self.config.sync_jump_ahead) % duration
            if duration
            else target_position + self.config.sync_jump_ahead
        )

        if self.video_player.set_position(seek_position):
            log_info(
                f"🔄 SYNC: {median_deviation:.3f}s → seeking to {seek_position:.3f}s",
                component="sync",
            )
            self.state = SyncState.WAITING_FOR_SYNC
            self.sync_timer = time.time()
            self.last_correction_time = time.time()
            return True
        else:
            log_warning("Seek failed, resuming playback", component="sync")
            self.video_player.resume()
            return False

    def check_sync_resume(self, leader_time: float) -> bool:
        """
        Check if we should resume from waiting state
        Returns True if resumed
        """
        if self.state != SyncState.WAITING_FOR_SYNC:
            return False

        current_position = self.video_player.get_position() or 0
        deviation = abs(leader_time - current_position)

        if deviation < self.config.sync_deviation_threshold_resume:
            log_info(f"Sync achieved! Deviation: {deviation:.3f}s", component="sync")
            self.video_player.resume()
            self.state = SyncState.SYNCED
            return True
        elif time.time() - self.sync_timer > self.config.sync_timeout_seconds:
            log_warning(
                f"Sync timeout after {self.config.sync_timeout_seconds}s",
                component="sync",
            )
            self.video_player.resume()
            self.state = SyncState.SYNCED
            return True

        return False


class CollaboratorPi:
    """Refactored Collaborator Pi with clean separation of concerns"""

    def __init__(self, config_file: str = "collaborator_config.ini"):
        # Load configuration
        self.config_manager = ConfigManager(config_file)
        self.sync_config = self._load_sync_config()

        # Configure logging
        enable_system_logging(self.config_manager.enable_system_logging)

        # Initialize core components
        self.system_state = SystemState()
        self.sync_tracker = SyncTracker()

        # Initialize video components
        self.video_manager = VideoFileManager(
            self.config_manager.video_file, self.config_manager.usb_mount_point
        )
        self.video_player = VLCVideoPlayer(
            debug_mode=self.config_manager.debug_mode,
            enable_vlc_logging=self.config_manager.enable_vlc_logging,
            vlc_log_level=self.config_manager.vlc_log_level,
            enable_looping=True,
            loop_strategy=LoopStrategy.NATURAL,
        )

        # Initialize sync manager
        self.sync_manager = VideoSyncManager(self.sync_config, self.video_player)

        # Initialize MIDI
        self.midi_manager = MidiManager(self.config_manager.getint("midi_port", 0))
        self.midi_scheduler = MidiScheduler(self.midi_manager)

        # Initialize networking
        self.command_listener = CommandListener()
        self.sync_receiver = SyncReceiver(
            sync_port=self.config_manager.getint("sync_port", 5005),
            sync_callback=self._handle_sync,
        )

        # Load video
        self._load_video_file()

        # Debug flags
        self.debug_modes = {"sync": False, "critical_window": False, "deviation": False}

        log_info(
            f"Collaborator '{self.config_manager.device_id}' initialized",
            component="collaborator",
        )

    def _load_sync_config(self) -> SyncConfig:
        """Load sync configuration from config file"""
        config = SyncConfig()

        # Override with config file values
        config.sync_check_interval = self.config_manager.getfloat(
            "sync_check_interval", config.sync_check_interval
        )
        config.deviation_threshold = self.config_manager.getfloat(
            "deviation_threshold", config.deviation_threshold
        )
        config.sync_jump_ahead = self.config_manager.getfloat(
            "sync_jump_ahead", config.sync_jump_ahead
        )
        config.latency_compensation = self.config_manager.getfloat(
            "latency_compensation", config.latency_compensation
        )
        config.seek_settle_time = self.config_manager.getfloat(
            "seek_settle_time", config.seek_settle_time
        )
        config.post_loop_sync_delay = self.config_manager.getfloat(
            "post_loop_sync_delay", config.post_loop_sync_delay
        )

        return config

    def _load_video_file(self):
        """Find and load video file"""
        video_path = self.video_manager.find_video_file()
        if video_path:
            self.video_player.load_video(video_path)
            log_info(f"Video loaded: {video_path}", component="collaborator")
        else:
            log_warning("No video file found", component="collaborator")

    def _handle_sync(
        self, leader_time: float, received_at: Optional[float] = None
    ) -> None:
        """Handle time sync from leader"""
        local_time = received_at or time.time()
        self.sync_tracker.record_sync(leader_time, local_time)

        # Auto-start on first sync
        if not self.system_state.is_running:
            self.start_playbook()
            log_info(
                f"Auto-started from sync: {leader_time:.3f}s", component="collaborator"
            )

        self.system_state.current_time = leader_time
        self.midi_scheduler.process_cues(leader_time)

        # Handle sync waiting state
        if self.sync_manager.check_sync_resume(leader_time):
            return

        # Check video sync if running long enough
        if (
            self.system_state.is_running
            and hasattr(self, "video_start_time")
            and time.time() - self.video_start_time
            > self.sync_config.initial_sync_wait_seconds
        ):
            self._check_video_sync(leader_time)

        # Debug logging
        self._handle_debug_logging(leader_time)

    def _check_video_sync(self, leader_time: float) -> None:
        """Streamlined video sync checking"""
        if not self.video_player.is_playing:
            return

        video_position = self.video_player.get_position()
        if video_position is None:
            return

        # Handle debug deviation mode
        if self.debug_modes["deviation"]:
            self._log_deviation_debug(leader_time, video_position)

        # Check for video loop
        if self.sync_manager.handle_video_loop(video_position):
            return

        # Calculate deviation
        duration = self.video_player.get_duration()
        expected_position = (
            (leader_time + self.sync_config.latency_compensation) % duration
            if duration
            else leader_time
        )
        deviation = video_position - expected_position

        # Loop-aware deviation
        if duration and duration > 0:
            candidates = [deviation, deviation + duration, deviation - duration]
            deviation = min(candidates, key=abs)

        deviation = round(deviation, 4)
        self.sync_manager.deviation_samples.append(deviation)

        # Check if we have enough samples
        min_samples = self.sync_config.deviation_samples_maxlen // 2
        if len(self.sync_manager.deviation_samples) < min_samples:
            return

        # Calculate median deviation
        median_deviation = self.sync_manager.calculate_median_deviation(
            self.sync_manager.deviation_samples
        )

        # Check if correction is needed
        if abs(median_deviation) <= self.sync_config.deviation_threshold:
            return

        # Check if correction should be skipped
        should_skip, reason = self.sync_manager.should_skip_correction(leader_time)
        if should_skip:
            if self.debug_modes["critical_window"]:
                log_info(f"Correction blocked: {reason}", component="sync")
            return

        # Perform correction
        self.sync_manager.perform_sync_correction(leader_time, median_deviation)

    def _log_deviation_debug(self, leader_time: float, video_position: float):
        """Debug logging for deviation analysis"""
        raw_deviation = video_position - leader_time
        duration = self.video_player.get_duration()

        # Calculate median for comparison
        median_deviation = self.sync_manager.calculate_median_deviation(
            self.sync_manager.deviation_samples
        )

        print(
            f"[DEBUG_DEVIATION] Leader: {leader_time:.3f}s | "
            f"Video: {video_position:.3f}s | "
            f"Raw: {raw_deviation:.3f}s | "
            f"Median: {median_deviation:.3f}s"
        )

    def _handle_debug_logging(self, leader_time: float):
        """Handle all debug logging with appropriate throttling"""
        current_time = time.time()

        # Determine logging interval based on mode
        if self.debug_modes["critical_window"] and self.sync_manager.in_critical_window:
            interval = self.sync_config.critical_window_log_interval
        elif self.debug_modes["sync"]:
            interval = self.sync_config.debug_log_interval
        else:
            return

        # Throttled logging
        if current_time - self.sync_manager.last_debug_log_time >= interval:
            self._log_sync_debug_info(leader_time)
            self.sync_manager.last_debug_log_time = current_time

    def _log_sync_debug_info(self, leader_time: float):
        """Log detailed sync information"""
        if not self.video_player.is_playing:
            return

        video_position = self.video_player.get_position()
        if video_position is None:
            return

        duration = self.video_player.get_duration()
        samples_count = len(self.sync_manager.deviation_samples)
        max_samples = self.sync_config.deviation_samples_maxlen

        log_info(
            f"SYNC_DEBUG | Leader: {leader_time:.3f}s | "
            f"Video: {video_position:.3f}s | "
            f"Samples: {samples_count}/{max_samples}",
            component="sync",
        )

    def start_playbook(self) -> None:
        """Start video and MIDI playback"""
        log_info("Starting playback...", component="collaborator")

        self.system_state.start_session()
        self.video_start_time = time.time()

        if self.video_player.video_path:
            self.video_player.start_playback()

        video_duration = self.video_player.get_duration()
        self.midi_scheduler.start_playback(self.system_state.start_time, video_duration)

        # Reset sync state
        self.sync_manager.reset()

        log_info("Playback started", component="collaborator")

    def stop_playback(self) -> None:
        """Stop all playback"""
        log_info("Stopping playback...", component="collaborator")

        self.video_player.stop_playback()
        self.midi_scheduler.stop_playback()
        self.system_state.stop_session()
        self.sync_manager.reset()

        if hasattr(self, "video_start_time"):
            delattr(self, "video_start_time")

        log_info("Playback stopped", component="collaborator")

    def run(self) -> None:
        """Main run loop with improved error handling"""
        print(f"Starting KitchenSync Collaborator '{self.config_manager.device_id}'")

        try:
            # Start networking
            self.sync_receiver.start_listening()

            # Start heartbeat in separate thread
            heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop, daemon=True
            )
            heartbeat_thread.start()

            # Initial registration
            self.command_listener.send_registration(
                self.config_manager.device_id, self.config_manager.video_file
            )

            print(f"✅ Collaborator {self.config_manager.device_id} started!")
            print("Waiting for time sync from leader...")
            print("Press Ctrl+C to exit")

            # Main loop
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.cleanup()

    def _heartbeat_loop(self):
        """Heartbeat loop with periodic re-registration"""
        last_registration = time.time()

        while True:
            try:
                status = "running" if self.system_state.is_running else "ready"
                self.command_listener.send_heartbeat(
                    self.config_manager.device_id, status
                )

                # Periodic re-registration
                now = time.time()
                if (
                    now - last_registration
                    >= self.sync_config.reregister_interval_seconds
                ):
                    self.command_listener.send_registration(
                        self.config_manager.device_id, self.config_manager.video_file
                    )
                    last_registration = now

                time.sleep(self.sync_config.heartbeat_interval_seconds)

            except Exception as e:
                log_error(f"Heartbeat error: {e}", component="heartbeat")
                time.sleep(self.sync_config.heartbeat_interval_seconds)

    def cleanup(self) -> None:
        """Clean up resources"""
        if self.system_state.is_running:
            self.stop_playback()

        self.video_player.cleanup()
        self.midi_manager.cleanup()
        log_info("Cleanup completed", component="collaborator")

    def set_debug_mode(self, mode: str, enabled: bool):
        """Set debug mode flags"""
        if mode in self.debug_modes:
            self.debug_modes[mode] = enabled
            print(
                f"✓ {mode.title()} debug mode: {'ENABLED' if enabled else 'DISABLED'}"
            )


def main():
    """Main entry point with improved argument parsing"""
    parser = argparse.ArgumentParser(description="KitchenSync Collaborator Pi")
    parser.add_argument(
        "config_file",
        nargs="?",
        default="collaborator_config.ini",
        help="Configuration file to use",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--debug_loop",
        action="store_true",
        help="Enable detailed loop transition logging",
    )
    parser.add_argument(
        "--debug_deviation", action="store_true", help="Print raw deviation analysis"
    )

    args = parser.parse_args()

    try:
        collaborator = CollaboratorPi(args.config_file)

        # Set debug modes
        if args.debug:
            collaborator.set_debug_mode("sync", True)

        if args.debug_loop:
            collaborator.set_debug_mode("critical_window", True)

        if args.debug_deviation:
            collaborator.set_debug_mode("deviation", True)

        collaborator.run()

    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        log_error(f"Fatal error: {e}", component="main")
        sys.exit(1)


if __name__ == "__main__":
    main()
