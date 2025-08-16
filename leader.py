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
import os  # Added for os.path.basename
import subprocess

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import ConfigManager
from video import VideoFileManager, VLCVideoPlayer, LoopStrategy
from networking import SyncBroadcaster, CommandManager
from midi import MidiScheduler, MidiManager
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

        # Initialize video components with configurable logging
        self.video_manager = VideoFileManager(
            self.config.video_file, self.config.usb_mount_point
        )
        self.video_player = VLCVideoPlayer(
            debug_mode=self.config.debug_mode,
            enable_vlc_logging=self.config.enable_vlc_logging,
            vlc_log_level=self.config.vlc_log_level,
            enable_looping=True,  # Ensure leader also loops
            loop_strategy=LoopStrategy.NATURAL,  # Force natural VLC looping
        )

        # Initialize networking (wire tick_interval from config)
        self.sync_broadcaster = SyncBroadcaster(
            sync_port=self.config.getint("sync_port", 5005),
            tick_interval=1.0,  # Changed: 1 time per second for omxplayer-sync style
        )
        self.command_manager = CommandManager()

        # Initialize MIDI (for local MIDI if needed)
        self.midi_manager = MidiManager(use_mock=True)
        self.midi_scheduler = MidiScheduler(self.midi_manager)

        # Find video file before creating debug overlay
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            self.video_player.load_video(self.video_path)
            log_info(f"Video file loaded: {self.video_path}", component="leader")
        else:
            log_warning("No video file found at startup.", component="leader")

        # Create HTML debug overlay only if debug mode is enabled
        self.html_debug = None
        if self.config.debug_mode:
            log_info("About to create HTML debug overlay", component="leader")
            device_id = "leader-pi"  # Define the device_id variable
            self.debug_manager = HTMLDebugManager(
                device_id, self.video_player, self.midi_scheduler
            )
            log_info("HTMLDebugManager created, about to start", component="leader")
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

        # Start video playback first so VLC creates its window
        if self.video_player.video_path:
            log_info("Starting video playback...", component="video")
            log_info("About to start video playback", component="leader")
            try:
                result = self.video_player.start_playback()
                log_info(f"Video playback start result: {result}", component="leader")
                if not result:
                    log_error("Video playback failed to start", component="leader")
                else:
                    # Position VLC window on the left side after it starts (debug mode only)
                    if self.config.debug_mode:
                        import threading

                        def position_vlc_window():
                            time.sleep(1)  # Wait for VLC window to appear first
                            try:
                                import subprocess

                                result = subprocess.run(
                                    [
                                        "wmctrl",
                                        "-r",
                                        "VLC media player",
                                        "-e",
                                        "0,0,0,1280,1080",
                                    ],
                                    check=False,
                                    timeout=5,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                                if result.returncode == 0:
                                    log_info(
                                        "Positioned VLC window on left side",
                                        component="leader",
                                    )
                                else:
                                    log_warning(
                                        "Could not position VLC window",
                                        component="leader",
                                    )
                            except Exception as e:
                                log_warning(
                                    f"Failed to position VLC window: {e}",
                                    component="leader",
                                )

                        threading.Thread(
                            target=position_vlc_window, daemon=True
                        ).start()
                    else:
                        log_info(
                            "Production mode - no window positioning",
                            component="leader",
                        )
            except Exception as e:
                log_error(f"Exception starting video playback: {e}", component="leader")

        # Now create overlay (after VLC window exists) so both windows are visible
        if self.config.debug_mode and self.html_debug is not None:
            # HTML overlay already exists from __init__, just ensure it's visible
            log_info("HTML overlay already exists", component="leader")
        else:
            log_warning(
                "HTML overlay not found - falling back to file debug",
                component="leader",
            )
            # Fallback to file debug if overlay fails
            self.debug_file = "/tmp/kitchensync_leader_debug.txt"
            with open(self.debug_file, "w") as f:
                f.write("KitchenSync Leader Debug (Fallback)\n")
                f.write("=" * 40 + "\n")
                f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(
                    f"Video: {os.path.basename(self.video_path) if self.video_path else 'None'}\n"
                )
                f.write("=" * 40 + "\n\n")

        # Start networking
        # Use media clock if available so collaborators follow actual video time
        def media_time_provider():
            try:
                return self.video_player.get_position()
            except Exception:
                return None

        self.sync_broadcaster.set_time_provider(media_time_provider)
        self.sync_broadcaster.set_duration_provider(self.video_player.get_duration)
        self.sync_broadcaster.start_broadcasting(self.system_state.start_time)
        self.command_manager.start_listening()

        # Start MIDI playback with video duration for looping
        video_duration = self.video_player.get_duration()
        self.midi_scheduler.start_playback(self.system_state.start_time, video_duration)

        # Send start command to collaborators
        start_command = {
            "type": "start",
            "schedule": self.schedule.get_cues(),
            "start_time": self.system_state.start_time,
            "debug_mode": self.config.debug_mode,
        }
        self.command_manager.send_command(start_command)

        log_info("System started successfully!", component="leader")
        paths = log_file_paths()
        log_info(
            "Log paths: " + ", ".join([f"{k}={v}" for k, v in paths.items()]),
            component="leader",
        )

    def stop_system(self) -> None:
        """Stop the synchronized playback system"""
        if not self.system_state.is_running:
            log_warning("System is not running", component="leader")
            return

        log_info("Stopping KitchenSync system...", component="leader")

        # Stop video playback
        self.video_player.stop_playback()

        # Stop networking
        self.sync_broadcaster.stop_broadcasting()
        self.command_manager.stop_listening()

        # Stop MIDI
        self.midi_scheduler.stop_playback()

        # Stop system state
        self.system_state.stop_session()

        # Send stop command to collaborators
        self.command_manager.send_command({"type": "stop"})

        log_info("System stopped", component="leader")

    def show_status(self) -> None:
        """Display system status"""
        StatusDisplay.show_leader_status(
            self.system_state,
            self.collaborators.get_collaborators(),
            self.schedule.get_cue_count(),
        )

        # Show schedule summary
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

        current_status = self.video_player.is_fullscreen()
        log_info(f"Current fullscreen status: {current_status}", component="leader")

        if not current_status:
            log_info("Forcing fullscreen mode...", component="leader")
            success = self.video_player.force_fullscreen()
            if success:
                log_info("✓ Fullscreen mode enabled", component="leader")
            else:
                log_error("✗ Failed to enable fullscreen mode", component="leader")
        else:
            log_info("✓ Already in fullscreen mode", component="leader")

    def seek_video(self, time_str: str) -> None:
        """Seek the video to a specific time."""
        if not self.video_player:
            log_warning("No video player available", component="leader")
            return

        try:
            seconds = float(time_str)
            log_info(f"Seeking video to {seconds} seconds...", component="leader")
            success = self.video_player.set_position(seconds)
            if success:
                log_info(f"✓ Seek successful to {seconds}s", component="leader")
            else:
                log_error("✗ Failed to seek video", component="leader")
        except ValueError:
            log_error(
                f"Invalid time format: '{time_str}'. Please use seconds (e.g., '120.5').",
                component="leader",
            )
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
        if hasattr(self, "debug_file") and self.debug_file:
            try:
                with open(self.debug_file, "a") as f:
                    f.write(f"\n[{time.strftime('%H:%M:%S')}] Leader shutdown\n")
                    f.write("=" * 40 + "\n")
            except:
                pass
        log_info("Cleanup completed", component="leader")


def create_command_interface(leader: LeaderPi) -> CommandInterface:
    """Create command interface for leader"""
    interface = CommandInterface("KitchenSync Leader")

    interface.register_command(
        "start", leader.start_system, "Start synchronized playback"
    )
    interface.register_command("stop", leader.stop_system, "Stop playback")
    interface.register_command("status", leader.show_status, "Show system status")
    interface.register_command("schedule", leader.edit_schedule, "Edit schedule")
    interface.register_command(
        "seek", leader.seek_video, "Seek video to a specific time (in seconds)"
    )
    interface.register_command(
        "fullscreen", leader.force_fullscreen, "Force fullscreen mode"
    )

    return interface


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="KitchenSync Leader Pi")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Start automatically without interactive interface",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with detailed console output",
    )
    args = parser.parse_args()

    # Global variable to hold the leader instance for signal handlers
    global leader_instance
    leader_instance = None

    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"\n🛑 Received signal {signum}, shutting down gracefully...")
        if leader_instance:
            try:
                leader_instance.cleanup()
            except Exception as e:
                print(f"Error during cleanup: {e}")
        sys.exit(0)

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Create LeaderPi instance first to configure logging
        try:
            leader_instance = LeaderPi()
            # Now logging is configured, safe to log
            log_info("LeaderPi initialized successfully", component="autostart")
        except Exception as e:
            # Always log errors regardless of logging settings
            log_error(
                f"FATAL: LeaderPi initialization failed: {e}", component="autostart"
            )
            import traceback

            log_error(f"Traceback: {traceback.format_exc()}", component="autostart")
            raise

        # Override debug mode if specified via command line
        if args.debug:
            leader_instance.config.config["KITCHENSYNC"]["debug"] = "true"
            print("✓ Debug mode: ENABLED (via command line)")
            log_info("Debug mode enabled", component="autostart")

        log_info(f"args.auto = {args.auto}", component="autostart")
        if args.auto:
            print("🎯 Leader Pi starting in automatic mode...")
            print("System will auto-start playback and run continuously.")
            print("Press Ctrl+C to stop.\n")
            log_info("About to call start_system() in auto mode", component="autostart")

            # Auto-start the system
            leader_instance.start_system()
            log_info("start_system() call completed", component="autostart")

            # Keep running until interrupted
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Stopping system...")
                leader_instance.stop_system()
        else:
            # Interactive mode
            interface = create_command_interface(leader_instance)
            interface.run()

        leader_instance.cleanup()

    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
