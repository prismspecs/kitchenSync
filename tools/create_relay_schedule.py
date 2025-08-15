#!/usr/bin/env python3
"""
Relay Schedule Creator - Generate MIDI schedules for relay control
Example script showing how to create relay control schedules programmatically
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.schedule import Schedule
import json


def create_relay_demo_schedule():
    """Create a demonstration relay control schedule"""

    # Create a new schedule
    schedule = Schedule("demo_relay_schedule.json")
    schedule.clear_schedule()

    print("🔧 Creating relay control demonstration schedule...")

    # Example relay control patterns

    # Pattern 1: Sequential relay activation (5s, 10s, 15s, 20s)
    for i in range(1, 5):
        time = i * 5.0
        schedule.add_relay_on(time, relay_channel=i)
        schedule.add_relay_off(time + 2.0, relay_channel=i)  # 2 second duration

    # Pattern 2: Relay pulse at 25 seconds (0.5s duration)
    schedule.add_relay_pulse(25.0, relay_channel=5, duration=0.5)

    # Pattern 3: Multiple relays at once (30s)
    schedule.add_relay_on(30.0, relay_channel=1)
    schedule.add_relay_on(30.0, relay_channel=3)
    schedule.add_relay_on(30.0, relay_channel=5)

    # Turn them off at different times
    schedule.add_relay_off(31.0, relay_channel=1)
    schedule.add_relay_off(32.0, relay_channel=3)
    schedule.add_relay_off(33.0, relay_channel=5)

    # Pattern 4: Rapid sequence (35-40s)
    for i in range(6):
        time = 35.0 + (i * 0.5)  # Every 0.5 seconds
        channel = (i % 4) + 1  # Cycle through channels 1-4
        schedule.add_relay_pulse(time, relay_channel=channel, duration=0.2)

    # Save the schedule
    schedule.save_schedule()

    print(f"\n📋 Generated schedule with {schedule.get_cue_count()} cues:")
    schedule.print_schedule()

    return schedule


def create_custom_schedule():
    """Interactive schedule creation"""

    schedule = Schedule("custom_relay_schedule.json")
    schedule.clear_schedule()

    print("\n🎛️ Custom Relay Schedule Creator")
    print("=" * 40)

    while True:
        print("\nOptions:")
        print("1. Add relay ON")
        print("2. Add relay OFF")
        print("3. Add relay pulse")
        print("4. Show current schedule")
        print("5. Save and exit")
        print("6. Exit without saving")

        choice = input("\nChoice: ").strip()

        if choice == "1":
            try:
                time = float(input("Time (seconds): "))
                channel = int(input("Relay channel (1-16): "))
                schedule.add_relay_on(time, channel)
                print(f"✓ Added relay {channel} ON at {time}s")
            except ValueError:
                print("❌ Invalid input")

        elif choice == "2":
            try:
                time = float(input("Time (seconds): "))
                channel = int(input("Relay channel (1-16): "))
                schedule.add_relay_off(time, channel)
                print(f"✓ Added relay {channel} OFF at {time}s")
            except ValueError:
                print("❌ Invalid input")

        elif choice == "3":
            try:
                time = float(input("Time (seconds): "))
                channel = int(input("Relay channel (1-16): "))
                duration = float(input("Pulse duration (seconds): "))
                schedule.add_relay_pulse(time, channel, duration)
                print(f"✓ Added relay {channel} pulse at {time}s for {duration}s")
            except ValueError:
                print("❌ Invalid input")

        elif choice == "4":
            print(f"\nCurrent schedule ({schedule.get_cue_count()} cues):")
            schedule.print_schedule()

        elif choice == "5":
            schedule.save_schedule()
            print("💾 Schedule saved!")
            break

        elif choice == "6":
            print("🚪 Exiting without saving")
            break

        else:
            print("❌ Invalid choice")


def main():
    """Main menu"""
    print("🎬 KitchenSync Relay Schedule Creator")
    print("=" * 40)
    print("1. Create demonstration schedule")
    print("2. Create custom schedule interactively")
    print("3. Exit")

    choice = input("\nChoice: ").strip()

    if choice == "1":
        create_relay_demo_schedule()
    elif choice == "2":
        create_custom_schedule()
    elif choice == "3":
        print("👋 Goodbye!")
    else:
        print("❌ Invalid choice")


if __name__ == "__main__":
    main()
