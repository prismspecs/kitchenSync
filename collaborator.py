#!/usr/bin/env python3
"""
Refactored KitchenSync Collaborator Pi
Clean, modul        self.video_player = VLCVideoPlayer(
            debug_mode=self.config.debug_mode,
            enable_vlc_logging=self.config.enable_vlc_logging,
            vlc_log_level=self.config.vlc_log_level,
            enable_looping=False, # Collaborator should not loop; it follows the leader
            loop_strategy=LoopStrategy.NATURAL,
        )ementation using the new architecture
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
DEFAULT_SYNC_TOLERANCE = 1.0  # General sync tolerance (not currently used)
DEFAULT_SYNC_CHECK_INTERVAL = 5.0  # Min time between corrections
DEFAULT_DEVIATION_THRESHOLD = 0.2  # Error threshold to trigger correction
DEFAULT_SYNC_GRACE_TIME = 5.0  # Cooldown period after correction
DEFAULT_SYNC_JUMP_AHEAD = 3.0  # How far ahead to seek for corrections
DEFAULT_LATENCY_COMPENSATION = (
    0.0  # Network/processing delay offset (DISABLED - may cause issues)
)
DEFAULT_SEEK_SETTLE_TIME = 0.1  # VLC settling time after seek

# =============================================================================


class CollaboratorPi:
    """Refactored Collaborator Pi with clean separation of concerns"""

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
            enable_looping=False,  # Collaborator should not loop; it follows the leader
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
        self.sync_tolerance = self.config.getfloat(
            "sync_tolerance", DEFAULT_SYNC_TOLERANCE
        )
        self.sync_check_interval = self.config.getfloat(
            "sync_check_interval", DEFAULT_SYNC_CHECK_INTERVAL
        )
        self.deviation_threshold = self.config.getfloat(
            "deviation_threshold", DEFAULT_DEVIATION_THRESHOLD
        )
        self.sync_grace_time = self.config.getfloat(
            "sync_grace_time", DEFAULT_SYNC_GRACE_TIME
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

        # Video sync state
        self.deviation_samples = deque(maxlen=self.deviation_samples_maxlen)
        self.last_correction_time = 0
        self.video_start_time = None
        self.last_video_position = None  # Track position to detect loops

        # Sync state management
        self.wait_for_sync = False
        self.wait_after_sync = False
        self.sync_timer = 0

        # Loop detection and grace period
        self.loop_grace_period = 1.0  # 1 second grace period after loop
        self.last_loop_time = 0

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
        self.video_restart_time = None  # Track when video restarts after loop

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

        # Debug sync logging - critical window logging only if enabled via --debug_loop
        if self.critical_window_logging and self.in_critical_window:
            current_time = time.time()
            log_interval = 0.05  # 50ms interval during critical window
            if current_time - self.last_debug_log_time >= log_interval:
                self._log_sync_debug_info(leader_time)
                self.last_debug_log_time = current_time
        elif self.debug_sync_logging:
            # Standard debug logging (if manually enabled via --debug)
            current_time = time.time()
            if current_time - self.last_debug_log_time >= self.debug_log_interval:
                self._log_sync_debug_info(leader_time)
                self.last_debug_log_time = current_time

        # Handle omxplayer-sync style wait states
        if self.wait_for_sync:
            # We're waiting for deviation to become small enough after a seek
            current_position = self.video_player.get_position() or 0
            deviation = abs(leader_time - current_position)
            if deviation < self.sync_deviation_threshold_resume:
                log_info(
                    f"Sync achieved! Deviation: {deviation:.3f}s, resuming playback",
                    component="sync",
                )
                self.video_player.resume()
                self.wait_for_sync = False
                self.wait_after_sync = time.time()
            else:
                # Still waiting for sync
                if time.time() - self.sync_timer > self.sync_timeout_seconds:
                    log_warning(
                        f"Sync timeout after {self.sync_timeout_seconds}s, deviation still {deviation:.3f}s",
                        component="sync",
                    )
                    self.video_player.resume()
                    self.wait_for_sync = False
                    self.wait_after_sync = time.time()
                return

        if self.wait_after_sync:
            # Grace period after correction - don't allow new corrections
            if (time.time() - self.wait_after_sync) > self.sync_grace_time:
                self.wait_after_sync = False
            else:
                return

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
        self.last_video_position = None
        self.deviation_samples.clear()

        log_info("Playback stopped", component="collaborator")

    def _update_critical_window_status(self, leader_time: float) -> None:
        """Update whether we're in the critical sync logging window"""
        if not self.video_player.is_playing:
            if self.in_critical_window:
                self.in_critical_window = False
                print("EXITING CRITICAL SYNC WINDOW (playback stopped)")
            return

        duration = self.video_player.get_duration()
        if not duration or duration <= 0:
            return

        # Use the collaborator's actual video position for window detection
        video_position = self.video_player.get_position()
        if video_position is None:
            return

        time_to_end = duration - video_position

        # Check if we're in the pre-end critical window
        approaching_end = time_to_end <= self.critical_window_start_threshold

        # Check if we're in the post-restart critical window
        after_restart = False
        if self.video_restart_time:
            time_since_restart = time.time() - self.video_restart_time
            if time_since_restart > self.critical_window_end_threshold:
                # Window is over, reset the restart time
                self.video_restart_time = None
                after_restart = False
            else:
                after_restart = True

        was_in_critical_window = self.in_critical_window
        self.in_critical_window = approaching_end or after_restart

        # Log when entering/exiting critical window
        if self.in_critical_window and not was_in_critical_window:
            reason = "approaching end" if approaching_end else "after restart"
            print(
                f"ENTERING CRITICAL SYNC WINDOW: {reason} (CollabPos={video_position:.2f}s, TimeToEnd={time_to_end:.2f}s)"
            )
        elif not self.in_critical_window and was_in_critical_window:
            print(f"EXITING CRITICAL SYNC WINDOW (CollabPos={video_position:.2f}s)")

    def _check_video_sync(self, leader_time: float) -> None:
        """Check and correct video sync using median filtering"""
        if not self.video_player.is_playing or not self.video_start_time:
            return

        # Get current video position
        video_position = self.video_player.get_position()
        if video_position is None:
            log_warning("Could not get video position for sync check", component="sync")
            return

        # Detect if we just looped
        if self.last_video_position is not None:
            duration = self.video_player.get_duration()
            if duration and duration > 0:
                # If position jumped backwards significantly, we likely looped
                position_jump = self.last_video_position - video_position
                if position_jump > duration * 0.8:  # More than 80% of video duration
                    log_info(
                        f"Loop detected: position jumped from {self.last_video_position:.2f}s to {video_position:.2f}s",
                        component="sync",
                    )
                    self.last_loop_time = time.time()
                    self.deviation_samples.clear()  # Clear old samples after loop

                    # Track video restart for critical window logging
                    self.video_restart_time = time.time()
                    if self.critical_window_logging and self.in_critical_window:
                        log_info(
                            f"VIDEO RESTART detected at {video_position:.2f}s -> {self.last_video_position:.2f}s",
                            component="sync",
                        )

        self.last_video_position = video_position

        # Check if we're in loop grace period
        current_time = time.time()
        if current_time - self.last_loop_time < self.loop_grace_period:
            log_info(
                f"In loop grace period, ignoring sync for {self.loop_grace_period - (current_time - self.last_loop_time):.2f}s more",
                component="sync",
            )
            return

        # Calculate expected position with latency compensation
        # Wrap to video duration if known
        duration = self.video_player.get_duration()
        expected_position = leader_time + self.latency_compensation
        if duration and duration > 0:
            expected_position = expected_position % duration

        deviation = video_position - expected_position

        # Make sync logic "loop-aware" by finding the shortest path on the timeline circle
        if duration and duration > 0:
            # Check distances in three scenarios: direct, collaborator looped, leader has looped
            d_direct = deviation
            d_collab_looped = deviation + duration
            d_leader_looped = deviation - duration

            # Choose the deviation with the smallest absolute magnitude
            if abs(d_leader_looped) < abs(d_direct):
                deviation = d_leader_looped
            if abs(d_collab_looped) < abs(deviation):
                deviation = d_collab_looped

        # Add to samples for median filtering
        self.deviation_samples.append(deviation)

        # Log sync evaluation in critical window
        if self.critical_window_logging and self.in_critical_window:
            log_info(
                f"SYNC_EVAL: Added deviation sample {deviation:.3f}s (samples: {len(self.deviation_samples)}/{self.deviation_samples_maxlen})",
                component="sync",
            )

        # Only proceed if we have enough samples
        if len(self.deviation_samples) < self.deviation_samples_maxlen // 2:
            if self.critical_window_logging and self.in_critical_window:
                log_info(
                    f"SYNC_EVAL: Insufficient samples ({len(self.deviation_samples)} < {self.deviation_samples_maxlen // 2}), skipping correction check",
                    component="sync",
                )
            return

        # Calculate median deviation with outlier filtering
        sorted_deviations = sorted(self.deviation_samples)
        # Use trimmed mean (remove top/bottom 20% to filter outliers)
        trim_count = max(1, len(sorted_deviations) // 5)
        trimmed_deviations = (
            sorted_deviations[trim_count:-trim_count]
            if len(sorted_deviations) > 2 * trim_count
            else sorted_deviations
        )
        median_deviation = (
            trimmed_deviations[len(trimmed_deviations) // 2]
            if trimmed_deviations
            else 0.0
        )

        # Log median calculation in critical window
        if self.critical_window_logging and self.in_critical_window:
            log_info(
                f"SYNC_EVAL: Median deviation {median_deviation:.3f}s from {len(trimmed_deviations)} trimmed samples (threshold: {self.deviation_threshold:.3f}s)",
                component="sync",
            )

        # Check if correction is needed
        # Use configured deviation_threshold directly (no hard 1.0s floor)
        correction_threshold = self.deviation_threshold
        if abs(median_deviation) > correction_threshold:
            current_time = time.time()

            # Avoid corrections too close together
            if current_time - self.last_correction_time < self.sync_check_interval:
                if self.critical_window_logging and self.in_critical_window:
                    log_info(
                        f"SYNC_EVAL: Correction needed but too soon since last correction ({current_time - self.last_correction_time:.2f}s < {self.sync_check_interval:.2f}s)",
                        component="sync",
                    )
                return

            log_info(
                f"Sync correction needed: {median_deviation:.3f}s deviation (threshold: {correction_threshold:.3f}s)",
                component="sync",
            )
            print(f"🔄 Sync correction: {median_deviation:.3f}s deviation")

            # Apply correction (respect duration wrap)
            # Nudge toward/away from leader to overcome actuation lag
            correction_lead = 0.0
            if median_deviation < 0:
                # Video is behind → seek slightly ahead
                correction_lead = self.latency_compensation
            elif median_deviation > 0:
                # Video is ahead → seek slightly behind
                correction_lead = -self.latency_compensation

            target_position = expected_position + correction_lead
            if duration and duration > 0:
                target_position = target_position % duration

            # Clear old deviation samples BEFORE seeking to prevent feedback loop
            # The old samples are from before the correction and will skew future measurements
            self.deviation_samples.clear()

            # omxplayer-sync approach: pause, seek ahead, wait for sync
            log_info(
                f"Pausing for correction, seeking to {target_position:.3f}s (jump ahead: {self.sync_jump_ahead:.3f}s)",
                component="sync",
            )

            # Pause playback during correction
            if not self.video_player.pause():
                log_warning("Failed to pause for correction", component="sync")
                return

            time.sleep(0.1)  # Brief pause for VLC to settle

            # Seek to target + jump ahead (like omxplayer-sync)
            jump_ahead_position = target_position + self.sync_jump_ahead
            if duration and duration > 0:
                jump_ahead_position = jump_ahead_position % duration

            if self.video_player.set_position(jump_ahead_position):
                log_info(
                    f"Seek successful to {jump_ahead_position:.3f}s (target was {target_position:.3f}s)",
                    component="sync",
                )
                # Enter wait-for-sync state
                self.wait_for_sync = True
                self.sync_timer = time.time()
                self.last_correction_time = time.time()

                # Log the expected sync behavior
                log_info(
                    f"Entering wait-for-sync state. Will resume when deviation < 0.1s",
                    component="sync",
                )
            else:
                log_warning("Seek failed, resuming playback", component="sync")
                self.video_player.resume()
        else:
            # No correction needed - log in critical window
            if self.critical_window_logging and self.in_critical_window:
                log_info(
                    f"SYNC_EVAL: No correction needed, median deviation {median_deviation:.3f}s within threshold {correction_threshold:.3f}s",
                    component="sync",
                )

    def _log_sync_debug_info(self, leader_time: float) -> None:
        """Log detailed sync information for debugging"""
        if not self.video_player.is_playing:
            return

        video_position = self.video_player.get_position()
        duration = self.video_player.get_duration()

        if video_position is None:
            return

        # Calculate expected position and deviation
        expected_position = leader_time + self.latency_compensation
        if duration and duration > 0:
            expected_position = expected_position % duration

        raw_deviation = video_position - expected_position

        # Calculate loop-aware deviation
        loop_aware_deviation = raw_deviation
        if duration and duration > 0:
            half_duration = duration / 2.0
            if raw_deviation > half_duration:
                loop_aware_deviation = raw_deviation - duration
            elif raw_deviation < -half_duration:
                loop_aware_deviation = raw_deviation + duration

        # Check if we're in various states
        in_grace_period = (time.time() - self.last_loop_time) < self.loop_grace_period
        waiting_for_sync = self.wait_for_sync
        waiting_after_sync = self.wait_after_sync

        # Calculate additional metrics for critical window
        time_to_end = duration - (leader_time % duration) if duration > 0 else 0
        time_since_restart = (
            time.time() - self.video_restart_time if self.video_restart_time else 999
        )
        deviation_samples_count = len(self.deviation_samples)

        if self.critical_window_logging and self.in_critical_window:
            # Simplified critical logging
            print(
                f"SYNC_LOOP_DEBUG | Leader: {leader_time:.3f}s | Collaborator: {video_position:.3f}s | "
                f"Deviation: {loop_aware_deviation:.3f}s | Samples: {len(self.deviation_samples)}/{self.deviation_samples_maxlen}"
            )
        elif self.debug_sync_logging:
            # Standard debug logging
            print(
                f"SYNC_DEBUG: Leader={leader_time:.3f}s | Video={video_position:.3f}s | "
                f"Expected={expected_position:.3f}s | RawDev={raw_deviation:.3f}s | "
                f"LoopDev={loop_aware_deviation:.3f}s | Duration={duration:.1f}s | "
                f"Grace={in_grace_period} | WaitSync={waiting_for_sync} | WaitAfter={waiting_after_sync}"
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

        collaborator.run()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
