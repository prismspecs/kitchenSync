#!/usr/bin/env python3
"""
Refactored KitchenSync Collaborator Pi
Clean, modular implementation using the new architecture
"""

import argparse
import sys
import threading
import time
from collections import deque
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import ConfigManager
from video import VideoFileManager, VLCVideoPlayer, LoopStrategy
from networking import CommandListener, SyncReceiver
from midi import MidiManager, MidiScheduler
from core import SystemState, Schedule, SyncTracker
from core.logger import (
    log_info,
    log_warning,
    log_error,
    enable_system_logging,
)


# =============================================================================
# SYNCHRONIZATION PARAMETERS - Edit these values to tune sync behavior
# =============================================================================

# Constants for sync logic - these control the basic behavior of the sync system
DEVIATION_SAMPLES_MAXLEN = 20  # How many timing samples to keep for median filtering
INITIAL_SYNC_WAIT_SECONDS = (
    2.0  # Grace period after startup before sync corrections begin
)
SYNC_TIMEOUT_SECONDS = 10.0  # Max time to wait for sync after a seek operation
SYNC_DEVIATION_THRESHOLD_RESUME = (
    0.1  # Deviation (seconds) required to resume after seek
)
HEARTBEAT_INTERVAL_SECONDS = 2.0  # How often to send status updates to leader
REREGISTER_INTERVAL_SECONDS = 60.0  # How often to re-register with leader

# Default sync settings - these are tunable parameters that affect sync quality
# (Can be overridden in config file)
DEFAULT_SYNC_CHECK_INTERVAL = 5.0  # Min time between corrections
DEFAULT_DEVIATION_THRESHOLD = 0.3  # Error threshold to trigger correction
DEFAULT_SYNC_JUMP_AHEAD = 3.0  # How far ahead to seek for corrections
DEFAULT_LATENCY_COMPENSATION = (
    0.0  # Network/processing delay offset (DISABLED - may cause issues)
)
DEFAULT_SEEK_SETTLE_TIME = 0.1  # VLC settling time after seek

POST_LOOP_SYNC_DELAY_SECONDS = (
    5.0  # Grace period after a loop before sync corrections resume
)
NO_SYNC_AFTER_LOOP = False  # If True, disables all sync corrections after a loop


# =============================================================================

# =============================================================================


