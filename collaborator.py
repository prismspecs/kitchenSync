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
from video import VideoFileManager, VLCVideoPlayer
from networking import SyncReceiver, CommandListener
from midi import MidiScheduler, MidiManager
from core import SystemState, SyncTracker
from core.logger import log_info, log_warning, log_error, enable_system_logging


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
        self.sync_receiver = SyncReceiver(sync_callback=self._handle_sync)
        self.command_listener = CommandListener()

        # Find and load video file before creating debug overlay
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            self.video_player.load_video(self.video_path)
            log_info(f"Video file loaded: {self.video_path}", component="collaborator")
        else:
            log_warning("No video file found at startup", component="collaborator")

        # Sync settings
        # sync_tolerance: general upper bound for considering system "in sync" (seconds)
        # Currently not used in the correction logic
        # sync_check_interval: minimum time between corrective seeks (seconds)
        # Example: 5.0 means once we correct, we won’t correct again for at least 5 seconds.
        # deviation_threshold: absolute median error (seconds) that triggers a correction
        # Example: 0.2 means only if we’re ≳200 ms off (consistently) we’ll correct.

        self.sync_tolerance = self.config.getfloat("sync_tolerance", 1.0)
        self.sync_check_interval = self.config.getfloat("sync_check_interval", 5.0)
        self.deviation_threshold = self.config.getfloat(
            "deviation_threshold", 0.2
        )  # Reverted: 0.05s was too tight, causing overcorrection
        # old defaults: sync_tolerance=1.0, sync_check_interval=5.0, deviation_threshold=0.5s

        # Video sync state
        self.deviation_samples = deque(
            maxlen=20
        )  # Increased: more samples for frequent sync (50x/sec)
        self.last_correction_time = 0
        self.video_start_time = None

        # Sync state management (based on omxplayer-sync approach)
        self.wait_for_sync = False
        self.wait_after_sync = False
        self.sync_timer = 0
        self.sync_grace_time = self.config.getfloat(
            "sync_grace_time", 5.0
        )  # Match omxplayer-sync: 5 second grace
        self.sync_jump_ahead = self.config.getfloat(
            "sync_jump_ahead", 3.0
        )  # Exact match to omxplayer-sync: SYNC_JUMP_AHEAD = 3

        # Latency/seek tuning
        # Accounts for network transit + decode/display pipeline latency
        self.latency_compensation = self.config.getfloat("latency_compensation", 0.15)
        # Small delay for VLC to settle after a seek (seconds)
        self.seek_settle_time = self.config.getfloat("seek_settle_time", 0.1)

        # Setup command handlers
        self._setup_command_handlers()

        log_info(
            f"KitchenSync Collaborator '{self.config.device_id}' initialized",
            component="collaborator",
        )

    def _setup_command_handlers(self) -> None:
        """No-op: collaborator now auto-starts on timecode; no commands handled"""
        return

    def _handle_sync(
        self, leader_time: float, received_at: float | None = None
    ) -> None:
        """Handle time sync from leader

        leader_time: the leader's broadcasted media/wall time in seconds
        received_at: local receipt timestamp (seconds, time.time()); if None, computed now
        """
        local_time = received_at if received_at is not None else time.time()
        self.sync_tracker.record_sync(leader_time, local_time)

        # Debug: Log every sync packet received
        log_info(
            f"SYNC PACKET: leader_time={leader_time:.3f}s, local_time={local_time:.3f}s, "
            f"running={self.system_state.is_running}",
            component="sync_debug",
        )

        # Auto-start playback on first valid sync
        if not self.system_state.is_running:
            log_info(
                f"AUTO-START: First sync received, leader_time={leader_time:.3f}s",
                component="sync_debug",
            )
            self.start_playback(initial_position=leader_time)
            log_info(
                f"Auto-started from sync, leader time: {leader_time:.3f}s. Initial seek scheduled.",
                component="collaborator",
            )
            # Set a longer initial grace period before sync corrections
            self.video_start_time = (
                time.time() - 2.5
            )  # Add delay to allow initial seek to settle
            return

        # Update system time and maintain sync
        # leader_time is now wall-clock time since start, so we can use it directly
        self.system_state.current_time = leader_time

        # Process MIDI cues (safe no-op if no schedule)
        self.midi_scheduler.process_cues(leader_time)

        # Check video sync (only if we've been running for a bit)
        if self.system_state.is_running and self.video_start_time:
            time_since_start = time.time() - self.video_start_time
            if time_since_start > 5.0:  # Wait 5 seconds before sync corrections
                self._check_video_sync(leader_time)

        # Handle omxplayer-sync style wait states
        if self.wait_for_sync:
            # We're waiting for leader time to catch up to our seek-ahead position
            # Check if leader time has caught up to where we seeked ahead
            time_since_seek = time.time() - self.sync_timer
            current_position = self.video_player.get_position() or 0

            # omxplayer-sync logic: if leader time catches up to our position, resume
            if abs(leader_time - current_position) < 0.1:
                log_info(
                    f"Leader caught up! Resuming playback. Time since seek: {time_since_seek:.2f}s",
                    component="sync",
                )
                self.video_player.resume()
                self.wait_for_sync = False
                self.wait_after_sync = time.time()
            else:
                # Still waiting - timeout after 10 seconds
                if time_since_seek > 10:
                    log_warning(
                        f"Wait timeout after {time_since_seek:.1f}s, forcing resume",
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
                log_info(
                    "Grace period ended, sync monitoring resumed", component="sync"
                )
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

    def start_playback(self, initial_position: float | None = None) -> None:
        """Start video and MIDI playback"""
        log_info("Starting playback...", component="collaborator")

        # Start system state
        self.system_state.start_session()
        self.video_start_time = time.time()

        # Start video playback first so VLC creates its window
        if self.video_player.video_path:
            log_info("Starting video...", component="video")
            self.video_player.start_playback()

            # If an initial position is provided, seek to it after a short delay
            if initial_position is not None:

                def delayed_seek():
                    time.sleep(2.5)  # Wait for VLC to initialize
                    
                    # Convert wall-clock time to video position
                    duration = self.video_player.get_duration()
                    if duration and duration > 0:
                        target_pos = (initial_position % duration) + self.latency_compensation
                        if target_pos >= duration:
                            target_pos -= duration
                    else:
                        target_pos = initial_position + self.latency_compensation
                        
                    log_info(
                        f"Performing initial seek to {target_pos:.3f}s (initial sync from wall-time {initial_position:.3f}s)",
                        component="sync",
                    )
                    self.video_player.set_position(target_pos)

                threading.Thread(target=delayed_seek, daemon=True).start()

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

    def _check_video_sync(self, leader_time: float) -> None:
        """Check and correct video sync using median filtering"""
        if not self.video_player.is_playing or not self.video_start_time:
            return

        # Get current video position
        video_position = self.video_player.get_position()
        if video_position is None:
            log_warning("Could not get video position for sync check", component="sync")
            return

        # Calculate expected position with latency compensation
        # leader_time is wall-clock time since start, convert to video position
        duration = self.video_player.get_duration()
        if duration and duration > 0:
            # Convert wall-clock time to video position (handle looping)
            expected_position = (leader_time % duration) + self.latency_compensation
            if expected_position >= duration:
                expected_position -= duration
        else:
            # No duration available, assume linear time
            expected_position = leader_time + self.latency_compensation

        deviation = video_position - expected_position

        # Debug: Enhanced logging with more context
        log_info(
            f"SYNC_CHECK: leader={leader_time:.3f}s, video_pos={video_position:.3f}s, "
            f"expected={expected_position:.3f}s, deviation={deviation:.3f}s, "
            f"duration={duration:.3f}s, samples={len(self.deviation_samples)}, "
            f"wait_sync={self.wait_for_sync}, wait_after={self.wait_after_sync}",
            component="sync_debug",
        )

        # Add to samples for median filtering
        self.deviation_samples.append(deviation)

        log_info(
            f"Sync check: leader_time={leader_time:.3f}, video_pos={video_position:.3f}, "
            f"deviation={deviation:.3f}",
            component="sync_debug",
        )

        # Only proceed if we have enough samples
        if (
            len(self.deviation_samples) < 8
        ):  # Adjusted: more samples needed for frequent sync
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

        # Debug: Log deviation analysis
        log_info(
            f"DEVIATION_ANALYSIS: raw={deviation:.3f}s, median={median_deviation:.3f}s, "
            f"threshold={self.deviation_threshold:.3f}s, samples={sorted_deviations}",
            component="sync_debug",
        )

        # Check if correction is needed - use omxplayer-sync logic
        correction_threshold = self.deviation_threshold
        if abs(median_deviation) > correction_threshold:
            current_time = time.time()

            # Avoid corrections too close together
            if current_time - self.last_correction_time < self.sync_check_interval:
                return

            log_info(
                f"Large deviation detected: {median_deviation:.3f}s (threshold: {correction_threshold:.3f}s)",
                component="sync",
            )
            print(f"🔄 Sync correction: {median_deviation:.3f}s deviation")

            # omxplayer-sync approach: pause, seek to leader + jump ahead, wait for leader to catch up
            log_info("Pausing for sync correction...", component="sync")
            
            # Pause playback during correction
            if not self.video_player.pause():
                log_warning("Failed to pause for correction", component="sync")
                return

            time.sleep(0.1)  # Brief pause for VLC to settle

            # Convert leader wall-clock time to video position + jump ahead
            if duration and duration > 0:
                video_leader_pos = leader_time % duration
                target_position = (video_leader_pos + self.sync_jump_ahead) % duration
            else:
                video_leader_pos = leader_time
                target_position = leader_time + self.sync_jump_ahead

            # Clear old deviation samples BEFORE seeking to prevent feedback loop
            self.deviation_samples.clear()

            if self.video_player.set_position(target_position):
                log_info(
                    f"Seeked ahead to {target_position:.3f}s (leader wall-time: {leader_time:.3f}s, video-pos: {video_leader_pos:.3f}s + {self.sync_jump_ahead:.3f}s jump)",
                    component="sync",
                )
                # Enter wait-for-sync state - wait for leader to catch up
                self.wait_for_sync = True
                self.sync_timer = time.time()
                self.last_correction_time = time.time()

                log_info(
                    f"Entering wait-for-sync state. Waiting for leader to reach our position...",
                    component="sync",
                )
            else:
                log_warning("Seek failed, resuming playback", component="sync")
                self.video_player.resume()

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
            while True:
                status = "running" if self.system_state.is_running else "ready"
                self.command_listener.send_heartbeat(self.config.device_id, status)
                # Periodic re-registration (every 60s)
                now = time.time()
                if now - last_registration >= 60:
                    self.command_listener.send_registration(
                        self.config.device_id, self.config.video_file
                    )
                    last_registration = now
                time.sleep(2)

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
    args = parser.parse_args()

    try:
        collaborator = CollaboratorPi(args.config_file)

        # Override debug mode if specified
        if args.debug:
            collaborator.config.config["KITCHENSYNC"]["debug"] = "true"
            print("✓ Debug mode: ENABLED (via command line)")

        collaborator.run()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
