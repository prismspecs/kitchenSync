#!/usr/bin/env python3
"""
Core Schedule Management for KitchenSync
Handles loading, saving, and editing MIDI schedules
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional


class ScheduleError(Exception):
    """Raised when schedule operations fail"""
    pass


class Schedule:
    """Manages MIDI cue schedule"""
    
    def __init__(self, schedule_file: str = 'schedule.json'):
        self.schedule_file = Path(schedule_file)
        self.cues: List[Dict[str, Any]] = []
        self.load_schedule()
    
    def load_schedule(self) -> None:
        """Load schedule from JSON file"""
        try:
            if self.schedule_file.exists():
                with open(self.schedule_file, 'r') as f:
                    self.cues = json.load(f)
                print(f"✓ Loaded schedule with {len(self.cues)} cues")
            else:
                print("📋 No schedule file found, using empty schedule")
                self.cues = []
        except json.JSONDecodeError as e:
            raise ScheduleError(f"Invalid JSON in schedule file: {e}")
        except Exception as e:
            raise ScheduleError(f"Error loading schedule: {e}")
    
    def save_schedule(self) -> None:
        """Save current schedule to JSON file"""
        try:
            with open(self.schedule_file, 'w') as f:
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
        self.cues.sort(key=lambda x: x.get('time', 0))
    
    @staticmethod
    def create_note_on_cue(time: float, channel: int, note: int, velocity: int) -> Dict[str, Any]:
        """Create a note on cue"""
        return {
            'time': time,
            'type': 'note_on',
            'channel': channel,
            'note': note,
            'velocity': velocity
        }
    
    @staticmethod
    def create_note_off_cue(time: float, channel: int, note: int) -> Dict[str, Any]:
        """Create a note off cue"""
        return {
            'time': time,
            'type': 'note_off',
            'channel': channel,
            'note': note,
            'velocity': 0
        }
    
    @staticmethod
    def create_control_change_cue(time: float, channel: int, control: int, value: int) -> Dict[str, Any]:
        """Create a control change cue"""
        return {
            'time': time,
            'type': 'control_change',
            'channel': channel,
            'control': control,
            'value': value
        }
    
    def format_cue_description(self, cue: Dict[str, Any]) -> str:
        """Format a cue for display"""
        cue_type = cue.get('type', 'unknown')
        time_val = cue.get('time', 0)
        
        if cue_type == 'note_on':
            return f"Time {time_val}s - Note {cue.get('note', 0)} ON (vel:{cue.get('velocity', 0)}, ch:{cue.get('channel', 1)})"
        elif cue_type == 'note_off':
            return f"Time {time_val}s - Note {cue.get('note', 0)} OFF (ch:{cue.get('channel', 1)})"
        elif cue_type == 'control_change':
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
                
                if cmd == 'add':
                    self._add_cue_interactive()
                elif cmd.startswith('remove '):
                    self._remove_cue_interactive(cmd)
                elif cmd == 'clear':
                    self.schedule.clear_schedule()
                    self.schedule.print_schedule()
                elif cmd == 'save':
                    self.schedule.save_schedule()
                    break
                elif cmd == 'help':
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
            
            if event_type == '1':
                cue = self._create_note_on_cue(time_val)
            elif event_type == '2':
                cue = self._create_note_off_cue(time_val)
            elif event_type == '3':
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
