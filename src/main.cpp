/**
 * ESP32 Physiological Signal Acquisition System
 *
 * Sensors:
 * - AD8232 (ECG) - 1000Hz sampling
 * - MAX30102 (PPG) - Heart rate and SpO2
 * - INMP441 (Audio) - 16kHz I2S microphone
 *
 * Signal Processing:
 * - DC Blocker
 * - Notch filters (50Hz, 100Hz)
 * - Bandpass filter (1-100Hz)
 * - Haar Wavelet denoising
 *
 * Output: Teleplot compatible format
 */

#include "MAX30105.h"
#include "spo2_algorithm.h"
#include <Arduino.h>
#include <Wire.h>

#include "config.h"
#include "filters.h"
#include "inmp441.h"
#include "wavelet.h"

// ============================================================================
// GLOBAL OBJECTS
// ============================================================================
MAX30105 particleSensor;
INMP441 microphone;

// Filter instances
SignalFilter ecgFilter;
SignalFilter ppgFilter;
AudioFilter audioFilter;

// Wavelet denoiser instances
RealTimeWaveletDenoiser ecgWavelet;
RealTimeWaveletDenoiser ppgWavelet;

// ============================================================================
// TIMING VARIABLES
// ============================================================================
hw_timer_t *ecgTimer = NULL;
volatile bool ecgSampleReady = false;
volatile uint32_t ecgTimestamp = 0;

unsigned long lastDisplayTime = 0;
unsigned long lastAudioTime = 0;
const unsigned long AUDIO_INTERVAL_US = 1000000 / AUDIO_SAMPLE_RATE; // ~62.5us

// ============================================================================
// DATA VARIABLES
// ============================================================================
// ECG
volatile int rawECG = 0;
float filteredECG = 0;
float waveletECG = 0;

// PPG
uint32_t irBuffer[100];
uint32_t redBuffer[100];
int32_t bufferLength = 100;
int32_t spo2Value;
int8_t validSPO2;
int32_t heartRateValue;
int8_t validHeartRate;

float filteredHeartRate = 0;
float filteredSpO2 = 0;
const float SMOOTHING_FACTOR = 0.15f;

bool fingerDetected = false;
int noFingerCount = 0;

// PPG raw for waveform
long rawPPG_IR = 0;
float filteredPPG = 0;
float waveletPPG = 0;

// Sensor initialization flags
bool max30102Initialized = false;

// Audio
int16_t rawAudio = 0;
float filteredAudio = 0;

// Output decimation counter (to avoid Serial overflow)
int outputCounter = 0;

// ============================================================================
// TIMER ISR - 1000Hz sampling for ECG
// ============================================================================
void IRAM_ATTR onEcgTimer() {
  rawECG = analogRead(AD8232_OUTPUT_PIN);
  ecgTimestamp = micros();
  ecgSampleReady = true;
}

// ============================================================================
// SETUP
// ============================================================================
void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(100);

  Serial.println("\n========================================");
  Serial.println("ESP32 Physiological Signal Acquisition");
  Serial.println("========================================");

  // Configure ADC
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  // Configure ECG pins
  pinMode(AD8232_OUTPUT_PIN, INPUT);
  pinMode(AD8232_LO_PLUS_PIN, INPUT);
  pinMode(AD8232_LO_MINUS_PIN, INPUT);

  // Initialize filters
  ecgFilter.init(ECG_SAMPLE_RATE);
  ppgFilter.init(PPG_SAMPLE_RATE);
  audioFilter.init(AUDIO_SAMPLE_RATE);

  Serial.println("[OK] Filters initialized");

  // Initialize I2C for MAX30102
  Wire.begin(MAX30102_SDA_PIN, MAX30102_SCL_PIN);

  // Initialize MAX30102
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("[ERROR] MAX30102 not found!");
    max30102Initialized = false;
  } else {
    particleSensor.setup(MAX30102_LED_BRIGHTNESS, MAX30102_SAMPLE_AVERAGE,
                         MAX30102_LED_MODE, MAX30102_SAMPLE_RATE,
                         MAX30102_PULSE_WIDTH, MAX30102_ADC_RANGE);
    particleSensor.setPulseAmplitudeRed(0x0A);
    particleSensor.setPulseAmplitudeGreen(0);
    max30102Initialized = true;
    Serial.println("[OK] MAX30102 initialized");
  }

  // Initialize INMP441
  if (!microphone.begin()) {
    Serial.println("[WARNING] INMP441 not initialized");
  } else {
    Serial.println("[OK] INMP441 initialized");
  }

  // Setup hardware timer for ECG (1000Hz)
  ecgTimer = timerBegin(0, 80, true); // 80 prescaler = 1MHz
  timerAttachInterrupt(ecgTimer, &onEcgTimer, true);
  timerAlarmWrite(ecgTimer, ECG_SAMPLE_INTERVAL_US, true); // 1000us = 1kHz
  timerAlarmEnable(ecgTimer);

  Serial.println("[OK] Timer started at 1000Hz");
  Serial.println("========================================\n");

  delay(500);
}

