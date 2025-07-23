#!/usr/bin/env python3
"""
Simple Video Test Script
Tests VLC video playback without network components
"""

import os
import sys
import time
import subprocess
import glob

# Add the current directory to Python path to import VLC player
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import vlc
    VLC_PYTHON_AVAILABLE = True
    print("✅ VLC Python bindings available")
except ImportError:
    VLC_PYTHON_AVAILABLE = False
    print("❌ VLC Python bindings not available, using command line")

class SimpleVideoPlayer:
    def __init__(self):
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        
    def find_video_file(self):
        """Find a video file to test with"""
        # Check USB drives first
        mount_result = subprocess.run(['mount'], capture_output=True, text=True)
        if mount_result.returncode == 0:
            for line in mount_result.stdout.split('\n'):
                if '/media/' in line:
                    parts = line.split(' on ')
                    if len(parts) >= 2:
                        mount_point = parts[1].split(' type ')[0]
                        if os.path.exists(mount_point) and os.path.isdir(mount_point):
                            # Look for video files
                            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv']
                            for ext in video_extensions:
                                videos = glob.glob(os.path.join(mount_point, f'*{ext}'))
                                if videos:
                                    return videos[0]
        
        # Check local videos directory
        if os.path.exists('./videos'):
            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv']
            for ext in video_extensions:
                videos = glob.glob(f'./videos/*{ext}')
                if videos:
                    return videos[0]
        
        return None
    
    def play_video(self, video_path):
        """Play video using VLC"""
        print(f"🎬 Playing: {video_path}")
        
        # Always use command line VLC for better reliability
        return self._play_with_command_vlc(video_path)
    
    def _play_with_python_vlc(self, video_path):
        """Play with VLC Python bindings"""
        try:
            # Create VLC instance for fullscreen playbook
            vlc_args = [
                '--fullscreen',
                '--no-video-title-show',
                '--no-osd',
                '--quiet',
                '--mouse-hide-timeout=0',
            ]
            
            self.vlc_instance = vlc.Instance(' '.join(vlc_args))
            if not self.vlc_instance:
                print("❌ Failed to create VLC instance")
                return False
                
            self.vlc_player = self.vlc_instance.media_player_new()
            if not self.vlc_player:
                print("❌ Failed to create VLC player")
                return False
            
            # Set fullscreen
            self.vlc_player.set_fullscreen(True)
            
            # Load and play media
            self.vlc_media = self.vlc_instance.media_new(video_path)
            if not self.vlc_media:
                print("❌ Failed to create VLC media")
                return False
                
            self.vlc_player.set_media(self.vlc_media)
            
            result = self.vlc_player.play()
            print(f"✅ VLC play result: {result}")
            print("🎬 Video should now be playing in fullscreen")
            
            # Wait for VLC to start
            time.sleep(2)
            
            # Check player state and retry if needed
            state = self.vlc_player.get_state()
            print(f"📊 VLC player state: {state}")
            
            if state != vlc.State.Playing:
                print("🔄 Video not playing, triggering play again...")
                self.vlc_player.play()
                time.sleep(1)
                state = self.vlc_player.get_state()
                print(f"📊 VLC player state after retry: {state}")
            
            # Set position to start and play again to ensure it's not stuck
            self.vlc_player.set_position(0.0)
            self.vlc_player.play()
            
            return True
            
        except Exception as e:
            print(f"❌ Error with VLC Python: {e}")
            return False
    
    def _play_with_command_vlc(self, video_path):
        """Play with VLC command line"""
        try:
            cmd = [
                'vlc',
                '--intf', 'dummy',  # No interface
                '--fullscreen',
                '--no-video-title-show',
                '--no-osd',
                '--quiet',
                '--mouse-hide-timeout=0',
                '--play-and-exit',  # Exit when done
                '--no-loop',
                '--start-time=0',   # Start from beginning
                video_path
            ]
            
            print(f"🔧 Running: {' '.join(cmd)}")
            process = subprocess.Popen(cmd)
            print(f"✅ VLC command started with PID: {process.pid}")
            
            # Give VLC a moment to start
            time.sleep(3)
            
            # Check if process is still running
            if process.poll() is None:
                print("✅ VLC process is running")
            else:
                print(f"❌ VLC process exited with code: {process.returncode}")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ Error with VLC command: {e}")
            return False
    
    def stop(self):
        """Stop video playback"""
        if self.vlc_player:
            self.vlc_player.stop()
        # Also kill any VLC processes
        subprocess.run(['pkill', 'vlc'], capture_output=True)

def main():
    print("🎬 Simple Video Test")
    print("=" * 30)
    
    player = SimpleVideoPlayer()
    
    # Find video file
    video_path = player.find_video_file()
    if not video_path:
        print("❌ No video file found")
        print("💡 Place a video file in ./videos/ or on a USB drive")
        return
    
    print(f"📹 Found video: {video_path}")
    
    # Play video
    if player.play_video(video_path):
        print("\n⏱️  Playing for 10 seconds...")
        print("   (Video should be visible on display)")
        
        try:
            time.sleep(10)
        except KeyboardInterrupt:
            print("\n⏹️  Interrupted by user")
        
        print("\n🛑 Stopping video...")
        player.stop()
        print("✅ Test complete!")
    else:
        print("❌ Failed to start video")

if __name__ == "__main__":
    main()
