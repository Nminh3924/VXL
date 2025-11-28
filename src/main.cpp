#include <Wire.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"

MAX30105 particleSensor;


const int AD8232_OUTPUT = 36; 
const int AD8232_LO_PLUS = 25;
const int AD8232_LO_MINUS = 26;
const int I2C_SDA = 21;
const int I2C_SCL = 22;

class SimpleECGFilter {
private:

  float dcBlocker_x1, dcBlocker_y1;
  const float DC_ALPHA = 0.995; 
  

  static const int MA_SIZE = 3;
  float maBuffer[MA_SIZE];
  int maIndex;
  

  float notch_x1, notch_x2, notch_y1, notch_y2;
  float b0_n, b1_n, b2_n, a1_n, a2_n;
  
  void calculateNotchCoeffs() {
    float fs = 250.0;
    float f0 = 50.0; 
    float Q = 10.0; 
    
    float w0 = 2.0 * PI * f0 / fs;
    float alpha = sin(w0) / (2.0 * Q);
    float a0 = 1.0 + alpha;
    
    b0_n = 1.0 / a0;
    b1_n = -2.0 * cos(w0) / a0;
    b2_n = 1.0 / a0;
    a1_n = -2.0 * cos(w0) / a0;
    a2_n = (1.0 - alpha) / a0;
  }
  
public:
  SimpleECGFilter() {
    dcBlocker_x1 = dcBlocker_y1 = 0;
    notch_x1 = notch_x2 = notch_y1 = notch_y2 = 0;
    maIndex = 0;
    for(int i = 0; i < MA_SIZE; i++) maBuffer[i] = 0;
    calculateNotchCoeffs();
  }
  
  float filter(int rawValue) {
    float x = (float)rawValue;
    
    // DC Blocker (loại bỏ offset, giữ nguyên sóng, t đ biết nó có tác dụng không nhưng trong bài báo EEG nó dùng)
    float y_dc = x - dcBlocker_x1 + DC_ALPHA * dcBlocker_y1;
    dcBlocker_x1 = x;
    dcBlocker_y1 = y_dc;
    
    // Notch 50Hz (loại nhiễu điện, giữ sóng ECG)
    float y_notch = b0_n * y_dc + b1_n * notch_x1 + b2_n * notch_x2
                    - a1_n * notch_y1 - a2_n * notch_y2;
    notch_x2 = notch_x1;
    notch_x1 = y_dc;
    notch_y2 = notch_y1;
    notch_y1 = y_notch;
    
    //Moving Average nhẹ (làm mượt chút, t mà cho mạnh khả năng nó ra đường thẳng =)))
    maBuffer[maIndex] = y_notch;
    maIndex = (maIndex + 1) % MA_SIZE;
    
    float sum = 0;
    for(int i = 0; i < MA_SIZE; i++) sum += maBuffer[i];
    float result = sum / MA_SIZE;
    
    if (isnan(result) || isinf(result)) return 0;
    
    return result;
  }
};

SimpleECGFilter ecgFilter;

// BIẾN CHO MAX30102
uint32_t irBuffer[100];
uint32_t redBuffer[100];
int32_t bufferLength = 100;
int32_t spo2;
int8_t validSPO2;
int32_t heartRate;
int8_t validHeartRate;

float filteredHeartRate = 0;
float filteredSpO2 = 0;
const float SMOOTHING_FACTOR = 0.15;

// BIẾN TIMING 
unsigned long lastECGTime = 0;
unsigned long lastDisplayTime = 0;
const unsigned long ECG_INTERVAL = 4;
const unsigned long DISPLAY_INTERVAL = 1000;

bool fingerDetected = false;
int noFingerCount = 0;

void readECG();
void readSpO2AndHeartRate();
void setupMAX30105();

void setup() {
  Serial.begin(115200);
  
  // Cấu hình ADC cho ESP32
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  
  // Set chân ADC về INPUT (quan trọng!)
  pinMode(AD8232_OUTPUT, INPUT);
  pinMode(AD8232_LO_PLUS, INPUT);
  pinMode(AD8232_LO_MINUS, INPUT);
  
  Wire.begin(I2C_SDA, I2C_SCL);
  setupMAX30105();
  
  
  // Test ADC ngay lập tức
  delay(500);
  for(int i = 0; i < 10; i++) {
    int raw = analogRead(AD8232_OUTPUT);
    Serial.println(raw);
    delay(100);
  }
  
  delay(1000);
}

