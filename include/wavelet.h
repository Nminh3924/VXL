/**
 * @file wavelet.h
 * @brief Haar Wavelet Transform for Signal Denoising
 *
 * Implements real-time Haar wavelet denoising optimized for ESP32:
 * - Low computational complexity (additions/subtractions only)
 * - Fixed buffer size for predictable memory usage
 * - Soft thresholding for noise removal
 */

#ifndef WAVELET_H
#define WAVELET_H

#include "config.h"
#include <Arduino.h>
#include <math.h>


// ============================================================================
// HAAR WAVELET DENOISER CLASS
// ============================================================================
class WaveletDenoiser {
private:
  // Circular buffer for incoming samples
  float buffer[WAVELET_BUFFER_SIZE];
  int bufferIndex;
  int samplesCollected;

  // Working arrays for DWT
  float approx[WAVELET_BUFFER_SIZE];
  float detail[WAVELET_BUFFER_SIZE];

  // Output buffer
  float denoisedBuffer[WAVELET_BUFFER_SIZE];
  int outputIndex;
  bool bufferReady;

  // Threshold calculation using MAD (Median Absolute Deviation)
  float calculateThreshold(float *data, int length) {
    // Simplified: use standard deviation estimate
    float sum = 0, sumSq = 0;
    for (int i = 0; i < length; i++) {
      sum += data[i];
      sumSq += data[i] * data[i];
    }
    float mean = sum / length;
    float variance = (sumSq / length) - (mean * mean);
    float sigma = sqrt(max(variance, 0.0f));

    // Universal threshold: sigma * sqrt(2 * log(N))
    float threshold =
        sigma * sqrt(2.0f * log((float)length)) * WAVELET_THRESHOLD_MULTIPLIER;
    return threshold;
  }

  // Soft thresholding
  float softThreshold(float x, float threshold) {
    if (x > threshold) {
      return x - threshold;
    } else if (x < -threshold) {
      return x + threshold;
    }
    return 0;
  }

  // Haar forward transform (decomposition)
  void haarDecompose(float *signal, int length, float *approxOut,
                     float *detailOut) {
    int halfLen = length / 2;
    float sqrt2 = 1.41421356f;

    for (int i = 0; i < halfLen; i++) {
      float s1 = signal[2 * i];
      float s2 = signal[2 * i + 1];
      approxOut[i] = (s1 + s2) / sqrt2; // Approximation (low-pass)
      detailOut[i] = (s1 - s2) / sqrt2; // Detail (high-pass)
    }
  }

  // Haar inverse transform (reconstruction)
  void haarReconstruct(float *approxIn, float *detailIn, int halfLen,
                       float *signalOut) {
    float sqrt2 = 1.41421356f;

    for (int i = 0; i < halfLen; i++) {
      float a = approxIn[i];
      float d = detailIn[i];
      signalOut[2 * i] = (a + d) / sqrt2;
      signalOut[2 * i + 1] = (a - d) / sqrt2;
    }
  }

  // Multi-level decomposition and denoising
  void processBuffer() {
    // Copy buffer to working array
    float working[WAVELET_BUFFER_SIZE];
    for (int i = 0; i < WAVELET_BUFFER_SIZE; i++) {
      working[i] = buffer[(bufferIndex + i) % WAVELET_BUFFER_SIZE];
    }

    // Store detail coefficients at each level
    float details[WAVELET_DECOMPOSITION_LEVEL][WAVELET_BUFFER_SIZE / 2];
    int lengths[WAVELET_DECOMPOSITION_LEVEL];

    // Forward DWT (decomposition)
    int currentLen = WAVELET_BUFFER_SIZE;
    for (int level = 0; level < WAVELET_DECOMPOSITION_LEVEL; level++) {
      int halfLen = currentLen / 2;
      lengths[level] = halfLen;

      haarDecompose(working, currentLen, approx, detail);

      // Store detail coefficients
      for (int i = 0; i < halfLen; i++) {
        details[level][i] = detail[i];
      }

      // Copy approximation for next level
      for (int i = 0; i < halfLen; i++) {
        working[i] = approx[i];
      }

      currentLen = halfLen;
    }

    // Apply soft thresholding to detail coefficients
    for (int level = 0; level < WAVELET_DECOMPOSITION_LEVEL; level++) {
      float threshold = calculateThreshold(details[level], lengths[level]);
      for (int i = 0; i < lengths[level]; i++) {
        details[level][i] = softThreshold(details[level][i], threshold);
      }
    }

    // Inverse DWT (reconstruction)
    // Start with the lowest level approximation
    for (int level = WAVELET_DECOMPOSITION_LEVEL - 1; level >= 0; level--) {
      int halfLen = lengths[level];

      // Copy thresholded details
      for (int i = 0; i < halfLen; i++) {
        detail[i] = details[level][i];
      }

      // Copy approximation
      for (int i = 0; i < halfLen; i++) {
        approx[i] = working[i];
      }

      // Reconstruct
      haarReconstruct(approx, detail, halfLen, working);
    }

    // Copy to output buffer
    for (int i = 0; i < WAVELET_BUFFER_SIZE; i++) {
      denoisedBuffer[i] = working[i];
    }

    bufferReady = true;
    outputIndex = 0;
  }

public:
  WaveletDenoiser() { reset(); }

  void reset() {
    bufferIndex = 0;
    samplesCollected = 0;
    outputIndex = 0;
    bufferReady = false;

    for (int i = 0; i < WAVELET_BUFFER_SIZE; i++) {
      buffer[i] = 0;
      denoisedBuffer[i] = 0;
    }
  }

