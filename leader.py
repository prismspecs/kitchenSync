#!/usr/bin/env python3
"""
Refactored KitchenSync Leader Pi
Clean, modular implementation using the new architecture
"""

import argparse
import sys
import threading
import time
from pathlib import Path
import os  # Added for os.path.basename

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import ConfigManager
from video import VideoFileManager, VLCVideoPlayer
from networking import SyncBroadcaster, CommandManager
from midi import MidiScheduler, MidiManager
from core import Schedule, ScheduleEditor, SystemState, CollaboratorRegistry
from ui import CommandInterface, StatusDisplay
from debug.html_overlay import HTMLDebugManager
from core.logger import log_info, log_warning, log_error, snapshot_env, log_file_paths


class LeaderPi:
    """Refactored Leader Pi with clean separation of concerns"""

    def __init__(self):
        # Initialize configuration
        self.config = ConfigManager("leader_config.ini")

        # Initialize core components
        self.system_state = SystemState()
        self.collaborators = CollaboratorRegistry()
        self.schedule = Schedule()

        # Initialize video components
        self.video_manager = VideoFileManager(
            self.config.video_file, self.config.usb_mount_point
        )
        self.video_player = VLCVideoPlayer(self.config.debug_mode)

        # Initialize networking
        self.sync_broadcaster = SyncBroadcaster()
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

        # Create HTML debug overlay
        pi_id = "leader-pi"  # Define the pi_id variable
        self.html_debug = HTMLDebugManager(pi_id)
        self.html_debug.start()
        log_info("HTML overlay created")

        # Setup command handlers
        self._setup_command_handlers()

    def _setup_command_handlers(self) -> None:
        """Setup networking command handlers"""
        self.command_manager.register_handler("register", self._handle_registration)
        self.command_manager.register_handler("heartbeat", self._handle_heartbeat)

    def _handle_registration(self, msg: dict, addr: tuple) -> None:
        """Handle collaborator registration"""
        pi_id = msg.get("pi_id")
        if pi_id:
            self.collaborators.register_collaborator(
                pi_id, addr[0], msg.get("status", "ready"), msg.get("video_file", "")
            )

    def _handle_heartbeat(self, msg: dict, addr: tuple) -> None:
        """Handle collaborator heartbeat"""
        pi_id = msg.get("pi_id")
        if pi_id:
            self.collaborators.update_heartbeat(pi_id, msg.get("status", "ready"))

    def start_system(self) -> None:
        """Start the synchronized playback system"""
        if self.system_state.is_running:
            print("System is already running")
            return

        print("🚀 Starting KitchenSync system...")
        snapshot_env()

        # Start system state
        self.system_state.start_session()

        # Load schedule for MIDI scheduler
        self.midi_scheduler.load_schedule(self.schedule.get_cues())

        # Start video playback first so VLC creates its window
        if self.video_player.video_path:
            print("🎬 Starting video playback...")
            self.video_player.start_playback()

        # Now create overlay (after VLC window exists) so both windows are visible
        if self.config.debug_mode and self.html_debug is None:
            self.html_debug = HTMLDebugManager("leader-pi", is_leader=True)
            if self.html_debug.overlay:
                log_info("HTML overlay created", component="leader")
            else:
                log_warning(
                    "Failed to create overlay - falling back to file debug",
                    component="leader",
                )
                # Fallback to file debug if pygame fails
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
        self.sync_broadcaster.start_broadcasting(self.system_state.start_time)
        self.command_manager.start_listening()

        # Start MIDI playback
        self.midi_scheduler.start_playback(self.system_state.start_time)

        # Send start command to collaborators
        start_command = {
            "type": "start",
            "schedule": self.schedule.get_cues(),
            "start_time": self.system_state.start_time,
            "debug_mode": self.config.debug_mode,
        }
        self.command_manager.send_command(start_command)

        # Start simple debug updates if enabled
        if self.config.debug_mode:
            self._start_simple_debug()

        print("✅ System started successfully!")
        paths = log_file_paths()
        log_info(
            "Log paths: " + ", ".join([f"{k}={v}" for k, v in paths.items()]),
            component="leader",
        )

    def stop_system(self) -> None:
        """Stop the synchronized playback system"""
        if not self.system_state.is_running:
            print("System is not running")
            return

        print("🛑 Stopping KitchenSync system...")

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

        print("✅ System stopped")

    def show_status(self) -> None:
        """Display system status"""
        StatusDisplay.show_leader_status(
            self.system_state,
            self.collaborators.get_collaborators(),
            self.schedule.get_cue_count(),
        )

        # Show schedule summary
        print("\nSchedule Summary:")
        StatusDisplay.show_schedule_summary(self.schedule.get_cues())

    def edit_schedule(self) -> None:
        """Edit the MIDI schedule"""
        editor = ScheduleEditor(self.schedule)
        editor.run_editor()

    def _start_simple_debug(self) -> None:
        """Start simple visual debug updates"""

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
                            video_file = (
                                self.video_player.video_path
                                or self.video_path
                                or "Unknown"
                            )
                            self.html_debug.update_debug_info(
                                video_file=video_file,
                                current_time=current_time,
                                total_time=video_duration,
                                session_time=session_time,
                                video_position=video_position,
                                current_cues=current_cues,
                                upcoming_cues=upcoming_cues,
                            )

                        # Fallback to file debug if overlay failed
                        elif hasattr(self, "debug_file") and self.debug_file:
                            # Format time
                            current_min = int(current_time // 60)
                            current_sec = int(current_time % 60)
                            total_min = int(video_duration // 60)
                            total_sec = int(video_duration % 60)
                            time_str = f"{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}"

                            # Write debug info
                            with open(self.debug_file, "a") as f:
                                timestamp = time.strftime("%H:%M:%S")
                                video_name = os.path.basename(
                                    self.video_player.video_path
                                    or self.video_path
                                    or "Unknown"
                                )

                                f.write(f"[{timestamp}] KitchenSync Leader\n")
                                f.write(f"  Video: {video_name}\n")
                                f.write(f"  Time: {time_str}\n")
                                f.write(
                                    f"  Session: {session_time:.1f}s, Video pos: {video_position or 'N/A'}\n"
                                )

                                if current_cues:
                                    cue = current_cues[0]
                                    f.write(
                                        f"  Current MIDI: {cue.get('type', 'unknown')} Ch{cue.get('channel', 1)}\n"
                                    )

                                if upcoming_cues:
                                    next_cue = upcoming_cues[0]
                                    time_until = next_cue.get("time", 0) - current_time
                                    f.write(
                                        f"  Next MIDI: {next_cue.get('type', 'unknown')} in {time_until:.1f}s\n"
                                    )

                                f.write("  " + "-" * 30 + "\n")
                                f.flush()

                    time.sleep(0.5)  # Check twice per second for smoother updates

                except Exception as e:
                    print(f"[DEBUG] Simple debug error: {e}")
                    time.sleep(5)

        print("[DEBUG] Starting simple debug loop")
        thread = threading.Thread(target=simple_debug_loop, daemon=True)
        thread.start()

    def _start_debug_updates(self) -> None:
        """No longer needed - using simple debug"""
        pass

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
        print("🧹 Cleanup completed")


def create_command_interface(leader: LeaderPi) -> CommandInterface:
    """Create command interface for leader"""
    interface = CommandInterface("KitchenSync Leader")

    interface.register_command(
        "start", leader.start_system, "Start synchronized playback"
    )
    interface.register_command("stop", leader.stop_system, "Stop playback")
    interface.register_command("status", leader.show_status, "Show system status")
    interface.register_command("schedule", leader.edit_schedule, "Edit schedule")

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

    try:
        leader = LeaderPi()

        # Override debug mode if specified via command line
        if args.debug:
            leader.config.config["KITCHENSYNC"]["debug"] = "true"
            print("✓ Debug mode: ENABLED (via command line)")

        if args.auto:
            print("🎯 Leader Pi starting in automatic mode...")
            print("System will auto-start playback and run continuously.")
            print("Press Ctrl+C to stop.\n")

            # Auto-start the system
            leader.start_system()

            # Keep running until interrupted
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Stopping system...")
                leader.stop_system()
        else:
            # Interactive mode
            interface = create_command_interface(leader)
            interface.run()

        leader.cleanup()

    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
