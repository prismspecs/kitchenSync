#!/usr/bin/env python3
"""
MIDI Management for KitchenSync
Handles MIDI output.
"""

from typing import Dict, Any, List

# Try to import rtmidi
try:
    import rtmidi

    MIDI_AVAILABLE = True
except ImportError:
    MIDI_AVAILABLE = False

from core.logger import log_info, log_warning, log_error


class MockMidiOut:
    """Mock MIDI output for testing/simulation"""

    def open_port(self, port: int = 0) -> None:
        log_info(f"MIDI: Opened mock port {port}", component="midi")

    def send_message(self, message: List[int]) -> None:
        log_info(f"MIDI: {message}", component="midi")

    def close_port(self) -> None:
        log_info("MIDI: Closed mock port", component="midi")

    def get_port_count(self) -> int:
        return 1

    def get_port_name(self, port: int) -> str:
        return f"Mock MIDI Port {port}"


class MidiError(Exception):
    """Raised when MIDI operations fail"""

    pass


class MidiManager:
    """Manages MIDI I/O using python-rtmidi"""

    def __init__(self, port_index: int = 0, use_mock: bool = False):
        self.port_index = port_index
        self.midi_out = None
        self.use_mock = use_mock or not MIDI_AVAILABLE

        if self.use_mock:
            log_warning("Using mock MIDI manager", component="midi")
            self.midi_out = MockMidiOut()
            self.midi_out.open_port(self.port_index)
            return

        try:
            self.midi_out = rtmidi.MidiOut()
            available_ports = self.midi_out.get_ports()

            if not available_ports:
                log_warning(
                    "No MIDI output ports found, falling back to mock.",
                    component="midi",
                )
                self.use_mock = True
                self.midi_out = MockMidiOut()
                self.midi_out.open_port(self.port_index)
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
                self.port_index = 0
                self.midi_out.open_port(0)
                log_info(
                    f"Opened MIDI port: {available_ports[self.port_index]}",
                    component="midi",
                )
        except Exception as e:
            log_error(
                f"Error initializing MIDI: {e}. Falling back to mock.", component="midi"
            )
            self.use_mock = True
            self.midi_out = MockMidiOut()
            self.midi_out.open_port(self.port_index)

    def send(self, cue: Dict[str, Any]) -> None:
        """Send a MIDI message from a cue"""
        if self.use_mock:
            log_info(f"Mock MIDI send: {cue}", component="midi")
            return

        if not self.midi_out or not self.midi_out.is_port_open():
            log_warning("MIDI port not open, cannot send message.", component="midi")
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
            else:
                log_warning(f"Unknown cue type: {msg_type}", component="midi")
        except Exception as e:
            log_error(f"Error sending MIDI message: {e}", component="midi")

    def cleanup(self) -> None:
        """Clean up MIDI resources"""
        if self.midi_out and not self.use_mock:
            self.midi_out.close_port()
            del self.midi_out
            log_info("MIDI port closed.", component="midi")
