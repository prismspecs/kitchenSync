#!/usr/bin/env python3
"""
MIDI Management for KitchenSync
Handles MIDI output and scheduling
"""

import time
import threading
from typing import List, Dict, Any

from . import rtmidi
from core.logger import log_info, log_warning
from enum import Enum, auto

# Try to import rtmidi
try:
    import rtmidi

    MIDI_AVAILABLE = True
except ImportError:
    MIDI_AVAILABLE = False


class MockMidiOut:
    """Mock MIDI output for testing/simulation"""

    def open_port(self, port: int = 0) -> None:
        print(f"MIDI: Opened mock port {port}")

    def send_message(self, message: List[int]) -> None:
        print(f"MIDI: {message}")

    def close_port(self) -> None:
        print("MIDI: Closed mock port")

    def get_port_count(self) -> int:
        return 1

    def get_port_name(self, port: int) -> str:
        return f"Mock MIDI Port {port}"


class MidiError(Exception):
    """Raised when MIDI operations fail"""

    pass


class MidiManager:
    """Manages MIDI output and message sending"""

    def __init__(self, port: int = 0, use_mock: bool = False):
        self.port = port
        self.use_mock = use_mock or not MIDI_AVAILABLE
        self.midi_out = None
        self._setup_midi()

    def _setup_midi(self) -> None:
        """Initialize MIDI output"""
        try:
            if self.use_mock:
                self.midi_out = MockMidiOut()
            else:
                self.midi_out = rtmidi.MidiOut()

            self.midi_out.open_port(self.port)

            if self.use_mock:
                print(f"✓ MIDI mock output initialized on port {self.port}")
            else:
                print(f"✓ MIDI output initialized on port {self.port}")

        except Exception as e:
            print(f"⚠️ MIDI setup failed: {e}")
            print("Falling back to simulation mode")
            self.midi_out = MockMidiOut()
            self.midi_out.open_port(self.port)

    def send_note_on(self, channel: int, note: int, velocity: int) -> None:
        """Send MIDI note on message"""
        try:
            # MIDI channels are 0-15, but often displayed as 1-16
            channel = max(0, min(15, channel - 1))
            note = max(0, min(127, note))
            velocity = max(0, min(127, velocity))

            message = [0x90 | channel, note, velocity]
            self.midi_out.send_message(message)
            print(f"🎵 MIDI Note ON: Ch{channel+1} Note{note} Vel{velocity}")

        except Exception as e:
            print(f"Error sending note on: {e}")

    def send_note_off(self, channel: int, note: int) -> None:
        """Send MIDI note off message"""
        try:
            channel = max(0, min(15, channel - 1))
            note = max(0, min(127, note))

            message = [0x80 | channel, note, 0]
            self.midi_out.send_message(message)
            print(f"🎵 MIDI Note OFF: Ch{channel+1} Note{note}")

        except Exception as e:
            print(f"Error sending note off: {e}")

    def send_control_change(self, channel: int, control: int, value: int) -> None:
        """Send MIDI control change message"""
        try:
            channel = max(0, min(15, channel - 1))
            control = max(0, min(127, control))
            value = max(0, min(127, value))

            message = [0xB0 | channel, control, value]
            self.midi_out.send_message(message)
            print(f"🎛️ MIDI CC: Ch{channel+1} CC{control}={value}")

        except Exception as e:
            print(f"Error sending control change: {e}")

    def send_cue_message(self, cue: Dict[str, Any]) -> None:
        """Send MIDI message based on cue data"""
        cue_type = cue.get("type")

        if cue_type == "note_on":
            self.send_note_on(
                cue.get("channel", 1), cue.get("note", 60), cue.get("velocity", 64)
            )
        elif cue_type == "note_off":
            self.send_note_off(cue.get("channel", 1), cue.get("note", 60))
        elif cue_type == "control_change":
            self.send_control_change(
                cue.get("channel", 1), cue.get("control", 0), cue.get("value", 0)
            )
        else:
            print(f"⚠️ Unknown MIDI cue type: {cue_type}")

    def cleanup(self) -> None:
        """Clean up MIDI resources"""
        try:
            if self.midi_out:
                self.midi_out.close_port()
                print("🛑 MIDI output closed")
        except Exception as e:
            print(f"Error closing MIDI: {e}")


