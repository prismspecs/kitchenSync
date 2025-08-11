#!/usr/bin/env python3
"""
MIDI Management for KitchenSync
Handles MIDI output and scheduling
"""

import time
from typing import List, Dict, Any, Set, Optional
from core.logger import log_info, log_warning, log_error

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


class MidiScheduler:
    """Handles scheduled MIDI events"""

    def __init__(self, midi_manager: MidiManager):
        self.midi_manager = midi_manager
        self.schedule: List[Dict[str, Any]] = []
        self.triggered_cues: Set[str] = set()
        self.is_running = False
        self.start_time: Optional[float] = None
        self.video_duration: Optional[float] = None
        self.loop_count = 0
        self.enable_looping = True

    def load_schedule(self, schedule: List[Dict[str, Any]]) -> None:
        """Load MIDI schedule"""
        self.schedule = sorted(schedule, key=lambda x: x.get("time", 0))
        self.triggered_cues.clear()
        print(f"📋 Loaded MIDI schedule with {len(self.schedule)} cues")

    def start_playback(
        self, start_time: float, video_duration: Optional[float] = None
    ) -> None:
        """Start MIDI playback"""
        self.start_time = start_time
        self.video_duration = video_duration
        self.is_running = True
        self.triggered_cues.clear()
        self.loop_count = 0
        print("🎵 Started MIDI playback")

    def stop_playback(self) -> None:
        """Stop MIDI playback"""
        self.is_running = False
        self.start_time = None
        print("🛑 Stopped MIDI playback")

    def process_cues(self, current_time: float) -> None:
        """Process MIDI cues for current time with looping support"""
        if not self.is_running or not self.start_time:
            return

        playback_time = current_time

        # Handle looping if video duration is known and looping is enabled
        if (
            self.enable_looping
            and self.video_duration
            and playback_time >= self.video_duration
        ):
            # Calculate which loop we're in and the position within the loop
            loop_number = int(playback_time // self.video_duration)
            loop_time = playback_time % self.video_duration

            # If we've entered a new loop, reset triggered cues
            if loop_number > self.loop_count:
                self.loop_count = loop_number
                self.triggered_cues.clear()
                log_info(
                    f"MIDI schedule loop #{self.loop_count} started", component="midi"
                )

            playback_time = loop_time

        for cue in self.schedule:
            cue_time = cue.get("time", 0)
            cue_id = f"{cue_time}_{cue.get('type', 'unknown')}_{cue.get('note', 0)}_{cue.get('channel', 1)}"

            if cue_time <= playback_time and cue_id not in self.triggered_cues:
                self.midi_manager.send_cue_message(cue)
                self.triggered_cues.add(cue_id)
                loop_info = f" (Loop #{self.loop_count})" if self.loop_count > 0 else ""
                print(
                    f"⏰ MIDI triggered at {cue_time}s: {cue.get('type', 'unknown')}{loop_info}"
                )

    def get_current_cues(
        self, current_time: float, window: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Get cues that are currently active (within time window)"""
        # Adjust time for looping
        effective_time = self._get_loop_adjusted_time(current_time)

        current_cues = []
        for cue in self.schedule:
            cue_time = cue.get("time", 0)
            if abs(effective_time - cue_time) <= window:
                current_cues.append(cue)
        return current_cues

    def get_upcoming_cues(
        self, current_time: float, lookahead: float = 10.0
    ) -> List[Dict[str, Any]]:
        """Get upcoming cues within lookahead time"""
        # Adjust time for looping
        effective_time = self._get_loop_adjusted_time(current_time)

        upcoming_cues = []
        for cue in self.schedule:
            cue_time = cue.get("time", 0)
            if effective_time < cue_time <= effective_time + lookahead:
                upcoming_cues.append(cue)
        return upcoming_cues[:5]  # Limit to next 5 cues

    def get_recent_cues(
        self, current_time: float, lookback: float = 5.0
    ) -> List[Dict[str, Any]]:
        """Get recently triggered cues"""
        recent_cues = []
        for cue in self.schedule:
            cue_time = cue.get("time", 0)
            if current_time - lookback <= cue_time <= current_time:
                recent_cues.append(cue)
        return recent_cues[-5:]  # Last 5 cues

    def _get_loop_adjusted_time(self, current_time: float) -> float:
        """Get time adjusted for looping"""
        if (
            self.enable_looping
            and self.video_duration
            and current_time >= self.video_duration
        ):
            return current_time % self.video_duration
        return current_time

    def get_stats(self) -> Dict[str, int]:
        """Get scheduler statistics"""
        return {
            "total_cues": len(self.schedule),
            "triggered_cues": len(self.triggered_cues),
            "remaining_cues": len(self.schedule) - len(self.triggered_cues),
            "loop_count": self.loop_count,
        }
