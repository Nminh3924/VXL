/*
 * Tính toán SpO2 sử dụng phương pháp R-ratio (Beer-Lambert)
 * R = (AC_red / DC_red) / (AC_ir / DC_ir)
 * SpO2 = 110 - 25 * R
 */

#ifndef SPO2_CUSTOM_H
#define SPO2_CUSTOM_H

#include <Arduino.h>

// Cấu hình
#define SPO2_BUFFER_SIZE 200
#define SPO2_MIN_SAMPLES 50         // Giảm để phản hồi nhanh hơn
#define SPO2_UPDATE_INTERVAL 300    // Cập nhật thường xuyên hơn
#define HR_SMOOTHING_FACTOR 0.15f   // Tăng để hội tụ nhanh hơn
#define SPO2_SMOOTHING_FACTOR 0.15f // Tăng để hội tụ nhanh hơn
#define HR_MAX_CHANGE 25.0f         // Cho phép biến đổi lớn hơn

// Ngưỡng phát hiện ngón tay - QUAN TRỌNG
#define FINGER_THRESHOLD_LOW 1500    // Ngưỡng thấp (có thể điều chỉnh)
#define FINGER_THRESHOLD_HIGH 100000 // Ngưỡng cao
#define FINGER_STABLE_COUNT 30       // Số mẫu ổn định cần thiết

class SpO2Calculator {
private:
  uint32_t redBuffer[SPO2_BUFFER_SIZE];
  uint32_t irBuffer[SPO2_BUFFER_SIZE];
  int bufferIndex = 0;
  int sampleCount = 0;

  float redDC = 0;
  float irDC = 0;
  float redAC = 0;
  float irAC = 0;

  float currentSpO2 = 0;
  float currentHeartRate = 0;
  float filteredSpO2 = 98.0f;
  float filteredHeartRate = 75.0f;

  unsigned long lastUpdateTime = 0;
  unsigned long lastPeakTime = 0;
  int peakCount = 0;

  float lastIR = 0;
  float lastLastIR = 0;
  uint32_t peakThreshold = 0;

  bool fingerPresent = false;
  int stableFingerCount = 0;

public:
  void init() {
    bufferIndex = 0;
    sampleCount = 0;
    filteredSpO2 = 98.0f;
    filteredHeartRate = 75.0f;
    fingerPresent = false;
    stableFingerCount = 0;
  }

  void addSample(uint32_t redValue, uint32_t irValue) {
    redBuffer[bufferIndex] = redValue;
    irBuffer[bufferIndex] = irValue;
    bufferIndex = (bufferIndex + 1) % SPO2_BUFFER_SIZE;

    if (sampleCount < SPO2_BUFFER_SIZE) {
      sampleCount++;
    }

    // Phát hiện ngón tay - sử dụng ngưỡng thích ứng
    // Giá trị IR thường dao động từ 1000-3000 khi không có ngón tay
    // và tăng lên 5000+ khi có ngón tay
    if (irValue > FINGER_THRESHOLD_LOW && irValue < FINGER_THRESHOLD_HIGH) {
      stableFingerCount++;
      if (stableFingerCount > FINGER_STABLE_COUNT) {
        fingerPresent = true;
      }
    } else {
      if (stableFingerCount > 0) {
        stableFingerCount--; // Giảm từ từ thay vì reset ngay
      }
      if (stableFingerCount == 0) {
        fingerPresent = false;
      }
    }

    detectPeak(irValue);
  }

  void calculate() {
    if (!fingerPresent || sampleCount < SPO2_MIN_SAMPLES)
      return;

    unsigned long now = millis();
    if (now - lastUpdateTime < SPO2_UPDATE_INTERVAL)
      return;
    lastUpdateTime = now;

    // Tính DC (giá trị trung bình)
    uint64_t redSum = 0;
    uint64_t irSum = 0;

    for (int i = 0; i < sampleCount; i++) {
      redSum += redBuffer[i];
      irSum += irBuffer[i];
    }

    redDC = (float)redSum / sampleCount;
    irDC = (float)irSum / sampleCount;

    // Tính AC (độ lệch chuẩn)
    float redSqSum = 0;
    float irSqSum = 0;

    for (int i = 0; i < sampleCount; i++) {
      float redDiff = (float)redBuffer[i] - redDC;
      float irDiff = (float)irBuffer[i] - irDC;
      redSqSum += redDiff * redDiff;
      irSqSum += irDiff * irDiff;
    }

    redAC = sqrtf(redSqSum / sampleCount);
    irAC = sqrtf(irSqSum / sampleCount);

    if (irDC < 1.0f || redDC < 1.0f || irAC < 1.0f)
      return;

    // Tính R-ratio
    float R = (redAC / redDC) / (irAC / irDC);

    // Tính SpO2
    float spo2 = 110.0f - 25.0f * R;

    if (spo2 > 100.0f)
      spo2 = 100.0f;
    if (spo2 < 70.0f)
      spo2 = 70.0f;

    if (spo2 >= 85.0f && spo2 <= 100.0f) {
      currentSpO2 = spo2;
      filteredSpO2 = filteredSpO2 * (1.0f - SPO2_SMOOTHING_FACTOR) +
                     currentSpO2 * SPO2_SMOOTHING_FACTOR;
    }
  }

  void detectPeak(uint32_t irValue) {
    if (!fingerPresent) {
      lastIR = 0;
      lastLastIR = 0;
      peakCount = 0;
      return;
    }

    // Cập nhật ngưỡng thích ứng - phản hồi nhanh hơn
    if (peakThreshold == 0) {
      peakThreshold = irValue;
    } else {
      peakThreshold = peakThreshold * 0.95f + irValue * 0.05f;
    }

    float currentIR = (float)irValue;

    // Phát hiện đỉnh với ngưỡng thích ứng tốt hơn
    // Đỉnh phải cao hơn ngưỡng trung bình ít nhất 0.5%
    if (lastIR > lastLastIR && lastIR > currentIR &&
        lastIR > peakThreshold * 1.005f) {
      unsigned long now = millis();
      unsigned long interval = now - lastPeakTime;

      if (interval > 300 && interval < 1500 && lastPeakTime > 0) {
        float instantHR = 60000.0f / interval;

        if (instantHR >= 40.0f && instantHR <= 180.0f) {
          float hrDiff = instantHR - filteredHeartRate;
          if (hrDiff < 0)
            hrDiff = -hrDiff;

          if (hrDiff <= HR_MAX_CHANGE || peakCount < 3) {
            currentHeartRate = instantHR;
            filteredHeartRate =
                filteredHeartRate * (1.0f - HR_SMOOTHING_FACTOR) +
                currentHeartRate * HR_SMOOTHING_FACTOR;
            peakCount++;
          }
        }
      }
      lastPeakTime = now;
    }

    lastLastIR = lastIR;
    lastIR = currentIR;
  }

  // Getters
  float getSpO2() const { return filteredSpO2; }
  float getHeartRate() const { return filteredHeartRate; }
  float getRawSpO2() const { return currentSpO2; }
  float getRawHeartRate() const { return currentHeartRate; }
  bool isFingerDetected() const { return fingerPresent; }
  float getRedDC() const { return redDC; }
  float getIrDC() const { return irDC; }
  float getRedAC() const { return redAC; }
  float getIrAC() const { return irAC; }
  int getSampleCount() const { return sampleCount; }
};

#endif
