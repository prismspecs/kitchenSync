#!/usr/bin/env python3
"""
Convert a MIDI file (.mid) to KitchenSync schedule.json format.
Usage:
    python3 midi_to_schedule.py input.mid [output.json]
If output.json is not provided, defaults to schedule.json.
"""
import sys
import os
import json
from mido import MidiFile, tick2second


def midi_to_schedule(midi_path):
    mid = MidiFile(midi_path)
    schedule = []
    for msg in mid:
        if msg.type == "note_on":
            schedule.append({"note": msg.note, "velocity": msg.velocity})
        elif msg.type == "note_off":
            schedule.append({"note": msg.note, "velocity": 0})
    # Assign time as event index (1 second per event)
    for i, event in enumerate(schedule):
        event["time"] = float(i)
    return schedule


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 midi_to_schedule.py input.mid [output.json]")
        sys.exit(1)
    midi_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "schedule.json"
    if not os.path.isfile(midi_path):
        print(f"Error: MIDI file '{midi_path}' not found.")
        sys.exit(1)
    schedule = midi_to_schedule(midi_path)
    with open(output_path, "w") as f:
        json.dump(schedule, f, indent=2)
    print(f"Converted {midi_path} to {output_path} with {len(schedule)} events.")


if __name__ == "__main__":
    main()
