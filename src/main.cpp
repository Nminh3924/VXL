#include "MAX30105.h"
#include "config.h"
#include <Arduino.h>
#include <driver/i2s.h>

// --- OBJECTS ---
MAX30105 ppg;

// --- CONFIGURATION ---
// Total measurement time: 30 seconds (adjustable)
#define SAMPLE_DURATION_MS 30000

// --- STATES ---
enum State {
  STATE_IDLE,
  STATE_MEASURING, // Đo tất cả cùng lúc!
  STATE_DONE
};

State currentState = STATE_IDLE;
unsigned long phaseStartTime = 0;

// --- I2S CONFIG (INMP441) ---
void initI2S() {
  i2s_config_t i2s_config = {.mode =
                                 (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
                             .sample_rate = 16000,
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
  // adcRange Mode 2: Red + IR, 100Hz sample rate
  ppg.setup(0x1F, 4, 2, 100, 411, 4096);
  return true;
}

void setup() {
  Serial.begin(115200);

  // PIN CONFIG
  pinMode(AD8232_LO_PLUS_PIN, INPUT);
  pinMode(AD8232_LO_MINUS_PIN, INPUT);

  // INIT SENSORS
  if (!initPPG()) {
    Serial.println("# Error: MAX30102 Init Failed!");
  }
  initI2S();

  Serial.println("# System Ready - SIMULTANEOUS MODE");
  Serial.println(
      "# Send 's' or ENTER to start measuring ECG + PPG + Audio together.");
}

void loop() {
  unsigned long now = millis();

  switch (currentState) {
  case STATE_IDLE:
    if (Serial.available() > 0) {
      while (Serial.available())
        Serial.read();

      Serial.println("# ========================================");
      Serial.println("# STARTING: ECG + PPG + AUDIO (Simultaneous)");
      Serial.print("# Duration: ");
      Serial.print(SAMPLE_DURATION_MS / 1000);
      Serial.println(" seconds");
      Serial.println("# ========================================");

      currentState = STATE_MEASURING;
      phaseStartTime = now;
    }
    break;

  case STATE_MEASURING: {
    // ===== 1. ECG (Analog ~500Hz) =====
    int ecgVal = analogRead(AD8232_OUTPUT_PIN);
    Serial.print(">ecg_raw:");
    Serial.println(ecgVal);

    // ===== 2. PPG (I2C ~100Hz) =====
    ppg.check();
    if (ppg.available()) {
      Serial.print(">ppg_ir_raw:");
      Serial.println(ppg.getIR());
      Serial.print(">ppg_red_raw:");
      Serial.println(ppg.getRed());
      ppg.nextSample();
    }

    // ===== 3. Audio (I2S ~16kHz) =====
    int32_t audioSample = 0;
    size_t bytes_read = 0;
    i2s_read(I2S_NUM_0, &audioSample, 4, &bytes_read, 0);
    if (bytes_read > 0) {
      Serial.print(">audio_raw:");
      Serial.println(audioSample >> 14);
    }

    // Check if done
    if (now - phaseStartTime >= SAMPLE_DURATION_MS) {
      Serial.println("# ========================================");
      Serial.println("# MEASUREMENT COMPLETE!");
      Serial.println("# ========================================");
      currentState = STATE_DONE;
    }

    // Small delay to control loop rate (~500Hz for ECG)
    delay(2);
  } break;

  case STATE_DONE:
    // Nothing - measurement finished
    break;
  }

  // Log runtime every second for FS calculation
  static unsigned long lastSec = 0;
  if (now - lastSec >= 1000 && currentState == STATE_MEASURING) {
    lastSec = now;
    Serial.print(">runtime_sec:");
    Serial.println((now - phaseStartTime) / 1000);
  }
}