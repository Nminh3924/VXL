/*
 * Hệ thống đo tín hiệu sinh lý ESP32
 * Cảm biến: AD8232 (ECG), MAX30102 (PPG), INMP441 (Audio)
 * Output: Định dạng Teleplot
 */

#include "MAX30105.h"
#include "config.h"
#include "filters.h"
#include "inmp441.h"
#include "spo2_custom.h"
#include "wavelet.h"
#include <Arduino.h>
#include <Wire.h>

// Đối tượng cảm biến
MAX30105 particleSensor;
INMP441 microphone;

// Bộ lọc tín hiệu
SignalFilter ecgFilter;
SignalFilter ppgFilter;
AudioFilter audioFilter;

// Bộ khử nhiễu wavelet
RealTimeWaveletDenoiser ecgWavelet;
RealTimeWaveletDenoiser ppgWavelet;

// Timer và biến thời gian
hw_timer_t *ecgTimer = NULL;
volatile bool ecgSampleReady = false;
volatile uint32_t ecgTimestamp = 0;
unsigned long lastDisplayTime = 0;
unsigned long lastAudioTime = 0;
const unsigned long AUDIO_INTERVAL_US = 1000000 / AUDIO_SAMPLE_RATE;

// Dữ liệu ECG
volatile int rawECG = 0;
float filteredECG = 0;
float waveletECG = 0;

// Dữ liệu PPG
SpO2Calculator spo2Calc;
bool fingerDetected = false;
long rawPPG_IR = 0;
float filteredPPG = 0;
float waveletPPG = 0;
bool max30102Initialized = false;

// Dữ liệu Audio
int16_t rawAudio = 0;
float filteredAudio = 0;

// Bộ đếm output
int outputCounter = 0;

// Debug variables
unsigned long startTime = 0;

// Biến xử lý ECG
static int lastValidECG = 2048;
static float lastValidFiltered = 0;
static unsigned long ecgStartTime = 0;
static bool ecgWarmupDone = false;
const unsigned long ECG_WARMUP_MS = 2000;

// Timer ISR - Lấy mẫu ECG 1000Hz
void IRAM_ATTR onEcgTimer() {
  rawECG = analogRead(AD8232_OUTPUT_PIN);
  ecgTimestamp = micros();
  ecgSampleReady = true;
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(100);

  Serial.println("\nHe thong do tin hieu sinh ly ESP32");
  Serial.println("-----------------------------------");

  // Cấu hình ADC
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  // Cấu hình chân ECG
  pinMode(AD8232_OUTPUT_PIN, INPUT);
  pinMode(AD8232_LO_PLUS_PIN, INPUT);
  pinMode(AD8232_LO_MINUS_PIN, INPUT);

  // Khởi tạo bộ lọc
  ecgFilter.init(ECG_SAMPLE_RATE);
  ppgFilter.init(PPG_SAMPLE_RATE);
  audioFilter.init(AUDIO_SAMPLE_RATE);
  Serial.println("[OK] Bo loc da khoi tao");

  // Khởi tạo I2C cho MAX30102
  Wire.begin(MAX30102_SDA_PIN, MAX30102_SCL_PIN);

  // Khởi tạo MAX30102
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("[LOI] Khong tim thay MAX30102!");
    max30102Initialized = false;
  } else {
    particleSensor.setup(MAX30102_LED_BRIGHTNESS, MAX30102_SAMPLE_AVERAGE,
                         MAX30102_LED_MODE, MAX30102_SAMPLE_RATE,
                         MAX30102_PULSE_WIDTH, MAX30102_ADC_RANGE);
    particleSensor.setPulseAmplitudeRed(0x0A);
    particleSensor.setPulseAmplitudeGreen(0);
    max30102Initialized = true;
    spo2Calc.init();
    Serial.println("[OK] MAX30102 da khoi tao");
  }

  // Khởi tạo INMP441
  if (!microphone.begin()) {
    Serial.println("[CANH BAO] INMP441 khong khoi tao duoc");
  } else {
    Serial.println("[OK] INMP441 da khoi tao");
  }

  // Thiết lập timer cho ECG (1000Hz)
  ecgTimer = timerBegin(0, 80, true);
  timerAttachInterrupt(ecgTimer, &onEcgTimer, true);
  timerAlarmWrite(ecgTimer, ECG_SAMPLE_INTERVAL_US, true);
  timerAlarmEnable(ecgTimer);

  Serial.println("[OK] Timer 1000Hz da bat dau");
  Serial.println("-----------------------------------");
  Serial.println("# FINGER_THRESHOLD_LOW: 1500");
  Serial.println("# FINGER_THRESHOLD_HIGH: 100000");
  Serial.println("# Put finger on MAX30102 sensor");
  Serial.println("-----------------------------------\n");

  startTime = millis();
  delay(500);
}

