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
from core.logger import log_info, log_warning, log_error
from debug.html_overlay import HTMLDebugManager


class CollaboratorPi:
    """Refactored Collaborator Pi with clean separation of concerns"""

    def __init__(self, config_file: str = "collaborator_config.ini"):
        # Initialize configuration
        self.config = ConfigManager(config_file)

        # Initialize core components
        self.system_state = SystemState()
        self.sync_tracker = SyncTracker()

        # Initialize video components
        self.video_manager = VideoFileManager(
            self.config.video_file, self.config.usb_mount_point
        )
        self.video_player = VLCVideoPlayer(self.config.debug_mode)

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

        # Delay overlay creation until after VLC window exists (start_playback)
        self.html_debug = None

        # Sync settings
        self.sync_tolerance = self.config.getfloat("sync_tolerance", 1.0)
        self.sync_check_interval = self.config.getfloat("sync_check_interval", 5.0)
        self.deviation_threshold = self.config.getfloat("deviation_threshold", 0.5)

        # Video sync state
        self.deviation_samples = deque(maxlen=10)
        self.last_correction_time = 0
        self.video_start_time = None

        # Setup command handlers
        self._setup_command_handlers()

        log_info(
            f"KitchenSync Collaborator '{self.config.pi_id}' initialized",
            component="collaborator",
        )

    def _setup_command_handlers(self) -> None:
        """Setup command handlers"""
        self.command_listener.register_handler("start", self._handle_start_command)
        self.command_listener.register_handler("stop", self._handle_stop_command)
        self.command_listener.register_handler(
            "update_schedule", self._handle_schedule_update
        )

    def _handle_sync(self, leader_time: float) -> None:
        """Handle time sync from leader"""
        local_time = time.time()
        self.sync_tracker.record_sync(leader_time, local_time)

        # Update system time if running
        if self.system_state.is_running:
            self.system_state.current_time = leader_time

            # Process MIDI cues
            self.midi_scheduler.process_cues(leader_time)

            # Check video sync
            self._check_video_sync(leader_time)

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

        # Create overlay after VLC window exists
        if self.config.debug_mode and self.html_debug is None:
            self.html_debug = HTMLDebugManager(
                self.config.device_id, self.video_player, self.midi_scheduler
            )
            # Start the HTML overlay manager (opens browser and begins updates)
            self.html_debug.start()
            if self.html_debug.overlay:
                log_info(
                    f"HTML overlay created for {self.config.device_id}",
                    component="debug",
                )
            else:
                log_error(
                    f"Failed to create HTML overlay for {self.config.device_id}",
                    component="debug",
                )

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
            return

        # Calculate expected position
        time_since_start = leader_time
        deviation = video_position - time_since_start

        # Add to samples for median filtering
        self.deviation_samples.append(deviation)

        # Only proceed if we have enough samples
        if len(self.deviation_samples) < 5:
            return

        # Calculate median deviation
        sorted_deviations = sorted(self.deviation_samples)
        median_deviation = sorted_deviations[len(sorted_deviations) // 2]

        # Check if correction is needed
        if abs(median_deviation) > self.deviation_threshold:
            current_time = time.time()

            # Avoid corrections too close together
            if current_time - self.last_correction_time < self.sync_check_interval:
                return

            print(f"🔄 Sync correction: {median_deviation:.3f}s deviation")

            # Apply correction
            target_position = time_since_start
            if self.video_player.set_position(target_position):
                self.last_correction_time = current_time
                self.deviation_samples.clear()

    def run(self) -> None:
        """Main run loop"""
        print(f"Starting KitchenSync Collaborator '{self.config.pi_id}'")

        # Start networking
        self.sync_receiver.start_listening()
        self.command_listener.start_listening()

        # Register with leader
        self.command_listener.send_registration(
            self.config.pi_id, self.config.video_file
        )

        # Start heartbeat
        def heartbeat_loop():
            while True:
                status = "running" if self.system_state.is_running else "ready"
                self.command_listener.send_heartbeat(self.config.pi_id, status)
                time.sleep(2)

        heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        heartbeat_thread.start()

        # Start simple debug updates if enabled (overlay is created in start_playback)
        if self.config.debug_mode:
            self._start_simple_debug()

        print(f"✅ Collaborator {self.config.device_id} started successfully!")

        print("Collaborator ready. Waiting for commands from leader...")
        print("Press Ctrl+C to exit")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.stop_playback()
        finally:
            self.cleanup()

    def _start_simple_debug(self) -> None:
        """Start simple visual debug updates for collaborator"""

        def simple_debug_loop():
            last_time = 0
            while self.system_state.is_running:
                try:
                    # Get actual video position and timing
                    session_time = self.system_state.current_time
                    video_position = self.video_player.get_position()
                    video_duration = self.video_player.get_duration() or 180.0

                    # Use video position if available, otherwise session time
                    if (
                        video_position is not None
                        and 0 <= video_position <= video_duration
                    ):
                        current_time = video_position
                    else:
                        current_time = (
                            session_time % video_duration
                            if video_duration > 0
                            else session_time
                        )

                    # Update debug overlay every second
                    if abs(current_time - last_time) >= 1.0:
                        last_time = current_time

                        # Get MIDI info
                        current_cues = (
                            self.midi_scheduler.get_current_cues(current_time)
                            if hasattr(self.midi_scheduler, "get_current_cues")
                            else []
                        )
                        upcoming_cues = (
                            self.midi_scheduler.get_upcoming_cues(current_time)
                            if hasattr(self.midi_scheduler, "get_upcoming_cues")
                            else []
                        )

                        # Update visual overlay
                        if self.html_debug and self.html_debug.overlay:
                            video_file = self.video_player.video_path or "Unknown"

                            # Get loop information
                            video_info = self.video_player.get_video_info()
                            video_loop_count = video_info.get("loop_count", 0)
                            video_looping_enabled = video_info.get(
                                "looping_enabled", True
                            )

                            midi_stats = self.midi_scheduler.get_stats()
                            midi_loop_count = midi_stats.get("loop_count", 0)

                            self.html_debug.update_debug_info(
                                video_file=video_file,
                                current_time=current_time,
                                total_time=video_duration,
                                session_time=session_time,
                                video_position=video_position,
                                current_cues=current_cues,
                                upcoming_cues=upcoming_cues,
                                video_loop_count=video_loop_count,
                                midi_loop_count=midi_loop_count,
                                looping_enabled=video_looping_enabled,
                            )

                    time.sleep(0.5)  # Check twice per second for smoother updates

                except Exception as e:
                    log_error(f"Collaborator debug error: {e}", component="debug")
                    time.sleep(5)

        log_info(
            f"Starting simple debug loop for {self.config.device_id}", component="debug"
        )
        thread = threading.Thread(target=simple_debug_loop, daemon=True)
        thread.start()

    def cleanup(self) -> None:
        """Clean up resources"""
        if self.system_state.is_running:
            self.stop_playback()

        self.video_player.cleanup()
        self.midi_manager.cleanup()
        if self.html_debug:
            self.html_debug.cleanup()
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
