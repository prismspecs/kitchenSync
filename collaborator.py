#!/usr/bin/env python3
"""
Refactored KitchenSync Collaborator Pi
Clean, modular implementation preserving original sync mechanism
"""

import argparse
import sys
import threading
import time
from collections import deque
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import ConfigManager
from video import VideoFileManager, VLCVideoPlayer, LoopStrategy
from networking import CommandListener, SyncReceiver
from midi import MidiManager, MidiScheduler
from core import SystemState, Schedule, SyncTracker
from core.logger import log_info, log_warning, log_error, enable_system_logging


# =============================================================================
# SYNCHRONIZATION PARAMETERS - Edit these values to tune sync behavior
# =============================================================================


@dataclass
class SyncConstants:
    """Centralized sync configuration constants"""

    # Constants for sync logic - these control the basic behavior of the sync system
    DEVIATION_SAMPLES_MAXLEN: int = 20
    INITIAL_SYNC_WAIT_SECONDS: float = 2.0
    SYNC_TIMEOUT_SECONDS: float = 10.0
    SYNC_DEVIATION_THRESHOLD_RESUME: float = 0.1
    HEARTBEAT_INTERVAL_SECONDS: float = 2.0
    REREGISTER_INTERVAL_SECONDS: float = 60.0

    # Default sync settings - these are tunable parameters that affect sync quality
    DEFAULT_SYNC_CHECK_INTERVAL: float = 5.0
    DEFAULT_DEVIATION_THRESHOLD: float = 0.3
    DEFAULT_SYNC_JUMP_AHEAD: float = 3.0
    DEFAULT_LATENCY_COMPENSATION: float = 0.0
    DEFAULT_SEEK_SETTLE_TIME: float = 0.1
    POST_LOOP_SYNC_DELAY_SECONDS: float = 5.0
    NO_SYNC_AFTER_LOOP: bool = False


# =============================================================================


