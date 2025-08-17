#include <Arduino.h>
#include <Adafruit_PWMServoDriver.h>
#include <MIDI.h>
#include <Wire.h>
#include <SoftwareSerial.h>

// --- Configuration ---
const uint16_t PWM_FREQ = 200;
const uint8_t MIDI_BASE_NOTE = 60;      // C4 is mapped to the first PWM channel
const uint32_t MIDI_IDLE_OFF_MS = 5000; // Turn off a channel after 5 sec of inactivity
const uint32_t SERIAL_BAUD = 9600;    // Use common high-speed baud rate

// --- Pins ---
const uint8_t PIN_LED_HEARTBEAT = 13;
const uint8_t PIN_LED_ACTIVITY = 12;

// --- Globals ---
const uint8_t CHANS_LEN = 16;
uint32_t chans_last_trig_ms[CHANS_LEN];
uint32_t last_input_rx_ms = 0;
String serial_buffer = "";

// --- Objects ---
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();
SoftwareSerial midiSerial(2, 3); // RX=2, TX=3 for MIDI
MIDI_CREATE_INSTANCE(SoftwareSerial, midiSerial, MIDI);

// --- Forward Declarations ---
void on_midi_note_on(byte channel, byte pitch, byte velocity);
void on_midi_note_off(byte channel, byte pitch, byte velocity);
void pwm_set_from_pitch(byte pitch, byte velocity);
void process_serial_input();
void parse_serial_command(String command);

void setup() {
  pinMode(PIN_LED_HEARTBEAT, OUTPUT);
  pinMode(PIN_LED_ACTIVITY, OUTPUT);
  
  Serial.begin(SERIAL_BAUD);
  serial_buffer.reserve(64); // Pre-allocate memory for the string
  Serial.println("System Initialized. Waiting for input...");
  
  // MIDI on SoftwareSerial (pins 2,3) - Serial free for debugging
  MIDI.begin(MIDI_CHANNEL_OMNI);
  MIDI.setHandleNoteOn(on_midi_note_on);
  MIDI.setHandleNoteOff(on_midi_note_off);
  
  pwm.begin();
  pwm.setPWMFreq(PWM_FREQ);
  // Removed fast I2C mode - using default speed for reliability
  
  // Initialize all channels to off and reset timers
  for (uint8_t i = 0; i < CHANS_LEN; i++) {
    pwm.setPWM(i, 0, 0);
    chans_last_trig_ms[i] = millis();
  }
  
  // Test PWM immediately after initialization
  Serial.println("Testing PWM channel 0...");
  pwm.setPWM(0, 0, 4000);
  delay(1000);
  pwm.setPWM(0, 0, 0);
  Serial.println("PWM test complete - ready for commands");
  Serial.println("Try: 'noteon 0 60 127' or simple format '60 127'");
}

void loop() {
  // Blink LEDs for status
  digitalWrite(PIN_LED_HEARTBEAT, millis() % 2000 > 1000);
  digitalWrite(PIN_LED_ACTIVITY, millis() - last_input_rx_ms < 50);
  
  // Process incoming MIDI (on pins 2,3) and Serial messages
  MIDI.read();
  process_serial_input();
  
  // Automatically turn off channels that have been idle for too long
  uint32_t ms = millis();
  for (uint8_t i = 0; i < CHANS_LEN; i++) {
    if (chans_last_trig_ms[i] != 0 && (ms - chans_last_trig_ms[i] > MIDI_IDLE_OFF_MS)) {
      pwm.setPWM(i, 0, 0);
      chans_last_trig_ms[i] = 0; // Mark as off to prevent re-sending
    }
  }
}

// --- MIDI Callback Functions ---
void on_midi_note_on(byte channel, byte pitch, byte velocity) {
  pwm_set_from_pitch(pitch, velocity);
}

void on_midi_note_off(byte channel, byte pitch, byte velocity) {
  pwm_set_from_pitch(pitch, 0);
}

