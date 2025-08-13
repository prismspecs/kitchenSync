#!/usr/bin/env python3
"""
KitchenSync Video Position Control Tool

This tool allows you to manually control the leader's video position
for testing sync functionality with collaborators.

Usage:
  python3 test_video_control.py

Commands while running:
  j <seconds>  - Jump to specific time (e.g., "j 30" for 30 seconds)
  +<seconds>   - Jump forward (e.g., "+10" for 10 seconds forward)
  -<seconds>   - Jump backward (e.g., "-5" for 5 seconds back)
  p            - Show current position
  d            - Show video duration
  pause        - Pause video
  resume       - Resume video
  restart      - Jump to beginning (0 seconds)
  help         - Show commands
  quit         - Exit
"""

import json
import socket
import sys
import threading
import time
from pathlib import Path

# Add src to path to import KitchenSync modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from video import VLCVideoPlayer
    from config import ConfigManager
except ImportError as e:
    print(f"❌ Error importing KitchenSync modules: {e}")
    print("Make sure you're running this from the KitchenSync directory")
    sys.exit(1)


class VideoController:
    """Controls video playback position for testing"""
    
    def __init__(self):
        self.config = ConfigManager("leader_config.ini")
        self.video_player = None
        self.running = False
        self.sync_broadcaster = None
        
    def find_running_leader(self):
        """Try to connect to a running leader's video player"""
        print("🔍 Looking for running leader video player...")
        
        # Try to find VLC process
        import subprocess
        try:
            result = subprocess.run(['pgrep', '-f', 'vlc'], capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Found VLC process - leader appears to be running")
                return True
            else:
                print("❌ No VLC process found")
                return False
        except Exception as e:
            print(f"❌ Error checking for VLC: {e}")
            return False
            
    def start_standalone_video(self):
        """Start video player in standalone mode for testing"""
        print("🎬 Starting standalone video player for testing...")
        
        # Find video file
        from video import VideoFileManager
        video_manager = VideoFileManager(
            self.config.video_file, self.config.usb_mount_point
        )
        
        video_path = video_manager.find_video_file()
        if not video_path:
            print("❌ No video file found!")
            print("Make sure you have a video file configured or on a USB drive")
            return False
            
        # Create and start video player
        self.video_player = VLCVideoPlayer(debug_mode=True)  # Force debug mode for control
        
        if not self.video_player.load_video(video_path):
            print(f"❌ Failed to load video: {video_path}")
            return False
            
        print(f"📹 Loaded video: {video_path}")
        
        if not self.video_player.start_playback():
            print("❌ Failed to start video playback")
            return False
            
        print("✅ Video playback started")
        
        # Wait a moment for VLC to initialize
        time.sleep(2)
        
        return True
        
    def show_status(self):
        """Show current video status"""
        if not self.video_player:
            print("❌ No video player available")
            return
            
        position = self.video_player.get_position()
        duration = self.video_player.get_duration()
        
        if position is not None and duration is not None:
            pos_min, pos_sec = divmod(int(position), 60)
            dur_min, dur_sec = divmod(int(duration), 60)
            print(f"📊 Position: {pos_min:02d}:{pos_sec:02d} / {dur_min:02d}:{dur_sec:02d} ({position:.1f}s / {duration:.1f}s)")
        else:
            print("❌ Could not get video position/duration")
            
    def jump_to(self, seconds):
        """Jump to specific time"""
        if not self.video_player:
            print("❌ No video player available")
            return
            
        duration = self.video_player.get_duration()
        if duration and seconds > duration:
            print(f"⚠️  Time {seconds}s exceeds video duration {duration:.1f}s")
            seconds = duration - 1
            
        if self.video_player.set_position(seconds):
            print(f"⏭️  Jumped to {seconds:.1f}s")
            time.sleep(0.5)  # Give VLC time to seek
            self.show_status()
        else:
            print("❌ Failed to jump to position")
            
    def jump_relative(self, delta_seconds):
        """Jump forward or backward by delta seconds"""
        if not self.video_player:
            print("❌ No video player available")
            return
            
        current_pos = self.video_player.get_position()
        if current_pos is None:
            print("❌ Could not get current position")
            return
            
        new_pos = current_pos + delta_seconds
        duration = self.video_player.get_duration()
        
        if new_pos < 0:
            new_pos = 0
        elif duration and new_pos > duration:
            new_pos = duration - 1
            
        self.jump_to(new_pos)
        
    def pause_video(self):
        """Pause video playback"""
        if not self.video_player:
            print("❌ No video player available")
            return
            
        if self.video_player.pause():
            print("⏸️  Video paused")
        else:
            print("❌ Failed to pause video")
            
    def resume_video(self):
        """Resume video playback"""
        if not self.video_player:
            print("❌ No video player available")
            return
            
        if self.video_player.resume():
            print("▶️  Video resumed")
        else:
            print("❌ Failed to resume video")
            
    def show_help(self):
        """Show available commands"""
        print("\n📋 Available Commands:")
        print("  j <seconds>  - Jump to specific time (e.g., 'j 30')")
        print("  +<seconds>   - Jump forward (e.g., '+10')")
        print("  -<seconds>   - Jump backward (e.g., '-5')")
        print("  p            - Show current position")
        print("  d            - Show video duration")
        print("  pause        - Pause video")
        print("  resume       - Resume video")
        print("  restart      - Jump to beginning")
        print("  help         - Show this help")
        print("  quit         - Exit\n")
        
    def run_interactive(self):
        """Run interactive control loop"""
        print("\n🎮 KitchenSync Video Position Controller")
        print("=" * 50)
        
        # Try to find running leader first
        if not self.find_running_leader():
            print("\n⚠️  No running leader found. Starting standalone video for testing...")
            if not self.start_standalone_video():
                print("❌ Failed to start video player")
                return
        else:
            print("⚠️  Leader is running, but direct control may not work.")
            print("This tool works best with standalone video testing.")
            print("Consider stopping the leader first for full control.")
            
        self.show_help()
        self.show_status()
        
        print("\n🎯 Ready for commands! Type 'help' for command list.")
        
        try:
            while True:
                try:
                    command = input("\n> ").strip().lower()
                    
                    if not command:
                        continue
                        
                    if command == "quit" or command == "q":
                        break
                    elif command == "help" or command == "h":
                        self.show_help()
                    elif command == "p":
                        self.show_status()
                    elif command == "d":
                        duration = self.video_player.get_duration() if self.video_player else None
                        if duration:
                            dur_min, dur_sec = divmod(int(duration), 60)
                            print(f"📏 Duration: {dur_min:02d}:{dur_sec:02d} ({duration:.1f}s)")
                        else:
                            print("❌ Could not get video duration")
                    elif command == "pause":
                        self.pause_video()
                    elif command == "resume":
                        self.resume_video()
                    elif command == "restart":
                        self.jump_to(0)
                    elif command.startswith("j "):
                        try:
                            seconds = float(command[2:])
                            self.jump_to(seconds)
                        except ValueError:
                            print("❌ Invalid time format. Use: j <seconds>")
                    elif command.startswith("+"):
                        try:
                            delta = float(command[1:])
                            self.jump_relative(delta)
                        except ValueError:
                            print("❌ Invalid format. Use: +<seconds>")
                    elif command.startswith("-"):
                        try:
                            delta = -float(command[1:])
                            self.jump_relative(delta)
                        except ValueError:
                            print("❌ Invalid format. Use: -<seconds>")
                    else:
                        print(f"❌ Unknown command: {command}")
                        print("Type 'help' for available commands")
                        
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"❌ Error: {e}")
                    
        except KeyboardInterrupt:
            pass
            
        print("\n🛑 Stopping video controller...")
        if self.video_player:
            self.video_player.stop_playback()
            self.video_player.cleanup()


def main():
    """Main entry point"""
    print(__doc__)
    
    try:
        controller = VideoController()
        controller.run_interactive()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
