#!/usr/bin/env python3
"""
Refactored KitchenSync Collaborator Pi
Clean, modular version with proper separation of concerns
"""

import argparse
import sys
import time
import threading
from collections import deque

# Import our modular components
from src.config import ConfigManager
from src.video import VideoFileManager, VLCVideoPlayer
from src.networking import CollaboratorNetworking
from src.midi import MIDIManager, ScheduleManager
from src.debug import DebugManager


class VideoSyncManager:
    """Manages video synchronization with leader"""
    
    def __init__(self, video_player: VLCVideoPlayer, config: ConfigManager):
        self.video_player = video_player
        self.sync_tolerance = config.getfloat('sync_tolerance', 1.0)
        self.sync_check_interval = config.getfloat('sync_check_interval', 5.0)
        self.deviation_threshold = config.getfloat('deviation_threshold', 0.5)
        self.max_deviation_samples = config.getint('max_deviation_samples', 10)
        
        # Sync state
        self.synced_start = None
        self.last_sync_received = 0
        self.video_start_time = None
        self.last_sync_check = 0
        self.deviation_samples = deque(maxlen=self.max_deviation_samples)
        self.last_correction_time = 0
    
    def handle_sync_message(self, msg: dict) -> None:
        """Handle time sync message from leader"""
        leader_time = msg.get('time', 0)
        self.last_sync_received = time.time()
        
        if self.synced_start is None:
            self.synced_start = time.time() - leader_time
            print(f"✓ Initial sync established at {leader_time:.2f}s")
    
    def check_video_sync(self, leader_time: float) -> None:
        """Check and correct video sync if needed"""
        if not self.video_start_time or not self.video_player.is_playing:
            return
        
        now = time.time()
        if now - self.last_sync_check < self.sync_check_interval:
            return
        
        self.last_sync_check = now
        
        video_position = self.video_player.get_position()
        if video_position is None:
            return
        
        expected_position = leader_time
        deviation = video_position - expected_position
        
        # Use median filtering for stable sync correction
        self.deviation_samples.append(deviation)
        if len(self.deviation_samples) >= 3:
            median_deviation = sorted(self.deviation_samples)[len(self.deviation_samples) // 2]
            
            if abs(median_deviation) > self.deviation_threshold:
                if now - self.last_correction_time > 3.0:  # Don't correct too frequently
                    print(f"🔧 Sync correction: {median_deviation:.2f}s")
                    self.video_player.set_position(expected_position)
                    self.last_correction_time = now
                    self.deviation_samples.clear()


class KitchenSyncCollaborator:
    """
    Refactored Collaborator Pi for synchronized playback.
    Now uses modular components for better maintainability.
    """
    
    def __init__(self, config_file: str = 'collaborator_config.ini'):
        # Initialize configuration
        self.config = ConfigManager(config_file)
        
        # Initialize components
        self.video_manager = VideoFileManager(
            configured_file=self.config.video_file,
            usb_mount_point=self.config.usb_mount_point
        )
        self.video_player = VLCVideoPlayer(debug_mode=self.config.debug_mode)
        self.networking = CollaboratorNetworking(self.config.pi_id)
        self.midi_manager = MIDIManager(self.config.getint('midi_port', 0))
        self.schedule_manager = ScheduleManager()
        self.sync_manager = VideoSyncManager(self.video_player, self.config)
        
        # Debug manager
        self.debug_manager = DebugManager(
            self.config.pi_id,
            enabled=self.config.debug_mode
        ) if self.config.debug_mode else None
        
        # System state
        self.is_running = False
        self.video_path = None
        
        # Setup video
        self._setup_video()
        
        # Setup networking
        self.networking.setup_sockets()
        self.networking.set_handlers(
            self.sync_manager.handle_sync_message,
            self._handle_command
        )
        
        print(f"✓ Collaborator '{self.config.pi_id}' initialized")
        print(f"✓ Video: {self.video_path or 'Not found'}")
        print(f"✓ Debug: {'ON' if self.config.debug_mode else 'OFF'}")
    
    def _setup_video(self) -> None:
        """Setup video player"""
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            self.video_player.load_video(self.video_path)
    
    def _handle_command(self, msg: dict) -> None:
        """Handle commands from leader"""
        command_type = msg.get('type')
        
        if command_type == 'start':
            self._handle_start_command(msg)
        elif command_type == 'stop':
            self._handle_stop_command()
        elif command_type == 'update_schedule':
            schedule_data = msg.get('schedule', [])
            self.schedule_manager.load_schedule(schedule_data)
    
    def _handle_start_command(self, msg: dict) -> None:
        """Handle start command from leader"""
        if self.is_running:
            print("Already running, stopping first...")
            self.stop_playback()
        
        # Load schedule
        schedule_data = msg.get('schedule', [])
        self.schedule_manager.load_schedule(schedule_data)
        self.midi_manager.reset_triggered_cues()
        
        # Override debug mode if leader specifies it
        leader_debug_mode = msg.get('debug_mode', False)
        if leader_debug_mode and not self.config.debug_mode:
            self.config.config.set('KITCHENSYNC', 'debug', 'true')
            print("🐛 Debug mode enabled by leader")
        
        self.is_running = True
        
        # Wait for sync
        print("⏳ Waiting for time sync...")
        while self.sync_manager.synced_start is None:
            time.sleep(0.1)
        
        # Start video playback
        if self.video_path:
            print("🎬 Starting video playback...")
            self.video_player.start_playback()
            self.sync_manager.video_start_time = time.time()
        
        # Start MIDI control loop
        threading.Thread(target=self._midi_control_loop, daemon=True).start()
        
        # Start debug updates if enabled
        if self.debug_manager:
            self.debug_manager.start()
            threading.Thread(target=self._debug_update_loop, daemon=True).start()
        
        print("✅ Collaborator started successfully")
    
    def _handle_stop_command(self) -> None:
        """Handle stop command from leader"""
        self.stop_playback()
        print("🛑 Stopped by leader command")
    
    def stop_playback(self) -> None:
        """Stop playback and reset state"""
        self.is_running = False
        
        # Stop video
        self.video_player.stop_playback()
        
        # Stop debug manager
        if self.debug_manager:
            self.debug_manager.stop()
        
        # Reset sync state
        self.sync_manager.synced_start = None
        self.sync_manager.video_start_time = None
        
        print("✅ Playback stopped")
    
    def _midi_control_loop(self) -> None:
        """Main loop for MIDI output"""
        while self.is_running:
            if self.sync_manager.synced_start is None:
                time.sleep(0.1)
                continue
            
            current_time = time.time() - self.sync_manager.synced_start
            
            # Check for lost sync
            if time.time() - self.sync_manager.last_sync_received > 5:
                print("❌ Lost sync with leader")
                self.stop_playback()
                break
            
            # Check video sync
            self.sync_manager.check_video_sync(current_time)
            
            # Process MIDI schedule
            self.midi_manager.process_schedule(self.schedule_manager.schedule, current_time)
            
            time.sleep(0.01)  # 10ms precision
    
    def _debug_update_loop(self) -> None:
        """Update debug display"""
        while self.is_running and self.debug_manager:
            if self.sync_manager.synced_start:
                current_time = time.time() - self.sync_manager.synced_start
                video_position = self.video_player.get_position()
                
                debug_info = [
                    f"Sync time: {current_time:.1f}s",
                    f"Video pos: {video_position:.1f}s" if video_position else "Video pos: N/A",
                    f"MIDI cues: {len(self.midi_manager.triggered_cues)}/{len(self.schedule_manager.schedule)}"
                ]
                
                self.debug_manager.update_display(
                    current_time=current_time,
                    total_time=180.0,  # Estimate
                    additional_info=debug_info
                )
            
            time.sleep(1)  # Update every second
    
    def run(self) -> None:
        """Main run loop"""
        print(f"🎵 Starting KitchenSync Collaborator '{self.config.pi_id}'")
        
        # Start networking
        self.networking.start_networking()
        
        # Register with leader
        self.networking.register_with_leader(self.video_path)
        
        print("✅ Collaborator ready. Waiting for commands...")
        print("Press Ctrl+C to exit")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
            self.stop_playback()
        finally:
            self.cleanup()
    
    def cleanup(self) -> None:
        """Clean up resources"""
        self.networking.stop_networking()
        self.video_player.cleanup()
        self.midi_manager.cleanup()
        if self.debug_manager:
            self.debug_manager.cleanup()
        self.networking.cleanup()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='KitchenSync Collaborator Pi (Refactored)')
    parser.add_argument('config_file', nargs='?', default='collaborator_config.ini',
                       help='Configuration file path')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()
    
    try:
        collaborator = KitchenSyncCollaborator(args.config_file)
        
        # Override debug mode if specified
        if args.debug:
            collaborator.config.config.set('KITCHENSYNC', 'debug', 'true')
            print("✓ Debug mode: ENABLED (via command line)")
        
        collaborator.run()
        
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