// --- Core Logic ---
void pwm_set_from_pitch(byte pitch, byte velocity) {
  last_input_rx_ms = millis(); // Update activity timer
  
  // Map MIDI pitch to a PWM channel (0-15)
  int8_t chan = pitch - MIDI_BASE_NOTE;
  if (chan < 0 || chan >= CHANS_LEN) {
    Serial.print("Pitch "); Serial.print(pitch); 
    Serial.println(" is outside channel range (60-75)");
    return; // Ignore notes outside our target range
  }
  
  // Convert MIDI velocity (0-127) to PWM value (0-4095)
  // Multiplying by 32 maps 127 to 4064, which is safely within the 12-bit range.
  uint16_t pwr = velocity * 32;
  
  // Send the command to the PWM driver
  pwm.setPWM(chan, 0, pwr);
  
  // Update the idle timer for this channel
  if (velocity > 0) {
    chans_last_trig_ms[chan] = millis();
  } else {
    chans_last_trig_ms[chan] = 0; // Mark as off immediately
  }
  
  // --- DEBUGGING ---
  Serial.print("Set PWM Chan: "); Serial.print(chan);
  Serial.print(" from Pitch: "); Serial.print(pitch);
  Serial.print(" | Power: "); Serial.println(pwr);
}

// --- Serial Input Handling ---
void process_serial_input() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (serial_buffer.length() > 0) {
        parse_serial_command(serial_buffer);
        serial_buffer = ""; // Clear buffer for next command
      }
    } else {
      serial_buffer += c;
    }
  }
}

void parse_serial_command(String command) {
  command.trim();
  command.toLowerCase();
  
  // --- DEBUGGING ---
  Serial.print("Received Serial Command: '"); Serial.print(command); Serial.println("'");
  
  // Check for simple format first: "60 127" (pitch velocity)
  int spaceIndex = command.indexOf(' ');
  if (spaceIndex > 0 && command.indexOf(' ', spaceIndex + 1) == -1) {
    // Simple two-parameter format
    byte pitch = command.substring(0, spaceIndex).toInt();
    byte velocity = command.substring(spaceIndex + 1).toInt();
    Serial.print("Simple format - pitch: "); Serial.print(pitch);
    Serial.print(" velocity: "); Serial.println(velocity);
    pwm_set_from_pitch(pitch, velocity);
    return;
  }
  
  // Split the command string into parts for full format
  String parts[4];
  int partIndex = 0;
  int lastSpace = -1;
  
  for (int i = 0; i < command.length() && partIndex < 4; i++) {
    if (command.charAt(i) == ' ') {
      parts[partIndex++] = command.substring(lastSpace + 1, i);
      lastSpace = i;
    }
  }
  parts[partIndex] = command.substring(lastSpace + 1);
  
  // Fixed: Check for minimum required parts
  if (partIndex < 3) {
    Serial.println("Error: Invalid command format.");
    Serial.println("Try: 'noteon 0 60 127' or simple '60 127'");
    return;
  }
  
  // parts[0] is command, parts[1] is channel, parts[2] is pitch, parts[3] is velocity
  String cmd_type = parts[0];
  // byte channel = parts[1].toInt(); // Channel is not used in your pwm_set_from_pitch logic
  byte pitch = parts[2].toInt();
  byte velocity = parts[3].toInt();
  
  Serial.print("Full format - cmd: "); Serial.print(cmd_type);
  Serial.print(" pitch: "); Serial.print(pitch);
  Serial.print(" velocity: "); Serial.println(velocity);
  
  if (cmd_type == "noteon") {
    pwm_set_from_pitch(pitch, velocity);
  } else if (cmd_type == "noteoff") {
    pwm_set_from_pitch(pitch, 0);
  } else {
    Serial.println("Error: Unknown command. Use 'noteon' or 'noteoff'");
  }
}