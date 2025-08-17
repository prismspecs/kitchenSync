import rtmidi
import time
import sys

midiout = rtmidi.MidiOut()
ports = midiout.get_ports()

print("Available MIDI ports:")
for i, port in enumerate(ports):
    print(f"{i}: {port}")

if len(ports) == 0:
    print("No MIDI ports found!")
    sys.exit(1)

# CHANGE THIS: Don't automatically use port 0!
port_index = int(input("Enter the port number for your Arduino: "))

if port_index >= len(ports):
    print("Invalid port number!")
    sys.exit(1)

print(f"\nUsing port: {ports[port_index]}")
midiout.open_port(port_index)

print("Testing Note 60...")
midiout.send_message([0x90, 60, 127])  # Note On
time.sleep(2)
midiout.send_message([0x80, 60, 0])  # Note Off

print("Testing Note 61...")
midiout.send_message([0x90, 61, 100])  # Note On
time.sleep(2)
midiout.send_message([0x80, 61, 0])  # Note Off

midiout.close_port()
print("Done!")
