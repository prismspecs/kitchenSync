#!/usr/bin/env python3
"""
Base Video Driver Interface for kSync
Ensures all video backends (GStreamer, VLC, mpv) follow the same contract.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any


class PlayerState(Enum):
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    BUFFERING = "buffering"
    ERROR = "error"


class VideoDriver(ABC):
    """
    Abstract Base Class for all Video Drivers.
    Follows the 'High Organization' mandate for modularity.
    """

    @abstractmethod
    def load(self, video_path: str) -> bool:
        """Load a video file and prepare for playback."""
        pass

    @abstractmethod
    def play(self) -> bool:
        """Start or resume playback."""
        pass

    @abstractmethod
    def pause(self) -> bool:
        """Pause playback."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop playback and reset position."""
        pass

    @abstractmethod
    def seek(self, seconds: float) -> bool:
        """Jump to a specific time in the video."""
        pass

    @abstractmethod
    def set_speed(self, rate: float) -> bool:
        """
        Adjust playback speed (e.g., 1.001 to catch up).
        Critical for seamless GStreamer synchronization.
        """
        pass

    @abstractmethod
    def get_position(self) -> float:
        """Get current playback position in seconds."""
        pass

    @abstractmethod
    def get_duration(self) -> float:
        """Get total video duration in seconds."""
        pass

    @abstractmethod
    def get_state(self) -> PlayerState:
        """Get the current state of the player."""
        pass

    @abstractmethod
    def set_fullscreen(self, enabled: bool) -> None:
        """Toggle fullscreen mode."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Release hardware resources."""
        pass

    @abstractmethod
    def set_overlay_text(self, text: str) -> None:
        """Set on-screen telemetry overlay text. If empty or not supported, it is a no-op."""
        pass

    @property
    def is_playing(self) -> bool:
        """Check if the player is currently playing."""
        return self.get_state() == PlayerState.PLAYING

    def get_info(self) -> Dict[str, Any]:
        """Return a standardized dictionary of player info for the debug overlay."""
        return {
            "position": self.get_position(),
            "duration": self.get_duration(),
            "state": self.get_state().value,
            "is_playing": self.get_state() == PlayerState.PLAYING,
        }
