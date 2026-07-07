#!/usr/bin/env python3
"""
MIDI Management for kSync
Handles MIDI output and scheduling
"""


import time
import glob
import bisect
from typing import List, Dict, Any, Set, Optional
from core.logger import log_info


# Try to import rtmidi
try:
    import rtmidi

    MIDI_AVAILABLE = True
except ImportError:
    MIDI_AVAILABLE = False

# Try to import pyserial
try:
    import serial

    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    SERIAL_AVAILABLE = False


__all__ = [
    "MidiManager",
    "MidiScheduler",
    "MidiError",
    "MockMidiOut",
]


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


class SerialMidiOut:
    """Serial output for Arduino MIDI controller"""

    def __init__(self, port: str = None, baud: int = 115200, timeout: float = 1.0):
        self.port = port or self._detect_port()
        self.baud = baud
        self.timeout = timeout
        self.ser = None

    def _detect_port(self):
        # Prefer /dev/ttyACM* or /dev/ttyUSB* (Linux, Pi)
        acm_ports = glob.glob("/dev/ttyACM*")
        usb_ports = glob.glob("/dev/ttyUSB*")
        if acm_ports:
            print(f" Auto-detected Arduino port: {acm_ports[0]}")
            return acm_ports[0]
        elif usb_ports:
            print(f" Auto-detected Arduino port: {usb_ports[0]}")
            return usb_ports[0]
        else:
            print(" No Arduino serial port detected, using default /dev/ttyACM0")
            return "/dev/ttyACM0"

    def open_port(self, port: int = 0):
        if not SERIAL_AVAILABLE:
            print("pyserial not available, using mock serial")
            self.ser = None
            return
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
            time.sleep(2)  # Wait for Arduino to reset
            print(f" Serial MIDI output initialized on {self.port} @ {self.baud}")
        except Exception as e:
            print(f" Serial MIDI setup failed: {e}")
            self.ser = None

    def send_message(self, message: List[int]):
        # Not used for serial, but kept for compatibility
        pass

    def send_note_on(self, channel: int, pitch: int, velocity: int):
        cmd = f"{pitch} {velocity}\n"
        self._send(cmd)

    def send_note_off(self, channel: int, pitch: int):
        cmd = f"{pitch} 0\n"
        self._send(cmd)

    def send_control_change(self, channel: int, control: int, value: int):
        # Not implemented for Arduino serial version
        pass

    def close_port(self):
        if self.ser:
            self.ser.close()
            print("Serial MIDI: Closed port")

    def flush_buffers(self):
        """Flush input/output buffers to clear any pending commands"""
        if self.ser:
            try:
                self.ser.flushInput()  # Clear any pending input
                self.ser.flushOutput()  # Clear any pending output
                print("Serial MIDI: Buffers flushed")
            except Exception as e:
                print(f"Serial MIDI buffer flush failed: {e}")

    def send_reset_command(self):
        """Send a reset command to clear Arduino PWM state"""
        if self.ser:
            try:
                # Send all channels to 0 (turn everything off)
                for channel in range(12):  # PWM channels 0-11 (notes 60-71)
                    note = 60 + channel
                    cmd = f"noteoff {channel} {note} 0\n"
                    self.ser.write(cmd.encode("utf-8"))
                    time.sleep(0.002)  # Reduced delay for faster reset
                print("Serial MIDI: Reset command sent (all channels off)")
            except Exception as e:
                print(f"Serial MIDI reset failed: {e}")

    def _send(self, cmd: str):
        if self.ser:
            try:
                self.ser.write(cmd.encode("utf-8"))
                # Reduced delay to 5ms for faster communication with improved Arduino buffering
                # print(f"Serial MIDI Sent: {cmd.strip()}")
            except Exception as e:
                # log_error(f"Serial MIDI send failed: {e}", component="midi")
                pass
        else:
            # print(f"[MOCK] Would send to Arduino: {cmd.strip()}")
            pass


class MidiError(Exception):
    """Raised when MIDI operations fail"""

    pass


