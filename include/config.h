/**
 * @file config.h
 * @brief Configuration file for ESP32 Physiological Signal Acquisition System
 * 
 * Defines GPIO pins, sampling rates, and buffer sizes for:
 * - AD8232 (ECG)
 * - MAX30102 (PPG)
 * - INMP441 (Audio)
 */

#ifndef CONFIG_H
#define CONFIG_H

// ============================================================================
// SAMPLING CONFIGURATION
// ============================================================================
#define ECG_SAMPLE_RATE     1000    // Hz - ECG sampling frequency
#define PPG_SAMPLE_RATE     1000    // Hz - PPG sampling frequency
#define AUDIO_SAMPLE_RATE   16000   // Hz - INMP441 sampling frequency

// Sampling interval in microseconds
#define ECG_SAMPLE_INTERVAL_US   (1000000 / ECG_SAMPLE_RATE)   // 1000us = 1ms
#define PPG_SAMPLE_INTERVAL_US   (1000000 / PPG_SAMPLE_RATE)   // 1000us = 1ms

// ============================================================================
// BUFFER CONFIGURATION
// ============================================================================
#define WAVELET_BUFFER_SIZE     128     // Power of 2 for FFT/wavelet
#define AUDIO_BUFFER_SIZE       512     // I2S DMA buffer size
#define SERIAL_OUTPUT_DECIMATION 10     // Output every Nth sample to avoid Serial overflow

// ============================================================================
// AD8232 ECG SENSOR PINS
// ============================================================================
#define AD8232_OUTPUT_PIN       36      // ADC1_CH0 - Analog output from AD8232
#define AD8232_LO_PLUS_PIN      25      // Lead-off detection +
#define AD8232_LO_MINUS_PIN     26      // Lead-off detection -

// ============================================================================
// MAX30102 PPG SENSOR PINS (I2C)
// ============================================================================
#define MAX30102_SDA_PIN        21      // I2C Data
#define MAX30102_SCL_PIN        22      // I2C Clock

// ============================================================================
// INMP441 MICROPHONE PINS (I2S)
// ============================================================================
#define INMP441_WS_PIN          32      // Word Select (Left/Right Clock)
#define INMP441_SCK_PIN         33      // Serial Clock (Bit Clock)
#define INMP441_SD_PIN          35      // Serial Data (ADC input only)

// I2S Port
#define I2S_PORT                I2S_NUM_0

// ============================================================================
// FILTER CONFIGURATION
// ============================================================================
#define FILTER_SAMPLE_RATE      1000.0f  // Must match ECG/PPG sample rate

// Notch filter parameters
#define NOTCH_50HZ_FREQ         50.0f
#define NOTCH_100HZ_FREQ        100.0f
#define NOTCH_Q_FACTOR          30.0f    // Higher Q = narrower notch

// Bandpass filter parameters
#define BANDPASS_LOW_FREQ       1.0f     // High-pass cutoff
#define BANDPASS_HIGH_FREQ      100.0f   // Low-pass cutoff

// DC Blocker
#define DC_BLOCKER_ALPHA        0.995f

// ============================================================================
// WAVELET CONFIGURATION
// ============================================================================
#define WAVELET_DECOMPOSITION_LEVEL  3   // Number of decomposition levels
#define WAVELET_THRESHOLD_MULTIPLIER 1.5f // Soft threshold multiplier

// ============================================================================
// MAX30102 CONFIGURATION
// ============================================================================
#define MAX30102_LED_BRIGHTNESS     60
#define MAX30102_SAMPLE_AVERAGE     4
#define MAX30102_LED_MODE           2       // Red + IR
#define MAX30102_SAMPLE_RATE        800     // Internal sample rate
#define MAX30102_PULSE_WIDTH        411
#define MAX30102_ADC_RANGE          4096

// ============================================================================
// SERIAL OUTPUT
// ============================================================================
#define SERIAL_BAUD_RATE        500000      // High baud rate for 1000Hz data
#define DISPLAY_INTERVAL_MS     1000        // HR/SpO2 display interval

#endif // CONFIG_H
