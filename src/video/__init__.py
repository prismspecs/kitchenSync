#!/usr/bin/env python3
"""
Video Driver Factory for kSync
Loads the appropriate driver backend based on configuration.
"""

from typing import Optional, Any
from video.driver import VideoDriver
from video.file_manager import VideoFileManager
from core.logger import log_info, log_error, log_warning

def get_video_driver(driver_name: str, debug_mode: bool = False, enable_audio: bool = True, config: Optional[Any] = None) -> Optional[VideoDriver]:
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
            video_width = config.video_width if config else 0
            video_height = config.video_height if config else 0
            poll_interval = config.position_poll_interval if (config and hasattr(config, "position_poll_interval")) else 0.05
            crop_mode = config.crop_mode if (config and hasattr(config, "crop_mode")) else "letterbox"
            return GstDriver(
                debug_mode=debug_mode,
                enable_audio=enable_audio,
                video_width=video_width,
                video_height=video_height,
                poll_interval=poll_interval,
                crop_mode=crop_mode,
                config=config
            )
            
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
