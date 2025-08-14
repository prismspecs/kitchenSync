#!/usr/bin/env python3
"""
Test script to verify VLC fullscreen enforcement works correctly
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from video import VLCVideoPlayer
from core.logger import log_info, log_warning, log_error


def main():
    print("🎯 Testing VLC Fullscreen Enforcement")
    print("=" * 50)

    # Create VLC player in production mode (should enable fullscreen)
    player = VLCVideoPlayer(debug_mode=False, enable_vlc_logging=True)

    # Find a test video file
    test_video = None
    possible_paths = ["/home/pi/videos/test.mp4", "/tmp/test.mp4", "./test.mp4"]

    for path in possible_paths:
        if Path(path).exists():
            test_video = path
            break

    if not test_video:
        print("❌ No test video found. Please place a video file at one of:")
        for path in possible_paths:
            print(f"   - {path}")
        return

    try:
        print(f"📹 Loading video: {test_video}")
        player.load_video(test_video)

        print("▶️  Starting playback...")
        success = player.start_playback()

        if success:
            print("✅ Playback started successfully")

            # Check fullscreen status periodically
            for i in range(10):
                time.sleep(2)
                info = player.get_video_info()
                print(
                    f"⏱️  Check #{i+1}: Fullscreen={info['is_fullscreen']}, "
                    f"Should={info['should_be_fullscreen']}, "
                    f"Enforcement={info['enforcement_active']}"
                )

                # Manually test the force_fullscreen method
                if i == 5:
                    print("🔧 Testing manual fullscreen enforcement...")
                    player.force_fullscreen()

            print("⏹️  Stopping playback...")
            player.stop_playback()
        else:
            print("❌ Failed to start playback")

    except Exception as e:
        print(f"💥 Error: {e}")
    finally:
        player.cleanup()
        print("🧹 Cleanup completed")


if __name__ == "__main__":
    main()
