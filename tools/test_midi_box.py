#!/usr/bin/env python3
"""
MIDI Relay Box Test Script
Direct testing of MIDI relay outputs for KitchenSync
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from midi.manager import MidiManager
    print("✓ KitchenSync MIDI manager available")
except ImportError as e:
    print("❌ KitchenSync MIDI manager not available")
    print(f"Import error: {e}")
    print("This script needs to run from the KitchenSync directory")
    print("Falling back to direct MIDI commands...")
    
    # Fallback: direct amidi testing
    import subprocess
    
    def test_with_amidi():
        """Simple fallback testing using amidi commands"""
        print("\n🔧 Using direct amidi commands for testing")
        print("Make sure your MIDI box is connected!")
        
        # Get MIDI port
        port = input("Enter MIDI port (e.g., hw:3,0,0): ").strip()
        if not port:
            port = "hw:3,0,0"
        
        print(f"Testing with port: {port}")
        
        # Test each output
        for output in range(1, 9):
            note_hex = f"{59 + output:02X}"  # Convert to hex
            print(f"\nTesting Output {output} (Note {59 + output}, Hex {note_hex})")
            
            try:
                # Turn ON
                subprocess.run(["amidi", "-p", port, "--send-hex", f"90 {note_hex} 7F"], check=True)
                print(f"  ✓ Output {output} ON")
                time.sleep(1.5)
                
                # Turn OFF  
                subprocess.run(["amidi", "-p", port, "--send-hex", f"80 {note_hex} 00"], check=True)
                print(f"  ✓ Output {output} OFF")
                time.sleep(0.5)
                
            except subprocess.CalledProcessError as e:
                print(f"  ❌ Error testing output {output}: {e}")
            except FileNotFoundError:
                print("  ❌ amidi command not found. Install alsa-utils package.")
                return
        
        print("\n✅ Basic testing completed!")
        
        # Offer manual testing
        print("\nManual testing:")
        print("Commands: 'on X' or 'off X' where X is output 1-8")
        print("Type 'quit' to exit")
        
        while True:
            cmd = input("\nCommand: ").strip().lower()
            if cmd == 'quit':
                break
                
            try:
                parts = cmd.split()
                if len(parts) >= 2:
                    action = parts[0]
                    output = int(parts[1])
                    
                    if 1 <= output <= 8:
                        note_hex = f"{59 + output:02X}"
                        
                        if action == 'on':
                            subprocess.run(["amidi", "-p", port, "--send-hex", f"90 {note_hex} 7F"], check=True)
                            print(f"✓ Output {output} ON")
                        elif action == 'off':
                            subprocess.run(["amidi", "-p", port, "--send-hex", f"80 {note_hex} 00"], check=True)
                            print(f"✓ Output {output} OFF")
                        else:
                            print("Use 'on' or 'off'")
                    else:
                        print("Output must be 1-8")
                else:
                    print("Format: 'on 1' or 'off 1'")
                    
            except Exception as e:
                print(f"Error: {e}")
    
    # Run fallback testing
    test_with_amidi()
    sys.exit(0)
    sys.exit(1)


class MidiBoxTester:
    """Test utility for MIDI relay box"""

    def __init__(self, midi_port: int = 0):
        try:
            self.midi = MidiManager(port=midi_port, use_mock=False)
            print(f"✓ Connected to MIDI port {midi_port}")
        except Exception as e:
            print(f"❌ Failed to connect to MIDI port {midi_port}: {e}")
            print("💡 Try checking 'amidi -l' for available ports")
            sys.exit(1)

    def test_output(self, output_num: int, velocity: int = 127, duration: float = 2.0):
        """Test a single output"""
        if not (1 <= output_num <= 8):
            print(f"❌ Output number must be 1-8, got {output_num}")
            return

        note = 59 + output_num  # Convert to MIDI note (60-67)

        print(
            f"🔧 Testing Output {output_num} (Note {note}) at velocity {velocity} for {duration}s"
        )

        # Turn ON
        self.midi.send_note_on(channel=1, note=note, velocity=velocity)
        print(f"  ✓ Sent Note ON: Output {output_num}")

        # Wait
        time.sleep(duration)

        # Turn OFF
        self.midi.send_note_off(channel=1, note=note)
        print(f"  ✓ Sent Note OFF: Output {output_num}")

    def test_all_outputs(self, duration: float = 1.0):
        """Test all 8 outputs sequentially"""
        print(f"🎯 Testing all outputs sequentially ({duration}s each)")

        for output in range(1, 9):
            self.test_output(output, velocity=127, duration=duration)
            time.sleep(0.5)  # Brief pause between outputs

        print("✅ All outputs tested")

    def test_power_levels(self, output_num: int = 1):
        """Test different power levels on one output"""
        print(f"⚡ Testing power levels on Output {output_num}")

        power_levels = [127, 100, 75, 50, 25]
        note = 59 + output_num

        for power in power_levels:
            print(f"  🔋 Setting power level {power}/127 ({int(power/127*100)}%)")
            self.midi.send_note_on(channel=1, note=note, velocity=power)
            time.sleep(2.0)

        # Turn off
        self.midi.send_note_off(channel=1, note=note)
        print("  ✓ Output turned OFF")

    def test_multiple_outputs(self):
        """Test multiple outputs simultaneously"""
        print("🎪 Testing multiple outputs simultaneously")

        outputs = [1, 3, 5]  # Test outputs 1, 3, and 5

        # Turn all ON
        for output in outputs:
            note = 59 + output
            self.midi.send_note_on(channel=1, note=note, velocity=127)
            print(f"  ✓ Output {output} ON")

        print("  ⏳ Waiting 3 seconds...")
        time.sleep(3.0)

        # Turn all OFF
        for output in outputs:
            note = 59 + output
            self.midi.send_note_off(channel=1, note=note)
            print(f"  ✓ Output {output} OFF")

    def test_timeout_behavior(self, output_num: int = 1):
        """Test the 5-second auto-timeout behavior"""
        print(f"⏰ Testing 5-second timeout on Output {output_num}")
        note = 59 + output_num

        print("  🔧 Sending Note ON...")
        self.midi.send_note_on(channel=1, note=note, velocity=127)

        print("  ⏳ Waiting for 6 seconds (should auto-timeout at 5s)...")
        for i in range(6):
            print(f"    {i+1}s...")
            time.sleep(1.0)

        print("  ✓ If timeout works, output should now be OFF")
        print("  💡 Send a Note OFF to be sure:")
        self.midi.send_note_off(channel=1, note=note)

    def test_keepalive(self, output_num: int = 1):
        """Test keepalive messages for long events"""
        print(f"💓 Testing keepalive behavior on Output {output_num}")
        note = 59 + output_num

        print("  🔧 Starting long event with keepalives...")
        self.midi.send_note_on(channel=1, note=note, velocity=127)

        # Send keepalives every 4 seconds for 12 seconds total
        for i in range(3):
            print(f"  ⏳ Waiting 4 seconds... (keepalive {i+1}/3)")
            time.sleep(4.0)
            self.midi.send_note_on(channel=1, note=note, velocity=127)
            print(f"  💓 Sent keepalive {i+1}")

        print("  ⏳ Waiting 2 more seconds, then turning OFF...")
        time.sleep(2.0)
        self.midi.send_note_off(channel=1, note=note)
        print("  ✓ Long event completed (14 seconds total)")

    def interactive_test(self):
        """Interactive testing menu"""
        while True:
            print("\n" + "=" * 50)
            print("🎛️  MIDI Relay Box Interactive Tester")
            print("=" * 50)
            print("1. Test single output")
            print("2. Test all outputs sequentially")
            print("3. Test power levels")
            print("4. Test multiple outputs simultaneously")
            print("5. Test 5-second timeout behavior")
            print("6. Test keepalive for long events")
            print("7. Manual note control")
            print("8. Exit")

            choice = input("\nChoice (1-8): ").strip()

            if choice == "1":
                output = int(input("Output number (1-8): "))
                velocity = int(input("Velocity (1-127): ") or "127")
                duration = float(input("Duration (seconds): ") or "2.0")
                self.test_output(output, velocity, duration)

            elif choice == "2":
                duration = float(input("Duration per output (seconds): ") or "1.0")
                self.test_all_outputs(duration)

            elif choice == "3":
                output = int(input("Output number (1-8): ") or "1")
                self.test_power_levels(output)

            elif choice == "4":
                self.test_multiple_outputs()

            elif choice == "5":
                output = int(input("Output number (1-8): ") or "1")
                self.test_timeout_behavior(output)

            elif choice == "6":
                output = int(input("Output number (1-8): ") or "1")
                self.test_keepalive(output)

            elif choice == "7":
                print("Manual note control (enter 'quit' to return)")
                while True:
                    cmd = input("Command (on/off output# velocity): ").strip().lower()
                    if cmd == "quit":
                        break
                    try:
                        parts = cmd.split()
                        if len(parts) >= 2:
                            action = parts[0]
                            output = int(parts[1])
                            velocity = int(parts[2]) if len(parts) > 2 else 127
                            note = 59 + output

                            if action == "on":
                                self.midi.send_note_on(1, note, velocity)
                                print(f"✓ Output {output} ON (velocity {velocity})")
                            elif action == "off":
                                self.midi.send_note_off(1, note)
                                print(f"✓ Output {output} OFF")
                    except:
                        print("Format: 'on 1 127' or 'off 1'")

            elif choice == "8":
                print("👋 Goodbye!")
                break

            else:
                print("❌ Invalid choice")


def main():
    print("🎬 KitchenSync MIDI Relay Box Tester")
    print("=" * 40)

    # Ask for MIDI port (default 0)
    try:
        port_input = input("MIDI port number (default 0): ").strip()
        midi_port = int(port_input) if port_input else 0
    except ValueError:
        midi_port = 0

    # Create tester
    tester = MidiBoxTester(midi_port)

    # Ask for test mode
    print("\nTest modes:")
    print("1. Quick test (all outputs)")
    print("2. Interactive mode")

    mode = input("Mode (1 or 2): ").strip()

    if mode == "1":
        tester.test_all_outputs(duration=1.5)
        print("\n✅ Quick test completed!")
    else:
        tester.interactive_test()


if __name__ == "__main__":
    main()
