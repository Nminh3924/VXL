/*
 * ESP32 Raw Signal Collector
 * Chỉ thu thập dữ liệu thô từ: AD8232 (ECG), MAX30102 (PPG)
 * Output: Định dạng Teleplot (raw data only)
 * Lọc và xử lý tín hiệu sẽ thực hiện bằng Python
 *
 * TẦN SỐ: ECG 1000Hz sampling, PPG 1000Hz, Output 500Hz
 */

#include "MAX30105.h"
#include "config.h"
#include <Arduino.h>
#include <Wire.h>

// Đối tượng cảm biến
MAX30105 particleSensor;

// Timer cho ECG
hw_timer_t *ecgTimer = NULL;
volatile bool ecgSampleReady = false;
volatile int rawECG = 0;

// Dữ liệu PPG
long rawPPG_IR = 0;
long rawPPG_Red = 0;
bool max30102Initialized = false;

// Bộ đếm output
int outputCounter = 0;
unsigned long startTime = 0;
unsigned long lastDisplayTime = 0;

// Tần số cấu hình
#define ECG_SAMPLE_RATE 1000 // Hz - tần số lấy mẫu ECG
#define PPG_SAMPLE_RATE 1000 // Hz - tần số lấy mẫu PPG
#define OUTPUT_RATE 500      // Hz - tần số output ra serial
#define ECG_DECIMATION (ECG_SAMPLE_RATE / OUTPUT_RATE) // = 2
#define PPG_INTERVAL_US (1000000 / PPG_SAMPLE_RATE)    // = 1000us

// Timer ISR - Lấy mẫu ECG 1000Hz
void IRAM_ATTR onEcgTimer() {
  rawECG = analogRead(AD8232_OUTPUT_PIN);
  ecgSampleReady = true;
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(100);

  Serial.println("\n========================================");
  Serial.println("ESP32 Raw Signal Collector v2.0");
  Serial.println("ECG: AD8232 @ 1000Hz sampling, 500Hz output");
  Serial.println("PPG: MAX30102 @ 1000Hz sampling, 500Hz output");
  Serial.println("========================================");

  // Cấu hình ADC
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  // Cấu hình chân ECG
  pinMode(AD8232_OUTPUT_PIN, INPUT);
  pinMode(AD8232_LO_PLUS_PIN, INPUT);
  pinMode(AD8232_LO_MINUS_PIN, INPUT);

  // Khởi tạo I2C cho MAX30102
  Wire.begin(MAX30102_SDA_PIN, MAX30102_SCL_PIN);

  // Khởi tạo MAX30102 với cấu hình tối ưu
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("[LOI] Khong tim thay MAX30102!");
    max30102Initialized = false;
  } else {
    // Cấu hình MAX30102 cho 1000Hz
    byte ledBrightness = 0x1F; // 31
    byte sampleAverage = 1;    // Không average để đạt 1000Hz
    byte ledMode = 2;          // Red + IR
    int sampleRate = 1000;     // 1000Hz
    int pulseWidth = 215;      // 215us - cân bằng giữa độ chính xác và tốc độ
    int adcRange = 16384;      // 14-bit ADC

    particleSensor.setup(ledBrightness, sampleAverage, ledMode, sampleRate,
                         pulseWidth, adcRange);
    particleSensor.setPulseAmplitudeRed(0x1F);
    particleSensor.setPulseAmplitudeGreen(0);
    max30102Initialized = true;
    Serial.println("[OK] MAX30102 da khoi tao (14-bit, 1000Hz)");
  }

  // Thiết lập timer cho ECG (1000Hz)
  ecgTimer = timerBegin(0, 80, true); // 80MHz / 80 = 1MHz
  timerAttachInterrupt(ecgTimer, &onEcgTimer, true);
  timerAlarmWrite(ecgTimer, 1000, true); // 1MHz / 1000 = 1000Hz
  timerAlarmEnable(ecgTimer);

  Serial.println("[OK] ECG Timer 1000Hz da bat dau");
  Serial.println("========================================");
  Serial.print("# Output rate: ");
  Serial.print(OUTPUT_RATE);
  Serial.println(" Hz");
  Serial.println("# Format: >sensor:value");
  Serial.println("========================================\n");

  startTime = millis();
  delay(500);
}

// Xử lý ECG - chỉ xuất raw data @ 500Hz output
void processECG() {
  if (!ecgSampleReady)
    return;
  ecgSampleReady = false;

  // Kiểm tra lead-off
  bool loPlus = digitalRead(AD8232_LO_PLUS_PIN);
  bool loMinus = digitalRead(AD8232_LO_MINUS_PIN);

  // Xuất dữ liệu mỗi ECG_DECIMATION lần (1000Hz / 2 = 500Hz output)
  if (outputCounter % ECG_DECIMATION == 0) {
    if (loPlus == 1 || loMinus == 1) {
      // Lead-off - vẫn xuất để biết trạng thái
      Serial.println(">ecg_raw:0");
      Serial.println(">ecg_leadoff:1");
    } else {
      Serial.print(">ecg_raw:");
      Serial.println(rawECG);
    }
  }
}

// Xử lý PPG - chỉ xuất raw data @ 500Hz output
void processPPG() {
  if (!max30102Initialized)
    return;

  // Lấy mẫu với tần số PPG_SAMPLE_RATE (1000Hz)
  static unsigned long lastPPGSample = 0;
  static int ppgCounter = 0;

  if (micros() - lastPPGSample < PPG_INTERVAL_US) // 1000us = 1ms = 1000Hz
    return;
  lastPPGSample = micros();

  rawPPG_IR = particleSensor.getIR();
  rawPPG_Red = particleSensor.getRed();

  // Xuất mỗi 2 lần để đạt 500Hz output
  ppgCounter++;
  if (ppgCounter >= 2) {
    ppgCounter = 0;
    Serial.print(">ppg_ir_raw:");
    Serial.println(rawPPG_IR);
    Serial.print(">ppg_red_raw:");
    Serial.println(rawPPG_Red);
  }
}

// Hiển thị thông tin mỗi giây
void displayStatus() {
  unsigned long currentTime = millis();

  if (currentTime - lastDisplayTime >= 1000) {
    lastDisplayTime = currentTime;

    Serial.print(">runtime_sec:");
    Serial.println((currentTime - startTime) / 1000);
  }
}

void loop() {
  processECG();
  processPPG();
  displayStatus();

  outputCounter++;
  if (outputCounter >= 10000)
    outputCounter = 0;
}