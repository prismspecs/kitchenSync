#!/usr/bin/env python3
"""
Refactored KitchenSync Collaborator Pi
Clean, modul         # Initialize video components
        self.video_manager = VideoFileManager(
            self.config.video_file, self.config.usb_mount_point
        )
        self.video_player = VLCVideoPlayer(
            debug_mode=self.config.debug_mode,
            enable_vlc_logging=self.config.enable_vlc_logging,
            vlc_log_level=self.config.vlc_log_level,
            enable_looping=True,
            loop_strategy=LoopStrategy.NATURAL,
        ).video_player = VLCVideoPlayer(
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
# SYNCHRONIZATION PARAMETERS
# =============================================================================

# Core sync behavior
DEVIATION_SAMPLES_MAXLEN = 10  # Reduced: 10 samples is enough for median filtering
INITIAL_SYNC_WAIT_SECONDS = 2.0  # Grace period after startup
SYNC_TIMEOUT_SECONDS = 5.0  # Reduced: Max time to wait after seek
HEARTBEAT_INTERVAL_SECONDS = 2.0  # Status update frequency

# Sync thresholds (configurable via config file)
DEFAULT_SYNC_CHECK_INTERVAL = 2.0  # Reduced: Min time between corrections  
DEFAULT_DEVIATION_THRESHOLD = 0.15  # Reduced: Tighter sync tolerance
DEFAULT_SYNC_JUMP_AHEAD = 2.0  # Reduced: Less aggressive jump-ahead

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
        """Initialize synchronization parameters"""
        # Core constants
        self.deviation_samples_maxlen = DEVIATION_SAMPLES_MAXLEN
        self.initial_sync_wait_seconds = INITIAL_SYNC_WAIT_SECONDS
        self.sync_timeout_seconds = SYNC_TIMEOUT_SECONDS
        self.heartbeat_interval_seconds = HEARTBEAT_INTERVAL_SECONDS

        # Configurable sync settings
        self.sync_check_interval = self.config.getfloat(
            "sync_check_interval", DEFAULT_SYNC_CHECK_INTERVAL
        )
        self.deviation_threshold = self.config.getfloat(
            "deviation_threshold", DEFAULT_DEVIATION_THRESHOLD
        )
        self.sync_jump_ahead = self.config.getfloat(
            "sync_jump_ahead", DEFAULT_SYNC_JUMP_AHEAD
        )

        # Sync state
        self.deviation_samples = deque(maxlen=self.deviation_samples_maxlen)
        self.last_correction_time = 0
        self.video_start_time = None
        self.last_video_position = None

        # Wait states
        self.wait_for_sync = False
        self.sync_timer = 0

        # Debug logging (simplified)
        self.debug_sync_logging = False

    def _handle_sync(self, leader_time: float, received_at: float | None = None) -> None:
        """Handle time sync from leader"""
        local_time = received_at if received_at is not None else time.time()
        self.sync_tracker.record_sync(leader_time, local_time)

        # Auto-start playback on first sync
        if not self.system_state.is_running:
            self.start_playback()
            log_info(f"Auto-started from sync, leader time: {leader_time:.3f}s", component="collaborator")

        # Update system time and process MIDI
        self.system_state.current_time = leader_time
        self.midi_scheduler.process_cues(leader_time)

        # Check video sync (after initial grace period)
        if self.system_state.is_running and self.video_start_time:
            time_since_start = time.time() - self.video_start_time
            if time_since_start > self.initial_sync_wait_seconds:
                self._check_video_sync(leader_time)

        # Handle post-correction waiting
        if self.wait_for_sync:
            current_position = self.video_player.get_position() or 0
            deviation = abs(leader_time - current_position)

            if deviation < 0.1 or time.time() - self.sync_timer > self.sync_timeout_seconds:
                self.video_player.resume()
                self.wait_for_sync = False
                log_info("Resuming playback after sync correction", component="sync")

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

    def _check_video_sync(self, leader_time: float) -> None:
        """Check and correct video sync using simplified logic"""
        if not self.video_player.is_playing or not self.video_start_time:
            return

        video_position = self.video_player.get_position()
        if video_position is None:
            return

        # Simple loop detection: significant backward jump
        if self.last_video_position is not None:
            if self.last_video_position - video_position > 10.0:  # Simple 10s threshold
                log_info("Video loop detected, clearing sync samples", component="sync")
                self.deviation_samples.clear()

        self.last_video_position = video_position

        # Calculate loop-aware deviation
        duration = self.video_player.get_duration()
        expected_position = leader_time
        if duration and duration > 0:
            expected_position = expected_position % duration

        deviation = video_position - expected_position

        # Handle wraparound (loop-aware)
        if duration and duration > 0:
            if deviation > duration / 2:
                deviation -= duration
            elif deviation < -duration / 2:
                deviation += duration

        # Collect sample
        self.deviation_samples.append(round(deviation, 3))

        # Need enough samples for stable correction
        if len(self.deviation_samples) < 5:
            return

        # Simple median calculation
        sorted_samples = sorted(self.deviation_samples)
        median_deviation = sorted_samples[len(sorted_samples) // 2]

        # Debug logging
        if self.debug_sync_logging:
            print(f"SYNC: Leader={leader_time:.2f}s Video={video_position:.2f}s Deviation={median_deviation:.3f}s")

        # Check if correction needed
        if abs(median_deviation) > self.deviation_threshold:
            # Rate limiting
            if time.time() - self.last_correction_time < self.sync_check_interval:
                return

            log_info(f"Sync correction: {median_deviation:.3f}s deviation", component="sync")

            # Clear samples and perform correction
            self.deviation_samples.clear()
            
            # Pause and seek
            if not self.video_player.pause():
                return

            target_position = expected_position + self.sync_jump_ahead
            if duration and duration > 0:
                target_position = target_position % duration

            if self.video_player.set_position(target_position):
                self.wait_for_sync = True
                self.sync_timer = time.time()
                self.last_correction_time = time.time()
            else:
                self.video_player.resume()

    def run(self) -> None:
        """Main run loop"""
        print(f"Starting KitchenSync Collaborator '{self.config.device_id}'")

        # Start networking
        self.sync_receiver.start_listening()

        # Simple heartbeat
        def heartbeat_loop():
            while True:
                status = "running" if self.system_state.is_running else "ready"
                self.command_listener.send_heartbeat(self.config.device_id, status)
                time.sleep(self.heartbeat_interval_seconds)

        threading.Thread(target=heartbeat_loop, daemon=True).start()

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
    parser.add_argument("config_file", nargs="?", default="collaborator_config.ini", help="Configuration file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    try:
        collaborator = CollaboratorPi(args.config_file)

        if args.debug:
            collaborator.config.config["KITCHENSYNC"]["debug"] = "true"
            collaborator.debug_sync_logging = True
            print("✓ Debug mode enabled")

        collaborator.run()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
