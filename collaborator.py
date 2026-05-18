#!/usr/bin/env python3
"""
KitchenSync Collaborator - Main entry point for the Collaborator role.
Receives time sync from the Leader and adjusts local playback.
"""

import sys
import os
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
            self.config.debug_mode
        )

        log_info(f"Starting KitchenSync Collaborator '{self.config.device_id}'", component="collaborator")

        # Core Components
        self.system_state = SystemState()
        self.video_manager = VideoFileManager(self.config.video_file, self.config.usb_mount_point)

        # Video Driver
        driver_name = self.config.video_driver
        self.video_player = get_video_driver(
            driver_name,
            debug_mode=self.config.debug_mode,
            enable_audio=self.config.enable_audio
        )

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
        self.active_leader_id = None
        self.video_start_time = None
        self.debug_sync_logging = self.config.debug_mode
        self.critical_window_logging = False
        self.in_critical_window = False
        self.debug_deviation_mode = False
        self.deviation_samples = []
        self.max_samples = 3  # Reduced for lower phase lag
        self.max_drift = self.config.max_drift
        self.min_drift = self.config.min_drift
        self.kp = self.config.kp
        self.min_rate = self.config.min_rate
        self.max_rate = self.config.max_rate
        self.video_path = None
        self.active_session_key = None
        self.startup_sync_count = 0
        self.FAST_SYNC_THRESHOLD = 3  # Lower threshold for faster lock

        # Sync Decoupling
        self._latest_sync_state = None
        self._sync_lock = threading.Lock()
        self._sync_thread = None
        self._stop_sync_thread = threading.Event()

    def _handle_sync(self, leader_time: float, received_at: float, leader_id: str = "unknown", sent_at: float = None) -> None:
        """Handle incoming sync packets from leader - LOW LATENCY ONLY"""
        # Leader Locking
        if self.active_leader_id is None:
            self.active_leader_id = leader_id
            log_info(f"Locked onto leader: {leader_id}", component="sync")
        elif self.active_leader_id != leader_id:
            return

        self.last_sync_at = received_at

        if not self.system_state.is_running:
            return

        # Thread-safe update of the latest sync state
        with self._sync_lock:
            self._latest_sync_state = (leader_time, received_at, sent_at)

    def _sync_processor_loop(self) -> None:
        """High-frequency loop to process stored sync state and adjust playback"""
        log_info("Sync processor thread started", component="sync")
        while not self._stop_sync_thread.is_set():
            try:
                self._process_sync_tick()
            except Exception as e:
                log_error(f"Sync processor error: {e}")
            
            # Run at 20Hz (every 50ms) for high-precision correction
            time.sleep(0.05)

    def _process_sync_tick(self) -> None:
        """Perform one tick of sync logic based on the latest stored state"""
        state = None
        with self._sync_lock:
            state = self._latest_sync_state

        if state and self.system_state.is_running:
            leader_time, received_at, sent_at = state
            
            # 1. Compensate for packet transit and local processing delay.
            adjusted_leader_time = leader_time

            if sent_at is not None:
                try:
                    transport_latency = received_at - float(sent_at)
                    if 0.0 <= transport_latency <= 0.25:
                        adjusted_leader_time += transport_latency
                except (TypeError, ValueError):
                    pass

            processing_latency = max(0.0, time.time() - received_at)
            adjusted_leader_time += processing_latency
            
            # 2. Update shared state
            self.system_state.current_time = adjusted_leader_time
            
            # 3. Process MIDI (Non-blocking)
            if self.midi_scheduler:
                self.midi_scheduler.process_cues(adjusted_leader_time)
            
            # 4. Adjust Video
            self._maintain_video_sync(adjusted_leader_time)

    def _maintain_video_sync(self, leader_time: float) -> None:
        """Calculate drift and adjust playback speed - FAST VERSION"""
        if not self.video_player.is_playing or getattr(self.video_player, "is_seeking", False):
            return

        # Query position (Now instantaneous due to background polling in GstDriver)
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

        # "Instant Lock" for startup or after a large seek
        use_immediate = self.startup_sync_count < self.FAST_SYNC_THRESHOLD
        
        if len(self.deviation_samples) >= self.max_samples or use_immediate:
            if use_immediate:
                median_dev = deviation
                self.startup_sync_count += 1
            else:
                median_dev = statistics.median(self.deviation_samples)
            
            # Tiered correction
            if abs(median_dev) > 2.0:
                log_warning(f" Huge sync deviation: {median_dev:.3f}s. Fast seeking...", component="sync")
                self.video_player.seek(leader_time, accurate=False)
                self.deviation_samples.clear()
                self.startup_sync_count = 0 # Re-trigger instant lock
            elif abs(median_dev) > self.max_drift:
                log_warning(f" Sync deviation: {median_dev:.3f}s. Precise seeking...", component="sync")
                self.video_player.seek(leader_time, accurate=True)
                self.deviation_samples.clear()
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
            self.stop_playback()
        elif cmd_type == "schedule_update":
            self._handle_schedule_update(msg, addr)
        elif cmd_type == "config_request":
            self._handle_config_request(msg, addr)
        elif cmd_type == "config_update":
            self._handle_config_update(msg, addr)
        elif cmd_type == "config_reset":
            self._handle_config_reset(msg, addr)

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
                        key in updates for key in {"midi_port"}
                    ),
                    "values": self.config.get_editable_values("collaborator"),
                }
            )
        except Exception as exc:
            response.update({"status": "error", "error": str(exc)})

        self.command_listener.send_message(response, host=addr[0])

    def _handle_config_reset(self, msg: dict, addr: tuple) -> None:
        """Reset collaborator config to defaults."""
        if not self._message_targets_this_device(msg):
            return

        response = {
            "type": "config_update_result",
            "device_id": self.config.device_id,
            "role": "collaborator",
            "config_path": self.config.get_config_path() or "collaborator_config.ini",
        }

        try:
            defaults = self.config.get_default_values("collaborator")
            config_path = self.config.get_config_path() or "collaborator_config.ini"
            self.config.clean_and_save_config(config_path, defaults, role="collaborator")
            
            response.update(
                {
                    "status": "ok",
                    "requires_restart": True,
                    "values": self.config.get_editable_values("collaborator"),
                }
            )
        except Exception as exc:
            response.update({"status": "error", "error": str(exc)})

        self.command_listener.send_message(response, host=addr[0])

    def _handle_start_command(self, msg: dict) -> None:
        """Initialize playback session from leader start command"""
        leader_file = msg.get("video_file")
        leader_id = msg.get("leader_id")
        leader_start_time = msg.get("start_time")
        
        # Lock or re-lock to leader
        if leader_id:
            if self.active_leader_id != leader_id:
                log_info(f"Sync: Switching leader to {leader_id}", component="sync")
                self.active_leader_id = leader_id

        # Find the specific file the leader is playing
        local_video_path = self.video_manager.find_video_file(target_file=leader_file)
        
        if not local_video_path:
            log_error(f"Sync: Could not find leader's video file: {leader_file}", component="collaborator")
            return

        # Compare base filenames to avoid infinite loops caused by absolute vs relative path strings
        current_playing_name = Path(self.video_path).name if self.video_path else None
        new_video_name = Path(local_video_path).name
        session_key = (leader_id, new_video_name, leader_start_time)

        if current_playing_name == new_video_name:
            sync_params = msg.get("sync_params", {})
            if sync_params:
                self._update_sync_params(sync_params)

            if self.system_state.is_running:
                if session_key == self.active_session_key:
                    return

                log_info(f"Start command received for restarted session {leader_file}", component="collaborator")
                self.stop_playback()
                self.active_session_key = None
            else:
                log_info(f"Start command received for already-loaded {leader_file}; starting playback", component="collaborator")
                self.active_session_key = session_key
                self.start_playback()
                return

        log_info(f"Start command received for {leader_file}", component="collaborator")

        # If we are here, we need to load a new file (or start for the first time)
        if self.system_state.is_running:
            self.stop_playback()

        # Load schedule
        schedule = msg.get("schedule", [])
        if self.midi_scheduler:
            self.midi_scheduler.load_schedule(schedule)

        # Update sync parameters
        sync_params = msg.get("sync_params", {})
        if sync_params:
            self._update_sync_params(sync_params)

        self.video_path = local_video_path
        if not self.video_player.load(self.video_path):
            log_error(f"Failed to load video file: {self.video_path}", component="collaborator")
            self.video_path = None
            return

        log_info(f"Collaborator Loading: {os.path.abspath(self.video_path)}", component="collaborator")
        self.active_session_key = session_key
        self.start_playback()

    def _update_sync_params(self, params: dict) -> None:
        """Update sync parameters from message"""
        self.max_drift = params.get("max_drift", self.max_drift)
        self.min_drift = params.get("min_drift", self.min_drift)
        self.kp = params.get("kp", self.kp)
        self.min_rate = params.get("min_rate", self.min_rate)
        self.max_rate = params.get("max_rate", self.max_rate)
        new_max_samples = params.get("max_samples", self.max_samples)
        if new_max_samples != self.max_samples:
            self.max_samples = new_max_samples
            self.deviation_samples.clear()

    def _handle_schedule_update(self, msg: dict, addr: tuple) -> None:
        """Handle schedule update from leader"""
        schedule = msg.get("schedule", [])
        if self.midi_scheduler:
            self.midi_scheduler.load_schedule(schedule)

    def start_playback(self) -> None:
        """Start video playback"""
        log_info("Starting playback...", component="collaborator")
        self.system_state.start_session()
        self.video_start_time = time.time()
        
        # Reset sync tracking state for fresh lock
        self.startup_sync_count = 0
        self.deviation_samples.clear()
        
        # Start sync processor thread
        self._stop_sync_thread.clear()
        self._sync_thread = threading.Thread(target=self._sync_processor_loop, daemon=True)
        self._sync_thread.start()

        if self.video_path:
            self.video_player.play()
        
        video_duration = self.video_player.get_duration()
        if self.midi_scheduler:
            self.midi_scheduler.start_playback(self.system_state.start_time, video_duration)
            
        log_info("Playback started", component="collaborator")

    def stop_playback(self) -> None:
        """Stop video playback"""
        log_info("Stopping playback...", component="collaborator")
        
        # Stop sync thread
        self._stop_sync_thread.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=0.2)
            self._sync_thread = None

        self.video_player.stop()
        if self.midi_scheduler:
            self.midi_scheduler.stop_playback()
        self.system_state.stop_session()
        self.video_start_time = None
        self.active_session_key = None
        self.deviation_samples.clear()
        log_info("Playback stopped", component="collaborator")

    def _update_critical_window_status(self, leader_time: float) -> None:
        """Update critical sync logging window status"""
        if not self.video_player.is_playing:
            self.in_critical_window = False
            return

        duration = self.video_player.get_duration()
        video_position = self.video_player.get_position()
        if not duration or duration <= 0 or video_position is None:
            return

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
        hide_mouse_cursor()
        log_info(f"Collaborator {self.config.device_id} ready.", component="collaborator")

        self.command_listener.start_listening()
        self.sync_receiver.start_listening()
        self.command_listener.send_registration(self.config.device_id, self.config.video_file)

        try:
            while True:
                self.command_listener.send_heartbeat(self.config.device_id)
                time.sleep(5)
        except KeyboardInterrupt:
            self.cleanup()

    def cleanup(self) -> None:
        """Clean up resources"""
        log_info("Cleaning up...", component="collaborator")
        self.sync_receiver.stop_listening()
        self.command_listener.stop_listening()
        if self.system_state.is_running:
            self.stop_playback()
        self.video_player.cleanup()
        if self.midi_manager:
            self.midi_manager.cleanup()
        log_info("Cleanup completed", component="collaborator")


def main():
    parser = argparse.ArgumentParser(description="KitchenSync Collaborator Node")
    parser.add_argument("--config", dest="config_file", help="Path to config file")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--debug_loop", action="store_true", help="Enable critical window sync logging")
    parser.add_argument("--debug_deviation", action="store_true", help="Print raw deviation")
    args = parser.parse_args()

    try:
        collaborator = CollaboratorPi(args.config_file)
        if args.debug:
            enable_system_logging(True)
        if args.debug_loop:
            collaborator.critical_window_logging = True
        if args.debug_deviation:
            collaborator.debug_deviation_mode = True
            
        collaborator.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
