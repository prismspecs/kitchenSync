#!/usr/bin/env python3
"""
kSync Leader - Main entry point for the Leader role.
Coordinates playback, broadcasts time sync, and manages collaborators.
"""

import json
import sys
import os
import socket
import threading
import time
import argparse
import signal
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config.manager import ConfigManager
from video import get_video_driver
from video.file_manager import VideoFileManager
from networking.communication import SyncBroadcaster, CommandManager
from core.schedule import Schedule
from core.system_state import SystemState
from core.logger import log_info, log_error, log_warning, enable_system_logging
from ui.interface import CommandInterface, StatusDisplay
from ui.window_manager import hide_mouse_cursor
from protocols.midi_handler import MidiManager, MidiScheduler


def _log_startup_crash(exc_type, exc_value, exc_tb):
    """Log startup crashes to file — catches import-time errors before logging init."""
    import traceback
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "startup_crash.log", "a") as f:
        f.write(f"--- CRASH at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    traceback.print_exception(exc_type, exc_value, exc_tb)


sys.excepthook = _log_startup_crash


class LeaderPi:
    def __init__(self, config_file=None):
        # Load configuration
        self.config = ConfigManager(config_file)
        enable_system_logging(self.config.debug_mode or self.config.enable_system_logging)

        log_info("Starting kSync Leader...", component="leader")

        # Core Components
        self.system_state = SystemState()
        self.video_manager = VideoFileManager(self.config.video_file, self.config.usb_mount_point)
        self.schedule = Schedule(self.config.schedule_file)

        # Video Driver
        driver_name = self.config.video_driver
        try:
            self.video_player = get_video_driver(
                driver_name,
                debug_mode=self.config.debug_mode,
                enable_audio=self.config.enable_audio,
                config=self.config
            )
        except Exception as e:
            log_error(f"Exception initializing video driver '{driver_name}': {e}", component="leader")
            self.video_player = None

        if not self.video_player:
            log_warning(f"Failed to initialize primary video driver '{driver_name}'. Falling back to mock driver.", component="leader")
            try:
                self.video_player = get_video_driver("mock", debug_mode=self.config.debug_mode, enable_audio=False)
            except Exception as e:
                log_error(f"Failed to load mock video driver fallback: {e}", component="leader")
                sys.exit(1)

        # Initialize Networking
        self.sync_broadcaster = SyncBroadcaster(
            sync_port=self.config.getint("sync_port", 5005),
            tick_interval=0.1,
        )
        self.command_manager = CommandManager()

        # Initialize Protocols (MIDI/OSC)
        self.midi_manager = None
        self.midi_scheduler = None
        if self.config.enable_midi:
            self.midi_manager = MidiManager(use_serial=True)
            self.midi_scheduler = MidiScheduler(self.midi_manager)
            log_info("MIDI: Initialized", component="leader")

        # Find video file
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            abs_path = os.path.abspath(self.video_path)
            try:
                load_success = self.video_player.load(self.video_path)
                if not load_success:
                    raise RuntimeError("Driver load returned False")
                log_info(f"Leader Loaded: {abs_path}", component="leader")
                log_info(f"Video file basename (broadcasted): {Path(self.video_path).name}", component="leader")
            except Exception as e:
                log_error(f"Failed to load video '{abs_path}' under '{driver_name}' driver: {e}. Falling back to mock driver.", component="leader")
                try:
                    self.video_player = get_video_driver("mock", debug_mode=self.config.debug_mode, enable_audio=False)
                    self.video_player.load(self.video_path)
                    log_info(f"Leader Loaded (Mock fallback): {abs_path}", component="leader")
                except Exception as me:
                    log_error(f"Failed to load video on mock fallback driver: {me}", component="leader")
        else:
            log_error("No video file found in leader search paths!", component="leader")

        # Register remote control handlers
        self.command_manager.register_handler("remote_start", lambda msg, addr: self.start_system())
        self.command_manager.register_handler("remote_stop", lambda msg, addr: self.stop_system())
        self.command_manager.register_handler("remote_seek", lambda msg, addr: self.seek_video(str(msg.get("value", 0))))
        self.command_manager.register_handler("remote_set", lambda msg, addr: self.set_sync_param(msg.get("param"), msg.get("value")))

        self.command_manager.start_listening()
        self.command_manager.start_latency_probing()

    def start_system(self) -> None:
        """Start the synchronized playback system"""
        if self.system_state.is_running:
            log_warning("System is already running", component="leader")
            return

        log_info("Launching kSync system...", component="leader")
        hide_mouse_cursor()

        # Start system state
        self.system_state.start_session()

        # Load schedule
        if self.midi_scheduler:
            self.midi_scheduler.load_schedule(self.schedule.get_cues())

        # Start video playback
        if self.video_path:
            log_info("Starting video playback...", component="video")
            try:
                self.video_player.play()
                # If we are on a desktop with a display, try to make it fullscreen
                if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                    self.video_player.set_fullscreen(True)
            except Exception as e:
                log_error(f"Exception starting video playback: {e}", component="leader")

        # Start networking
        def media_time_provider():
            try:
                base_time = self.video_player.get_position()
                if base_time is None:
                    return None
                # Broadcast raw media position only.
                # Latency compensation is now handled per-device on the
                # collaborator side using EWMA-smoothed one-way transport
                # latency, which is more accurate than a global RTT average.
                return base_time
            except Exception:
                return None

        self.sync_broadcaster.set_time_provider(media_time_provider)
        self.sync_broadcaster.set_duration_provider(self.video_player.get_duration)
        self.sync_broadcaster.leader_id = self.config.device_id
        self.sync_broadcaster.start_broadcasting(self.system_state.start_time)

        # Start MIDI playback
        video_duration = self.video_player.get_duration()
        if self.midi_scheduler:
            self.midi_scheduler.start_playback(0.0, video_duration)

        # Periodically send start command to collaborators
        def start_broadcast_loop():
            start_command = {
                "type": "start",
                "video_file": Path(self.video_path).name if self.video_path else None,
                "schedule": self.schedule.get_cues(),
                "start_time": self.system_state.start_time,
                "leader_id": self.config.device_id,
                "debug_mode": self.config.debug_mode,
                "sync_params": {
                    "max_drift": self.config.max_drift,
                    "min_drift": self.config.min_drift,
                    "kp": self.config.kp,
                    "min_rate": self.config.min_rate,
                    "max_rate": self.config.max_rate,
                    "max_samples": self.config.max_samples,
                    "enable_audio": self.config.enable_audio,
                },
            }
            # Send immediately on start
            self.command_manager.send_command(start_command)
            
            # Then much slower re-broadcast for late joiners (every 30s instead of 10s)
            while self.system_state.is_running:
                time.sleep(30.0)
                if self.system_state.is_running:
                    # Only broadcast (don't send direct to everyone again to reduce noise)
                    self.command_manager._ensure_send_socket()
                    payload = json.dumps(start_command)
                    self.command_manager.control_sock.sendto(
                        payload.encode(), (self.command_manager.broadcast_ip, self.command_manager.control_port)
                    )

        threading.Thread(target=start_broadcast_loop, daemon=True).start()

        # MIDI processing loop
        def midi_cue_loop():
            while self.system_state.is_running and self.midi_scheduler:
                current_time = self.video_player.get_position()
                if current_time is not None:
                    self.midi_scheduler.process_cues(current_time)
                time.sleep(0.02)

        if self.midi_scheduler:
            threading.Thread(target=midi_cue_loop, daemon=True).start()

        log_info("System started successfully!", component="leader")

    def stop_system(self) -> None:
        """Stop the synchronized playback system"""
        if not self.system_state.is_running:
            return

        log_info("Stopping kSync system...", component="leader")
        self.video_player.stop()
        self.sync_broadcaster.stop_broadcasting()
        if self.midi_scheduler:
            self.midi_scheduler.stop_playback()
        self.system_state.stop_session()
        self.command_manager.send_command({"type": "stop"})
        log_info("System stopped", component="leader")

    def seek_video(self, time_str: str) -> None:
        """Seek the video to a specific time."""
        if not self.video_player:
            return
        try:
            seconds = float(time_str)
            log_info(f"Seeking video to {seconds} seconds...", component="leader")
            self.video_player.seek(seconds)
            if self.midi_scheduler:
                self.midi_scheduler.reset(seconds)
        except Exception as e:
            log_error(f"An error occurred during seek: {e}", component="leader")

    def cleanup(self) -> None:
        """Clean up resources"""
        if self.system_state.is_running:
            self.stop_system()
        self.video_player.cleanup()
        self.command_manager.stop_listening()
        if self.midi_manager:
            self.midi_manager.cleanup()
        log_info("Cleanup completed", component="leader")

    def set_sync_param(self, param: str, value: Any) -> None:
        """Set a sync parameter live"""
        try:
            if param == "tick_interval":
                val = float(value)
                self.sync_broadcaster.tick_interval = val
                log_info(f"Sync interval set to {val}s", component="leader")
            elif hasattr(self.config, param):
                # ConfigManager handles internal type conversion for getboolean/getfloat
                # But here we are setting it directly on the config object if possible,
                # or just updating the internal config parser.
                self.config.set_param(param, value)
                log_info(f"Parameter {param} set to {value}", component="leader")
        except Exception as e:
            log_error(f"Failed to set parameter {param}: {e}", component="leader")

    def _handle_file_list_request(self, msg: dict, addr: tuple) -> None:
        """Reply with the local media list."""
        device_id = msg.get("target_device_id")
        if device_id and device_id != "leader-pi":
            return

        response = {
            "type": "file_list_response",
            "device_id": "leader-pi",
            "media": self.video_manager.list_videos(),
        }
        self.command_manager.send_command(response, target_pi=None) # Broadcast back or send to addr?
        # CommandManager.send_command currently broadcasts if target_pi not in collaborators.
        # But addr is where it came from.
        # I'll use a more direct send if I can.
        
    def _handle_file_delete_request(self, msg: dict, addr: tuple) -> None:
        """Delete a local file and report updated list."""
        device_id = msg.get("target_device_id")
        if device_id and device_id != "leader-pi":
            return

        filename = msg.get("filename")
        if filename:
            self.video_manager.delete_video(filename)

        # Always reply with updated list
        self._handle_file_list_request(msg, addr)

    def _handle_config_request(self, msg: dict, addr: tuple) -> None:
        """Reply with current configuration."""
        response = {
            "type": "config_state",
            "device_id": self.config.device_id,
            "role": "leader",
            "fields": self.config.get_editable_fields("leader"),
            "values": self.config.get_editable_values("leader"),
            "config_path": self.config.get_config_path() or "ksync.ini"
        }
        self.command_manager.send_command(response, target_pi=None)

    def _handle_config_update(self, msg: dict, addr: tuple) -> None:
        """Handle a configuration update from the remote controller."""
        updates = msg.get("updates", {})
        log_info(f"Applying leader config updates: {updates}", component="leader")
        
        self.config.clean_and_save_config("ksync.ini", updates, role="leader")
        
        response = {
            "type": "config_update_result",
            "device_id": self.config.device_id,
            "status": "ok",
            "requires_restart": "role" in updates
        }
        self.command_manager.send_command(response, target_pi=None)
        
        if "role" in updates and updates["role"] != "leader":
            log_info("Role change detected. Restarting...", component="leader")
            time.sleep(1)
            os.execv(sys.executable, [sys.executable, "kitchensync.py"])


def main():
    parser = argparse.ArgumentParser(description="kSync Leader Node")
    parser.add_argument("--config", dest="config_file", help="Path to config file")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--auto", action="store_true", help="Start playback automatically")
    args = parser.parse_args()

    def signal_handler(sig, frame):
        if "leader_instance" in locals():
            leader_instance.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        leader_instance = LeaderPi(args.config_file)
        if args.debug:
            enable_system_logging(True)

        if args.auto:
            try:
                leader_instance.start_system()
            except Exception as e:
                log_error(f"Auto-start playback failed: {e}. Keeping leader process alive for remote Web UI command control.", component="leader")
            while True:
                time.sleep(1)
        else:
            interface = CommandInterface("kSync Leader")
            interface.register_command("start", leader_instance.start_system, "Start synchronized playback")
            interface.register_command("stop", leader_instance.stop_system, "Stop synchronized playback")
            interface.register_command("status", lambda: StatusDisplay.show_leader_status(
                leader_instance.system_state, leader_instance.command_manager.get_collaborators(), 0
            ), "Show system status")
            interface.register_command("set", leader_instance.set_sync_param, "Set sync parameter")
            interface.run()
        leader_instance.cleanup()
    except Exception as e:
        log_error(f"Fatal leader startup error: {e}", component="leader")
        time.sleep(30)
        sys.exit(1)


if __name__ == "__main__":
    main()
