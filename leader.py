#!/usr/bin/env python3
"""
Refactored KitchenSync Leader Pi
Clean, modular implementation using the new architecture
"""

import argparse
import sys
import threading
import time
import signal
from pathlib import Path
import os
import subprocess

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import ConfigManager
from video import VideoFileManager, get_video_driver
from networking import SyncBroadcaster, CommandManager
from protocols.midi_handler import MidiScheduler, MidiManager
from core import Schedule, ScheduleEditor, SystemState, CollaboratorRegistry
from ui import CommandInterface, StatusDisplay
from debug.html_overlay import HTMLDebugManager
from core.logger import (
    log_info,
    log_warning,
    log_error,
    snapshot_env,
    log_file_paths,
    enable_system_logging,
)


class LeaderPi:
    """Refactored Leader Pi with clean separation of concerns"""

    def __init__(self):
        # Initialize configuration
        self.config = ConfigManager("leader_config.ini")

        # Configure logging based on config settings (must be AFTER config loaded)
        enable_system_logging(self.config.enable_system_logging)

        # Initialize core components
        self.system_state = SystemState()
        self.collaborators = CollaboratorRegistry()
        self.schedule = Schedule()

        # Initialize video components
        self.video_manager = VideoFileManager(
            self.config.video_file, self.config.usb_mount_point
        )
        self.video_player = get_video_driver(
            self.config.video_driver,
            debug_mode=self.config.debug_mode
        )

        if not self.video_player:
            log_error("Failed to initialize video driver", component="leader")
            sys.exit(1)

        # Initialize networking (wire tick_interval from config)
        self.sync_broadcaster = SyncBroadcaster(
            sync_port=self.config.getint("sync_port", 5005),
            tick_interval=0.1,
        )
        self.command_manager = CommandManager()

        # Initialize MIDI (for local MIDI if needed)
        self.midi_manager = MidiManager(
            use_mock=False, use_serial=True, serial_port=None
        )
        self.midi_scheduler = MidiScheduler(self.midi_manager)

        # Find video file before creating debug overlay
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            self.video_player.load(self.video_path)
            log_info(f"Video file loaded: {self.video_path}", component="leader")
        else:
            log_warning("No video file found at startup.", component="leader")

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
        else:
            log_info("Debug mode disabled - no overlay created", component="leader")

        # Setup command handlers
        self._setup_command_handlers()

    def _setup_command_handlers(self) -> None:
        """Setup networking command handlers"""
        self.command_manager.register_handler("register", self._handle_registration)
        self.command_manager.register_handler("heartbeat", self._handle_heartbeat)

    def _handle_registration(self, msg: dict, addr: tuple) -> None:
        """Handle collaborator registration"""
        device_id = msg.get("device_id")
        if device_id:
            self.collaborators.register_collaborator(
                device_id,
                addr[0],
                msg.get("status", "ready"),
                msg.get("video_file", ""),
            )

    def _handle_heartbeat(self, msg: dict, addr: tuple) -> None:
        """Handle collaborator heartbeat"""
        device_id = msg.get("device_id")
        if device_id:
            self.collaborators.update_heartbeat(device_id, msg.get("status", "ready"))

    def start_system(self) -> None:
        """Start the synchronized playback system"""
        if self.system_state.is_running:
            log_warning("System is already running", component="leader")
            return

        log_info("Starting KitchenSync system...", component="leader")
        snapshot_env()

        # Start system state
        self.system_state.start_session()

        # Load schedule for MIDI scheduler
        self.midi_scheduler.load_schedule(self.schedule.get_cues())

        # Start video playback
        if self.video_path:
            log_info("Starting video playback...", component="video")
            try:
                result = self.video_player.play()
                if not result:
                    log_error("Video playback failed to start", component="leader")
                else:
                    # Position video window (debug mode & VLC only)
                    if self.config.debug_mode and self.config.video_driver == "vlc":
                        def position_vlc_window():
                            time.sleep(1)
                            try:
                                subprocess.run(
                                    ["wmctrl", "-r", "VLC media player", "-e", "0,0,0,1280,1080"],
                                    check=False, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                                )
                            except Exception:
                                pass
                        threading.Thread(target=position_vlc_window, daemon=True).start()
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
        self.midi_scheduler.start_playback(0.0, video_duration)

        # Send start command to collaborators
        start_command = {
            "type": "start",
            "schedule": self.schedule.get_cues(),
            "start_time": self.system_state.start_time,
            "debug_mode": self.config.debug_mode,
        }
        self.command_manager.send_command(start_command)

        # MIDI SCHEDULER CUE PROCESSING LOOP
        def midi_cue_loop():
            while self.system_state.is_running:
                current_time = None
                try:
                    current_time = self.video_player.get_position()
                except Exception:
                    current_time = time.time() - self.system_state.start_time

                if current_time is not None and self.system_state.is_running:
                    self.midi_scheduler.process_cues(current_time)
                time.sleep(0.02)

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
        log_info("✓ Fullscreen mode requested", component="leader")

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
                log_info(f"✓ Seek successful to {seconds}s", component="leader")
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
        self.midi_manager.cleanup()
        if self.html_debug:
            self.html_debug.cleanup()
        log_info("Cleanup completed", component="leader")


def create_command_interface(leader: LeaderPi) -> CommandInterface:
    """Create command interface for leader"""
    interface = CommandInterface("KitchenSync Leader")
    interface.register_command("start", leader.start_system, "Start synchronized playback")
    interface.register_command("stop", leader.stop_system, "Stop playback")
    interface.register_command("status", leader.show_status, "Show system status")
    interface.register_command("schedule", leader.edit_schedule, "Edit schedule")
    interface.register_command("seek", leader.seek_video, "Seek video to a specific time")
    interface.register_command("fullscreen", leader.force_fullscreen, "Force fullscreen mode")
    return interface


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="KitchenSync Leader Pi")
    parser.add_argument("--auto", action="store_true", help="Start automatically")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    global leader_instance
    leader_instance = None

    def signal_handler(signum, frame):
        print(f"\n🛑 Received signal {signum}, shutting down gracefully...")
        if leader_instance:
            leader_instance.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        leader_instance = LeaderPi()
        if args.debug:
            leader_instance.config.config["KITCHENSYNC"]["debug"] = "true"
            log_info("Debug mode enabled", component="autostart")

        if args.auto:
            print("🎯 Leader Pi starting in automatic mode...")
            leader_instance.start_system()
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                leader_instance.stop_system()
        else:
            interface = create_command_interface(leader_instance)
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
