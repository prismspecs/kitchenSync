#!/usr/bin/env python3
"""
KitchenSync Leader - Main entry point for the Leader role.
Coordinates playback, broadcasts time sync, and manages collaborators.
"""

import sys
import socket
import threading
import time
import argparse
import signal
import subprocess
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config.manager import ConfigManager
from video import get_video_driver
from video.file_manager import VideoFileManager
from networking.communication import SyncBroadcaster, CommandManager
from core.schedule import Schedule, ScheduleEditor
from core.system_state import SystemState
from core.logger import log_info, log_error, log_warning, enable_system_logging
from ui.interface import CommandInterface, StatusDisplay
from ui.window_manager import hide_mouse_cursor
from protocols.midi_handler import MidiManager, MidiScheduler
from debug.html_overlay import HTMLDebugManager


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
        self.video_player = get_video_driver(driver_name, debug_mode=self.config.debug_mode)

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
        self.osc_handler = None

        if self.config.enable_midi:
            self.midi_manager = MidiManager(
                use_mock=False, use_serial=True, serial_port=None
            )
            self.midi_scheduler = MidiScheduler(self.midi_manager)
            log_info("MIDI: Initialized", component="leader")
        
        if self.config.enable_osc:
            from protocols.osc_handler import OscHandler
            self.osc_handler = OscHandler()
            log_info("OSC: Initialized", component="leader")

        # Find video file before creating debug overlay
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            self.video_player.load(self.video_path)
            log_info(f"Video file loaded: {self.video_path}", component="leader")

        # Create HTML debug overlay only if debug mode is enabled
        self.html_debug = None
        if self.config.debug_mode:
            log_info("About to create HTML debug overlay", component="leader")
            device_id = "leader-pi"
            self.html_debug = HTMLDebugManager(
                device_id, self.video_player, self.midi_scheduler
            )
            self.html_debug.start()
            log_info("HTML overlay started successfully", component="leader")

        # Collaboration State
        # CommandManager already has a 'collaborators' dict internally
        # We'll use its get_collaborators() method for the UI
        self.collaborators = self.command_manager

        # Register remote control handlers
        self.command_manager.register_handler("remote_start", lambda msg, addr: self.start_system())
        self.command_manager.register_handler("remote_stop", lambda msg, addr: self.stop_system())
        self.command_manager.register_handler("remote_seek", lambda msg, addr: self.seek_video(str(msg.get("value", 0))))

        # Wire command listener for registration handled internally by CommandManager
        # but we can add an extra callback if we want custom logging
        self.command_manager.start_listening()

    def start_system(self) -> None:
        """Start the synchronized playback system"""
        if self.system_state.is_running:
            log_warning("System is already running", component="leader")
            return

        log_info("Launching KitchenSync system...", component="leader")

        hide_mouse_cursor()

        # Log system environment
        def snapshot_env():
            log_info("--- SYSTEM ENVIRONMENT SNAPSHOT ---", component="leader")
            try:
                import os
                log_info(f"DISPLAY: {os.environ.get('DISPLAY')}", component="leader")
                log_info(f"XAUTHORITY: {os.environ.get('XAUTHORITY')}", component="leader")
            except Exception:
                pass
        snapshot_env()

        # Start system state
        self.system_state.start_session()

        # Load schedule for protocol schedulers
        if self.midi_scheduler:
            self.midi_scheduler.load_schedule(self.schedule.get_cues())

        # Start video playback
        if self.video_path:
            log_info("Starting video playback...", component="video")
            try:
                self.video_player.play()
            except Exception as e:
                log_error(f"Exception starting video playback: {e}", component="leader")

        # Start networking
        def media_time_provider():
            try:
                return self.video_player.get_position()
            except Exception:
                return None

        self.sync_broadcaster.set_time_provider(media_time_provider)
        self.sync_broadcaster.set_duration_provider(self.video_player.get_duration)
        self.sync_broadcaster.start_broadcasting(self.system_state.start_time)
        self.command_manager.start_listening()

        # Start MIDI playback
        video_duration = self.video_player.get_duration()
        if self.midi_scheduler:
            self.midi_scheduler.start_playback(0.0, video_duration)

        # Periodically send start command to collaborators (handles late joiners/packet loss)
        def start_broadcast_loop():
            start_command = {
                "type": "start",
                "schedule": self.schedule.get_cues(),
                "start_time": self.system_state.start_time,
                "debug_mode": self.config.debug_mode,
                "sync_params": {
                    "max_drift": self.config.max_drift,
                    "min_drift": self.config.min_drift,
                    "kp": self.config.kp,
                    "min_rate": self.config.min_rate,
                    "max_rate": self.config.max_rate,
                    "max_samples": self.config.max_samples,
                },
            }
            while self.system_state.is_running:
                self.command_manager.send_command(start_command)
                time.sleep(2.0)

        threading.Thread(target=start_broadcast_loop, daemon=True).start()

        # MIDI SCHEDULER CUE PROCESSING LOOP
        def midi_cue_loop():
            while self.system_state.is_running and self.midi_scheduler:
                current_time = None
                try:
                    current_time = self.video_player.get_position()
                except Exception:
                    current_time = time.time() - self.system_state.start_time

                if current_time is not None and self.system_state.is_running:
                    self.midi_scheduler.process_cues(current_time)
                time.sleep(0.02)

        if self.midi_scheduler:
            threading.Thread(target=midi_cue_loop, daemon=True).start()
        
        log_info("System started successfully!", component="leader")

    def stop_system(self) -> None:
        """Stop the synchronized playback system"""
        if not self.system_state.is_running:
            log_warning("System is not running", component="leader")
            return

        log_info("Stopping KitchenSync system...", component="leader")
        self.video_player.stop()
        self.sync_broadcaster.stop_broadcasting()
        self.command_manager.stop_listening()
        if self.midi_scheduler:
            self.midi_scheduler.stop_playback()
        self.system_state.stop_session()
        self.command_manager.send_command({"type": "stop"})
        log_info("System stopped", component="leader")

    def show_status(self) -> None:
        """Display system status"""
        StatusDisplay.show_leader_status(
            self.system_state,
            self.collaborators.get_collaborators(),
            self.schedule.get_cue_count(),
        )
        log_info("Schedule Summary:", component="schedule")
        StatusDisplay.show_schedule_summary(self.schedule.get_cues())

    def edit_schedule(self) -> None:
        """Edit the MIDI schedule"""
        editor = ScheduleEditor(self.schedule)
        editor.run_editor()

    def force_fullscreen(self) -> None:
        """Force fullscreen mode for video player"""
        if not self.video_player:
            log_warning("No video player available", component="leader")
            return
        self.video_player.set_fullscreen(True)
        log_info(" Fullscreen mode requested", component="leader")

    def seek_video(self, time_str: str) -> None:
        """Seek the video to a specific time."""
        if not self.video_player:
            log_warning("No video player available", component="leader")
            return
        try:
            seconds = float(time_str)
            log_info(f"Seeking video to {seconds} seconds...", component="leader")
            success = self.video_player.seek(seconds)
            if success:
                log_info(f" Seek successful to {seconds}s", component="leader")
                if self.midi_scheduler:
                    self.midi_scheduler.reset()
            else:
                log_error("✗ Failed to seek video", component="leader")
        except ValueError:
            log_error(f"Invalid time format: '{time_str}'.", component="leader")
        except Exception as e:
            log_error(f"An error occurred during seek: {e}", component="leader")

    def cleanup(self) -> None:
        """Clean up resources"""
        if self.system_state.is_running:
            self.stop_system()
        self.video_player.cleanup()
        
        if self.midi_manager:
            self.midi_manager.cleanup()
        
        if self.html_debug:
            self.html_debug.cleanup()
        log_info("Cleanup completed", component="leader")


