import serial
import time

# Update this to your Arduino's serial port (e.g., '/dev/tty.usbmodemXXXX' or '/dev/ttyUSB0')
SERIAL_PORT = "/dev/tty.usbmodem112101"
BAUD_RATE = 31250  # MIDI baud rate


def send_note_on(ser, pitch=60, velocity=127):
    """Send note on command using simple format"""
    cmd = f"{pitch} {velocity}\n"
    ser.write(cmd.encode("utf-8"))
    print(f"Sent: Note ON - Pitch {pitch}, Velocity {velocity}")


def send_note_off(ser, pitch=60):
    """Send note off command using simple format"""
    cmd = f"{pitch} 0\n"
    ser.write(cmd.encode("utf-8"))
    print(f"Sent: Note OFF - Pitch {pitch}")


def send_full_command(ser, command="noteon", channel=0, pitch=60, velocity=127):
    """Send full format command"""
    cmd = f"{command} {channel} {pitch} {velocity}\n"
    ser.write(cmd.encode("utf-8"))
    print(f"Sent: {cmd.strip()}")


if __name__ == "__main__":
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
            print("Connected to Arduino. Starting PWM control...")
            time.sleep(2)  # Wait for Arduino to reset

            # Test different channels and velocities
            while True:
                print("\n--- Testing Pitch 60 (Channel 0) ---")
                send_note_on(ser, pitch=60, velocity=127)  # Full power
                time.sleep(2)

                send_note_off(ser, pitch=60)  # Turn off
                time.sleep(1)

                print("\n--- Testing Pitch 61 (Channel 1) ---")
                send_note_on(ser, pitch=61, velocity=64)  # Half power
                time.sleep(2)

                send_note_off(ser, pitch=61)
                time.sleep(1)

                print("\n--- Testing Multiple Channels ---")
                send_note_on(ser, pitch=60, velocity=100)  # Channel 0
                send_note_on(ser, pitch=62, velocity=80)  # Channel 2
                send_note_on(ser, pitch=64, velocity=60)  # Channel 4
                time.sleep(3)

                # Turn all off
                send_note_off(ser, pitch=60)
                send_note_off(ser, pitch=62)
                send_note_off(ser, pitch=64)
                time.sleep(2)

                print("\n--- Using Full Command Format ---")
                send_full_command(ser, "noteon", 0, 65, 127)  # Channel 5
                time.sleep(2)
                send_full_command(ser, "noteoff", 0, 65, 0)  # Turn off channel 5
                time.sleep(2)

    except serial.SerialException as e:
        print(f"Serial connection error: {e}")
        print("Make sure the Arduino is connected and the port is correct.")
    except KeyboardInterrupt:
        print("\nProgram stopped by user.")
    except Exception as e:
        print(f"Unexpected error: {e}")
