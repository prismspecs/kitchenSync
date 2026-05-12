#!/usr/bin/env python3
"""
Mock Video Driver for KitchenSync
Simulates video playback timing for testing logic without hardware.
"""

import time
from video.driver import VideoDriver, PlayerState


class MockVideoDriver(VideoDriver):
    """
    Mock driver that simulates a video clock.
    Used for TDD and testing on systems without VLC/GStreamer.
    """

    def __init__(self, debug_mode: bool = False):
        self.state = PlayerState.STOPPED
        self.duration = 60.0  # Default 60s
        self.start_time = 0.0
        self.pause_time = 0.0
        self.rate = 1.0
        self.current_pos = 0.0

    def load(self, video_path: str) -> bool:
        # Just pretend we loaded it
        return True

    def play(self) -> bool:
        if self.state != PlayerState.PLAYING:
            # Adjust start time to account for when we were paused
            self.start_time = time.time() - (self.current_pos / self.rate)
            self.state = PlayerState.PLAYING
        return True

    def pause(self) -> bool:
        if self.state == PlayerState.PLAYING:
            self.current_pos = self.get_position()
            self.state = PlayerState.PAUSED
        return True

    def stop(self) -> None:
        self.state = PlayerState.STOPPED
        self.current_pos = 0.0

    def seek(self, seconds: float) -> bool:
        self.current_pos = seconds
        if self.state == PlayerState.PLAYING:
            self.start_time = time.time() - (self.current_pos / self.rate)
        return True

    def set_speed(self, rate: float) -> bool:
        # Capture current pos before changing rate
        self.current_pos = self.get_position()
        self.rate = rate
        if self.state == PlayerState.PLAYING:
            self.start_time = time.time() - (self.current_pos / self.rate)
        return True

    def get_position(self) -> float:
        if self.state == PlayerState.PLAYING:
            elapsed = (time.time() - self.start_time) * self.rate
            return elapsed % self.duration
        return self.current_pos

    def get_duration(self) -> float:
        return self.duration

    def get_state(self) -> PlayerState:
        return self.state

    def set_fullscreen(self, enabled: bool) -> None:
        pass

    def cleanup(self) -> None:
        self.stop()
