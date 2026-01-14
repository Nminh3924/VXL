/*
 * ESP32 Raw Signal Collector
 * Chỉ thu thập dữ liệu thô từ: AD8232 (ECG), MAX30102 (PPG)
 * Output: Định dạng Teleplot (raw data only)
 * Lọc và xử lý tín hiệu sẽ thực hiện bằng Python
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

// Timer ISR - Lấy mẫu ECG 500Hz (giống code tham khảo)
void IRAM_ATTR onEcgTimer() {
  rawECG = analogRead(AD8232_OUTPUT_PIN);
  ecgSampleReady = true;
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(100);

  Serial.println("\n========================================");
  Serial.println("ESP32 Raw Signal Collector");
  Serial.println("ECG: AD8232 @ 500Hz on GPIO36");
  Serial.println("PPG: MAX30102 @ 100Hz");
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
    // Cấu hình giống code tham khảo
    byte ledBrightness = 0x1F; // 31 - như code tham khảo
    byte sampleAverage = 4;
    byte ledMode = 2;     // Red + IR
    int sampleRate = 400; // 400Hz
    int pulseWidth = 411; // Xung rộng nhất = 18-bit
    int adcRange = 16384; // 16384 = 14-bit ADC

    particleSensor.setup(ledBrightness, sampleAverage, ledMode, sampleRate,
                         pulseWidth, adcRange);
    particleSensor.setPulseAmplitudeRed(0x1F);
    particleSensor.setPulseAmplitudeGreen(0);
    max30102Initialized = true;
    Serial.println("[OK] MAX30102 da khoi tao (14-bit, 400Hz)");
  }

  // Thiết lập timer cho ECG (500Hz như code tham khảo)
  ecgTimer = timerBegin(0, 80, true); // 80MHz / 80 = 1MHz
  timerAttachInterrupt(ecgTimer, &onEcgTimer, true);
  timerAlarmWrite(ecgTimer, 2000, true); // 1MHz / 2000 = 500Hz
  timerAlarmEnable(ecgTimer);

  Serial.println("[OK] ECG Timer 500Hz da bat dau");
  Serial.println("========================================");
  Serial.println("# Format: >sensor:value");
  Serial.println("# ecg_raw, ppg_ir_raw, ppg_red_raw");
  Serial.println("========================================\n");

  startTime = millis();
  delay(500);
}

// Xử lý ECG - chỉ xuất raw data
void processECG() {
  if (!ecgSampleReady)
    return;
  ecgSampleReady = false;

  // Kiểm tra lead-off
  bool loPlus = digitalRead(AD8232_LO_PLUS_PIN);
  bool loMinus = digitalRead(AD8232_LO_MINUS_PIN);

  // Xuất dữ liệu mỗi 5 lần (500Hz / 5 = 100Hz output)
  if (outputCounter % 5 == 0) {
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

// Xử lý PPG - chỉ xuất raw data
void processPPG() {
  if (!max30102Initialized)
    return;

  // Lấy mẫu 100Hz
  static unsigned long lastPPGSample = 0;
  if (micros() - lastPPGSample < 10000) // 10ms = 100Hz
    return;
  lastPPGSample = micros();

  rawPPG_IR = particleSensor.getIR();
  rawPPG_Red = particleSensor.getRed();

  // Xuất raw data
  Serial.print(">ppg_ir_raw:");
  Serial.println(rawPPG_IR);
  Serial.print(">ppg_red_raw:");
  Serial.println(rawPPG_Red);
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