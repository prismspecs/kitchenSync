#!/usr/bin/env python3
"""
Refactored KitchenSync Collaborator Pi
Clean, modular implementation using the new architecture
"""

import argparse
import sys
import threading
import time
from collections import deque
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config import ConfigManager
from video import VideoFileManager, VLCVideoPlayer
from networking import SyncReceiver, CommandListener
from midi import MidiScheduler, MidiManager
from core import SystemState, SyncTracker
from debug import DebugManager
from src.debug.simple_overlay import SimpleDebugManager


class CollaboratorPi:
    """Refactored Collaborator Pi with clean separation of concerns"""
    
    def __init__(self, config_file: str = 'collaborator_config.ini'):
        # Initialize configuration
        self.config = ConfigManager(config_file)
        
        # Initialize core components
        self.system_state = SystemState()
        self.sync_tracker = SyncTracker()
        
        # Initialize video components
        self.video_manager = VideoFileManager(
            self.config.video_file,
            self.config.usb_mount_point
        )
        self.video_player = VLCVideoPlayer(self.config.debug_mode)
        
        # Initialize MIDI
        midi_port = self.config.getint('midi_port', 0)
        self.midi_manager = MidiManager(midi_port)
        self.midi_scheduler = MidiScheduler(self.midi_manager)
        
        # Initialize networking
        self.sync_receiver = SyncReceiver(sync_callback=self._handle_sync)
        self.command_listener = CommandListener()
        
        # Find and load video file before creating debug overlay
        self.video_path = self.video_manager.find_video_file()
        if self.video_path:
            self.video_player.load_video(self.video_path)
            print(f"[DEBUG] Video file loaded: {self.video_path}")
        else:
            print("[DEBUG] No video file found at startup.")
        
        # Simple debug overlay (displays on Pi screen)
        self.simple_debug = None
        if self.config.debug_mode:
            self.simple_debug = SimpleDebugManager(self.config.device_id, is_leader=False)
            if self.simple_debug.overlay:
                print(f"[DEBUG] Simple overlay created for {self.config.device_id}")
            else:
                print(f"[DEBUG] Failed to create overlay for {self.config.device_id}")
        
        self.debug_manager = None  # Disabled - using simple overlay
        
        # Sync settings
        self.sync_tolerance = self.config.getfloat('sync_tolerance', 1.0)
        self.sync_check_interval = self.config.getfloat('sync_check_interval', 5.0)
        self.deviation_threshold = self.config.getfloat('deviation_threshold', 0.5)
        
        # Video sync state
        self.deviation_samples = deque(maxlen=10)
        self.last_correction_time = 0
        self.video_start_time = None
        
        # Setup command handlers
        self._setup_command_handlers()
        
        print(f"KitchenSync Collaborator '{self.config.pi_id}' initialized")
    
    def _setup_command_handlers(self) -> None:
        """Setup command handlers"""
        self.command_listener.register_handler('start', self._handle_start_command)
        self.command_listener.register_handler('stop', self._handle_stop_command)
        self.command_listener.register_handler('update_schedule', self._handle_schedule_update)
    
    def _handle_sync(self, leader_time: float) -> None:
        """Handle time sync from leader"""
        local_time = time.time()
        self.sync_tracker.record_sync(leader_time, local_time)
        
        # Update system time if running
        if self.system_state.is_running:
            self.system_state.current_time = leader_time
            
            # Process MIDI cues
            self.midi_scheduler.process_cues(leader_time)
            
            # Check video sync
            self._check_video_sync(leader_time)
            
            # Update debug overlay state (if present)
            if self.debug_manager and getattr(self.debug_manager, 'overlay', None):
                video_position = self.video_player.get_position() or 0.0
                video_duration = self.video_player.get_duration() or 0.0
                recent_cues = self.midi_scheduler.get_recent_cues(leader_time, lookback=10.0)
                upcoming_cues = self.midi_scheduler.get_upcoming_cues(leader_time, lookahead=30.0)
                current_cues = self.midi_scheduler.get_current_cues(leader_time, window=1.0)
                midi_data = {
                    'recent': recent_cues[-3:] if recent_cues else [],
                    'current': current_cues[0] if current_cues else None,
                    'upcoming': upcoming_cues[:3] if upcoming_cues else []
                }
                self.debug_manager.overlay.set_state(
                    video_file=self.video_player.video_path or self.video_path or self.config.video_file,
                    current_time=video_position,
                    total_time=video_duration,
                    midi_data=midi_data,
                    is_leader=self.config.is_leader,
                    pi_id=self.config.pi_id
                )
    
    def _handle_start_command(self, msg: dict, addr: tuple) -> None:
        """Handle start command from leader"""
        if self.system_state.is_running:
            print("Already running, stopping current session first")
            self.stop_playback()
        
        # Load schedule
        schedule = msg.get('schedule', [])
        self.midi_scheduler.load_schedule(schedule)
        
        # Override debug mode if leader specifies it
        leader_debug_mode = msg.get('debug_mode', False)
        if leader_debug_mode and not self.config.debug_mode:
            self.debug_manager.debug_mode = True
            print("Debug mode enabled by leader")
        
        print(f"Received start command with {len(schedule)} cues")
        
        # Wait for sync to be established
        print("⏳ Waiting for time sync...")
        timeout = 10.0
        start_wait = time.time()
        
        while not self.sync_tracker.is_synced() and (time.time() - start_wait) < timeout:
            time.sleep(0.1)
        
        if not self.sync_tracker.is_synced():
            print("Starting without sync (timeout)")
        else:
            print("Sync established")
        
        # Start playback
        self.start_playback()
    
    def _handle_stop_command(self, msg: dict, addr: tuple) -> None:
        """Handle stop command from leader"""
        self.stop_playback()
        print("Stopped by leader command")
    
    def _handle_schedule_update(self, msg: dict, addr: tuple) -> None:
        """Handle schedule update from leader"""
        schedule = msg.get('schedule', [])
        self.midi_scheduler.load_schedule(schedule)
        print(f"Updated schedule: {len(schedule)} cues")
    
    def start_playback(self) -> None:
        """Start video and MIDI playback"""
        print("Starting playback...")
        
        # Start system state
        self.system_state.start_session()
        self.video_start_time = time.time()
        
        # Start video playback
        if self.video_player.video_path:
            print("Starting video...")
            self.video_player.start_playback()
        
        # Create DebugManager ONLY if debug mode is enabled and not already created
        if self.config.debug_mode and self.debug_manager is None:
            print("[DEBUG] Creating debug overlay for collaborator...")
            self.debug_manager = DebugManager(
                self.config.pi_id,
                self.video_player.video_path or self.video_path or self.config.video_file,
                True
            )
            print(f"[DEBUG] Debug overlay created for video: {self.video_player.video_path or self.video_path or self.config.video_file}")
            
            # Set initial state immediately
            if self.debug_manager and getattr(self.debug_manager, 'overlay', None):
                video_duration = self.video_player.get_duration() or 180.0
                self.debug_manager.overlay.set_state(
                    video_file=self.video_player.video_path or self.video_path or self.config.video_file,
                    current_time=0.0,
                    total_time=video_duration,
                    midi_data={'recent': [], 'current': None, 'upcoming': []},
                    is_leader=self.config.is_leader,
                    pi_id=self.config.pi_id
                )
                print("[DEBUG] Initial debug overlay state set.")
        
        # Start MIDI playback
        self.midi_scheduler.start_playback(self.system_state.start_time)
        
        print("Playback started")
    
    def stop_playback(self) -> None:
        """Stop video and MIDI playback"""
        print("Stopping playback...")
        
        # Stop video
        self.video_player.stop_playback()
        
        # Stop MIDI
        self.midi_scheduler.stop_playback()
        
        # Stop system state
        self.system_state.stop_session()
        
        # Reset video state
        self.video_start_time = None
        self.deviation_samples.clear()
        
        print("Playback stopped")
    
    def _check_video_sync(self, leader_time: float) -> None:
        """Check and correct video sync using median filtering"""
        if not self.video_player.is_playing or not self.video_start_time:
            return
        
        # Get current video position
        video_position = self.video_player.get_position()
        if video_position is None:
            return
        
        # Calculate expected position
        time_since_start = leader_time
        deviation = video_position - time_since_start
        
        # Add to samples for median filtering
        self.deviation_samples.append(deviation)
        
        # Only proceed if we have enough samples
        if len(self.deviation_samples) < 5:
            return
        
        # Calculate median deviation
        sorted_deviations = sorted(self.deviation_samples)
        median_deviation = sorted_deviations[len(sorted_deviations) // 2]
        
        # Check if correction is needed
        if abs(median_deviation) > self.deviation_threshold:
            current_time = time.time()
            
            # Avoid corrections too close together
            if current_time - self.last_correction_time < self.sync_check_interval:
                return
            
            print(f"🔄 Sync correction: {median_deviation:.3f}s deviation")
            
            # Apply correction
            target_position = time_since_start
            if self.video_player.set_position(target_position):
                self.last_correction_time = current_time
                self.deviation_samples.clear()
    
    def run(self) -> None:
        """Main run loop"""
        print(f"Starting KitchenSync Collaborator '{self.config.pi_id}'")
        
        # Start networking
        self.sync_receiver.start_listening()
        self.command_listener.start_listening()
        
        # Register with leader
        self.command_listener.send_registration(
            self.config.pi_id,
            self.config.video_file
        )
        
        # Start heartbeat
        def heartbeat_loop():
            while True:
                status = 'running' if self.system_state.is_running else 'ready'
                self.command_listener.send_heartbeat(self.config.pi_id, status)
                time.sleep(2)
        
        heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        heartbeat_thread.start()
        
        # Start simple debug updates if enabled
        if self.config.debug_mode:
            self._start_simple_debug()
        
        print(f"✅ Collaborator {self.config.device_id} started successfully!")
        
        print("Collaborator ready. Waiting for commands from leader...")
        print("Press Ctrl+C to exit")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.stop_playback()
        finally:
            self.cleanup()
    
    def _start_simple_debug(self) -> None:
        """Start simple visual debug updates for collaborator"""
        def simple_debug_loop():
            last_time = 0
            while self.system_state.is_running:
                try:
                    # Get actual video position and timing
                    session_time = self.system_state.current_time
                    video_position = self.video_player.get_position()
                    video_duration = self.video_player.get_duration() or 180.0
                    
                    # Use video position if available, otherwise session time
                    if video_position is not None and 0 <= video_position <= video_duration:
                        current_time = video_position
                    else:
                        current_time = session_time % video_duration if video_duration > 0 else session_time
                    
                    # Update debug overlay every second
                    if abs(current_time - last_time) >= 1.0:
                        last_time = current_time
                        
                        # Get MIDI info
                        current_cues = self.midi_scheduler.get_current_cues(current_time) if hasattr(self.midi_scheduler, 'get_current_cues') else []
                        upcoming_cues = self.midi_scheduler.get_upcoming_cues(current_time) if hasattr(self.midi_scheduler, 'get_upcoming_cues') else []
                        
                        # Update visual overlay
                        if self.simple_debug and self.simple_debug.overlay:
                            video_file = self.video_player.video_path or 'Unknown'
                            self.simple_debug.update_debug_info(
                                video_file=video_file,
                                current_time=current_time,
                                total_time=video_duration,
                                session_time=session_time,
                                video_position=video_position,
                                current_cues=current_cues,
                                upcoming_cues=upcoming_cues
                            )
                    
                    time.sleep(0.5)  # Check twice per second for smoother updates
                    
                except Exception as e:
                    print(f"[DEBUG] Collaborator debug error: {e}")
                    time.sleep(5)
        
        print(f"[DEBUG] Starting simple debug loop for {self.config.device_id}")
        thread = threading.Thread(target=simple_debug_loop, daemon=True)
        thread.start()
    
    def _start_debug_updates(self) -> None:
        """No longer needed - using simple debug"""
        pass
    
    def cleanup(self) -> None:
        """Clean up resources"""
        if self.system_state.is_running:
            self.stop_playback()
        
        self.video_player.cleanup()
        self.midi_manager.cleanup()
        if self.simple_debug:
            self.simple_debug.cleanup()
        print("🧹 Cleanup completed")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='KitchenSync Collaborator Pi')
    parser.add_argument('config_file', nargs='?', default='collaborator_config.ini',
                       help='Configuration file to use')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode')
    args = parser.parse_args()
    
    try:
        collaborator = CollaboratorPi(args.config_file)
        
        # Override debug mode if specified
        if args.debug:
            collaborator.config.config['KITCHENSYNC']['debug'] = 'true'
            collaborator.debug_manager.debug_mode = True
            print("✓ Debug mode: ENABLED (via command line)")
        
        collaborator.run()
        
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
