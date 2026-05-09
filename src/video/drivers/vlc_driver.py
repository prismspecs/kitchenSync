#!/usr/bin/env python3
"""
VLC Implementation of the VideoDriver interface.
Wraps python-vlc to follow the standardized KitchenSync contract.
"""

import os
import time
import threading
from typing import Optional, Dict, Any

try:
    import vlc
    VLC_AVAILABLE = True
except ImportError:
    VLC_AVAILABLE = False

from src.video.driver import VideoDriver, PlayerState
from src.core.logger import log_info, log_error, log_warning


class VLCDriver(VideoDriver):
    """
    VLC Driver for KitchenSync.
    Implements the VideoDriver interface using python-vlc.
    """

    def __init__(self, debug_mode: bool = False):
        if not VLC_AVAILABLE:
            raise ImportError("python-vlc not found. Install via apt or pip.")

        self.debug_mode = debug_mode
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None
        self.video_path = None
        self.state = PlayerState.STOPPED
        self.fullscreen = not debug_mode

    def load(self, video_path: str) -> bool:
        if not os.path.exists(video_path):
            log_error(f"VLC: Video file not found: {video_path}")
            return False

        self.video_path = video_path
        
        # Initialize VLC instance with optimized Pi args
        vlc_args = self._get_vlc_args()
        self.vlc_instance = vlc.Instance(vlc_args)
        self.vlc_player = self.vlc_instance.media_player_new()
        
        self.vlc_media = self.vlc_instance.media_new(video_path)
        # Add infinite repeat option for natural looping
        self.vlc_media.add_option(":input-repeat=65535")
        self.vlc_player.set_media(self.vlc_media)
        
        log_info(f"VLC: Loaded {video_path}")
        return True

    def _get_vlc_args(self) -> list:
        args = [
            "--no-video-title-show",
            "--avcodec-hw=any",
            "--codec=avcodec",
            "--vout=gl",
            "--quiet",
            "--verbose=0"
        ]
        if self.fullscreen:
            args.extend(["--fullscreen", "--no-video-deco", "--video-on-top"])
        return args

    def play(self) -> bool:
        if not self.vlc_player:
            return False
        
        result = self.vlc_player.play()
        if result == 0:
            self.state = PlayerState.PLAYING
            return True
        return False

    def pause(self) -> bool:
        if self.vlc_player:
            self.vlc_player.pause()
            self.state = PlayerState.PAUSED
            return True
        return False

    def stop(self) -> None:
        if self.vlc_player:
            self.vlc_player.stop()
            self.state = PlayerState.STOPPED

    def seek(self, seconds: float) -> bool:
        if self.vlc_player:
            # VLC uses milliseconds for set_time
            self.vlc_player.set_time(int(seconds * 1000))
            return True
        return False

    def set_speed(self, rate: float) -> bool:
        if self.vlc_player:
            # VLC's rate control is less precise than GStreamer's but supported
            return self.vlc_player.set_rate(rate) == 0
        return False

    def get_position(self) -> float:
        if not self.vlc_player:
            return 0.0
        t = self.vlc_player.get_time()
        return t / 1000.0 if t > 0 else 0.0

    def get_duration(self) -> float:
        if not self.vlc_player:
            return 0.0
        d = self.vlc_player.get_length()
        return d / 1000.0 if d > 0 else 0.0

    def get_state(self) -> PlayerState:
        if not self.vlc_player:
            return PlayerState.STOPPED
        
        vlc_state = self.vlc_player.get_state()
        if vlc_state == vlc.State.Playing:
            return PlayerState.PLAYING
        elif vlc_state == vlc.State.Paused:
            return PlayerState.PAUSED
        elif vlc_state == vlc.State.Stopped:
            return PlayerState.STOPPED
        elif vlc_state == vlc.State.Error:
            return PlayerState.ERROR
        return self.state

    def set_fullscreen(self, enabled: bool) -> None:
        self.fullscreen = enabled
        if self.vlc_player:
            self.vlc_player.set_fullscreen(enabled)

    def cleanup(self) -> None:
        self.stop()
        if self.vlc_player:
            self.vlc_player.release()
        if self.vlc_instance:
            self.vlc_instance.release()
        self.vlc_player = None
        self.vlc_instance = None