class CollaboratorPi:
    """Refactored Collaborator Pi with clean separation of concerns"""

    def __init__(self, config_file: str = "collaborator_config.ini"):
        # Initialize configuration
        self.config = ConfigManager(config_file)
        self.sync_constants = SyncConstants()

        # Configure logging based on config settings
        enable_system_logging(self.config.enable_system_logging)

        # Initialize core components
        self.system_state = SystemState()
        self.sync_tracker = SyncTracker()

        # Initialize video components with configurable logging
        self.video_manager = VideoFileManager(
            self.config.video_file, self.config.usb_mount_point
        )
        self.video_player = VLCVideoPlayer(
            debug_mode=self.config.debug_mode,
            enable_vlc_logging=self.config.enable_vlc_logging,
            vlc_log_level=self.config.vlc_log_level,
            enable_looping=True,  # Re-enable looping for collaborator
            loop_strategy=LoopStrategy.NATURAL,
        )
        log_info(
            "Collaborator using Python VLC for precise sync control",
            component="collaborator",
        )

        # Initialize MIDI
        midi_port = self.config.getint("midi_port", 0)
        self.midi_manager = MidiManager(midi_port)
        self.midi_scheduler = MidiScheduler(self.midi_manager)

        # Initialize networking
        self.command_listener = CommandListener()
        self.sync_receiver = SyncReceiver(
            sync_port=self.config.getint("sync_port", 5005),
            sync_callback=self._handle_sync,
        )

        # Find and load video file
        self._load_video_file()

        # Initialize sync parameters and state
        self._initialize_sync_state()

        log_info(
            f"KitchenSync Collaborator '{self.config.device_id}' initialized",
            component="collaborator",
        )

    def _load_video_file(self):
        """Find and load video file"""
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            self.video_player.load_video(self.video_path)
            log_info(f"Video file loaded: {self.video_path}", component="collaborator")
        else:
            log_warning("No video file found at startup", component="collaborator")

    def _initialize_sync_state(self):
        """Initialize synchronization parameters from config and set initial state."""
        # Load sync settings from config with defaults from constants
        self.sync_check_interval = self.config.getfloat(
            "sync_check_interval", self.sync_constants.DEFAULT_SYNC_CHECK_INTERVAL
        )
        self.deviation_threshold = self.config.getfloat(
            "deviation_threshold", self.sync_constants.DEFAULT_DEVIATION_THRESHOLD
        )
        self.sync_jump_ahead = self.config.getfloat(
            "sync_jump_ahead", self.sync_constants.DEFAULT_SYNC_JUMP_AHEAD
        )
        self.latency_compensation = self.config.getfloat(
            "latency_compensation", self.sync_constants.DEFAULT_LATENCY_COMPENSATION
        )
        self.seek_settle_time = self.config.getfloat(
            "seek_settle_time", self.sync_constants.DEFAULT_SEEK_SETTLE_TIME
        )
        self.post_loop_sync_delay_seconds = self.config.getfloat(
            "post_loop_sync_delay", self.sync_constants.POST_LOOP_SYNC_DELAY_SECONDS
        )
        self.no_sync_after_loop = self.sync_constants.NO_SYNC_AFTER_LOOP

        # Video sync state - PRESERVING ORIGINAL LOGIC
        self.deviation_samples = deque(
            maxlen=self.sync_constants.DEVIATION_SAMPLES_MAXLEN
        )
        self.last_correction_time = 0
        self.video_start_time = None
        self.last_video_position = None
        self.in_post_loop_grace_period = False
        self.loop_time = 0
        self.no_sync_after_loop_active = False

        # Sync state management - PRESERVING ORIGINAL LOGIC
        self.wait_for_sync = False
        self.sync_timer = 0

        # Debug flags - organized but preserving original behavior
        self.debug_deviation_mode = False
        self.debug_sync_logging = False
        self.critical_window_logging = False
        self.last_debug_log_time = 0
        self.debug_log_interval = 0.2
        self.critical_window_start_threshold = 5.0
        self.critical_window_end_threshold = 5.0
        self.in_critical_window = False

    def _handle_sync(
        self, leader_time: float, received_at: Optional[float] = None
    ) -> None:
        """Handle time sync from leader - PRESERVING ORIGINAL LOGIC"""
        local_time = received_at if received_at is not None else time.time()
        self.sync_tracker.record_sync(leader_time, local_time)

        # Auto-start playback on first valid sync
        if not self.system_state.is_running:
            self.start_playback()
            log_info(
                f"Auto-started from sync, leader time: {leader_time:.3f}s",
                component="collaborator",
            )

        # Update system time and maintain sync
        self.system_state.current_time = leader_time

        # Process MIDI cues (safe no-op if no schedule)
        self.midi_scheduler.process_cues(leader_time)

        # Check for critical sync window (only if enabled via --debug_loop)
        if self.critical_window_logging:
            self._update_critical_window_status(leader_time)

        # Check video sync (only if we've been running for a bit)
        if self.system_state.is_running and self.video_start_time:
            time_since_start = time.time() - self.video_start_time
            if time_since_start > self.sync_constants.INITIAL_SYNC_WAIT_SECONDS:
                self._check_video_sync(leader_time)

        # Debug logging with appropriate intervals - PRESERVING ORIGINAL LOGIC
        if self.critical_window_logging and self.in_critical_window:
            self._throttled_debug_log(
                leader_time, 0.05
            )  # 50ms interval during critical window
        elif self.debug_sync_logging:
            self._throttled_debug_log(leader_time, self.debug_log_interval)

        # Handle post-correction sync waiting - PRESERVING ORIGINAL LOGIC
        if self.wait_for_sync:
            current_position = self.video_player.get_position() or 0
            deviation = abs(leader_time - current_position)

            if deviation < self.sync_constants.SYNC_DEVIATION_THRESHOLD_RESUME:
                log_info(
                    f"Sync achieved! Deviation: {deviation:.3f}s, resuming",
                    component="sync",
                )
                self.video_player.resume()
                self.wait_for_sync = False
            elif (
                time.time() - self.sync_timer > self.sync_constants.SYNC_TIMEOUT_SECONDS
            ):
                log_warning(
                    f"Sync timeout after {self.sync_constants.SYNC_TIMEOUT_SECONDS}s, resuming anyway",
                    component="sync",
                )
                self.video_player.resume()
                self.wait_for_sync = False
            return

    def _throttled_debug_log(self, leader_time: float, interval: float) -> None:
        """Log debug info with throttling"""
        current_time = time.time()
        if current_time - self.last_debug_log_time >= interval:
            self._log_sync_debug_info(leader_time)
            self.last_debug_log_time = current_time

    def _update_critical_window_status(self, leader_time: float) -> None:
        """Update critical sync logging window status (5s before end + 5s after restart)"""
        if not self.video_player.is_playing:
            if self.in_critical_window:
                self.in_critical_window = False
                print("EXITING CRITICAL SYNC WINDOW (playback stopped)")
            return

        duration = self.video_player.get_duration()
        video_position = self.video_player.get_position()
        if not duration or duration <= 0 or video_position is None:
            return

        time_to_end = duration - video_position
        in_pre_end = time_to_end <= self.critical_window_start_threshold
        in_post_start = video_position <= self.critical_window_end_threshold

        # State transitions
        if not self.in_critical_window and in_pre_end:
            self.in_critical_window = True
            print(
                f"ENTERING CRITICAL SYNC WINDOW (pos={video_position:.2f}s, ttl={time_to_end:.2f}s)"
            )
        elif self.in_critical_window and not (in_pre_end or in_post_start):
            self.in_critical_window = False
            print(f"EXITING CRITICAL SYNC WINDOW (pos={video_position:.2f}s)")

    def _check_video_sync(self, leader_time: float) -> None:
        """Check and correct video sync using median filtering - PRESERVING ORIGINAL LOGIC"""
        if not self.video_player.is_playing or not self.video_start_time:
            return

        # Debug deviation mode - PRESERVED
        if self.debug_deviation_mode:
            video_position = self.video_player.get_position()
            if video_position is not None:
                raw_deviation = video_position - leader_time
                duration = self.video_player.get_duration()
                expected_position = leader_time + self.latency_compensation
                if duration and duration > 0:
                    expected_position = expected_position % duration
                deviation = video_position - expected_position
                if duration and duration > 0:
                    candidates = [deviation, deviation + duration, deviation - duration]
                    deviation = min(candidates, key=abs)
                deviation = round(deviation, 4)

                # Median calculation
                samples = list(self.deviation_samples)
                median_deviation = self._calculate_median_deviation(samples)
                print(
                    f"[DEBUG_DEVIATION] Leader: {leader_time:.3f}s | Video: {video_position:.3f}s | Raw: {raw_deviation:.3f}s | Median: {median_deviation:.3f}s"
                )

        # NO_SYNC_AFTER_LOOP check - PRESERVED
        if self.no_sync_after_loop and self.no_sync_after_loop_active:
            if self.critical_window_logging:
                log_info(
                    "NO_SYNC_AFTER_LOOP active: blocking all sync corrections after loop.",
                    component="sync",
                )
            return

        # Post-loop grace period check - PRESERVED
        if self.in_post_loop_grace_period:
            if time.time() - self.loop_time < self.post_loop_sync_delay_seconds:
                if self.critical_window_logging:
                    log_info(
                        f"Post-loop grace period active ({time.time() - self.loop_time:.2f}s/{self.post_loop_sync_delay_seconds}s), blocking sync corrections.",
                        component="sync",
                    )
                return
            else:
                self.in_post_loop_grace_period = False

        # Get current video position
        video_position = self.video_player.get_position()
        if video_position is None:
            log_warning("Could not get video position for sync check", component="sync")
            return

        # Loop detection - PRESERVED ORIGINAL LOGIC
        if self.last_video_position is not None:
            if self.last_video_position > video_position + 1.0:
                log_info(
                    f"Loop detected! Position jumped from {self.last_video_position:.3f}s to {video_position:.3f}s. Clearing samples.",
                    component="sync",
                )
                self.deviation_samples.clear()
                self.last_video_position = video_position
                if self.no_sync_after_loop:
                    self.no_sync_after_loop_active = True
                    log_info(
                        "NO_SYNC_AFTER_LOOP flag set: all sync corrections will be blocked after this loop.",
                        component="sync",
                    )
                else:
                    self.in_post_loop_grace_period = True
                    self.loop_time = time.time()
                return
        self.last_video_position = video_position

        # Calculate deviation - PRESERVED ORIGINAL LOGIC
        duration = self.video_player.get_duration()
        expected_position = leader_time + self.latency_compensation
        if duration and duration > 0:
            expected_position = expected_position % duration

        deviation = video_position - expected_position

        # Loop-aware deviation calculation - PRESERVED
        if duration and duration > 0:
            candidates = [deviation, deviation + duration, deviation - duration]
            deviation = min(candidates, key=abs)

        deviation = round(deviation, 4)
        self.deviation_samples.append(deviation)

        # Critical window logging - PRESERVED
        if self.critical_window_logging and self.in_critical_window:
            log_info(
                f"SYNC_EVAL: Sample {deviation:.3f}s ({len(self.deviation_samples)}/{self.sync_constants.DEVIATION_SAMPLES_MAXLEN})",
                component="sync",
            )

        # Check samples count - PRESERVED
        min_samples = self.sync_constants.DEVIATION_SAMPLES_MAXLEN // 2
        if len(self.deviation_samples) < min_samples:
            if self.critical_window_logging and self.in_critical_window:
                log_info(
                    f"SYNC_EVAL: Need {min_samples - len(self.deviation_samples)} more samples",
                    component="sync",
                )
            return

        # Calculate median - PRESERVED ORIGINAL LOGIC
        median_deviation = self._calculate_median_deviation(
            list(self.deviation_samples)
        )

        if self.critical_window_logging and self.in_critical_window:
            if abs(median_deviation) > self.deviation_threshold:
                print(
                    f"SYNC_MEDIAN_CALC | Samples: {len(self.deviation_samples)} | Median: {median_deviation:.3f}s | Threshold: {self.deviation_threshold:.3f}s"
                )

        # Check if correction is needed - PRESERVED
        if abs(median_deviation) > self.deviation_threshold:
            # Safe zone check - PRESERVED
            time_to_end = (
                duration - video_position
                if duration and video_position is not None
                else 0
            )
            if duration and time_to_end < 2.0:
                log_info(
                    f"In loop safe zone ({time_to_end:.2f}s to end), blocking correction of {median_deviation:.3f}s to allow natural loop.",
                    component="sync",
                )
                return

            current_time = time.time()

            # Rate limit - PRESERVED
            if current_time - self.last_correction_time < self.sync_check_interval:
                if self.critical_window_logging and self.in_critical_window:
                    time_left = self.sync_check_interval - (
                        current_time - self.last_correction_time
                    )
                    log_info(
                        f"SYNC_EVAL: Correction blocked, {time_left:.1f}s remaining",
                        component="sync",
                    )
                return

            # Log correction - PRESERVED
            log_info(
                f"🔄 SYNC CORRECTION: {median_deviation:.3f}s deviation > {self.deviation_threshold:.3f}s threshold at {leader_time:.1f}s",
                component="sync",
            )
            print(f"🔄 Sync correction: {median_deviation:.3f}s deviation")

            # Perform correction - PRESERVED ORIGINAL LOGIC
            correction_offset = (
                -self.latency_compensation
                if median_deviation > 0
                else self.latency_compensation
            )
            target_position = expected_position + correction_offset
            if duration and duration > 0:
                target_position = target_position % duration

            self.deviation_samples.clear()

            if not self.video_player.pause():
                log_warning("Failed to pause for correction", component="sync")
                return

            time.sleep(0.1)

            seek_position = target_position + self.sync_jump_ahead
            if duration and duration > 0:
                seek_position = seek_position % duration

            if self.video_player.set_position(seek_position):
                log_info(
                    f"Seeking to {seek_position:.3f}s (target: {target_position:.3f}s)",
                    component="sync",
                )
                self.wait_for_sync = True
                self.sync_timer = time.time()
                self.last_correction_time = time.time()
                log_info(
                    "Waiting for sync (will resume when deviation < 0.1s)",
                    component="sync",
                )
            else:
                log_warning("Seek failed, resuming playback", component="sync")
                self.video_player.resume()
        else:
            if (
                self.critical_window_logging
                and self.in_critical_window
                and len(self.deviation_samples)
                < self.sync_constants.DEVIATION_SAMPLES_MAXLEN
            ):
                print(
                    f"SYNC_NO_CORRECTION | Median {median_deviation:.3f}s <= threshold {self.deviation_threshold:.3f}s"
                )

    def _calculate_median_deviation(self, samples: list) -> float:
        """Calculate median with outlier filtering - PRESERVED ORIGINAL LOGIC"""
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
            mid1 = trimmed[len(trimmed) // 2 - 1]
            mid2 = trimmed[len(trimmed) // 2]
            return (mid1 + mid2) / 2.0
        else:
            return trimmed[len(trimmed) // 2]

    def _log_sync_debug_info(self, leader_time: float) -> None:
        """Log sync information for debugging - PRESERVED"""
        if not self.video_player.is_playing:
            return

        video_position = self.video_player.get_position()
        duration = self.video_player.get_duration()
        if video_position is None:
            return

        expected_position = leader_time + self.latency_compensation
        if duration and duration > 0:
            expected_position = expected_position % duration

        raw_deviation = video_position - expected_position
        if duration and duration > 0:
            candidates = [
                raw_deviation,
                raw_deviation - duration,
                raw_deviation + duration,
            ]
            loop_aware_deviation = min(candidates, key=abs)
        else:
            loop_aware_deviation = raw_deviation

        if self.critical_window_logging and self.in_critical_window:
            print(
                f"SYNC_LOOP_DEBUG | Leader: {leader_time:.3f}s | Video: {video_position:.3f}s | Deviation: {loop_aware_deviation:.3f}s | Samples: {len(self.deviation_samples)}/{self.sync_constants.DEVIATION_SAMPLES_MAXLEN}"
            )

    def start_playback(self) -> None:
        """Start video and MIDI playback"""
        log_info("Starting playback...", component="collaborator")

        self.system_state.start_session()
        self.video_start_time = time.time()

        if self.video_player.video_path:
            log_info("Starting video...", component="video")
            self.video_player.start_playback()

        video_duration = self.video_player.get_duration()
        self.midi_scheduler.start_playback(self.system_state.start_time, video_duration)

        log_info("Playback started", component="collaborator")

    def stop_playback(self) -> None:
        """Stop video and MIDI playback"""
        log_info("Stopping playback...", component="collaborator")

        self.video_player.stop_playback()
        self.midi_scheduler.stop_playback()
        self.system_state.stop_session()

        # Reset video state
        self.video_start_time = None
        self.deviation_samples.clear()

        log_info("Playback stopped", component="collaborator")

    def run(self) -> None:
        """Main run loop"""
        print(f"Starting KitchenSync Collaborator '{self.config.device_id}'")

        # Start networking
        self.sync_receiver.start_listening()

        # Register with leader
        self.command_listener.send_registration(
            self.config.device_id, self.config.video_file
        )

        # Start heartbeat
        heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        heartbeat_thread.start()

        print(f"✅ Collaborator {self.config.device_id} started successfully!")
        print("Collaborator ready. Waiting for time sync from leader...")
        print("Press Ctrl+C to exit")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.stop_playback()
        finally:
            self.cleanup()

    def _heartbeat_loop(self):
        """Heartbeat loop with periodic re-registration"""
        last_registration = time.time()
        while (
            self.system_state.is_running or True
        ):  # Keep running even when not playing
            try:
                status = "running" if self.system_state.is_running else "ready"
                self.command_listener.send_heartbeat(self.config.device_id, status)

                # Periodic re-registration
                now = time.time()
                if (
                    now - last_registration
                    >= self.sync_constants.REREGISTER_INTERVAL_SECONDS
                ):
                    self.command_listener.send_registration(
                        self.config.device_id, self.config.video_file
                    )
                    last_registration = now

                time.sleep(self.sync_constants.HEARTBEAT_INTERVAL_SECONDS)
            except Exception as e:
                log_error(f"Heartbeat error: {e}", component="heartbeat")
                time.sleep(self.sync_constants.HEARTBEAT_INTERVAL_SECONDS)

    def cleanup(self) -> None:
        """Clean up resources"""
        if self.system_state.is_running:
            self.stop_playback()

        self.video_player.cleanup()
        self.midi_manager.cleanup()
        log_info("Cleanup completed", component="collaborator")


def main():
    """Main entry point"""
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
        help="Enable detailed sync logging during video loop transitions",
    )
    parser.add_argument(
        "--debug_deviation",
        action="store_true",
        help="Print raw deviation between leader and collaborator video positions",
    )

    args = parser.parse_args()

    try:
        collaborator = CollaboratorPi(args.config_file)

        # Set debug modes - PRESERVED ORIGINAL BEHAVIOR
        if args.debug:
            collaborator.config.config["KITCHENSYNC"]["debug"] = "true"
            collaborator.debug_sync_logging = True
            print("✓ Debug mode: ENABLED (via command line)")
            print("✓ Sync debug logging: ENABLED")

        if args.debug_loop:
            collaborator.critical_window_logging = True
            print("✓ Loop debug mode: ENABLED (via command line)")
            print(
                "✓ Critical window sync logging: ENABLED (5s before video end to 5s after restart)"
            )

        if args.debug_deviation:
            collaborator.debug_deviation_mode = True
            print("✓ Debug deviation mode: ENABLED (prints raw deviation)")

        collaborator.run()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
