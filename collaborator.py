#!/usr/bin/env python3
"""
KitchenSync Collaborator - Main entry point for the Collaborator role.
Receives time sync from the Leader and adjusts local playback.
"""

import sys
import time
import argparse
import signal
import statistics
import threading
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config.manager import ConfigManager
from video import get_video_driver
from video.file_manager import VideoFileManager
from networking.communication import CommandListener, SyncReceiver, CommandManager
from core.system_state import SystemState
from core.logger import log_info, log_error, log_warning, enable_system_logging
from protocols.midi_handler import MidiManager, MidiScheduler
from ui.window_manager import hide_mouse_cursor


class CollaboratorPi:
    def __init__(self, config_file=None):
        # Load configuration
        self.config = ConfigManager(config_file)
        enable_system_logging(
            self.config.enable_system_logging or self.config.debug_mode
        )

        log_info(f"Starting KitchenSync Collaborator '{self.config.device_id}'", component="collaborator")

        # Core Components
        self.system_state = SystemState()
        self.video_manager = VideoFileManager(self.config.video_file, self.config.usb_mount_point)

        # Video Driver
        driver_name = self.config.video_driver
        self.video_player = get_video_driver(driver_name, debug_mode=self.config.debug_mode)

        if not self.video_player:
            log_error("Failed to initialize video driver", component="collaborator")
            sys.exit(1)

        # Initialize Protocols (MIDI/OSC)
        self.midi_manager = None
        self.midi_scheduler = None
        self.osc_handler = None

        if self.config.enable_midi:
            midi_port = self.config.getint("midi_port", 0)
            self.midi_manager = MidiManager(midi_port)
            self.midi_scheduler = MidiScheduler(self.midi_manager)
            log_info("MIDI: Initialized", component="collaborator")

        if self.config.enable_osc:
            from protocols.osc_handler import OscHandler
            self.osc_handler = OscHandler()
            log_info("OSC: Initialized", component="collaborator")

        # Initialize networking
        self.command_listener = CommandListener()
        self.sync_receiver = SyncReceiver(
            sync_port=self.config.getint("sync_port", 5005),
            sync_callback=self._handle_sync,
        )

        # Register callbacks
        self.command_listener.register_callback(self._handle_command)

        # Sync state
        self.last_sync_at = 0
        self.video_start_time = None
        self.debug_sync_logging = self.config.debug_mode
        self.critical_window_logging = False
        self.in_critical_window = False
        self.debug_deviation_mode = False
        self.deviation_samples = []
        self.max_samples = self.config.max_samples
        self.max_drift = self.config.max_drift
        self.min_drift = self.config.min_drift
        self.kp = self.config.kp
        self.min_rate = self.config.min_rate
        self.max_rate = self.config.max_rate
        self.video_path = None

    def _register_with_leader(self):
        """DEPRECATED: Registration is now handled by command_listener.send_registration"""
        pass

    def _handle_sync(self, leader_time: float, received_at: float) -> None:
        """Handle incoming sync packets from leader"""
        self.last_sync_at = received_at

        if not self.system_state.is_running:
            if self.debug_sync_logging:
                log_info(f"Received sync while idle: {leader_time:.3f}s", component="sync")
            return

        # Update system time and maintain sync
        self.system_state.current_time = leader_time

        # Process MIDI cues (safe no-op if no schedule)
        if self.midi_scheduler:
            self.midi_scheduler.process_cues(leader_time)

        # Check for critical sync window (only if enabled via --debug_loop)
        if self.critical_window_logging:
            self._update_critical_window_status(leader_time)

        # Maintain video sync
        self._maintain_video_sync(leader_time)

    def _maintain_video_sync(self, leader_time: float) -> None:
        """Calculate drift and adjust playback speed"""
        if not self.video_player.is_playing:
            return

        video_pos = self.video_player.get_position()
        if video_pos is None:
            return

        deviation = video_pos - leader_time
        
        if self.debug_deviation_mode:
            print(f"DEVIATION: {deviation:+.4f}s (V:{video_pos:.3f} L:{leader_time:.3f})")

        # Sync logic (P-controller)
        self.deviation_samples.append(deviation)
        if len(self.deviation_samples) > self.max_samples:
            self.deviation_samples.pop(0)

        if len(self.deviation_samples) >= self.max_samples:
            median_dev = statistics.median(self.deviation_samples)
            
            # Hard seek if deviation is large (> 0.5s)
            if abs(median_dev) > self.max_drift:
                if self.debug_sync_logging:
                    log_warning(f" Large sync deviation: {median_dev:.3f}s. Seeking...", component="sync")
                self.video_player.seek(leader_time)
                self.deviation_samples.clear()
            # Fine-grained speed adjustment for smaller drifts
            elif abs(median_dev) > self.min_drift:
                new_rate = 1.0 - (median_dev * self.kp)
                new_rate = max(self.min_rate, min(self.max_rate, new_rate))
                self.video_player.set_speed(new_rate)
            else:
                self.video_player.set_speed(1.0)

    def _handle_command(self, msg: dict, addr: tuple) -> None:
        """Handle commands from leader"""
        cmd_type = msg.get("type")

        if cmd_type == "start":
            self._handle_start_command(msg)
        elif cmd_type == "stop":
            self._handle_stop_command()
        elif cmd_type == "schedule_update":
            self._handle_schedule_update(msg, addr)
        elif cmd_type == "config_request":
            self._handle_config_request(msg, addr)
        elif cmd_type == "config_update":
            self._handle_config_update(msg, addr)

    def _message_targets_this_device(self, msg: dict) -> bool:
        """Return True if a control message is addressed to this device."""
        target_device_id = msg.get("target_device_id")
        return not target_device_id or target_device_id == self.config.device_id

    def _handle_config_request(self, msg: dict, addr: tuple) -> None:
        """Reply with the editable collaborator config state."""
        if not self._message_targets_this_device(msg):
            return

        response = {
            "type": "config_state",
            "device_id": self.config.device_id,
            "role": "collaborator",
            "config_path": self.config.get_config_path() or "collaborator_config.ini",
            "fields": self.config.get_editable_fields("collaborator"),
            "values": self.config.get_editable_values("collaborator"),
        }
        self.command_listener.send_message(response, host=addr[0])

    def _handle_config_update(self, msg: dict, addr: tuple) -> None:
        """Persist collaborator config updates and report the result."""
        if not self._message_targets_this_device(msg):
            return

        editable_keys = {
            field["key"] for field in self.config.get_editable_fields("collaborator")
        }
        updates = {
            key: value
            for key, value in msg.get("updates", {}).items()
            if key in editable_keys
        }

        response = {
            "type": "config_update_result",
            "device_id": self.config.device_id,
            "role": "collaborator",
            "config_path": self.config.get_config_path() or "collaborator_config.ini",
        }

        try:
            config_path = self.config.get_config_path() or "collaborator_config.ini"
            self.config.clean_and_save_config(config_path, updates, role="collaborator")
            enable_system_logging(
                self.config.enable_system_logging or self.config.debug_mode
            )
            self.video_manager = VideoFileManager(
                self.config.video_file,
                self.config.usb_mount_point,
            )
            response.update(
                {
                    "status": "ok",
                    "requires_restart": any(
                        key in updates for key in {"video_file", "midi_port"}
                    ),
                    "values": self.config.get_editable_values("collaborator"),
                }
            )
        except Exception as exc:
            response.update({"status": "error", "error": str(exc)})

        self.command_listener.send_message(response, host=addr[0])

    def _handle_start_command(self, msg: dict) -> None:
        """Initialize playback session from leader start command"""
        incoming_video = self.video_manager.find_video_file()

        # If already playing the same content, just re-sync position instead of
        # doing a disruptive restart. The simulator resends start every 2s for
        # late joiners, so this is the common case.
        if self.system_state.is_running and incoming_video == self.video_path:
            leader_time = self.system_state.current_time
            current_position = self.video_player.get_position()
            if leader_time > 0 and current_position is not None:
                deviation = current_position - leader_time
                if abs(deviation) > self.max_drift:
                    self.video_player.seek(leader_time)
                    log_info(
                        f"Duplicate start command; re-synced to {leader_time:.2f}s",
                        component="collaborator",
                    )
                elif self.debug_sync_logging:
                    log_info(
                        f"Duplicate start command ignored; drift {deviation:+.3f}s",
                        component="collaborator",
                    )
            return

        log_info("Start command received, initializing playback...", component="collaborator")
        if self.system_state.is_running:
            log_warning("Video file changed; restarting playback.", component="collaborator")
            self.stop_playback()

        # Load schedule
        schedule = msg.get("schedule", [])
        if self.midi_scheduler:
            self.midi_scheduler.load_schedule(schedule)

        # Override debug mode if leader specifies it
        leader_debug_mode = msg.get("debug_mode", False)
        if leader_debug_mode and not self.config.debug_mode:
            self.config.config["KITCHENSYNC"]["debug"] = "true"
            self.debug_sync_logging = True
            enable_system_logging(
                self.config.enable_system_logging or self.config.debug_mode
            )

        # Update sync parameters if provided by leader
        sync_params = msg.get("sync_params", {})
        if sync_params:
            self.max_drift = sync_params.get("max_drift", self.max_drift)
            self.min_drift = sync_params.get("min_drift", self.min_drift)
            self.kp = sync_params.get("kp", self.kp)
            self.min_rate = sync_params.get("min_rate", self.min_rate)
            self.max_rate = sync_params.get("max_rate", self.max_rate)
            new_max_samples = sync_params.get("max_samples", self.max_samples)
            if new_max_samples != self.max_samples:
                self.max_samples = new_max_samples
                self.deviation_samples.clear()

        # Find and load video
        self.video_path = incoming_video
        if self.video_path:
            self.video_player.load(self.video_path)
            log_info(f"Loaded video: {self.video_path}", component="collaborator")
            self.start_playback()
        else:
            log_error("No video file found for playback!", component="collaborator")

    def _handle_stop_command(self) -> None:
        """Stop playback as requested by leader"""
        self.stop_playback()
        log_info("Stopped by leader command", component="collaborator")

    def _handle_schedule_update(self, msg: dict, addr: tuple) -> None:
        """Handle schedule update from leader"""
        schedule = msg.get("schedule", [])
        if self.midi_scheduler:
            self.midi_scheduler.load_schedule(schedule)
        print(f"Updated schedule: {len(schedule)} cues")

    def start_playback(self) -> None:
        """Start video and MIDI playback"""
        log_info("Starting playback...", component="collaborator")

        # Start system state
        self.system_state.start_session()
        self.video_start_time = time.time()

        # Start video playback first
        if self.video_path:
            log_info("Starting video...", component="video")
            self.video_player.play()

        # Start MIDI playback with video duration for looping
        video_duration = self.video_player.get_duration()
        if self.midi_scheduler:
            self.midi_scheduler.start_playback(self.system_state.start_time, video_duration)

        log_info("Playback started", component="collaborator")

    def stop_playback(self) -> None:
        """Stop video and MIDI playback"""
        log_info("Stopping playback...", component="collaborator")

        # Stop video
        self.video_player.stop()

        # Stop MIDI
        if self.midi_scheduler:
            self.midi_scheduler.stop_playback()

        # Stop system state
        self.system_state.stop_session()

        # Reset video state
        self.video_start_time = None
        self.deviation_samples.clear()

        log_info("Playback stopped", component="collaborator")

    def _update_critical_window_status(self, leader_time: float) -> None:
        """Update critical sync logging window status"""
        if not self.video_player.is_playing:
            if self.in_critical_window:
                self.in_critical_window = False
            return

        duration = self.video_player.get_duration()
        video_position = self.video_player.get_position()
        if not duration or duration <= 0 or video_position is None:
            return

        # 5 seconds before end or 5 seconds after start
        is_near_end = video_position > (duration - 5.0)
        is_near_start = video_position < 5.0

        if (is_near_end or is_near_start) and not self.in_critical_window:
            self.in_critical_window = True
            print("\n>>> ENTERING CRITICAL SYNC WINDOW (Loop point proximity) <<<")
        elif not (is_near_end or is_near_start) and self.in_critical_window:
            self.in_critical_window = False
            print(">>> EXITING CRITICAL SYNC WINDOW <<<\n")

    def run(self) -> None:
        """Main execution loop"""
        # Check for X server
        import os
        import subprocess
        x_running = False
        try:
            # Simple check if xset can query the display
            subprocess.run(["xset", "q"], check=True, capture_output=True, env={"DISPLAY": os.environ.get("DISPLAY", ":0")})
            x_running = True
            hide_mouse_cursor()
        except Exception:
            log_warning("X Server not detected on DISPLAY " + os.environ.get("DISPLAY", ":0") + ". Video will not be visible!", component="collaborator")

        log_info(f" Collaborator {self.config.device_id} started successfully!", component="collaborator")
        print(f"Collaborator '{self.config.device_id}' ready. Waiting for leader...")
        print("Press Ctrl+C to exit")

        self.command_listener.start_listening()
        self.sync_receiver.start_listening()

        # Send an initial registration immediately
        self.command_listener.send_registration(self.config.device_id, self.config.video_file)

        try:
            while True:
                # Send periodic heartbeat to keep registration alive
                self.command_listener.send_heartbeat(self.config.device_id)
                time.sleep(5)
        except KeyboardInterrupt:
            self.cleanup()

    def cleanup(self) -> None:
        """Clean up resources"""
        if self.system_state.is_running:
            self.stop_playback()

        self.video_player.cleanup()
        if self.midi_manager:
            self.midi_manager.cleanup()
        log_info("Cleanup completed", component="collaborator")