class CollaboratorPi:
    """Refactored Collaborator Pi with clean separation of concerns"""

    debug_deviation_mode = False

    def __init__(self, config_file: str = "collaborator_config.ini"):
        # Initialize configuration
        self.config = ConfigManager(config_file)

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

        # Find and load video file before creating debug overlay
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            self.video_player.load_video(self.video_path)
            log_info(f"Video file loaded: {self.video_path}", component="collaborator")
        else:
            log_warning("No video file found at startup", component="collaborator")

        # Initialize sync parameters and state
        self._initialize_sync_parameters()

        log_info(
            f"KitchenSync Collaborator '{self.config.device_id}' initialized",
            component="collaborator",
        )

    def _initialize_sync_parameters(self):
        """Initialize synchronization parameters from config and set initial state."""
        # Use constants defined at top of file for easy editing
        self.deviation_samples_maxlen = DEVIATION_SAMPLES_MAXLEN
        self.initial_sync_wait_seconds = INITIAL_SYNC_WAIT_SECONDS
        self.sync_timeout_seconds = SYNC_TIMEOUT_SECONDS
        self.sync_deviation_threshold_resume = SYNC_DEVIATION_THRESHOLD_RESUME
        self.heartbeat_interval_seconds = HEARTBEAT_INTERVAL_SECONDS
        self.reregister_interval_seconds = REREGISTER_INTERVAL_SECONDS

        # Load sync settings from config with defaults from constants
        self.sync_check_interval = self.config.getfloat(
            "sync_check_interval", DEFAULT_SYNC_CHECK_INTERVAL
        )
        self.deviation_threshold = self.config.getfloat(
            "deviation_threshold", DEFAULT_DEVIATION_THRESHOLD
        )
        self.sync_jump_ahead = self.config.getfloat(
            "sync_jump_ahead", DEFAULT_SYNC_JUMP_AHEAD
        )
        self.latency_compensation = self.config.getfloat(
            "latency_compensation", DEFAULT_LATENCY_COMPENSATION
        )
        self.seek_settle_time = self.config.getfloat(
            "seek_settle_time", DEFAULT_SEEK_SETTLE_TIME
        )
        self.post_loop_sync_delay_seconds = self.config.getfloat(
            "post_loop_sync_delay", POST_LOOP_SYNC_DELAY_SECONDS
        )
        self.no_sync_after_loop = NO_SYNC_AFTER_LOOP

        # Video sync state
        self.deviation_samples = deque(maxlen=self.deviation_samples_maxlen)
        self.last_correction_time = 0
        self.video_start_time = None
        self.last_video_position = None
        self.in_post_loop_grace_period = False
        self.loop_time = 0
        self.no_sync_after_loop_active = False

        # Sync state management
        self.wait_for_sync = False
        self.sync_timer = 0

        # Debug sync logging
        self.debug_sync_logging = False
        self.last_debug_log_time = 0
        self.debug_log_interval = 0.2  # Log every 200ms to avoid spam

        # Critical window sync logging (5s before video end to 5s after restart)
        self.critical_window_logging = (
            False  # Disabled by default, enabled via --debug_loop
        )
        self.critical_window_start_threshold = 5.0  # Start logging 5s before video end
        self.critical_window_end_threshold = 5.0  # Continue logging 5s after restart
        self.in_critical_window = False

    def _handle_sync(
        self, leader_time: float, received_at: float | None = None
    ) -> None:
        """Handle time sync from leader

        leader_time: the leader's broadcasted media/wall time in seconds
        received_at: local receipt timestamp (seconds, time.time()); if None, computed now
        """
        local_time = received_at if received_at is not None else time.time()
        self.sync_tracker.record_sync(leader_time, local_time)

        # Auto-start playback on first valid sync
        if not self.system_state.is_running:
            self.start_playback()
            # Don't attempt immediate seeking - let video stabilize first
            log_info(
                f"Auto-started from sync, leader time: {leader_time:.3f}s",
                component="collaborator",
            )

        # Update system time and maintain sync
        # leader_time is now wall-clock time since start, so we can use it directly
        self.system_state.current_time = leader_time

        # Process MIDI cues (safe no-op if no schedule)
        self.midi_scheduler.process_cues(leader_time)

        # Check for critical sync window (only if enabled via --debug_loop)
        if self.critical_window_logging:
            self._update_critical_window_status(leader_time)

        # Check video sync (only if we've been running for a bit)
        if self.system_state.is_running and self.video_start_time:
            time_since_start = time.time() - self.video_start_time
            if time_since_start > self.initial_sync_wait_seconds:
                self._check_video_sync(leader_time)

        # Debug logging with appropriate intervals
        if self.critical_window_logging and self.in_critical_window:
            self._throttled_debug_log(
                leader_time, 0.05
            )  # 50ms interval during critical window
        elif self.debug_sync_logging:
            self._throttled_debug_log(leader_time, self.debug_log_interval)

        # Handle post-correction sync waiting
        if self.wait_for_sync:
            current_position = self.video_player.get_position() or 0
            deviation = abs(leader_time - current_position)

            if deviation < self.sync_deviation_threshold_resume:
                log_info(
                    f"Sync achieved! Deviation: {deviation:.3f}s, resuming",
                    component="sync",
                )
                self.video_player.resume()
                self.wait_for_sync = False
            elif time.time() - self.sync_timer > self.sync_timeout_seconds:
                log_warning(
                    f"Sync timeout after {self.sync_timeout_seconds}s, resuming anyway",
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

    def _handle_start_command(self, msg: dict, addr: tuple) -> None:
        """Handle start command from leader"""
        if self.system_state.is_running:
            log_info(
                "Already running, stopping current session first",
                component="collaborator",
            )
            self.stop_playback()

        # Load schedule
        schedule = msg.get("schedule", [])
        self.midi_scheduler.load_schedule(schedule)

        # Override debug mode if leader specifies it
        leader_debug_mode = msg.get("debug_mode", False)
        if leader_debug_mode and not self.config.debug_mode:
            self.config.config["KITCHENSYNC"]["debug"] = "true"
            log_info("Debug mode enabled by leader", component="collaborator")

        log_info(
            f"Received start command with {len(schedule)} cues",
            component="collaborator",
        )

        # Wait for sync to be established
        log_info("Waiting for time sync...", component="sync")
        timeout = 10.0
        start_wait = time.time()

        while (
            not self.sync_tracker.is_synced() and (time.time() - start_wait) < timeout
        ):
            time.sleep(0.1)

        if not self.sync_tracker.is_synced():
            log_warning("Starting without sync (timeout)", component="sync")
        else:
            log_info("Sync established", component="sync")

        # Start playback
        self.start_playback()

    def _handle_stop_command(self, msg: dict, addr: tuple) -> None:
        """Handle stop command from leader"""
        self.stop_playback()
        log_info("Stopped by leader command", component="collaborator")

    def _handle_schedule_update(self, msg: dict, addr: tuple) -> None:
        """Handle schedule update from leader"""
        schedule = msg.get("schedule", [])
        self.midi_scheduler.load_schedule(schedule)
        print(f"Updated schedule: {len(schedule)} cues")

    def start_playback(self) -> None:
        """Start video and MIDI playback"""
        log_info("Starting playback...", component="collaborator")

        # Start system state
        self.system_state.start_session()
        self.video_start_time = time.time()

        # Start video playback first so VLC creates its window
        if self.video_player.video_path:
            log_info("Starting video...", component="video")
            self.video_player.start_playback()

        # Start MIDI playback with video duration for looping
        video_duration = self.video_player.get_duration()
        self.midi_scheduler.start_playback(self.system_state.start_time, video_duration)

        log_info("Playback started", component="collaborator")

    def stop_playback(self) -> None:
        """Stop video and MIDI playback"""
        log_info("Stopping playback...", component="collaborator")

        # Stop video
        self.video_player.stop_playback()

        # Stop MIDI
        self.midi_scheduler.stop_playback()

        # Stop system state
        self.system_state.stop_session()

        # Reset video state
        self.video_start_time = None
        self.deviation_samples.clear()

        log_info("Playback stopped", component="collaborator")

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
        """Check and correct video sync using median filtering"""
        if not self.video_player.is_playing or not self.video_start_time:
            return

        # Debug deviation mode: print raw and median deviation between leader and video (does not block sync logic)
        if self.debug_deviation_mode:
            video_position = self.video_player.get_position()
            if video_position is not None:
                raw_deviation = video_position - leader_time
                # Calculate expected position with latency compensation
                duration = self.video_player.get_duration()
                expected_position = leader_time + self.latency_compensation
                if duration and duration > 0:
                    expected_position = expected_position % duration
                deviation = video_position - expected_position
                # Loop-aware deviation calculation: find shortest path on timeline circle
                if duration and duration > 0:
                    candidates = [deviation, deviation + duration, deviation - duration]
                    deviation = min(candidates, key=abs)
                deviation = round(deviation, 4)
                # Median calculation (same as below)
                samples = list(self.deviation_samples)
                sorted_samples = sorted(samples)
                trim_count = max(1, len(sorted_samples) // 5)
                if len(sorted_samples) > 2 * trim_count:
                    trimmed = sorted_samples[trim_count:-trim_count]
                else:
                    trimmed = sorted_samples
                if not trimmed:
                    median_deviation = 0.0
                elif len(trimmed) % 2 == 0:
                    mid1 = trimmed[len(trimmed) // 2 - 1]
                    mid2 = trimmed[len(trimmed) // 2]
                    median_deviation = (mid1 + mid2) / 2.0
                else:
                    median_deviation = trimmed[len(trimmed) // 2]
                print(
                    f"[DEBUG_DEVIATION] Leader: {leader_time:.3f}s | Video: {video_position:.3f}s | Raw: {raw_deviation:.3f}s | Median: {median_deviation:.3f}s"
                )

        # If NO_SYNC_AFTER_LOOP is enabled and a loop has occurred, block all corrections
        if self.no_sync_after_loop and self.no_sync_after_loop_active:
            if self.critical_window_logging:
                log_info(
                    "NO_SYNC_AFTER_LOOP active: blocking all sync corrections after loop.",
                    component="sync",
                )
            return

        # Block all corrections during post-loop grace period
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

        # Loop detection: only after first sample
        if self.last_video_position is not None:
            # The threshold is large to avoid triggering on small stutters.
            if (
                self.last_video_position > video_position + 1.0
            ):  # e.g. 634.0 > 0.5 + 1.0
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
                return  # Skip sync check for one cycle to gather fresh data
        # Always update last_video_position
        self.last_video_position = video_position

        # Calculate expected position with latency compensation
        # Wrap to video duration if known
        duration = self.video_player.get_duration()
        expected_position = leader_time + self.latency_compensation
        if duration and duration > 0:
            expected_position = expected_position % duration

        deviation = video_position - expected_position

        # Loop-aware deviation calculation: find shortest path on timeline circle
        if duration and duration > 0:
            candidates = [deviation, deviation + duration, deviation - duration]
            deviation = min(candidates, key=abs)

        # Round to reduce floating point noise in logs
        deviation = round(deviation, 4)

        # Always collect samples for analysis
        self.deviation_samples.append(deviation)

        # Critical window logging
        if self.critical_window_logging and self.in_critical_window:
            log_info(
                f"SYNC_EVAL: Sample {deviation:.3f}s ({len(self.deviation_samples)}/{self.deviation_samples_maxlen})",
                component="sync",
            )

        # Check if we have enough samples for correction
        min_samples = self.deviation_samples_maxlen // 2
        if len(self.deviation_samples) < min_samples:
            if self.critical_window_logging and self.in_critical_window:
                log_info(
                    f"SYNC_EVAL: Need {min_samples - len(self.deviation_samples)} more samples",
                    component="sync",
                )
            return

        # Calculate median with outlier filtering (trimmed mean)
        sorted_samples = sorted(self.deviation_samples)
        trim_count = max(1, len(sorted_samples) // 5)
        if len(sorted_samples) > 2 * trim_count:
            trimmed = sorted_samples[trim_count:-trim_count]
        else:
            trimmed = sorted_samples

        # Calculate median properly
        if not trimmed:
            median_deviation = 0.0
        elif len(trimmed) % 2 == 0:
            # Even number of elements - average the two middle values
            mid1 = trimmed[len(trimmed) // 2 - 1]
            mid2 = trimmed[len(trimmed) // 2]
            median_deviation = (mid1 + mid2) / 2.0
        else:
            # Odd number of elements - take the middle value
            median_deviation = trimmed[len(trimmed) // 2]

        if self.critical_window_logging and self.in_critical_window:
            # Only show median calc when correction is actually needed
            if abs(median_deviation) > self.deviation_threshold:
                print(
                    f"SYNC_MEDIAN_CALC | Samples: {len(self.deviation_samples)} | "
                    f"Median: {median_deviation:.3f}s | Threshold: {self.deviation_threshold:.3f}s"
                )

        # Check if correction is needed
        if abs(median_deviation) > self.deviation_threshold:
            # SAFE ZONE: If we are very close to the end of the video,
            # block corrections to allow VLC's natural loop to occur without interference.
            time_to_end = (
                duration - video_position
                if duration and video_position is not None
                else 0
            )
            if duration and time_to_end < 2.0:
                log_info(
                    f"In loop safe zone ({time_to_end:.2f}s to end), "
                    f"blocking correction of {median_deviation:.3f}s to allow natural loop.",
                    component="sync",
                )
                return

            current_time = time.time()

            # Rate limit corrections
            if current_time - self.last_correction_time < self.sync_check_interval:
                # Don't spam during rate limiting - only log in critical window
                if self.critical_window_logging and self.in_critical_window:
                    time_left = self.sync_check_interval - (
                        current_time - self.last_correction_time
                    )
                    log_info(
                        f"SYNC_EVAL: Correction blocked, {time_left:.1f}s remaining",
                        component="sync",
                    )
                return

            # Always log sync corrections (this is important)
            log_info(
                f"🔄 SYNC CORRECTION: {median_deviation:.3f}s deviation > {self.deviation_threshold:.3f}s threshold at {leader_time:.1f}s",
                component="sync",
            )
            print(f"🔄 Sync correction: {median_deviation:.3f}s deviation")

            # Calculate target position with latency compensation
            correction_offset = (
                -self.latency_compensation
                if median_deviation > 0
                else self.latency_compensation
            )
            target_position = expected_position + correction_offset
            if duration and duration > 0:
                target_position = target_position % duration

            # Clear samples before correction to prevent feedback
            self.deviation_samples.clear()

            # Soft pause: set playback rate to 0
            if not self.video_player.set_playback_rate(0.0):
                log_warning(
                    "Failed to set playback rate to 0 (soft pause), falling back to hard pause",
                    component="sync",
                )
                if not self.video_player.pause():
                    log_warning("Failed to pause for correction", component="sync")
                    return

            time.sleep(0.1)  # Let VLC settle

            # Seek with jump-ahead
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
                # Reset state after correction
                self.last_correction_time = time.time()
                log_info(
                    "Waiting for sync (will resume when deviation < 0.1s)",
                    component="sync",
                )
            else:
                log_warning("Seek failed, resuming playback", component="sync")
                self.video_player.set_playback_rate(1.0)
                self.video_player.resume()
        else:
            # No correction needed - only log during critical window when samples are low
            if (
                self.critical_window_logging
                and self.in_critical_window
                and len(self.deviation_samples) < self.deviation_samples_maxlen
            ):
                print(
                    f"SYNC_NO_CORRECTION | Median {median_deviation:.3f}s <= threshold {self.deviation_threshold:.3f}s"
                )

    def _log_sync_debug_info(self, leader_time: float) -> None:
        """Log sync information for debugging"""
        if not self.video_player.is_playing:
            return

        video_position = self.video_player.get_position()
        duration = self.video_player.get_duration()
        if video_position is None:
            return

        # Calculate expected position and deviations
        expected_position = leader_time + self.latency_compensation
        if duration and duration > 0:
            expected_position = expected_position % duration

        raw_deviation = video_position - expected_position

        # Loop-aware deviation (choose shortest path around the circle)
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
                f"SYNC_LOOP_DEBUG | Leader: {leader_time:.3f}s | Video: {video_position:.3f}s | "
                f"Deviation: {loop_aware_deviation:.3f}s | Samples: {len(self.deviation_samples)}/{self.deviation_samples_maxlen}"
            )

    def run(self) -> None:
        """Main run loop"""
        print(f"Starting KitchenSync Collaborator '{self.config.device_id}'")

        # Start networking
        self.sync_receiver.start_listening()
        # No command listening needed; we only follow timecode

        # Register with leader
        self.command_listener.send_registration(
            self.config.device_id, self.config.video_file
        )

        # Start heartbeat
        def heartbeat_loop():
            last_registration = time.time()
            while self.system_state.is_running:
                status = "running" if self.system_state.is_running else "ready"
                self.command_listener.send_heartbeat(self.config.device_id, status)
                # Periodic re-registration
                now = time.time()
                if now - last_registration >= self.reregister_interval_seconds:
                    self.command_listener.send_registration(
                        self.config.device_id, self.config.video_file
                    )
                    last_registration = now
                time.sleep(self.heartbeat_interval_seconds)

        heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
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
        help="Enable detailed sync logging during video loop transitions (5s before end to 5s after restart)",
    )
    parser.add_argument(
        "--debug_deviation",
        action="store_true",
        help="Print raw deviation between leader and collaborator video positions to the console",
    )
    args = parser.parse_args()

    try:
        collaborator = CollaboratorPi(args.config_file)

        # Override debug mode if specified
        if args.debug:
            collaborator.config.config["KITCHENSYNC"]["debug"] = "true"
            collaborator.debug_sync_logging = True
            print("✓ Debug mode: ENABLED (via command line)")
            print("✓ Sync debug logging: ENABLED")

        # Enable critical window sync logging if specified
        if args.debug_loop:
            collaborator.critical_window_logging = True
            print("✓ Loop debug mode: ENABLED (via command line)")
            print(
                "✓ Critical window sync logging: ENABLED (5s before video end to 5s after restart)"
            )

        # Enable debug deviation mode if specified
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