class LoopMidi(Enum):
    """Defines how the MIDI scheduler should handle looping."""

    NONE = auto()  # No looping
    INTERNAL = auto()  # Loop within the scheduler (default)
    EXTERNAL = auto()  # Rely on an external component to trigger loop


import time
import threading
from typing import List, Dict, Any

try:
    import rtmidi

    MIDI_SUPPORT = True
except ImportError:
    MIDI_SUPPORT = False

import time
import threading
from typing import List, Dict, Any

try:
    import rtmidi

    MIDI_SUPPORT = True
except ImportError:
    MIDI_SUPPORT = False

from core.logger import log_info, log_warning, log_error


class MidiScheduler:
    """Schedules and sends MIDI cues based on an external time source."""

    def __init__(self, midi_manager):
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

        # Detect loop from time source (current time is less than last time)
        # Add a small tolerance to avoid false positives from minor time fluctuations
        if (
            elapsed_time < self.last_elapsed_time
            and (self.last_elapsed_time - elapsed_time) > 1.0
        ):
            self.last_processed_index = -1  # Reset for new loop
            log_info(
                f"MIDI schedule loop detected. Time jumped from {self.last_elapsed_time:.2f}s to {elapsed_time:.2f}s.",
                component="midi",
            )

        self.last_elapsed_time = elapsed_time

        # Find next cue to process
        start_index = self.last_processed_index + 1
        for i in range(start_index, len(self.cues)):
            cue = self.cues[i]
            if cue.get("time", 0) <= elapsed_time:
                self.midi_manager.send(cue)
                self.last_processed_index = i
            else:
                # Cues are sorted, so we can stop searching
                break


class MidiManager:
    """Manages MIDI I/O using python-rtmidi"""

    def __init__(self, port_index: int = 0, use_mock: bool = False):
        self.port_index = port_index
        self.midi_out = None
        self.use_mock = use_mock

        if use_mock:
            log_warning("Using mock MIDI manager", component="midi")
            return

        if not MIDI_SUPPORT:
            log_error(
                "rtmidi not available, cannot create MIDI manager", component="midi"
            )
            self.use_mock = True
            return

        try:
            self.midi_out = rtmidi.MidiOut()
            available_ports = self.midi_out.get_ports()

            if not available_ports:
                log_warning("No MIDI output ports found", component="midi")
                self.use_mock = True
                return

            if self.port_index < len(available_ports):
                self.midi_out.open_port(self.port_index)
                log_info(
                    f"Opened MIDI port: {available_ports[self.port_index]}",
                    component="midi",
                )
            else:
                log_warning(
                    f"MIDI port index {self.port_index} out of range, using port 0",
                    component="midi",
                )
                self.midi_out.open_port(0)
        except Exception as e:
            log_error(f"Error initializing MIDI: {e}", component="midi")
            self.use_mock = True

    def send(self, cue: Dict[str, Any]) -> None:
        """Send a MIDI message from a cue"""
        if self.use_mock:
            log_info(f"Mock MIDI send: {cue}", component="midi")
            return

        if not self.midi_out or not self.midi_out.is_port_open():
            return

        try:
            msg_type = cue.get("type")
            channel = cue.get("channel", 1) - 1  # Convert 1-16 to 0-15

            if msg_type == "note_on":
                note = cue.get("note", 60)
                velocity = cue.get("velocity", 127)
                self.midi_out.send_message([0x90 + channel, note, velocity])
            elif msg_type == "note_off":
                note = cue.get("note", 60)
                self.midi_out.send_message([0x80 + channel, note, 0])
            elif msg_type == "control_change":
                control = cue.get("control", 0)
                value = cue.get("value", 0)
                self.midi_out.send_message([0xB0 + channel, control, value])
        except Exception as e:
            log_error(f"Error sending MIDI message: {e}", component="midi")

    def cleanup(self) -> None:
        """Clean up MIDI resources"""
        if self.midi_out:
            del self.midi_out
