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
from dataclasses import dataclass, field
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import ConfigManager
from video import VideoFileManager, VLCVideoPlayer
from networking import SyncReceiver, CommandListener
from midi import MidiScheduler, MidiManager
from core import SystemState, SyncTracker
from core.logger import log_info, log_warning, log_error, enable_system_logging


@dataclass
class SyncConfig:
    """Configuration/tuning parameters for video synchronization."""

    # Minimum time between corrective seeks (seconds).
    # Prevents over-correction from rapid, small deviations.
    check_interval: float = 5.0

    # Absolute median error (seconds) that triggers a correction.
    # A value of 0.05 means we correct if consistently off by >50ms.
    deviation_threshold: float = 0.05

    # Grace period after a major sync correction before further checks (seconds).
    grace_time: float = 5.0

    # Time to seek ahead of the target position during a correction (seconds).
    # Helps ensure the video is ready to play at the correct moment.
    jump_ahead: float = 3.0

    # Estimated latency from leader broadcast to local display (seconds).
    # Compensates for network and video decoding delays.
    latency_compensation: float = 0.15

    # Number of deviation samples to collect before calculating a median.
    # More samples provide a more stable measurement.
    deviation_samples: int = 20


class CollaboratorPi:
    """Refactored Collaborator Pi with clean separation of concerns"""

    def __init__(self, config_file: str = "collaborator_config.ini"):
        # 1. Configuration
        self.config = ConfigManager(config_file)
        enable_system_logging(self.config.enable_system_logging)
        self.sync_config = self._load_sync_config()

        # 2. Core Components
        self.system_state = SystemState()
        self.sync_tracker = SyncTracker()

        # 3. Video Components
        self.video_manager = VideoFileManager(
            self.config.video_file, self.config.usb_mount_point
        )
        self.video_player = VLCVideoPlayer(
            debug_mode=self.config.debug_mode,
            enable_vlc_logging=self.config.enable_vlc_logging,
            vlc_log_level=self.config.vlc_log_level,
        )
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            self.video_player.load_video(self.video_path)
            log_info(f"Video file loaded: {self.video_path}", component="collaborator")
        else:
            log_warning("No video file found at startup", component="collaborator")

        # 4. MIDI Components
        midi_port = self.config.getint("midi_port", 0)
        self.midi_manager = MidiManager(midi_port)
        self.midi_scheduler = MidiScheduler(self.midi_manager)

        # 5. Networking
        self.sync_receiver = SyncReceiver(sync_callback=self._handle_sync)
        self.command_listener = CommandListener()

        # 6. Sync State
        self.deviation_samples = deque(maxlen=self.sync_config.deviation_samples)
        self.last_correction_time = 0
        self.video_start_time = None
        self.wait_for_sync = False
        self.wait_after_sync = False
        self.sync_timer = 0

        log_info(
            f"KitchenSync Collaborator '{self.config.device_id}' initialized",
            component="collaborator",
        )

    def _load_sync_config(self) -> SyncConfig:
        """Load sync parameters from the main config file."""
        return SyncConfig(
            check_interval=self.config.getfloat("sync_check_interval", 5.0),
            deviation_threshold=self.config.getfloat("deviation_threshold", 0.05),
            grace_time=self.config.getfloat("sync_grace_time", 5.0),
            jump_ahead=self.config.getfloat("sync_jump_ahead", 3.0),
            latency_compensation=self.config.getfloat("latency_compensation", 0.15),
            deviation_samples=self.config.getint("deviation_samples", 20),
        )

    def _handle_sync(
        self, leader_time: float, received_at: float | None = None
    ) -> None:
        """Handle time sync from leader and manage playback state."""
        local_time = received_at if received_at is not None else time.time()
        self.sync_tracker.record_sync(leader_time, local_time)

        # Auto-start playback on first valid sync message
        if not self.system_state.is_running:
            self.start_playback()
            log_info(
                f"Auto-started from sync, leader time: {leader_time:.3f}s",
                component="collaborator",
            )
            return  # Don't attempt immediate seeking

        # Update system time and process MIDI cues
        self.system_state.current_time = leader_time
        self.midi_scheduler.process_cues(leader_time)

        # Defer sync checks until video has stabilized
        if self.video_start_time and (time.time() - self.video_start_time > 2.0):
            self._manage_sync_state(leader_time)

    def _manage_sync_state(self, leader_time: float) -> None:
        """Handle the logic for waiting for sync and applying corrections."""
        # State 1: Waiting for sync to be achieved after a correction
        if self.wait_for_sync:
            current_position = self.video_player.get_position() or 0
            # Check against the expected position, including latency
            expected_position = leader_time + self.sync_config.latency_compensation
            deviation = abs(expected_position - current_position)

            if deviation < 0.1:  # Within 100ms, we're synced
                log_info(
                    f"Sync achieved! Deviation: {deviation:.3f}s, resuming playback",
                    component="sync",
                )
                self.video_player.resume()
                self.wait_for_sync = False
                self.wait_after_sync = time.time()
            elif time.time() - self.sync_timer > 10:  # Timeout after 10s
                log_warning(
                    f"Sync timeout after 10s, deviation still {deviation:.3f}s",
                    component="sync",
                )
                self.video_player.resume()
                self.wait_for_sync = False
                self.wait_after_sync = time.time()
            return

        # State 2: In a grace period after a correction
        if self.wait_after_sync:
            if (time.time() - self.wait_after_sync) > self.sync_config.grace_time:
                self.wait_after_sync = False
            else:
                return  # Don't check for new corrections during grace period

        # State 3: Normal operation, check for sync deviation
        self._check_video_sync(leader_time)

    def start_playback(self) -> None:
        """Start video and MIDI playback."""
        log_info("Starting playback...", component="collaborator")
        self.system_state.start_session()
        self.video_start_time = time.time()

        if self.video_path:
            log_info("Starting video...", component="video")
            self.video_player.start_playback()

        video_duration = self.video_player.get_duration()
        self.midi_scheduler.start_playback(self.system_state.start_time, video_duration)
        log_info("Playback started", component="collaborator")

    def stop_playback(self) -> None:
        """Stop video and MIDI playback."""
        log_info("Stopping playback...", component="collaborator")
        self.video_player.stop_playback()
        self.midi_scheduler.stop_playback()
        self.system_state.stop_session()
        self.video_start_time = None
        self.deviation_samples.clear()
        log_info("Playback stopped", component="collaborator")

    def _check_video_sync(self, leader_time: float) -> None:
        """Check and correct video sync using median filtering."""
        if not self.video_player.is_playing or not self.video_start_time:
            return

        video_position = self.video_player.get_position()
        if video_position is None:
            return

        duration = self.video_player.get_duration()
        expected_position = leader_time + self.sync_config.latency_compensation
        if duration and duration > 0:
            expected_position %= duration

        self.deviation_samples.append(video_position - expected_position)

        if len(self.deviation_samples) < self.sync_config.deviation_samples:
            return

        # Calculate median deviation with outlier filtering
        sorted_deviations = sorted(self.deviation_samples)
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

        # Check if correction is needed
        if abs(median_deviation) > self.sync_config.deviation_threshold:
            if (
                time.time() - self.last_correction_time
            ) < self.sync_config.check_interval:
                return
            self._apply_sync_correction(expected_position, median_deviation)

    def _apply_sync_correction(
        self, expected_position: float, median_deviation: float
    ) -> None:
        """Applies a sync correction by pausing, seeking, and waiting."""
        log_info(
            f"Sync correction needed: {median_deviation:.3f}s deviation (threshold: {self.sync_config.deviation_threshold:.3f}s)",
            component="sync",
        )
        print(f"🔄 Sync correction: {median_deviation:.3f}s deviation")

        duration = self.video_player.get_duration()
        correction_lead = (
            -self.sync_config.latency_compensation
            if median_deviation > 0
            else self.sync_config.latency_compensation
        )
        target_position = expected_position + correction_lead
        if duration and duration > 0:
            target_position %= duration

        self.deviation_samples.clear()

        log_info(
            f"Pausing for correction, seeking near {target_position:.3f}s",
            component="sync",
        )

        if not self.video_player.pause():
            log_warning("Failed to pause for correction", component="sync")
            return

        time.sleep(0.1)

        jump_ahead_position = target_position + self.sync_config.jump_ahead
        if duration and duration > 0:
            jump_ahead_position %= duration

        if self.video_player.set_position(jump_ahead_position):
            log_info(f"Seek successful to {jump_ahead_position:.3f}s", component="sync")
            self.wait_for_sync = True
            self.sync_timer = time.time()
            self.last_correction_time = time.time()
        else:
            log_warning("Seek failed, resuming playback", component="sync")
            self.video_player.resume()

    def run(self) -> None:
        """Main run loop for the collaborator."""
        print(f"Starting KitchenSync Collaborator '{self.config.device_id}'")
        self.sync_receiver.start_listening()
        self.command_listener.send_registration(
            self.config.device_id, self.config.video_file
        )

        heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        heartbeat_thread.start()

        print(f"✅ Collaborator {self.config.device_id} started successfully!")
        print("Waiting for time sync from leader...")
        print("Press Ctrl+C to exit")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.cleanup()

    def _heartbeat_loop(self):
        """Periodically sends heartbeat and re-registers with the leader."""
        last_registration = time.time()
        while True:
            status = "running" if self.system_state.is_running else "ready"
            self.command_listener.send_heartbeat(self.config.device_id, status)
            if time.time() - last_registration >= 60:
                self.command_listener.send_registration(
                    self.config.device_id, self.config.video_file
                )
                last_registration = time.time()
            time.sleep(2)

    def cleanup(self) -> None:
        """Clean up resources."""
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
    args = parser.parse_args()

    try:
        collaborator = CollaboratorPi(args.config_file)
        if args.debug:
            collaborator.config.config["KITCHENSYNC"]["debug"] = "true"
            print("✓ Debug mode: ENABLED (via command line)")
        collaborator.run()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        log_error(f"Fatal error: {e}", component="collaborator")
        import traceback

        log_error(f"Traceback: {traceback.format_exc()}", component="collaborator")
        sys.exit(1)


if __name__ == "__main__":
    main()
