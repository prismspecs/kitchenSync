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

        # Create HTML debug overlay only if debug mode is enabled
        self.html_debug = None
        if self.config.debug_mode:
            log_info("About to create HTML debug overlay", component="leader")
            pi_id = "leader-pi"  # Define the pi_id variable
            self.html_debug = HTMLDebugManager(
                pi_id, self.video_player, self.midi_scheduler
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
                            try:
                                import subprocess
                                import time

                                log_info(
                                    "Attempting to position 'VLC media player' window...",
                                    component="leader",
                                )

                                timeout = 5  # Total time to wait for the window
                                poll_interval = 0.2  # Time to wait between checks
                                start_time = time.time()
                                success = False

                                # 1. Wait for the window to exist
                                while time.time() - start_time < timeout:
                                    try:
                                        wmctrl_list = subprocess.run(
                                            ["wmctrl", "-l"],
                                            capture_output=True,
                                            text=True,
                                            timeout=2,
                                        )
                                        if (
                                            wmctrl_list.returncode == 0
                                            and "VLC media player" in wmctrl_list.stdout
                                        ):
                                            log_info(
                                                "Found 'VLC media player' window.",
                                                component="leader",
                                            )
                                            success = True
                                            break
                                    except Exception:
                                        # Ignore exceptions during polling
                                        pass
                                    time.sleep(poll_interval)

                                # 2. If found, try to move and resize it
                                if success:
                                    try:
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
                                                "Successfully positioned VLC window.",
                                                component="leader",
                                            )
                                        else:
                                            log_warning(
                                                "Found VLC window, but failed to position it.",
                                                component="leader",
                                            )
                                    except Exception as e:
                                        log_warning(
                                            f"Error positioning VLC window: {e}",
                                            component="leader",
                                        )
                                else:
                                    log_warning(
                                        "Could not find VLC window after timeout.",
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

        # Start simple debug updates if enabled
        if self.config.debug_mode:
            self._start_simple_debug()

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
                    log_error(f"Simple debug error: {e}", component="debug")
                    time.sleep(5)

        log_info("Starting simple debug loop", component="debug")
        thread = threading.Thread(target=simple_debug_loop, daemon=True)
        thread.start()

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
        log_info("Starting main() function", component="autostart")
        try:
            leader = LeaderPi()
            log_info("LeaderPi initialized successfully", component="autostart")
        except Exception as e:
            log_error(
                f"FATAL: LeaderPi initialization failed: {e}", component="autostart"
            )
            import traceback

            log_error(f"Traceback: {traceback.format_exc()}", component="autostart")
            raise

        # Override debug mode if specified via command line
        if args.debug:
            leader.config.config["KITCHENSYNC"]["debug"] = "true"
            print("✓ Debug mode: ENABLED (via command line)")
            log_info("Debug mode enabled", component="autostart")

        log_info(f"args.auto = {args.auto}", component="autostart")
        if args.auto:
            print("🎯 Leader Pi starting in automatic mode...")
            print("System will auto-start playback and run continuously.")
            print("Press Ctrl+C to stop.\n")
            log_info("About to call start_system() in auto mode", component="autostart")

            # Auto-start the system
            leader.start_system()
            log_info("start_system() call completed", component="autostart")

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
