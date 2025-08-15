#!/usr/bin/env python3
"""
MIDI Schedule Converter - Convert between JSON and MIDI formats
Demonstrates both input formats for KitchenSync relay control
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.schedule import Schedule, ScheduleError
import argparse


def convert_to_json(input_file: str, output_file: str = None):
    """Convert MIDI file to JSON schedule"""
    if not output_file:
        output_file = Path(input_file).with_suffix(".json")

    try:
        # Load the MIDI file
        schedule = Schedule()
        schedule.load_schedule_from_path(input_file)

        # Save as JSON
        schedule.schedule_file = Path(output_file)
        schedule.save_schedule()

        print(f"✅ Converted {input_file} to {output_file}")
        print(f"   Found {schedule.get_cue_count()} events")

    except ScheduleError as e:
        print(f"❌ Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


def convert_to_midi(input_file: str, output_file: str = None):
    """Convert JSON schedule to MIDI file"""
    if not output_file:
        output_file = Path(input_file).with_suffix(".mid")

    try:
        # Load the JSON file
        schedule = Schedule()
        schedule.load_schedule_from_path(input_file)

        # Export as MIDI
        schedule.export_to_midi(str(output_file))

        print(f"✅ Converted {input_file} to {output_file}")
        print(f"   Exported {schedule.get_cue_count()} events")

    except ScheduleError as e:
        print(f"❌ Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


def inspect_file(input_file: str):
    """Inspect and display contents of schedule file"""
    try:
        schedule = Schedule()
        schedule.load_schedule_from_path(input_file)

        print(f"📁 File: {input_file}")
        print(f"📊 Events: {schedule.get_cue_count()}")
        print(f"📋 Schedule contents:")
        schedule.print_schedule()

    except ScheduleError as e:
        print(f"❌ Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


def create_test_schedule():
    """Create a test schedule for demonstration"""
    schedule = Schedule("test_relay_schedule.json")
    schedule.clear_schedule()

    print("🔧 Creating test relay schedule...")

    # Create a simple test pattern
    schedule.add_relay_on(1.0, 1)  # Relay 1 ON at 1s
    schedule.add_relay_off(3.0, 1)  # Relay 1 OFF at 3s
    schedule.add_relay_pulse(5.0, 2, duration=0.5)  # Relay 2 pulse at 5s
    schedule.add_relay_on(8.0, 3)  # Relay 3 ON at 8s
    schedule.add_relay_on(8.0, 4)  # Relay 4 ON at 8s (simultaneous)
    schedule.add_relay_off(10.0, 3)  # Relay 3 OFF at 10s
    schedule.add_relay_off(12.0, 4)  # Relay 4 OFF at 12s

    schedule.save_schedule()
    print(f"✅ Created test schedule: {schedule.schedule_file}")
    print("📋 Test schedule contents:")
    schedule.print_schedule()

    return str(schedule.schedule_file)


def main():
    parser = argparse.ArgumentParser(description="KitchenSync MIDI Schedule Tools")
    parser.add_argument(
        "command",
        choices=["convert-to-json", "convert-to-midi", "inspect", "create-test"],
        help="Command to execute",
    )
    parser.add_argument("input_file", nargs="?", help="Input file path")
    parser.add_argument("-o", "--output", help="Output file path")

    args = parser.parse_args()

    if args.command == "create-test":
        create_test_schedule()
        return

    if not args.input_file:
        print("❌ Input file required for this command")
        parser.print_help()
        return

    if args.command == "convert-to-json":
        convert_to_json(args.input_file, args.output)
    elif args.command == "convert-to-midi":
        convert_to_midi(args.input_file, args.output)
    elif args.command == "inspect":
        inspect_file(args.input_file)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("🎼 KitchenSync MIDI Schedule Tools")
        print("=" * 40)
        print("Usage examples:")
        print("  python3 midi_tools.py create-test")
        print("  python3 midi_tools.py inspect schedule.json")
        print("  python3 midi_tools.py convert-to-midi schedule.json")
        print("  python3 midi_tools.py convert-to-json schedule.mid")
        print("")
        print("This tool demonstrates both JSON and MIDI file support.")
        print("Note: MIDI file support requires 'mido' library (pip install mido)")
    else:
        main()
