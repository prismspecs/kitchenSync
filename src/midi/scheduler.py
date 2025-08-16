#!/usr/bin/env python3
"""
MIDI Scheduling for KitchenSync
"""

from typing import List, Dict, Any
from .manager import MidiManager
from core.logger import log_info


class MidiScheduler:
    """Schedules and sends MIDI cues based on an external time source."""

    def __init__(self, midi_manager: MidiManager):
        self.midi_manager = midi_manager
        self.cues: List[Dict[str, Any]] = []
        self.is_playing = False
        self.last_processed_index = -1
        self.last_elapsed_time = -1.0

    def load_schedule(self, cues: list):
        """Load a new schedule and sort it by time."""
        self.cues = sorted(cues, key=lambda x: x.get("time", 0))
        self.last_processed_index = -1
        log_info(f"Loaded {len(self.cues)} MIDI cues", component="midi")

    def start_playback(self):
        """Enable MIDI playback."""
        if self.is_playing:
            return
        self.is_playing = True
        self.last_processed_index = -1
        self.last_elapsed_time = -1.0
        log_info("MIDI playback enabled.", component="midi")

    def stop_playback(self):
        """Disable MIDI playback."""
        self.is_playing = False
        log_info("MIDI playback disabled.", component="midi")

    def process_cues(self, elapsed_time: float):
        """
        Process cues based on a given elapsed time from an external source.
        This method is now responsible for handling looping by detecting when
        the elapsed_time resets.
        """
        if not self.is_playing or elapsed_time is None:
            return

        if (
            elapsed_time < self.last_elapsed_time
            and (self.last_elapsed_time - elapsed_time) > 1.0
        ):
            self.last_processed_index = -1
            log_info(
                f"MIDI schedule loop detected. Time jumped from {self.last_elapsed_time:.2f}s to {elapsed_time:.2f}s.",
                component="midi",
            )

        self.last_elapsed_time = elapsed_time

        start_index = self.last_processed_index + 1
        for i in range(start_index, len(self.cues)):
            cue = self.cues[i]
            if cue.get("time", 0) <= elapsed_time:
                self.midi_manager.send(cue)
                self.last_processed_index = i
            else:
                break