class MidiManager:
    """Manages MIDI output and message sending"""

    def __init__(
        self,
        port: int = 0,
        use_mock: bool = False,
        use_serial: bool = True,
        serial_port: str = None,
        serial_baud: int = 115200,  # Match Arduino Serial.begin
    ):
        self.port = port
        self.use_mock = use_mock
        self.use_serial = use_serial
        self.serial_port = serial_port
        self.serial_baud = serial_baud
        self.midi_out = None
        self._setup_midi()

    def _setup_midi(self) -> None:
        """Initialize MIDI or Serial output"""
        try:
            if self.use_serial:
                self.midi_out = SerialMidiOut(self.serial_port, self.serial_baud)
                self.midi_out.open_port()
            elif self.use_mock or not MIDI_AVAILABLE:
                self.midi_out = MockMidiOut()
                self.midi_out.open_port(self.port)
            else:
                self.midi_out = rtmidi.MidiOut()
                self.midi_out.open_port(self.port)
                print(f" MIDI output initialized on port {self.port}")
        except Exception as e:
            print(f" MIDI/Serial setup failed: {e}")
            print("Falling back to simulation mode")
            self.midi_out = MockMidiOut()
            self.midi_out.open_port(self.port)

    def send_note_on(self, channel: int, note: int, velocity: int) -> None:
        """Send MIDI note on message"""
        try:
            if self.use_serial:
                self.midi_out.send_note_on(channel, note, velocity)
            else:
                # MIDI channels are 0-15, but often displayed as 1-16
                channel = max(0, min(15, channel - 1))
                note = max(0, min(127, note))
                velocity = max(0, min(127, velocity))
                message = [0x90 | channel, note, velocity]
                self.midi_out.send_message(message)
                print(f" MIDI Note ON: Ch{channel+1} Note{note} Vel{velocity}")
        except Exception as e:
            print(f"Error sending note on: {e}")

    def send_note_off(self, channel: int, note: int) -> None:
        """Send MIDI note off message"""
        try:
            if self.use_serial:
                self.midi_out.send_note_off(channel, note)
            else:
                channel = max(0, min(15, channel - 1))
                note = max(0, min(127, note))
                message = [0x80 | channel, note, 0]
                self.midi_out.send_message(message)
                print(f" MIDI Note OFF: Ch{channel+1} Note{note}")
        except Exception as e:
            print(f"Error sending note off: {e}")

    def send_control_change(self, channel: int, control: int, value: int) -> None:
        """Send MIDI control change message"""
        try:
            if self.use_serial:
                self.midi_out.send_control_change(channel, control, value)
            else:
                channel = max(0, min(15, channel - 1))
                control = max(0, min(127, control))
                value = max(0, min(127, value))
                message = [0xB0 | channel, control, value]
                self.midi_out.send_message(message)
                print(f" MIDI CC: Ch{channel+1} CC{control}={value}")
        except Exception as e:
            print(f"Error sending control change: {e}")

    def send_cue_message(self, cue: Dict[str, Any]) -> None:
        """Send MIDI message based on cue data"""
        cue_type = cue.get("type")

        # If no type specified, auto-detect from velocity
        if not cue_type:
            velocity = cue.get("velocity", 0)
            if velocity > 0:
                cue_type = "note_on"
            else:
                cue_type = "note_off"

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
            print(f" Unknown MIDI cue type: {cue_type}")

    def cleanup(self) -> None:
        """Clean up MIDI resources"""
        try:
            if self.midi_out:
                self.midi_out.close_port()
                print(" MIDI output closed")
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
        self.previous_playback_time = None  # Track previous position for loop detection
        self.last_effective_time: Optional[float] = (
            None  # Fire cues only as time advances
        )
        self._next_cue_index = 0

    def reset(self, seek_time: Optional[float] = None):
        """Reset triggered cues for fresh playback or loop."""
        self.triggered_cues.clear()
        self._next_cue_index = 0

        # If resetting to a specific time, find the correct starting index
        if seek_time is not None and self.schedule:
            times = [cue.get("time", 0) for cue in self.schedule]
            self._next_cue_index = bisect.bisect_left(times, seek_time)

        # Clear Arduino state and serial buffers when looping
        if (
            hasattr(self.midi_manager, "use_serial")
            and self.midi_manager.use_serial
            and hasattr(self.midi_manager.midi_out, "flush_buffers")
        ):
            # print(" Resetting Arduino state for loop...")
            self.midi_manager.midi_out.flush_buffers()

        # After a reset (loop or seek), treat the next tick as a fresh start
        self.previous_playback_time = None
        self.last_effective_time = None

    def load_schedule(self, schedule: List[Dict[str, Any]]) -> None:
        """Load MIDI schedule"""
        self.schedule = sorted(schedule, key=lambda x: x.get("time", 0))
        self.triggered_cues.clear()
        self._next_cue_index = 0
        log_info(f"Loaded MIDI schedule with {len(self.schedule)} cues", component="midi")

    def start_playback(
        self, start_time: float, video_duration: Optional[float] = None
    ) -> None:
        """Start MIDI playback"""
        self.start_time = start_time
        self.video_duration = video_duration
        self.is_running = True
        self.loop_count = 0
        self.previous_playback_time = None
        self.last_effective_time = None
        self.reset()
        log_info("Started MIDI playback", component="midi")

    def stop_playback(self) -> None:
        """Stop MIDI playback"""
        self.is_running = False
        self.start_time = None
        self.previous_playback_time = None  # Reset to prevent comparison issues
        log_info("Stopped MIDI playback", component="midi")

    def process_cues(self, current_time: float) -> None:
        """Process MIDI cues for current time with optimized pointer-based iteration"""
        if not self.is_running or self.start_time is None or not self.schedule:
            return

        # Validate current_time parameter
        if current_time is None or not isinstance(current_time, (int, float)):
            return

        playback_time = current_time

        # Robust loop detection
        loop_detected = False
        regression_detected = (
            self.previous_playback_time is not None
            and playback_time + 0.5 < self.previous_playback_time
        )

        if self.video_duration is not None and self.video_duration > 0:
            effective_time = playback_time % self.video_duration
            if regression_detected:
                loop_detected = True
                self.loop_count += 1
            else:
                computed_loop = int(playback_time // self.video_duration)
                if computed_loop > self.loop_count:
                    loop_detected = True
                    self.loop_count = computed_loop
        else:
            effective_time = playback_time
            if regression_detected:
                loop_detected = True
                self.loop_count += 1

        if loop_detected:
            self.reset()
            log_info(f"MIDI schedule loop #{self.loop_count} started", component="midi")
            self.previous_playback_time = playback_time
            self.last_effective_time = effective_time
            return

        # Handle backward jumps (seeks) without full loop
        if self.last_effective_time is not None and effective_time < self.last_effective_time:
            self.reset(effective_time)
            self.last_effective_time = effective_time
            self.previous_playback_time = playback_time
            return

        # On first tick, initialize
        if self.last_effective_time is None:
            self.last_effective_time = effective_time
            self.previous_playback_time = playback_time
            # Find starting index for immediate start
            times = [cue.get("time", 0) for cue in self.schedule]
            self._next_cue_index = bisect.bisect_left(times, effective_time)
            return

        # Process cues from the current pointer
        while self._next_cue_index < len(self.schedule):
            cue = self.schedule[self._next_cue_index]
            cue_time = cue.get("time", 0)
            
            if cue_time <= effective_time:
                # Trigger cue
                cue_type = cue.get("type")
                if not cue_type:
                    velocity = cue.get("velocity", 0)
                    cue_type = "note_on" if velocity > 0 else "note_off"

                cue_id = f"{cue_time}_{cue_type}_{cue.get('note', 0)}_{cue.get('channel', 1)}"

                if cue_id not in self.triggered_cues:
                    self.midi_manager.send_cue_message(cue)
                    self.triggered_cues.add(cue_id)
                    # Only log if specifically debugging; otherwise too noisy
                    # log_info(f"MIDI at {cue_time}s: {cue_type}", component="midi")
                
                self._next_cue_index += 1
            else:
                # Cues are sorted, so we can stop here
                break

        self.last_effective_time = effective_time
        self.previous_playback_time = playback_time

    def get_current_cues(
        self, current_time: float, window: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Get cues that are currently active (within time window)"""
        # Safety check for None or invalid current_time
        if current_time is None or not isinstance(current_time, (int, float)):
            return []

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
        # Safety check for None or invalid current_time
        if current_time is None or not isinstance(current_time, (int, float)):
            return []

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
        # Safety check for None or invalid current_time
        if current_time is None or not isinstance(current_time, (int, float)):
            return []

        recent_cues = []
        for cue in self.schedule:
            cue_time = cue.get("time", 0)
            if current_time - lookback <= cue_time <= current_time:
                recent_cues.append(cue)
        return recent_cues[-5:]  # Last 5 cues

    def _get_loop_adjusted_time(self, current_time: float) -> float:
        """Get time adjusted for looping"""
        # Safety check for None or invalid current_time
        if current_time is None or not isinstance(current_time, (int, float)):
            return 0.0

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
