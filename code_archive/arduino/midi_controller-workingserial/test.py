import serial

import serial
import time

# Update this to your Arduino's serial port (e.g., '/dev/tty.usbmodemXXXX' or '/dev/ttyUSB0')
SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 115200  # Serial baud rate for USB communication


def send_note_on(ser, channel=1, pitch=60, velocity=100):
    cmd = f"noteon {channel} {pitch} {velocity}\n"
    ser.write(cmd.encode("utf-8"))
    print(f"Sent: {cmd.strip()}")


def send_note_off(ser, channel=1, pitch=60):
    cmd = f"noteoff {channel} {pitch} 0\n"
    ser.write(cmd.encode("utf-8"))
    print(f"Sent: {cmd.strip()}")


if __name__ == "__main__":
    with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
        time.sleep(2)  # Wait for Arduino to reset
        while True:
            send_note_on(ser)
            time.sleep(5)
            send_note_off(ser)
            time.sleep(5)
        send_note_on(ser)