  // Add a sample to the buffer
  // Returns true when a new denoised sample is available
  bool addSample(float sample) {
    buffer[bufferIndex] = sample;
    bufferIndex = (bufferIndex + 1) % WAVELET_BUFFER_SIZE;
    samplesCollected++;

    // Process when buffer is full
    if (samplesCollected >= WAVELET_BUFFER_SIZE) {
      processBuffer();
      samplesCollected = WAVELET_BUFFER_SIZE / 2; // Overlap
      return true;
    }

    return bufferReady;
  }

  // Get the current denoised sample
  float getDenoisedSample() {
    if (!bufferReady)
      return 0;

    float sample = denoisedBuffer[outputIndex];
    outputIndex++;

    if (outputIndex >= WAVELET_BUFFER_SIZE) {
      bufferReady = false;
      outputIndex = 0;
    }

    return sample;
  }

  // Check if denoised data is available
  bool isReady() { return bufferReady && (outputIndex < WAVELET_BUFFER_SIZE); }

  // Simple real-time denoising (sliding window approach)
  // This provides sample-by-sample output with some delay
  float denoise(float sample) {
    static float slidingBuffer[8];
    static int slidingIndex = 0;
    static bool initialized = false;

    if (!initialized) {
      for (int i = 0; i < 8; i++)
        slidingBuffer[i] = 0;
      initialized = true;
    }

    slidingBuffer[slidingIndex] = sample;
    slidingIndex = (slidingIndex + 1) % 8;

    // Simple 2-level Haar for real-time
    float a0 = (slidingBuffer[0] + slidingBuffer[1]) * 0.7071f;
    float a1 = (slidingBuffer[2] + slidingBuffer[3]) * 0.7071f;
    float a2 = (slidingBuffer[4] + slidingBuffer[5]) * 0.7071f;
    float a3 = (slidingBuffer[6] + slidingBuffer[7]) * 0.7071f;

    float d0 = (slidingBuffer[0] - slidingBuffer[1]) * 0.7071f;
    float d1 = (slidingBuffer[2] - slidingBuffer[3]) * 0.7071f;
    float d2 = (slidingBuffer[4] - slidingBuffer[5]) * 0.7071f;
    float d3 = (slidingBuffer[6] - slidingBuffer[7]) * 0.7071f;

    // Simple threshold (based on signal magnitude)
    float threshold = 0.1f * (abs(a0) + abs(a1) + abs(a2) + abs(a3));

    d0 = softThreshold(d0, threshold);
    d1 = softThreshold(d1, threshold);
    d2 = softThreshold(d2, threshold);
    d3 = softThreshold(d3, threshold);

    // Reconstruct (return center sample)
    float r2 = (a1 + d1) * 0.7071f;
    float r3 = (a1 - d1) * 0.7071f;

    return (r2 + r3) / 2.0f; // Average for smoothing
  }
};

// ============================================================================
// SIMPLIFIED REAL-TIME WAVELET DENOISER
// Uses a smaller sliding window for lower latency
// ============================================================================
class RealTimeWaveletDenoiser {
private:
  float buffer[16];
  int bufferIndex;
  float lastOutput;

  float softThreshold(float x, float threshold) {
    if (x > threshold)
      return x - threshold;
    if (x < -threshold)
      return x + threshold;
    return 0;
  }

public:
  RealTimeWaveletDenoiser() { reset(); }

  void reset() {
    bufferIndex = 0;
    lastOutput = 0;
    for (int i = 0; i < 16; i++)
      buffer[i] = 0;
  }

  float process(float sample) {
    // Add to circular buffer
    buffer[bufferIndex] = sample;

    // 2-level Haar decomposition on last 8 samples
    int idx = bufferIndex;
    float s[8];
    for (int i = 7; i >= 0; i--) {
      s[i] = buffer[idx];
      idx = (idx - 1 + 16) % 16;
    }

    // Level 1 decomposition
    float a1[4], d1[4];
    for (int i = 0; i < 4; i++) {
      a1[i] = (s[2 * i] + s[2 * i + 1]) * 0.7071f;
      d1[i] = (s[2 * i] - s[2 * i + 1]) * 0.7071f;
    }

    // Level 2 decomposition
    float a2[2], d2[2];
    for (int i = 0; i < 2; i++) {
      a2[i] = (a1[2 * i] + a1[2 * i + 1]) * 0.7071f;
      d2[i] = (a1[2 * i] - a1[2 * i + 1]) * 0.7071f;
    }

    // Calculate adaptive threshold
    float sumAbs = abs(d1[0]) + abs(d1[1]) + abs(d1[2]) + abs(d1[3]) +
                   abs(d2[0]) + abs(d2[1]);
    float threshold = sumAbs / 6.0f * WAVELET_THRESHOLD_MULTIPLIER;

    // Apply soft thresholding to details
    for (int i = 0; i < 4; i++)
      d1[i] = softThreshold(d1[i], threshold);
    for (int i = 0; i < 2; i++)
      d2[i] = softThreshold(d2[i], threshold * 0.7f);

    // Level 2 reconstruction
    float ra1[4];
    for (int i = 0; i < 2; i++) {
      ra1[2 * i] = (a2[i] + d2[i]) * 0.7071f;
      ra1[2 * i + 1] = (a2[i] - d2[i]) * 0.7071f;
    }

    // Level 1 reconstruction
    float rs[8];
    for (int i = 0; i < 4; i++) {
      rs[2 * i] = (ra1[i] + d1[i]) * 0.7071f;
      rs[2 * i + 1] = (ra1[i] - d1[i]) * 0.7071f;
    }

    bufferIndex = (bufferIndex + 1) % 16;

    // Return the center sample (with some delay)
    lastOutput = rs[4];

    if (isnan(lastOutput) || isinf(lastOutput))
      return sample * 0.5f;

    return lastOutput;
  }
};

#endif // WAVELET_H
