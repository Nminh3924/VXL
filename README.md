# ESP32 Physiological Signal Acquisition System

Hệ thống thu thập **đồng thời** tín hiệu sinh lý sử dụng ESP32 Dev Kit V1:
- **AD8232** - ECG (Điện tâm đồ)
- **MAX30102** - PPG (SpO2 và nhịp tim)
- **INMP441** - Microphone I2S (PCG / Tiếng tim)

## Kiến trúc phần mềm

Firmware sử dụng **FreeRTOS** để thu thập dữ liệu song song:

| Tín hiệu | Phương thức | Core | Tốc độ lấy mẫu | Tốc độ output |
|----------|-------------|------|----------------|---------------|
| **ECG** | Timer ISR | 1 | 1000 Hz | ~1000 Hz |
| **PPG** | FreeRTOS Task | 0 | 1600 Hz (sensor) | ~40 Hz (sau avg) |
| **Audio** | FreeRTOS Task | 0 | 16000 Hz (I2S) | ~100 Hz (sau avg) |

### Luồng dữ liệu
1. **ECG**: Timer interrupt đọc ADC → Ring Buffer → Main loop xuất Serial
2. **PPG**: Task đọc MAX30102 → Queue → Main loop xuất Serial
3. **Audio**: Task đọc I2S → Trung bình hóa → Queue → Main loop xuất Serial

## Kết nối phần cứng

### AD8232 (ECG)
| AD8232 | ESP32 |
|--------|-------|
| OUTPUT | GPIO36 |
| LO+ | GPIO25 |
| LO- | GPIO26 |
| 3.3V | 3.3V |
| GND | GND |

### MAX30102 (PPG - I2C)
| MAX30102 | ESP32 |
|----------|-------|
| SDA | GPIO21 |
| SCL | GPIO22 |
| 3.3V | 3.3V |
| GND | GND |

### INMP441 (Microphone - I2S)
| INMP441 | ESP32 |
|---------|-------|
| WS | GPIO32 |
| SCK | GPIO33 |
| SD | GPIO35 |
| VDD | 3.3V |
| GND | GND |
| L/R | GND (Left) hoặc 3.3V (Right) |

## Cách sử dụng

### 1. Build và Upload
```bash
pio run -t upload
```

### 2. Thu thập dữ liệu
```bash
python serial_logger.py
```
- Chọn cổng COM
- Bấm **ENTER** để bắt đầu đo (3 phút)
- Dữ liệu lưu vào `data_logs/serial_log_*.txt`

### 3. Xử lý và vẽ đồ thị
```bash
python process_signals.py data_logs/serial_log_XXXXXXXX_XXXXXX.txt
```
- Kết quả: `processed_data/result_*.png`

## Định dạng Output (Teleplot compatible)
```
>ecg_raw:value
>ppg_ir_raw:value
>ppg_red_raw:value
>audio_raw:value
>runtime_sec:seconds
```

## Cấu hình

### Firmware (`src/main.cpp`)
```cpp
#define SERIAL_BAUD 460800          // Baud rate
#define SAMPLE_DURATION_MS 180000   // 3 phút
```

### Logger (`serial_logger.py`)
```python
BAUD_RATE = 460800
```

## Cấu trúc thư mục
```
VXL_20251/
├── src/main.cpp           # Firmware chính
├── include/config.h       # Cấu hình GPIO
├── serial_logger.py       # Ghi dữ liệu từ Serial
├── process_signals.py     # Xử lý tín hiệu & vẽ đồ thị
├── data_logs/             # File log thô
└── processed_data/        # Ảnh kết quả
```

## Xử lý tín hiệu (Python)

| Tín hiệu | Xử lý |
|----------|-------|
| **ECG** | Notch 50Hz → Bandpass 0.5-40Hz → Wavelet db6 → R-peak detection |
| **PPG** | Invert → Bandpass 0.5-5Hz → Wavelet sym8 |
| **Audio** | Bandpass 25-400Hz |

## Lưu ý
- ECG hiển thị 4095 liên tục = Điện cực chưa tiếp xúc tốt (Lead-Off)
- PPG = 0 = Ngón tay chưa đặt đúng vị trí
- Audio cần môi trường yên tĩnh để thu tiếng tim rõ
