/**
 * @file inmp441.h
 * @brief INMP441 I2S MEMS Microphone Driver for ESP32
 *
 * Configures I2S peripheral for audio acquisition from INMP441.
 * Provides non-blocking read functionality.
 */

#ifndef INMP441_H
#define INMP441_H

#include "config.h"
#include <Arduino.h>
#include <driver/i2s.h>


class INMP441 {
private:
  bool initialized;
  int32_t rawBuffer[AUDIO_BUFFER_SIZE];

public:
  INMP441() : initialized(false) {}

  bool begin() {
    // I2S configuration for INMP441
    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate = AUDIO_SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 4,
        .dma_buf_len = AUDIO_BUFFER_SIZE,
        .use_apll = false,
        .tx_desc_auto_clear = false,
        .fixed_mclk = 0};

    // I2S pin configuration
    i2s_pin_config_t pin_config = {.bck_io_num = INMP441_SCK_PIN,
                                   .ws_io_num = INMP441_WS_PIN,
                                   .data_out_num = I2S_PIN_NO_CHANGE,
                                   .data_in_num = INMP441_SD_PIN};

    // Install I2S driver
    esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
    if (err != ESP_OK) {
      Serial.printf("ERROR: I2S driver install failed: %d\n", err);
      return false;
    }

    // Set I2S pins
    err = i2s_set_pin(I2S_PORT, &pin_config);
    if (err != ESP_OK) {
      Serial.printf("ERROR: I2S set pin failed: %d\n", err);
      i2s_driver_uninstall(I2S_PORT);
      return false;
    }

    // Clear DMA buffers
    i2s_zero_dma_buffer(I2S_PORT);

    initialized = true;
    Serial.println("INMP441 initialized successfully");
    return true;
  }

  void end() {
    if (initialized) {
      i2s_driver_uninstall(I2S_PORT);
      initialized = false;
    }
  }

  // Read a single sample (blocking)
  // Returns 16-bit signed value
  int16_t readSample() {
    if (!initialized)
      return 0;

    int32_t sample = 0;
    size_t bytesRead = 0;

    i2s_read(I2S_PORT, &sample, sizeof(sample), &bytesRead, portMAX_DELAY);

    // INMP441 outputs 24-bit data in 32-bit frame, left-aligned
    // Shift right by 14 to get 18-bit value, then by 2 more for 16-bit
    return (int16_t)(sample >> 16);
  }

  // Read multiple samples into buffer (blocking)
  // Returns number of samples read
  int readSamples(int16_t *buffer, int numSamples) {
    if (!initialized)
      return 0;

    size_t bytesRead = 0;
    int samplesToRead = min(numSamples, (int)AUDIO_BUFFER_SIZE);

    esp_err_t err =
        i2s_read(I2S_PORT, rawBuffer, samplesToRead * sizeof(int32_t),
                 &bytesRead, portMAX_DELAY);

    if (err != ESP_OK)
      return 0;

    int samplesRead = bytesRead / sizeof(int32_t);

    // Convert 32-bit to 16-bit
    for (int i = 0; i < samplesRead; i++) {
      buffer[i] = (int16_t)(rawBuffer[i] >> 16);
    }

    return samplesRead;
  }

  // Check if initialized
  bool isInitialized() { return initialized; }
};

#endif // INMP441_H
