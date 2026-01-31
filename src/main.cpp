#include "MAX30105.h" // Sử dụng thư viện MAX3010x của SparkFun
#include "config.h"
#include <Arduino.h>
#include <driver/i2s.h>

// --- OBJECTS ---
MAX30105 ppg;

// --- CONFIGURATION ---
// 3 minutes per phase = 180000 ms
#define SAMPLE_DURATION_MS 180000

// --- STATES ---
enum State {
  STATE_IDLE,
  STATE_ECG_MEASURE,
  STATE_WAIT_PPG,
  STATE_PPG_MEASURE,
  STATE_WAIT_AUDIO,
  STATE_AUDIO_MEASURE,
  STATE_DONE
};

State currentState = STATE_IDLE;
unsigned long phaseStartTime = 0;

// --- I2S CONFIG (INMP441) ---
void initI2S() {
  i2s_config_t i2s_config = {
      .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = 16000, // 16kHz typical for voice/heart sound
      .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
      .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 8,
      .dma_buf_len = 64,
      .use_apll = false,
      .tx_desc_auto_clear = false,
      .fixed_mclk = 0};

  i2s_pin_config_t pin_config = {.bck_io_num = INMP441_SCK_PIN,
                                 .ws_io_num = INMP441_WS_PIN,
                                 .data_out_num = I2S_PIN_NO_CHANGE,
                                 .data_in_num = INMP441_SD_PIN};

  i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pin_config);
  i2s_zero_dma_buffer(I2S_NUM_0);
}

// --- PPG INIT ---
bool initPPG() {
  if (!ppg.begin(Wire, I2C_SPEED_FAST)) {
    return false;
  }
  // Setup: ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth,
  // adcRange Mode 2: Red + IR
  ppg.setup(0x1F, 4, 2, 400, 411, 4096);
  return true;
}

void setup() {
  Serial.begin(921600); // Stable High Speed

  // 1. PIN CONFIG
  pinMode(AD8232_LO_PLUS_PIN, INPUT);
  pinMode(AD8232_LO_MINUS_PIN, INPUT);

  // 2. INIT SENSORS
  // ECG (Analog) - No init needed
  // PPG (I2C)
  if (!initPPG()) {
    Serial.println("# Error: MAX30102 Init Failed!");
  }
  // Audio (I2S)
  initI2S();

  Serial.println("# System Ready. Send 's' or ENTER to start ECG.");
}

void loop() {
  unsigned long now = millis();

  switch (currentState) {
  case STATE_IDLE:
    if (Serial.available() > 0) {
      // Consume all input
      while (Serial.available())
        Serial.read();

      Serial.println("# STARTING PHASE 1: ECG (3 Minutes)");
      currentState = STATE_ECG_MEASURE;
      phaseStartTime = now;
    }
    break;

  case STATE_ECG_MEASURE: {
    // Measure ECG ~ 500Hz
    int ecgVal = analogRead(AD8232_OUTPUT_PIN);
    Serial.print(">ecg_raw:");
    Serial.println(ecgVal);

    // Check Timer
    if (now - phaseStartTime >= SAMPLE_DURATION_MS) {
      Serial.println("# DONE_ECG. PAUSED.");
      Serial.println("# Please adjust sensor for PPG.");
      Serial.println("# Press ENTER to start PHASE 2: PPG.");
      currentState = STATE_WAIT_PPG;
    }
    delay(2); // ~500Hz
  } break;

  case STATE_WAIT_PPG:
    if (Serial.available() > 0) {
      while (Serial.available())
        Serial.read();
      Serial.println("# STARTING PHASE 2: PPG (3 Minutes)");
      currentState = STATE_PPG_MEASURE;
      phaseStartTime = now;
    }
    break;

  case STATE_PPG_MEASURE: {
    ppg.check();
    while (ppg.available()) {
      Serial.print(">ppg_ir_raw:");
      Serial.println(ppg.getIR());
      Serial.print(">ppg_red_raw:");
      Serial.println(ppg.getRed());
      ppg.nextSample();
    }

    if (now - phaseStartTime >= SAMPLE_DURATION_MS) {
      Serial.println("# DONE_PPG. PAUSED.");
      Serial.println("# Please quiet down for AUDIO.");
      Serial.println("# Press ENTER to start PHASE 3: AUDIO.");
      currentState = STATE_WAIT_AUDIO;
    }
  } break;

  case STATE_WAIT_AUDIO:
    if (Serial.available() > 0) {
      while (Serial.available())
        Serial.read();
      Serial.println("# STARTING PHASE 3: AUDIO (3 Minutes)");
      currentState = STATE_AUDIO_MEASURE;
      phaseStartTime = now;
    }
    break;

  case STATE_AUDIO_MEASURE: {
    int32_t sample = 0;
    size_t bytes_read = 0;
    i2s_read(I2S_NUM_0, &sample, 4, &bytes_read, 0); // Non-blocking
    if (bytes_read > 0) {
      Serial.print(">audio_raw:");
      Serial.println(sample >> 14);
    }

    if (now - phaseStartTime >= SAMPLE_DURATION_MS) {
      Serial.println("# DONE_AUDIO. SESSION COMPLETE.");
      currentState = STATE_DONE;
    }
  } break;

  case STATE_DONE:
    // Do nothing
    break;
  }

  // Log runtime roughly every second for FS calculation (Only in active states)
  static unsigned long lastSec = 0;
  if (now - lastSec >= 1000) {
    lastSec = now;
    if (currentState == STATE_ECG_MEASURE ||
        currentState == STATE_PPG_MEASURE ||
        currentState == STATE_AUDIO_MEASURE) {
      Serial.print(">runtime_sec:");
      Serial.println((now - phaseStartTime) / 1000);
    }
  }
}