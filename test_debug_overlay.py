#!/usr/bin/env python3
"""
Test script for KitchenSync debug mode functionality
Tests the debug overlay system without requiring full video playback
"""

import sys
import os
import time
from threading import Thread

# Add current directory to path so we can import from collaborator.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from collaborator import DebugOverlay
except ImportError as e:
    print(f"Error importing DebugOverlay: {e}")
    sys.exit(1)

def test_debug_overlay():
    """Test the debug overlay functionality"""
    print("🧪 Testing KitchenSync Debug Overlay")
    print("=" * 40)
    
    # Create debug overlay instance
    pi_id = "test-pi-001"
    video_file = "test_video.mp4"
    
    # Test with pygame if available
    try:
        import pygame
        print("✓ Pygame available - testing visual overlay")
        overlay = DebugOverlay(pi_id, video_file, use_pygame=True)
        pygame_available = True
    except ImportError:
        print("⚠️ Pygame not available - testing text overlay")
        overlay = DebugOverlay(pi_id, video_file, use_pygame=False)
        pygame_available = False
    
    print(f"Debug overlay created for Pi: {pi_id}")
    print(f"Video file: {video_file}")
    print(f"Using pygame: {pygame_available}")
    
    # Simulate running video with debug updates
    print("\n🎬 Simulating video playback with debug overlay...")
    print("(This will run for 30 seconds)")
    
    start_time = time.time()
    total_duration = 180.0  # 3 minute video
    
    try:
        for i in range(300):  # Run for 30 seconds (300 * 0.1s)
            current_time = time.time() - start_time
            
            # Simulate additional debug info
            additional_info = [
                f"Frame: {i * 2}",
                f"Sync status: OK",
                f"MIDI events: {i // 10}/50"
            ]
            
            # Update overlay
            overlay.update_display(current_time, total_duration, additional_info)
            
            # If using pygame, handle events to prevent window from becoming unresponsive
            if pygame_available:
                try:
                    import pygame
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            print("\n🛑 User closed window")
                            return
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_ESCAPE:
                                print("\n🛑 Escape key pressed")
                                return
                except:
                    pass
            
            time.sleep(0.1)  # 10 FPS update rate
            
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    
    finally:
        # Clean up
        overlay.cleanup()
        print("✓ Debug overlay cleaned up")
        print("🎉 Test complete!")

if __name__ == "__main__":
    test_debug_overlay()