def main():
    parser = argparse.ArgumentParser(description="KitchenSync Leader Node")
    parser.add_argument("--config", dest="config_file", help="Path to config file")
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode (HTML overlay)"
    )
    parser.add_argument(
        "--auto", action="store_true", help="Start playback automatically"
    )
    args = parser.parse_args()

    def signal_handler(sig, frame):
        log_info("Signal received, shutting down...", component="leader")
        if "leader_instance" in locals():
            leader_instance.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        leader_instance = LeaderPi(args.config_file)
        if args.debug:
            leader_instance.config.config["KITCHENSYNC"]["debug"] = "true"
            log_info("Debug mode enabled", component="autostart")

        if args.auto:
            print(" Leader Pi starting in automatic mode...")
            leader_instance.start_system()
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                leader_instance.stop_system()
        else:
            interface = CommandInterface("KitchenSync Leader")
            interface.register_command("start", leader_instance.start_system, "Start synchronized playback")
            interface.register_command("stop", leader_instance.stop_system, "Stop synchronized playback")
            interface.register_command("status", lambda: StatusDisplay.show_leader_status(
                leader_instance.system_state, leader_instance.collaborators.get_collaborators(), leader_instance.schedule.get_cue_count()
            ), "Show system status")
            interface.register_command("set", leader_instance.set_sync_param, "Set sync parameter (e.g. set tick_interval 0.05)")
            interface.register_command("cues", lambda: StatusDisplay.show_schedule_summary(
                leader_instance.schedule.get_cues()
            ), "Show schedule summary")
            interface.run()
        leader_instance.cleanup()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

    def set_sync_param(self, param: str, value: str) -> None:
        """Set a sync parameter live"""
        try:
            val = float(value)
            if param == "tick_interval":
                self.sync_broadcaster.tick_interval = max(0.02, min(val, 5.0))
                # Update config so next start packet reflects it
                self.config.config["DEFAULT"]["tick_interval"] = str(val)
                print(f"Sync interval set to {val}s")
            elif hasattr(self.config, param):
                self.config.config["DEFAULT"][param] = str(val)
                print(f"Parameter {param} set to {val} (will be updated on next sync cycle)")
            else:
                print(f"Unknown parameter: {param}")
        except ValueError:
            print(f"Invalid value: {value}. Must be a number.")
