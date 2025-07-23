#!/usr/bin/env python3
"""
Refactored KitchenSync Leader Pi
Clean, modular version with proper separation of concerns
"""

import argparse
import json
import sys
import time
import threading
from pathlib import Path

# Import our modular components
from src.config import ConfigManager
from src.video import VideoFileManager, VLCVideoPlayer
from src.networking import LeaderNetworking
from src.midi import ScheduleManager
from src.debug import DebugManager
from src.ui import UserInterface


class KitchenSyncLeader:
    """
    Refactored Leader Pi that orchestrates synchronized playback.
    Now uses modular components for better maintainability.
    """
    
    def __init__(self):
        # Initialize configuration
        self.config = ConfigManager('leader_config.ini')
        
        # Initialize components
        self.video_manager = VideoFileManager(
            configured_file=self.config.video_file,
            usb_mount_point=self.config.usb_mount_point
        )
        self.video_player = VLCVideoPlayer(debug_mode=self.config.debug_mode)
        self.networking = LeaderNetworking()
        self.schedule_manager = ScheduleManager()
        self.debug_manager = DebugManager(
            "leader-pi", 
            enabled=self.config.debug_mode
        ) if self.config.debug_mode else None
        
        # System state
        self.start_time = None
        self.is_running = False
        self.video_path = None
        
        # Load schedule
        self._load_schedule()
        
        # Setup video
        self._setup_video()
        
        # Setup networking
        self.networking.setup_sockets()
        
        print(f"✓ Leader Pi initialized - Debug: {'ON' if self.config.debug_mode else 'OFF'}")
    
    def _load_schedule(self) -> None:
        """Load MIDI schedule from file"""
        schedule_file = Path('schedule.json')
        try:
            if schedule_file.exists():
                with open(schedule_file, 'r') as f:
                    schedule_data = json.load(f)
                self.schedule_manager.load_schedule(schedule_data)
            else:
                print("schedule.json not found, using empty schedule")
        except Exception as e:
            print(f"Error loading schedule: {e}")
    
    def _setup_video(self) -> None:
        """Setup video player"""
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            self.video_player.load_video(self.video_path)
        else:
            print("⚠️ No video file found")
    
    def start_system(self) -> None:
        """Start the synchronized playback system"""
        if self.is_running:
            print("System is already running")
            return
        
        self.start_time = time.time()
        self.is_running = True
        
        # Start video playback
        if self.video_path:
            print("🎬 Starting video playback...")
            self.video_player.start_playback()
        
        # Start networking
        self.networking.start_networking()
        
        # Start sync broadcasting
        threading.Thread(target=self._sync_broadcast_loop, daemon=True).start()
        
        # Start debug updates if enabled
        if self.debug_manager:
            self.debug_manager.start()
            threading.Thread(target=self._debug_update_loop, daemon=True).start()
        
        # Send start command to collaborators
        self.networking.send_command({
            'type': 'start',
            'schedule': self.schedule_manager.schedule,
            'start_time': self.start_time,
            'debug_mode': self.config.debug_mode
        })
        
        print("✅ System started! Broadcasting time sync...")
    
    def stop_system(self) -> None:
        """Stop the synchronized playback system"""
        if not self.is_running:
            print("System is not running")
            return
        
        print("🛑 Stopping system...")
        self.is_running = False
        
        # Stop video playback
        self.video_player.stop_playback()
        
        # Stop networking
        self.networking.stop_networking()
        
        # Stop debug manager
        if self.debug_manager:
            self.debug_manager.stop()
        
        # Send stop command to collaborators
        self.networking.send_command({'type': 'stop'})
        
        # Reset state
        self.start_time = None
        
        print("✅ System stopped")
    
    def _sync_broadcast_loop(self) -> None:
        """Continuously broadcast time sync"""
        while self.is_running:
            if self.start_time:
                current_time = time.time() - self.start_time
                self.networking.broadcast_sync(current_time)
            time.sleep(0.1)  # 10Hz sync rate
    
    def _debug_update_loop(self) -> None:
        """Update debug information"""
        while self.is_running and self.debug_manager:
            if self.start_time:
                current_time = time.time() - self.start_time
                
                # Get MIDI event info
                current_events = self.schedule_manager.get_current_events(current_time)
                upcoming_events = self.schedule_manager.get_upcoming_events(current_time)
                
                # Update debug display
                debug_info = [
                    f"Connected Pis: {len(self.networking.get_connected_collaborators())}"
                ]
                
                if current_events:
                    for event in current_events[:2]:
                        debug_info.append(f"▶️ {event.get('type')} @{event.get('time')}s")
                
                if upcoming_events:
                    next_event = upcoming_events[0]
                    debug_info.append(f"⏭️ NEXT: {next_event.get('type')} @{next_event.get('time')}s")
                
                self.debug_manager.update_display(
                    current_time=current_time,
                    total_time=180.0,  # Estimate
                    additional_info=debug_info
                )
            
            time.sleep(1)  # Update every second
    
    def get_status(self) -> dict:
        """Get system status"""
        status = {
            'running': self.is_running,
            'video_loaded': self.video_path is not None,
            'collaborators': self.networking.get_connected_collaborators(),
            'schedule_cues': len(self.schedule_manager.schedule)
        }
        
        if self.start_time:
            status['elapsed_time'] = time.time() - self.start_time
        
        return status
    
    def cleanup(self) -> None:
        """Clean up resources"""
        if self.is_running:
            self.stop_system()
        
        self.video_player.cleanup()
        self.networking.cleanup()
        if self.debug_manager:
            self.debug_manager.cleanup()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='KitchenSync Leader Pi (Refactored)')
    parser.add_argument('--auto', action='store_true', help='Start automatically without interface')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()
    
    try:
        leader = KitchenSyncLeader()
        
        # Override debug mode if specified
        if args.debug:
            leader.config.config.set('KITCHENSYNC', 'debug', 'true')
            print("✓ Debug mode: ENABLED (via command line)")
        
        if args.auto:
            print("🎯 Leader Pi starting in automatic mode...")
            leader.start_system()
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Stopping system...")
                leader.stop_system()
        else:
            # Interactive mode
            ui = UserInterface(leader, leader.schedule_manager)
            ui.run()
            
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        if 'leader' in locals():
            leader.cleanup()


if __name__ == "__main__":
    main()