void setupMAX30105() {
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("ERROR: MAX30105 not found!");
    while (1);
  }
  
  byte ledBrightness = 60;
  byte sampleAverage = 4;
  byte ledMode = 2;
  byte sampleRate = 100;
  int pulseWidth = 411;
  int adcRange = 4096;
  
  particleSensor.setup(ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange);
  particleSensor.setPulseAmplitudeRed(0x0A);
  particleSensor.setPulseAmplitudeGreen(0);
}

void loop() {
  unsigned long currentTime = millis();
  
  if (currentTime - lastECGTime >= ECG_INTERVAL) {
    lastECGTime = currentTime;
    readECG();
  }
  
  readSpO2AndHeartRate();
  
  if (currentTime - lastDisplayTime >= DISPLAY_INTERVAL) {
    lastDisplayTime = currentTime;
    
    if (fingerDetected) {
      Serial.print(">heartrate:");
      Serial.println(filteredHeartRate, 1);
      Serial.print(">spo2:");
      Serial.println(filteredSpO2, 1);
    } else {
      Serial.println(">heartrate:0");
      Serial.println(">spo2:0");
    }
  }
}

void readECG() {
  // Kiểm tra lead-off
  bool loPlus = digitalRead(AD8232_LO_PLUS);
  bool loMinus = digitalRead(AD8232_LO_MINUS);
  
  // Debug lead-off status
  static unsigned long lastDebug = 0;
  if (millis() - lastDebug > 2000) {
    Serial.print("Lead-Off Status: LO+=");
    Serial.print(loPlus);
    Serial.print(" LO-=");
    Serial.println(loMinus);
    lastDebug = millis();
  }
  
  if (loPlus == 1 || loMinus == 1) {
    Serial.println(">ecg:0");
    Serial.println(">ecg_raw:0");
    return;
  }
  
  // Đọc tín hiệu RAW
  int rawECG = analogRead(AD8232_OUTPUT);
  
  // Kiểm tra nếu ADC bị treo ở giá trị MAX hoặc MIN
  if (rawECG >= 4090 || rawECG <= 5) {
    Serial.print("WARNING: ADC stuck at ");
    Serial.println(rawECG);
  }
  
  // Áp dụng bộ lọc
  float filteredECG = ecgFilter.filter(rawECG);
  
  // Gửi dữ liệu
  Serial.print(">ecg:");
  Serial.println(filteredECG, 1);
  
  Serial.print(">ecg_raw:");
  Serial.println(rawECG);
}

void readSpO2AndHeartRate() {
  static int sampleCount = 0;
  static bool isCollecting = false;
  
  long irValue = particleSensor.getIR();
  
  if (irValue < 50000) {
    fingerDetected = false;
    noFingerCount++;
    
    if (noFingerCount > 10) {
      isCollecting = false;
      sampleCount = 0;
    }
    return;
  }
  
  fingerDetected = true;
  noFingerCount = 0;
  
  if (!isCollecting) {
    sampleCount = 0;
    isCollecting = true;
  }
  
  if (sampleCount < bufferLength) {
    redBuffer[sampleCount] = particleSensor.getRed();
    irBuffer[sampleCount] = particleSensor.getIR();
    sampleCount++;
  } else {
    maxim_heart_rate_and_oxygen_saturation(
      irBuffer, bufferLength, redBuffer, 
      &spo2, &validSPO2, &heartRate, &validHeartRate
    );
    
    if (validHeartRate == 1 && heartRate > 40 && heartRate < 200) {
      filteredHeartRate = filteredHeartRate * (1 - SMOOTHING_FACTOR) + heartRate * SMOOTHING_FACTOR;
    }
    
    if (validSPO2 == 1 && spo2 > 70 && spo2 <= 100) {
      filteredSpO2 = filteredSpO2 * (1 - SMOOTHING_FACTOR) + spo2 * SMOOTHING_FACTOR;
    }
    
    for (int i = 25; i < bufferLength; i++) {
      redBuffer[i - 25] = redBuffer[i];
      irBuffer[i - 25] = irBuffer[i];
    }
    sampleCount = 75;
  }
}