def main():
    parser = argparse.ArgumentParser(description="KitchenSync Collaborator Node")
    parser.add_argument("--config", dest="config_file", help="Path to config file")
    parser.add_argument(
        "--debug", action="store_true", help="Enable verbose sync logging"
    )
    parser.add_argument(
        "--debug_loop",
        action="store_true",
        help="Enable critical window sync logging (looping behavior)",
    )
    parser.add_argument(
        "--debug_deviation",
        action="store_true",
        help="Print raw deviation between leader and collaborator video positions to the console",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Start playback immediately without waiting for leader command",
    )
    args = parser.parse_args()

    try:
        collaborator = CollaboratorPi(args.config_file)

        # Override debug mode if specified
        if args.debug:
            collaborator.config.config["KITCHENSYNC"]["debug"] = "true"
            collaborator.debug_sync_logging = True
            enable_system_logging(True)
            print(" Debug mode: ENABLED (via command line)")
            print(" Sync debug logging: ENABLED")

        # Enable critical window sync logging if specified
        if args.debug_loop:
            collaborator.critical_window_logging = True
            print(" Loop debug mode: ENABLED (via command line)")
            print(
                " Critical window sync logging: ENABLED (5s before video end to 5s after restart)"
            )

        # Enable debug deviation mode if specified
        if args.debug_deviation:
            collaborator.debug_deviation_mode = True
            print(" Debug deviation mode: ENABLED (prints raw deviation)")

        # Start playback immediately if --auto is specified
        if args.auto:
            print(" Auto-start: Triggering playback immediately...")
        # Update sync parameters if provided by leader
        sync_params = msg.get("sync_params", {})
        if sync_params:
            self.max_drift = sync_params.get("max_drift", self.max_drift)
            self.min_drift = sync_params.get("min_drift", self.min_drift)
            self.kp = sync_params.get("kp", self.kp)
            self.min_rate = sync_params.get("min_rate", self.min_rate)
            self.max_rate = sync_params.get("max_rate", self.max_rate)
            new_max_samples = sync_params.get("max_samples", self.max_samples)
            if new_max_samples != self.max_samples:
                self.max_samples = new_max_samples
                self.deviation_samples.clear()

            # Find and load video
            collaborator.video_path = collaborator.video_manager.find_video_file()
            if collaborator.video_path:
                collaborator.video_player.load(collaborator.video_path)
                collaborator.start_playback()
            else:
                log_error("Auto-start failed: No video file found.")

        collaborator.run()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
