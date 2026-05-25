#!/usr/bin/env python3
"""
Video Driver Factory for KitchenSync
Loads the appropriate driver backend based on configuration.
"""

from typing import Optional
from video.driver import VideoDriver
from video.file_manager import VideoFileManager
from core.logger import log_info, log_error, log_warning

def get_video_driver(driver_name: str, debug_mode: bool = False, enable_audio: bool = True) -> Optional[VideoDriver]:
    """
    Factory function to instantiate a video driver.
    """
    driver_name = driver_name.lower()

    if driver_name == "vlc":
        log_warning("Video: VLC backend has been removed; falling back to GStreamer")
        driver_name = "gst"
    
    try:
        if driver_name == "gstreamer" or driver_name == "gst":
            from video.drivers.gst_driver import GstDriver
            log_info("Video: Using GStreamer driver backend")
            return GstDriver(debug_mode=debug_mode, enable_audio=enable_audio)
            
        elif driver_name == "mock":
            from video.drivers.mock_driver import MockVideoDriver
            log_info("Video: Using Mock driver backend")
            return MockVideoDriver(debug_mode=debug_mode)
            
        else:
            log_error(f"Video: Unknown driver backend '{driver_name}'")
            return None
            
    except ImportError as e:
        log_error(f"Video: Failed to load driver '{driver_name}': {e}")
        return None
    except Exception as e:
        log_error(f"Video: Error initializing driver '{driver_name}': {e}")
        return None

__all__ = ["get_video_driver", "VideoFileManager", "VideoDriver"]