// Xử lý tín hiệu ECG
void processECG() {
  if (!ecgSampleReady)
    return;
  ecgSampleReady = false;

  // Khởi tạo thời gian bắt đầu
  if (ecgStartTime == 0) {
    ecgStartTime = millis();
  }

  // Kiểm tra warm-up xong chưa
  if (!ecgWarmupDone && (millis() - ecgStartTime) >= ECG_WARMUP_MS) {
    ecgWarmupDone = true;
    ecgFilter.reset();
    ecgWavelet.reset();
  }

  // Kiểm tra lead-off
  bool loPlus = digitalRead(AD8232_LO_PLUS_PIN);
  bool loMinus = digitalRead(AD8232_LO_MINUS_PIN);

  if (loPlus == 1 || loMinus == 1) {
    if (outputCounter % SERIAL_OUTPUT_DECIMATION == 0) {
      Serial.println(">ecg_raw:0");
      Serial.println(">ecg_filtered:0");
      Serial.println(">ecg_wavelet:0");
    }
    return;
  }

  // Phát hiện bão hòa
  bool isSaturated = (rawECG >= 3500 || rawECG <= 200);

  int ecgToProcess;
  if (isSaturated) {
    ecgToProcess = lastValidECG;
  } else {
    ecgToProcess = rawECG;
    lastValidECG = rawECG;
  }

  // Áp dụng bộ lọc
  float rawFloat = (float)ecgToProcess;
  filteredECG = ecgFilter.process(rawFloat);

  // Làm mượt khi bão hòa
  if (!isSaturated) {
    lastValidFiltered = filteredECG;
  } else {
    filteredECG = lastValidFiltered * 0.9f + filteredECG * 0.1f;
  }

  waveletECG = ecgWavelet.process(filteredECG);

  // Xuất dữ liệu (sau warm-up)
  if (outputCounter % SERIAL_OUTPUT_DECIMATION == 0 && ecgWarmupDone) {
    Serial.print(">ecg_raw:");
    Serial.println(ecgToProcess);
    Serial.print(">ecg_filtered:");
    Serial.println(filteredECG, 2);
    Serial.print(">ecg_wavelet:");
    Serial.println(waveletECG, 2);

    if (isSaturated) {
      Serial.println(">ecg_saturated:1");
    }
  }
}

// Xử lý tín hiệu PPG
void processPPG() {
  if (!max30102Initialized)
    return;

  static unsigned long lastPPGSample = 0;
  if (micros() - lastPPGSample < PPG_SAMPLE_INTERVAL_US)
    return;
  lastPPGSample = micros();

  long irValue = particleSensor.getIR();
  long redValue = particleSensor.getRed();

  rawPPG_IR = irValue;

  // Áp dụng bộ lọc
  float irFloat = (float)(irValue >> 4);
  filteredPPG = ppgFilter.process(irFloat);
  waveletPPG = ppgWavelet.process(filteredPPG);

  // Tính SpO2 và nhịp tim
  spo2Calc.addSample(redValue, irValue);
  fingerDetected = spo2Calc.isFingerDetected();
  spo2Calc.calculate();

  // Xuất waveform PPG
  if (outputCounter % SERIAL_OUTPUT_DECIMATION == 0) {
    Serial.print(">ppg_ir_raw:");
    Serial.println(irValue);
    Serial.print(">ppg_ir_filtered:");
    Serial.println(filteredPPG, 2);
    Serial.print(">ppg_ir_wavelet:");
    Serial.println(waveletPPG, 2);

    // Debug output - giúp xác định ngưỡng phù hợp
    Serial.print(">ppg_red_raw:");
    Serial.println(redValue);
  }
}

// Xử lý tín hiệu Audio
void processAudio() {
  if (!microphone.isInitialized())
    return;

  rawAudio = microphone.readSample();
  filteredAudio = audioFilter.process((float)rawAudio);

  // Xuất ~100Hz cho visualization
  static int audioOutputCounter = 0;
  audioOutputCounter++;

  if (audioOutputCounter >= 160) {
    audioOutputCounter = 0;
    Serial.print(">audio_raw:");
    Serial.println(rawAudio);
    Serial.print(">audio_filtered:");
    Serial.println(filteredAudio, 1);
  }
}

// Hiển thị nhịp tim và SpO2
void displayValues() {
  unsigned long currentTime = millis();

  if (currentTime - lastDisplayTime >= DISPLAY_INTERVAL_MS) {
    lastDisplayTime = currentTime;

    // Luôn hiển thị finger status trước
    Serial.print(">finger_detected:");
    Serial.println(fingerDetected ? 1 : 0);

    if (fingerDetected) {
      // Hiển thị HR và SpO2 khi có ngón tay
      float hr = spo2Calc.getHeartRate();
      float sp = spo2Calc.getSpO2();

      Serial.print(">heartrate:");
      Serial.println(hr, 1);
      Serial.print(">spo2:");
      Serial.println(sp, 1);

      // Debug: hiển thị các giá trị DC và AC
      Serial.print(">red_dc:");
      Serial.println(spo2Calc.getRedDC(), 0);
      Serial.print(">ir_dc:");
      Serial.println(spo2Calc.getIrDC(), 0);
      Serial.print(">red_ac:");
      Serial.println(spo2Calc.getRedAC(), 2);
      Serial.print(">ir_ac:");
      Serial.println(spo2Calc.getIrAC(), 2);
      Serial.print(">sample_count:");
      Serial.println(spo2Calc.getSampleCount());
    } else {
      // Khi không có ngón tay, vẫn hiển thị 0
      Serial.println(">heartrate:0");
      Serial.println(">spo2:0");

      // Hiển thị giá trị IR hiện tại để debug ngưỡng
      Serial.print(">ir_current:");
      Serial.println(rawPPG_IR);
    }

    // Hiển thị thời gian chạy (giây)
    Serial.print(">runtime_sec:");
    Serial.println((currentTime - startTime) / 1000);
  }
}

void loop() {
  processECG();
  processPPG();
  processAudio();
  displayValues();

  outputCounter++;
  if (outputCounter >= 10000)
    outputCounter = 0;
}