// ============================================================================
// ECG PROCESSING
// ============================================================================
void processECG() {
  if (!ecgSampleReady)
    return;
  ecgSampleReady = false;

  // Check lead-off
  bool loPlus = digitalRead(AD8232_LO_PLUS_PIN);
  bool loMinus = digitalRead(AD8232_LO_MINUS_PIN);

  if (loPlus == 1 || loMinus == 1) {
    // Lead off - output zeros
    if (outputCounter % SERIAL_OUTPUT_DECIMATION == 0) {
      Serial.println(">ecg_raw:0");
      Serial.println(">ecg_filtered:0");
      Serial.println(">ecg_wavelet:0");
    }
    return;
  }

  // Apply filters
  float rawFloat = (float)rawECG;
  filteredECG = ecgFilter.process(rawFloat);
  waveletECG = ecgWavelet.process(filteredECG);

  // Output (decimated to avoid Serial overflow)
  if (outputCounter % SERIAL_OUTPUT_DECIMATION == 0) {
    Serial.print(">ecg_raw:");
    Serial.println(rawECG);

    Serial.print(">ecg_filtered:");
    Serial.println(filteredECG, 2);

    Serial.print(">ecg_wavelet:");
    Serial.println(waveletECG, 2);
  }
}

// ============================================================================
// PPG PROCESSING (SpO2 and Heart Rate)
// ============================================================================
void processPPG() {
  // Skip if MAX30102 not initialized
  if (!max30102Initialized)
    return;

  static int sampleCount = 0;
  static bool isCollecting = false;
  static unsigned long lastPPGSample = 0;

  // Rate limit PPG sampling
  if (micros() - lastPPGSample < PPG_SAMPLE_INTERVAL_US)
    return;
  lastPPGSample = micros();

  long irValue = particleSensor.getIR();
  long redValue = particleSensor.getRed();

  // Store raw PPG for waveform display
  rawPPG_IR = irValue;

  // Apply filters to IR signal for waveform
  float irFloat = (float)(irValue >> 4); // Scale down for filter
  filteredPPG = ppgFilter.process(irFloat);
  waveletPPG = ppgWavelet.process(filteredPPG);

  // Output PPG waveform (decimated)
  if (outputCounter % SERIAL_OUTPUT_DECIMATION == 0) {
    Serial.print(">ppg_ir_raw:");
    Serial.println(irValue);

    Serial.print(">ppg_ir_filtered:");
    Serial.println(filteredPPG, 2);

    Serial.print(">ppg_ir_wavelet:");
    Serial.println(waveletPPG, 2);
  }

  // Finger detection
  if (irValue < 50000) {
    fingerDetected = false;
    noFingerCount++;

    if (noFingerCount > 10) {
      isCollecting = false;
      sampleCount = 0;
    }
    return;
  }

  fingerDetected = true;
  noFingerCount = 0;

  // Collect samples for SpO2/HR calculation
  if (!isCollecting) {
    sampleCount = 0;
    isCollecting = true;
  }

  if (sampleCount < bufferLength) {
    redBuffer[sampleCount] = redValue;
    irBuffer[sampleCount] = irValue;
    sampleCount++;
  } else {
    // Calculate SpO2 and Heart Rate
    maxim_heart_rate_and_oxygen_saturation(irBuffer, bufferLength, redBuffer,
                                           &spo2Value, &validSPO2,
                                           &heartRateValue, &validHeartRate);

    if (validHeartRate == 1 && heartRateValue > 40 && heartRateValue < 200) {
      filteredHeartRate = filteredHeartRate * (1 - SMOOTHING_FACTOR) +
                          heartRateValue * SMOOTHING_FACTOR;
    }

    if (validSPO2 == 1 && spo2Value > 70 && spo2Value <= 100) {
      filteredSpO2 =
          filteredSpO2 * (1 - SMOOTHING_FACTOR) + spo2Value * SMOOTHING_FACTOR;
    }

    // Shift buffer
    for (int i = 25; i < bufferLength; i++) {
      redBuffer[i - 25] = redBuffer[i];
      irBuffer[i - 25] = irBuffer[i];
    }
    sampleCount = 75;
  }
}

// ============================================================================
// AUDIO PROCESSING
// ============================================================================
void processAudio() {
  if (!microphone.isInitialized())
    return;

  // Read audio sample
  rawAudio = microphone.readSample();

  // Apply filter
  filteredAudio = audioFilter.process((float)rawAudio);

  // Output (heavily decimated for audio due to high sample rate)
  static int audioOutputCounter = 0;
  audioOutputCounter++;

  if (audioOutputCounter >= 160) { // Output at ~100Hz for visualization
    audioOutputCounter = 0;

    Serial.print(">audio_raw:");
    Serial.println(rawAudio);

    Serial.print(">audio_filtered:");
    Serial.println(filteredAudio, 1);
  }
}

// ============================================================================
// DISPLAY HR/SPO2 VALUES
// ============================================================================
void displayValues() {
  unsigned long currentTime = millis();

  if (currentTime - lastDisplayTime >= DISPLAY_INTERVAL_MS) {
    lastDisplayTime = currentTime;

    if (fingerDetected) {
      Serial.print(">heartrate:");
      Serial.println(filteredHeartRate, 1);

      Serial.print(">spo2:");
      Serial.println(filteredSpO2, 1);
    } else {
      Serial.println(">heartrate:0");
      Serial.println(">spo2:0");
    }

    // Debug info
    Serial.print(">finger_detected:");
    Serial.println(fingerDetected ? 1 : 0);
  }
}

// ============================================================================
// MAIN LOOP
// ============================================================================
void loop() {
  // Process ECG (timer interrupt driven)
  processECG();

  // Process PPG
  processPPG();

  // Process Audio (in main loop for simplicity)
  // Note: For better performance, consider using I2S interrupt
  processAudio();

  // Display HR/SpO2 values periodically
  displayValues();

  // Increment output counter
  outputCounter++;
  if (outputCounter >= 10000)
    outputCounter = 0;
}