/*
 * Cấu hình cho Hệ thống đo tín hiệu sinh lý ESP32
 * Định nghĩa chân GPIO, tốc độ lấy mẫu và kích thước buffer
 */

#ifndef CONFIG_H
#define CONFIG_H

// Tốc độ lấy mẫu (Hz)
#define ECG_SAMPLE_RATE 1000
#define PPG_SAMPLE_RATE 1000
#define AUDIO_SAMPLE_RATE 16000

// Khoảng thời gian lấy mẫu (us)
#define ECG_SAMPLE_INTERVAL_US (1000000 / ECG_SAMPLE_RATE)
#define PPG_SAMPLE_INTERVAL_US (1000000 / PPG_SAMPLE_RATE)

// Cấu hình buffer
#define WAVELET_BUFFER_SIZE 128
#define AUDIO_BUFFER_SIZE 512
#define SERIAL_OUTPUT_DECIMATION 10

// Chân cảm biến AD8232 ECG
#define AD8232_OUTPUT_PIN 36
#define AD8232_LO_PLUS_PIN 25
#define AD8232_LO_MINUS_PIN 26

// Chân cảm biến MAX30102 PPG (I2C)
#define MAX30102_SDA_PIN 21
#define MAX30102_SCL_PIN 22

// Chân micro INMP441 (I2S)
#define INMP441_WS_PIN 32
#define INMP441_SCK_PIN 33
#define INMP441_SD_PIN 35
#define I2S_PORT I2S_NUM_0

// Cấu hình bộ lọc
#define FILTER_SAMPLE_RATE 1000.0f
#define NOTCH_50HZ_FREQ 50.0f
#define NOTCH_100HZ_FREQ 100.0f
#define NOTCH_Q_FACTOR 30.0f
#define BANDPASS_LOW_FREQ 0.5f
#define BANDPASS_HIGH_FREQ 40.0f
#define DC_BLOCKER_ALPHA 0.995f

// Cấu hình wavelet
#define WAVELET_DECOMPOSITION_LEVEL 3
#define WAVELET_THRESHOLD_MULTIPLIER 1.5f

// Cấu hình MAX30102
#define MAX30102_LED_BRIGHTNESS 60
#define MAX30102_SAMPLE_AVERAGE 4
#define MAX30102_LED_MODE 2
#define MAX30102_SAMPLE_RATE 800
#define MAX30102_PULSE_WIDTH 411
#define MAX30102_ADC_RANGE 4096

// Cấu hình Serial
#define SERIAL_BAUD_RATE 115200
#define DISPLAY_INTERVAL_MS 1000

#endif
