#!/usr/bin/env python3
"""
KitchenSync Leader - Main entry point for the Leader role.
Coordinates playback, broadcasts time sync, and manages collaborators.
"""

import sys
import os
import socket
import threading
import time
import argparse
import signal
from pathlib import Path

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


class LeaderPi:
    def __init__(self, config_file=None):
        # Load configuration
        self.config = ConfigManager(config_file)
        enable_system_logging(self.config.debug_mode)

        log_info("Starting KitchenSync Leader...", component="leader")

        # Core Components
        self.system_state = SystemState()
        self.video_manager = VideoFileManager(self.config.video_file, self.config.usb_mount_point)
        self.schedule = Schedule(self.config.schedule_file)

        # Video Driver
        driver_name = self.config.video_driver
        self.video_player = get_video_driver(
            driver_name,
            debug_mode=self.config.debug_mode,
            enable_audio=self.config.enable_audio
        )

        if not self.video_player:
            log_error("Failed to initialize video driver", component="leader")
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
            self.video_player.load(self.video_path)
            log_info(f"Leader Playing: {abs_path}", component="leader")
            log_info(f"Video file basename (broadcasted): {Path(self.video_path).name}", component="leader")
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

        log_info("Launching KitchenSync system...", component="leader")
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
                
                # Automatic Latency Compensation
                if self.config.enable_latency_compensation:
                    # RTT is round trip; multiplier adjusts for one-way and jitter.
                    # By adding this to the broadcast time, we 'pre-advance' the packet.
                    avg_rtt = self.command_manager.get_average_rtt()
                    if avg_rtt > 0:
                        compensation = avg_rtt * self.config.latency_factor
                        return base_time + compensation
                
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
            
            # Then much slower re-broadcast for late joiners
            while self.system_state.is_running:
                time.sleep(10.0)
                if self.system_state.is_running:
                    self.command_manager.send_command(start_command)

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

        log_info("Stopping KitchenSync system...", component="leader")
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


def main():
    parser = argparse.ArgumentParser(description="KitchenSync Leader Node")
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
            leader_instance.start_system()
            while True:
                time.sleep(1)
        else:
            interface = CommandInterface("KitchenSync Leader")
            interface.register_command("start", leader_instance.start_system, "Start synchronized playback")
            interface.register_command("stop", leader_instance.stop_system, "Stop synchronized playback")
            interface.register_command("status", lambda: StatusDisplay.show_leader_status(
                leader_instance.system_state, leader_instance.command_manager.get_collaborators(), 0
            ), "Show system status")
            interface.register_command("set", leader_instance.set_sync_param, "Set sync parameter")
            interface.run()
        leader_instance.cleanup()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
