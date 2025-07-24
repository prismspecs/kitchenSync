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

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config import ConfigManager
from video import VideoFileManager, VLCVideoPlayer
from networking import SyncBroadcaster, CommandManager
from midi import MidiScheduler, MidiManager
from core import Schedule, ScheduleEditor, SystemState, CollaboratorRegistry
from debug import DebugManager
from ui import CommandInterface, StatusDisplay


class LeaderPi:
    """Refactored Leader Pi with clean separation of concerns"""
    
    def __init__(self):
        # Initialize configuration
        self.config = ConfigManager('leader_config.ini')
        
        # Initialize core components
        self.system_state = SystemState()
        self.collaborators = CollaboratorRegistry()
        self.schedule = Schedule()
        
        # Initialize video components
        self.video_manager = VideoFileManager(
            self.config.video_file, 
            self.config.usb_mount_point
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
            print(f"[DEBUG] Video file loaded: {self.video_path}")
        else:
            print("[DEBUG] No video file found at startup.")
        
        # DebugManager will be created after video is loaded
        self.debug_manager = None
        
        # Setup command handlers
        self._setup_command_handlers()
    
    def _setup_command_handlers(self) -> None:
        """Setup networking command handlers"""
        self.command_manager.register_handler('register', self._handle_registration)
        self.command_manager.register_handler('heartbeat', self._handle_heartbeat)
    
    def _handle_registration(self, msg: dict, addr: tuple) -> None:
        """Handle collaborator registration"""
        pi_id = msg.get('pi_id')
        if pi_id:
            self.collaborators.register_collaborator(
                pi_id, addr[0], 
                msg.get('status', 'ready'),
                msg.get('video_file', '')
            )
    
    def _handle_heartbeat(self, msg: dict, addr: tuple) -> None:
        """Handle collaborator heartbeat"""
        pi_id = msg.get('pi_id')
        if pi_id:
            self.collaborators.update_heartbeat(pi_id, msg.get('status', 'ready'))
    
    def start_system(self) -> None:
        """Start the synchronized playback system"""
        if self.system_state.is_running:
            print("System is already running")
            return
        
        print("🚀 Starting KitchenSync system...")
        
        # Start system state
        self.system_state.start_session()
        
        # Load schedule for MIDI scheduler
        self.midi_scheduler.load_schedule(self.schedule.get_cues())
        
        # Start video playback
        if self.video_player.video_path:
            print("🎬 Starting video playback...")
            self.video_player.start_playback()
        
        # (Re)create DebugManager with correct video file after video is loaded
        if self.config.debug_mode:
            if self.debug_manager is not None:
                print("[DEBUG] Cleaning up previous debug overlay before creating new one.")
                self.debug_manager.cleanup()
            self.debug_manager = DebugManager(
                'leader-pi',
                self.video_player.video_path or self.video_path or self.config.video_file,
                True
            )
            print(f"[DEBUG] Debug overlay created for video: {self.video_player.video_path or self.video_path or self.config.video_file}")
        
        # Start networking
        self.sync_broadcaster.start_broadcasting(self.system_state.start_time)
        self.command_manager.start_listening()
        
        # Start MIDI playback
        self.midi_scheduler.start_playback(self.system_state.start_time)
        
        # Send start command to collaborators
        start_command = {
            'type': 'start',
            'schedule': self.schedule.get_cues(),
            'start_time': self.system_state.start_time,
            'debug_mode': self.config.debug_mode
        }
        self.command_manager.send_command(start_command)
        
        print("✅ System started successfully!")
    
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
        self.command_manager.send_command({'type': 'stop'})
        
        print("✅ System stopped")
    
    def show_status(self) -> None:
        """Display system status"""
        StatusDisplay.show_leader_status(
            self.system_state,
            self.collaborators.get_collaborators(),
            self.schedule.get_cue_count()
        )
        
        # Show schedule summary
        print("\nSchedule Summary:")
        StatusDisplay.show_schedule_summary(self.schedule.get_cues())
    
    def edit_schedule(self) -> None:
        """Edit the MIDI schedule"""
        editor = ScheduleEditor(self.schedule)
        editor.run_editor()
    
    def _start_debug_updates(self) -> None:
        """No longer needed: debug update loop is now managed by the overlay itself. Remove this method."""
        pass
    
    def cleanup(self) -> None:
        """Clean up resources"""
        if self.system_state.is_running:
            self.stop_system()
        
        self.video_player.cleanup()
        self.midi_manager.cleanup()
        if self.debug_manager:
            print("[DEBUG] Cleaning up debug overlay.")
            self.debug_manager.cleanup()
        print("🧹 Cleanup completed")


def create_command_interface(leader: LeaderPi) -> CommandInterface:
    """Create command interface for leader"""
    interface = CommandInterface("KitchenSync Leader")
    
    interface.register_command("start", leader.start_system, "Start synchronized playback")
    interface.register_command("stop", leader.stop_system, "Stop playback")
    interface.register_command("status", leader.show_status, "Show system status")
    interface.register_command("schedule", leader.edit_schedule, "Edit schedule")
    
    return interface


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='KitchenSync Leader Pi')
    parser.add_argument('--auto', action='store_true', 
                       help='Start automatically without interactive interface')
    parser.add_argument('--debug', action='store_true', 
                       help='Enable debug mode with detailed console output')
    args = parser.parse_args()

    try:
        leader = LeaderPi()
        
        # Override debug mode if specified via command line
        if args.debug:
            leader.config.config['KITCHENSYNC']['debug'] = 'true'
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
