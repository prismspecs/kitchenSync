#!/usr/bin/env python3
"""
Core Schedule Management for KitchenSync
Handles loading, saving, and editing MIDI schedules
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional


# Try to import mido for MIDI file support
try:
    import mido

    MIDI_SUPPORT = True
except ImportError:
    MIDI_SUPPORT = False
    import os

    if not os.environ.get("KITCHENSYNC_MIDO_WARNED"):
        print("⚠️ mido not available - MIDI file support disabled")
        os.environ["KITCHENSYNC_MIDO_WARNED"] = "1"


class ScheduleError(Exception):
    """Raised when schedule operations fail"""

    pass


class Schedule:
    """Manages MIDI cue schedule"""

    def __init__(self, schedule_file: str = "schedule.json"):
        self.schedule_file = Path(schedule_file)
        self.cues: List[Dict[str, Any]] = []
        self.usb_schedule_path = None
        self.load_schedule()

    def load_schedule(self) -> None:
        """Load schedule from JSON file, trying USB first"""
        # Try to find and load from USB first
        if self._try_load_from_usb():
            return

        # Fall back to local schedule file
        try:
            if self.schedule_file.exists():
                with open(self.schedule_file, "r") as f:
                    self.cues = json.load(f)
                print(f"✓ Loaded local schedule with {len(self.cues)} cues")
            else:
                print("📋 No schedule file found, using empty schedule")
                self.cues = []
        except json.JSONDecodeError as e:
            raise ScheduleError(f"Invalid JSON in schedule file: {e}")
        except Exception as e:
            raise ScheduleError(f"Error loading schedule: {e}")

    def _try_load_from_usb(self) -> bool:
        """Try to load schedule from USB drive"""
        try:
            # Import here to avoid circular import
            from config import USBConfigLoader

            # First try JSON schedule files
            usb_schedule_path = USBConfigLoader.find_schedule_on_usb()
            if usb_schedule_path:
                if usb_schedule_path.lower().endswith(".json"):
                    return self._load_json_schedule(usb_schedule_path)

            # Then try MIDI files if no JSON found
            usb_midi_path = USBConfigLoader.find_midi_file_on_usb()
            if usb_midi_path and MIDI_SUPPORT:
                return self._load_midi_schedule(usb_midi_path)
            elif usb_midi_path and not MIDI_SUPPORT:
                print(
                    f"🎼 Found MIDI file {usb_midi_path} but mido library not available"
                )
                print("   Install with: pip install mido")

        except Exception as e:
            print(f"⚠️ Error loading schedule from USB: {e}")
        return False

    def _load_json_schedule(self, schedule_path: str) -> bool:
        """Load JSON schedule file"""
        try:
            with open(schedule_path, "r") as f:
                self.cues = json.load(f)
            self.usb_schedule_path = schedule_path
            print(
                f"🔌 Loaded USB JSON schedule with {len(self.cues)} cues from {schedule_path}"
            )
            return True
        except Exception as e:
            print(f"⚠️ Error loading JSON schedule: {e}")
            return False

    def _load_midi_schedule(self, midi_path: str) -> bool:
        """Load and convert MIDI file to schedule"""
        if not MIDI_SUPPORT:
            print("❌ MIDI file support not available - install mido library")
            return False

        try:
            midi_cues = self._parse_midi_file(midi_path)
            if midi_cues:
                self.cues = midi_cues
                self.usb_schedule_path = midi_path
                print(
                    f"🎼 Loaded USB MIDI file with {len(self.cues)} cues from {midi_path}"
                )
                return True
            else:
                print(f"⚠️ No usable MIDI events found in {midi_path}")
                return False
        except Exception as e:
            print(f"⚠️ Error loading MIDI file: {e}")
            return False

    def _parse_midi_file(self, midi_path: str) -> List[Dict[str, Any]]:
        """Parse MIDI file and convert to schedule format"""
        if not MIDI_SUPPORT:
            return []

        try:
            mid = mido.MidiFile(midi_path)
            cues = []
            current_time = 0.0

            # Parse all tracks
            for track_num, track in enumerate(mid.tracks):
                track_time = 0.0

                for msg in track:
                    # Update timing
                    track_time += mido.tick2second(
                        msg.time, mid.ticks_per_beat, 500000
                    )  # 500000 = default tempo

                    # Convert MIDI messages to our cue format
                    if msg.type == "note_on" and msg.velocity > 0:
                        cue = {
                            "time": round(track_time, 3),
                            "type": "note_on",
                            "channel": msg.channel + 1,  # Convert 0-15 to 1-16
                            "note": msg.note,
                            "velocity": msg.velocity,
                            "description": f"MIDI Note {msg.note} ON (Ch{msg.channel + 1}, Track{track_num + 1})",
                        }
                        cues.append(cue)

                    elif msg.type == "note_off" or (
                        msg.type == "note_on" and msg.velocity == 0
                    ):
                        cue = {
                            "time": round(track_time, 3),
                            "type": "note_off",
                            "channel": msg.channel + 1,  # Convert 0-15 to 1-16
                            "note": msg.note,
                            "velocity": 0,
                            "description": f"MIDI Note {msg.note} OFF (Ch{msg.channel + 1}, Track{track_num + 1})",
                        }
                        cues.append(cue)

                    elif msg.type == "control_change":
                        cue = {
                            "time": round(track_time, 3),
                            "type": "control_change",
                            "channel": msg.channel + 1,  # Convert 0-15 to 1-16
                            "control": msg.control,
                            "value": msg.value,
                            "description": f"MIDI CC{msg.control}={msg.value} (Ch{msg.channel + 1}, Track{track_num + 1})",
                        }
                        cues.append(cue)

            # Sort by time and return
            cues.sort(key=lambda x: x.get("time", 0))
            return cues

        except Exception as e:
            print(f"Error parsing MIDI file: {e}")
            return []

    def load_schedule_from_path(self, schedule_path: str) -> None:
        """Load schedule from a specific path - supports JSON and MIDI files"""
        file_path = Path(schedule_path)

        if not file_path.exists():
            raise ScheduleError(f"Schedule file not found: {schedule_path}")

        # Determine file type and load accordingly
        if file_path.suffix.lower() == ".json":
            self._load_json_from_path(schedule_path)
        elif file_path.suffix.lower() in [".mid", ".midi"]:
            self._load_midi_from_path(schedule_path)
        else:
            # Try JSON first, then MIDI
            try:
                self._load_json_from_path(schedule_path)
            except:
                self._load_midi_from_path(schedule_path)

    def _load_json_from_path(self, schedule_path: str) -> None:
        """Load JSON schedule from specific path"""
        try:
            with open(schedule_path, "r") as f:
                self.cues = json.load(f)
            print(
                f"✓ Loaded JSON schedule with {len(self.cues)} cues from {schedule_path}"
            )
        except json.JSONDecodeError as e:
            raise ScheduleError(f"Invalid JSON in schedule file: {e}")
        except Exception as e:
            raise ScheduleError(f"Error loading schedule from {schedule_path}: {e}")

    def _load_midi_from_path(self, midi_path: str) -> None:
        """Load MIDI file from specific path"""
        if not MIDI_SUPPORT:
            raise ScheduleError(
                "MIDI file support not available - install mido library"
            )

        try:
            midi_cues = self._parse_midi_file(midi_path)
            if midi_cues:
                self.cues = midi_cues
                print(f"✓ Loaded MIDI file with {len(self.cues)} cues from {midi_path}")
            else:
                raise ScheduleError(f"No usable MIDI events found in {midi_path}")
        except Exception as e:
            raise ScheduleError(f"Error loading MIDI file from {midi_path}: {e}")

    def load_midi_file(self, midi_path: str) -> None:
        """Explicitly load a MIDI file and convert to schedule"""
        self._load_midi_from_path(midi_path)

    def export_to_midi(self, output_path: str, ticks_per_beat: int = 480) -> None:
        """Export current schedule to MIDI file"""
        if not MIDI_SUPPORT:
            raise ScheduleError("MIDI file export not available - install mido library")

        try:
            mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
            track = mido.MidiTrack()
            mid.tracks.append(track)

            # Convert schedule to MIDI messages
            last_time = 0.0
            for cue in sorted(self.cues, key=lambda x: x.get("time", 0)):
                cue_time = cue.get("time", 0)
                delta_time = max(0, cue_time - last_time)
                delta_ticks = mido.second2tick(delta_time, ticks_per_beat, 500000)

                if cue.get("type") == "note_on":
                    msg = mido.Message(
                        "note_on",
                        channel=max(0, min(15, cue.get("channel", 1) - 1)),
                        note=max(0, min(127, cue.get("note", 60))),
                        velocity=max(0, min(127, cue.get("velocity", 127))),
                        time=int(delta_ticks),
                    )
                    track.append(msg)

                elif cue.get("type") == "note_off":
                    msg = mido.Message(
                        "note_off",
                        channel=max(0, min(15, cue.get("channel", 1) - 1)),
                        note=max(0, min(127, cue.get("note", 60))),
                        velocity=0,
                        time=int(delta_ticks),
                    )
                    track.append(msg)

                elif cue.get("type") == "control_change":
                    msg = mido.Message(
                        "control_change",
                        channel=max(0, min(15, cue.get("channel", 1) - 1)),
                        control=max(0, min(127, cue.get("control", 0))),
                        value=max(0, min(127, cue.get("value", 0))),
                        time=int(delta_ticks),
                    )
                    track.append(msg)

                last_time = cue_time

            mid.save(output_path)
            print(f"✅ Exported schedule to MIDI file: {output_path}")

        except Exception as e:
            raise ScheduleError(f"Error exporting to MIDI file: {e}")

    def save_schedule(self) -> None:
        """Save current schedule to JSON file"""
        try:
            with open(self.schedule_file, "w") as f:
                json.dump(self.cues, f, indent=2)
            print(f"✅ Schedule saved ({len(self.cues)} cues)")
        except Exception as e:
            raise ScheduleError(f"Error saving schedule: {e}")

    def add_cue(self, cue: Dict[str, Any]) -> None:
        """Add a cue to the schedule"""
        self.cues.append(cue)
        self._sort_cues()
        print(f"➕ Added cue at {cue.get('time', 0)}s")

    def remove_cue(self, index: int) -> Optional[Dict[str, Any]]:
        """Remove a cue by index"""
        if 0 <= index < len(self.cues):
            removed = self.cues.pop(index)
            print(f"➖ Removed cue at {removed.get('time', 0)}s")
            return removed
        return None

    def clear_schedule(self) -> None:
        """Clear all cues"""
        self.cues.clear()
        print("🗑️ Schedule cleared")

    def get_cues(self) -> List[Dict[str, Any]]:
        """Get all cues"""
        return self.cues.copy()

    def get_cue_count(self) -> int:
        """Get number of cues"""
        return len(self.cues)

    def _sort_cues(self) -> None:
        """Sort cues by time"""
        self.cues.sort(key=lambda x: x.get("time", 0))

    @staticmethod
    def create_note_on_cue(
        time: float, channel: int, note: int, velocity: int
    ) -> Dict[str, Any]:
        """Create a note on cue"""
        return {
            "time": time,
            "type": "note_on",
            "channel": channel,
            "note": note,
            "velocity": velocity,
        }

    @staticmethod
    def create_note_off_cue(time: float, channel: int, note: int) -> Dict[str, Any]:
        """Create a note off cue"""
        return {
            "time": time,
            "type": "note_off",
            "channel": channel,
            "note": note,
            "velocity": 0,
        }

    @staticmethod
    def create_control_change_cue(
        time: float, channel: int, control: int, value: int
    ) -> Dict[str, Any]:
        """Create a control change cue"""
        return {
            "time": time,
            "type": "control_change",
            "channel": channel,
            "control": control,
            "value": value,
        }

    # Relay-specific helper methods for easier schedule creation
    @staticmethod
    def create_relay_on_cue(
        time: float, relay_output: int, velocity: int = 127, channel: int = 1
    ) -> Dict[str, Any]:
        """Create a relay ON cue using Note On

        Args:
            time: Time in seconds
            relay_output: Output number (1-12)
            velocity: MIDI velocity (1-127, controls power level)
            channel: MIDI channel (1-16, ignored by hardware but good for organization)
        """
        if not (1 <= relay_output <= 12):
            raise ValueError("Relay output must be 1-12")

        note = 59 + relay_output  # Note 60-71 for outputs 1-12
        return {
            "time": time,
            "type": "note_on",
            "channel": channel,
            "note": note,
            "velocity": velocity,
            "description": f"Output {relay_output} ON (Note {note}, Velocity {velocity})",
        }

    @staticmethod
    def create_relay_off_cue(
        time: float, relay_output: int, channel: int = 1
    ) -> Dict[str, Any]:
        """Create a relay OFF cue using Note Off

        Args:
            time: Time in seconds
            relay_output: Output number (1-12)
            channel: MIDI channel (1-16, ignored by hardware)
        """
        if not (1 <= relay_output <= 12):
            raise ValueError("Relay output must be 1-12")

        note = 59 + relay_output  # Note 60-71 for outputs 1-12
        return {
            "time": time,
            "type": "note_off",
            "channel": channel,
            "note": note,
            "velocity": 0,
            "description": f"Output {relay_output} OFF (Note {note})",
        }

    @staticmethod
    def create_relay_pulse_cues(
        time: float,
        relay_output: int,
        duration: float = 0.5,
        velocity: int = 127,
        channel: int = 1,
    ) -> List[Dict[str, Any]]:
        """Create a relay pulse (ON then OFF after duration)

        Args:
            time: Time in seconds
            relay_output: Output number (1-12)
            duration: How long to stay ON (seconds, max 5s due to auto-timeout)
            velocity: MIDI velocity (1-127, controls power level)
            channel: MIDI channel (1-16, ignored by hardware)
        """
        if duration > 5.0:
            print("⚠️ Warning: Duration > 5s, hardware will auto-timeout at 5s")

        return [
            Schedule.create_relay_on_cue(time, relay_output, velocity, channel),
            Schedule.create_relay_off_cue(time + duration, relay_output, channel),
        ]

    def add_relay_on(
        self, time: float, relay_output: int, velocity: int = 127, channel: int = 1
    ) -> None:
        """Add a relay ON cue to the schedule"""
        cue = self.create_relay_on_cue(time, relay_output, velocity, channel)
        self.add_cue(cue)

    def add_relay_off(self, time: float, relay_output: int, channel: int = 1) -> None:
        """Add a relay OFF cue to the schedule"""
        cue = self.create_relay_off_cue(time, relay_output, channel)
        self.add_cue(cue)

    def add_relay_pulse(
        self,
        time: float,
        relay_output: int,
        duration: float = 0.5,
        velocity: int = 127,
        channel: int = 1,
    ) -> None:
        """Add a relay pulse (ON then OFF) to the schedule"""
        cues = self.create_relay_pulse_cues(
            time, relay_output, duration, velocity, channel
        )
        for cue in cues:
            self.add_cue(cue)

    def add_relay_long_event(
        self,
        start_time: float,
        end_time: float,
        relay_output: int,
        velocity: int = 127,
        channel: int = 1,
        keepalive_interval: float = 4.0,
    ) -> None:
        """Add a long relay event with automatic keepalive messages

        For events longer than 5 seconds, this automatically adds keepalive
        Note On messages every 4 seconds to prevent hardware auto-timeout.

        Args:
            start_time: When to start the event (seconds)
            end_time: When to end the event (seconds)
            relay_output: Output number (1-12)
            velocity: MIDI velocity (1-127, controls power level)
            channel: MIDI channel (1-16, ignored by hardware)
            keepalive_interval: How often to send keepalive (default 4s)
        """
        if end_time <= start_time:
            raise ValueError("End time must be after start time")

        duration = end_time - start_time

        # Add initial Note On
        self.add_relay_on(start_time, relay_output, velocity, channel)

        # Add keepalive messages for long events
        if duration > 5.0:
            current_time = start_time + keepalive_interval
            keepalive_count = 1

            while current_time < end_time:
                # Add keepalive Note On message
                note = 59 + relay_output
                cue = {
                    "time": current_time,
                    "type": "note_on",
                    "channel": channel,
                    "note": note,
                    "velocity": velocity,
                    "description": f"Output {relay_output} Keepalive #{keepalive_count} (Note {note})",
                }
                self.add_cue(cue)

                current_time += keepalive_interval
                keepalive_count += 1

        # Add final Note Off
        self.add_relay_off(end_time, relay_output, channel)

    def format_cue_description(self, cue: Dict[str, Any]) -> str:
        """Format a cue for display"""
        cue_type = cue.get("type", "unknown")
        time_val = cue.get("time", 0)

        # Use custom description if available (for relay cues)
        if "description" in cue:
            return f"Time {time_val}s - {cue['description']}"

        if cue_type == "note_on":
            return f"Time {time_val}s - Note {cue.get('note', 0)} ON (vel:{cue.get('velocity', 0)}, ch:{cue.get('channel', 1)})"
        elif cue_type == "note_off":
            return f"Time {time_val}s - Note {cue.get('note', 0)} OFF (ch:{cue.get('channel', 1)})"
        elif cue_type == "control_change":
            return f"Time {time_val}s - CC {cue.get('control', 0)}={cue.get('value', 0)} (ch:{cue.get('channel', 1)})"
        else:
            return f"Time {time_val}s - Unknown type: {cue_type}"

    def print_schedule(self) -> None:
        """Print the current schedule"""
        if not self.cues:
            print("  (empty)")
        else:
            for i, cue in enumerate(self.cues):
                print(f"  {i+1}. {self.format_cue_description(cue)}")


class ScheduleEditor:
    """Interactive schedule editor"""

    def __init__(self, schedule: Schedule):
        self.schedule = schedule

    def run_editor(self) -> None:
        """Run the interactive schedule editor"""
        print("\n=== Schedule Editor ===")
        self.schedule.print_schedule()

        print("\nOptions:")
        print("  add             - Add new cue")
        print("  remove <number> - Remove cue")
        print("  clear           - Clear all cues")
        print("  save            - Save and return")

        while True:
            try:
                cmd = input("schedule> ").strip().lower()

                if cmd == "add":
                    self._add_cue_interactive()
                elif cmd.startswith("remove "):
                    self._remove_cue_interactive(cmd)
                elif cmd == "clear":
                    self.schedule.clear_schedule()
                    self.schedule.print_schedule()
                elif cmd == "save":
                    self.schedule.save_schedule()
                    break
                elif cmd == "help":
                    self._show_help()
                else:
                    print("Unknown command. Type 'help' for options.")
            except (KeyboardInterrupt, EOFError):
                break

    def _add_cue_interactive(self) -> None:
        """Add a new cue interactively"""
        try:
            time_val = float(input("Enter time (seconds): "))

            print("\nMIDI Event Types:")
            print("  1. Note On")
            print("  2. Note Off")
            print("  3. Control Change")
            event_type = input("Select event type (1-3): ").strip()

            if event_type == "1":
                cue = self._create_note_on_cue(time_val)
            elif event_type == "2":
                cue = self._create_note_off_cue(time_val)
            elif event_type == "3":
                cue = self._create_control_change_cue(time_val)
            else:
                print("Invalid event type")
                return

            if cue:
                self.schedule.add_cue(cue)
                self.schedule.print_schedule()

        except ValueError:
            print("Invalid input. Please enter numeric values.")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled")

    def _create_note_on_cue(self, time_val: float) -> Optional[Dict[str, Any]]:
        """Create note on cue interactively"""
        try:
            note = int(input("Enter MIDI note (0-127): "))
            velocity = int(input("Enter velocity (0-127): "))
            channel = int(input("Enter MIDI channel (1-16): "))

            if not (0 <= note <= 127 and 0 <= velocity <= 127 and 1 <= channel <= 16):
                print("Invalid MIDI values")
                return None

            return Schedule.create_note_on_cue(time_val, channel, note, velocity)
        except ValueError:
            print("Invalid numeric input")
            return None

    def _create_note_off_cue(self, time_val: float) -> Optional[Dict[str, Any]]:
        """Create note off cue interactively"""
        try:
            note = int(input("Enter MIDI note (0-127): "))
            channel = int(input("Enter MIDI channel (1-16): "))

            if not (0 <= note <= 127 and 1 <= channel <= 16):
                print("Invalid MIDI values")
                return None

            return Schedule.create_note_off_cue(time_val, channel, note)
        except ValueError:
            print("Invalid numeric input")
            return None

    def _create_control_change_cue(self, time_val: float) -> Optional[Dict[str, Any]]:
        """Create control change cue interactively"""
        try:
            control = int(input("Enter control number (0-127): "))
            value = int(input("Enter control value (0-127): "))
            channel = int(input("Enter MIDI channel (1-16): "))

            if not (0 <= control <= 127 and 0 <= value <= 127 and 1 <= channel <= 16):
                print("Invalid MIDI values")
                return None

            return Schedule.create_control_change_cue(time_val, channel, control, value)
        except ValueError:
            print("Invalid numeric input")
            return None

    def _remove_cue_interactive(self, cmd: str) -> None:
        """Remove a cue interactively"""
        try:
            num = int(cmd.split()[1]) - 1
            removed = self.schedule.remove_cue(num)
            if removed:
                print(f"Removed: {self.schedule.format_cue_description(removed)}")
                self.schedule.print_schedule()
            else:
                print("Invalid cue number")
        except (IndexError, ValueError):
            print("Usage: remove <number>")

    def _show_help(self) -> None:
        """Show help information"""
        print("\nOptions:")
        print("  add             - Add new cue")
        print("  remove <number> - Remove cue")
        print("  clear           - Clear all cues")
        print("  save            - Save and return")
