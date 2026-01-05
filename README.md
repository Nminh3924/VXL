# ESP32 Physiological Signal Acquisition System

Hệ thống thu thập tín hiệu sinh lý sử dụng ESP32 Dev Kit V1 với các cảm biến:
- **AD8232** - ECG (Điện tâm đồ)
- **MAX30102** - PPG (SpO2 và nhịp tim)
- **INMP441** - Microphone I2S

## Tính năng

### Lấy mẫu
- ECG: 1000Hz (timer interrupt)
- PPG: 1000Hz
- Audio: 16000Hz (I2S)

### Xử lý tín hiệu
- **DC Blocker**: Loại bỏ DC offset
- **Notch 50Hz + 100Hz**: Loại nhiễu điện lưới (IIR, Q=30)
- **Bandpass [1-100Hz]**: Butterworth 2nd order
- **Wavelet Denoising**: Haar wavelet với soft thresholding

### Output (Teleplot compatible)
```
>ecg_raw:value
>ecg_filtered:value
>ecg_wavelet:value
>ppg_ir_raw:value
>ppg_ir_filtered:value
>ppg_ir_wavelet:value
>audio_raw:value
>audio_filtered:value
>heartrate:value
>spo2:value
```

## Kết nối phần cứng

### AD8232 (ECG)
| AD8232 Pin | ESP32 Pin |
|------------|-----------|
| OUTPUT     | GPIO36    |
| LO+        | GPIO25    |
| LO-        | GPIO26    |
| 3.3V       | 3.3V      |
| GND        | GND       |

### MAX30102 (PPG)
| MAX30102 Pin | ESP32 Pin |
|--------------|-----------|
| SDA          | GPIO21    |
| SCL          | GPIO22    |
| 3.3V         | 3.3V      |
| GND          | GND       |

### INMP441 (Microphone)
| INMP441 Pin | ESP32 Pin |
|-------------|-----------|
| WS          | GPIO32    |
| SCK         | GPIO33    |
| SD          | GPIO35    |
| VDD         | 3.3V      |
| GND         | GND       |
| L/R         | GND (Left channel) |

## Cách sử dụng

### 1. Build và Upload
```bash
# Build
pio run

# Upload
pio run --target upload
```

### 2. Mở Serial Monitor
```bash
pio device monitor
```
Hoặc sử dụng **Teleplot** extension trong VSCode để vẽ biểu đồ real-time.

### 3. Teleplot Setup
1. Cài extension "Teleplot" trong VSCode
2. Baud rate: **115200**
3. Kết nối ESP32 và mở Teleplot
4. Các kênh sẽ tự động hiển thị

## Cấu trúc file

```
include/
├── config.h      # GPIO pins, sampling rates, filter params
├── filters.h     # IIR filters (Notch, Bandpass, DC Blocker)
├── wavelet.h     # Haar wavelet denoising
└── inmp441.h     # I2S microphone driver

src/
└── main.cpp      # Main application
```

## Thay đổi cấu hình

Chỉnh sửa file `include/config.h`:

```cpp
// Sampling rates
#define ECG_SAMPLE_RATE     1000    // Hz
#define PPG_SAMPLE_RATE     1000    // Hz
#define AUDIO_SAMPLE_RATE   16000   // Hz

// Filter parameters  
#define NOTCH_Q_FACTOR      30.0f   // Higher = narrower notch
#define BANDPASS_LOW_FREQ   1.0f    // Hz
#define BANDPASS_HIGH_FREQ  100.0f  // Hz

// Wavelet
#define WAVELET_DECOMPOSITION_LEVEL  3
#define WAVELET_THRESHOLD_MULTIPLIER 1.5f
```

