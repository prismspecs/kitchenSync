#include <Arduino.h>
#include <Adafruit_PWMServoDriver.h>
#include <MIDI.h>
#include <Wire.h>

// --- Configuration ---
const uint16_t PWM_FREQ = 200;
const uint8_t MIDI_BASE_NOTE = 60;      // C4 is mapped to the first PWM channel
const uint32_t MIDI_IDLE_OFF_MS = 5000; // Turn off a channel after 5 sec of inactivity

// --- Pins ---
const uint8_t PIN_LED_HEARTBEAT = 13;
const uint8_t PIN_LED_ACTIVITY = 12;

// --- Globals ---
const uint8_t CHANS_LEN = 16;
uint32_t chans_last_trig_ms[CHANS_LEN];
uint32_t last_input_rx_ms = 0;

// --- Objects ---
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();
MIDI_CREATE_DEFAULT_INSTANCE();

// --- Forward Declarations ---
void on_midi_note_on(byte channel, byte pitch, byte velocity);
void on_midi_note_off(byte channel, byte pitch, byte velocity);
void pwm_set_from_pitch(byte pitch, byte velocity);

void setup() {
  pinMode(PIN_LED_HEARTBEAT, OUTPUT);
  pinMode(PIN_LED_ACTIVITY, OUTPUT);
  
  // Initialize MIDI
  MIDI.begin(MIDI_CHANNEL_OMNI);
  MIDI.setHandleNoteOn(on_midi_note_on);
  MIDI.setHandleNoteOff(on_midi_note_off);
  
  // Initialize PWM driver
  pwm.begin();
  pwm.setPWMFreq(PWM_FREQ);
  
  // Initialize all channels to off and reset timers
  for (uint8_t i = 0; i < CHANS_LEN; i++) {
    pwm.setPWM(i, 0, 0);
    chans_last_trig_ms[i] = millis();
  }
  
  // Flash both LEDs to indicate ready
  digitalWrite(PIN_LED_HEARTBEAT, HIGH);
  digitalWrite(PIN_LED_ACTIVITY, HIGH);
  delay(500);
  digitalWrite(PIN_LED_HEARTBEAT, LOW);
  digitalWrite(PIN_LED_ACTIVITY, LOW);
}

void loop() {
  // Heartbeat LED - always blinking to show system is alive
  digitalWrite(PIN_LED_HEARTBEAT, millis() % 2000 > 1000);
  
  // Activity LED - blinks when MIDI received
  digitalWrite(PIN_LED_ACTIVITY, millis() - last_input_rx_ms < 100);
  
  // Process incoming MIDI messages
  MIDI.read();
  
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
    return; // Ignore notes outside our target range (60-75)
  }
  
  // Convert MIDI velocity (0-127) to PWM value (0-4095)
  uint16_t pwr = velocity * 32;
  
  // Send the command to the PWM driver
  pwm.setPWM(chan, 0, pwr);
  
  // Update the idle timer for this channel
  if (velocity > 0) {
    chans_last_trig_ms[chan] = millis();
  } else {
    chans_last_trig_ms[chan] = 0; // Mark as off immediately
  }
}