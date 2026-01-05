/**
 * @file filters.h
 * @brief Digital Signal Processing Filters for ECG/PPG signals
 *
 * Implements:
 * - DC Blocker (removes DC offset)
 * - IIR Notch Filter 50Hz (power line interference)
 * - IIR Notch Filter 100Hz (2nd harmonic)
 * - IIR Butterworth Bandpass [1-100Hz]
 */

#ifndef FILTERS_H
#define FILTERS_H

#include "config.h"
#include <Arduino.h>
#include <math.h>


// ============================================================================
// BIQUAD FILTER STRUCTURE
// ============================================================================
struct BiquadCoeffs {
  float b0, b1, b2; // Numerator coefficients
  float a1, a2;     // Denominator coefficients (a0 normalized to 1)
};

struct BiquadState {
  float x1, x2; // Input delay line
  float y1, y2; // Output delay line
};

// ============================================================================
// SIGNAL FILTER CLASS
// ============================================================================
class SignalFilter {
private:
  // DC Blocker state
  float dc_x1, dc_y1;

  // Notch 50Hz
  BiquadCoeffs notch50_coeffs;
  BiquadState notch50_state;

  // Notch 100Hz
  BiquadCoeffs notch100_coeffs;
  BiquadState notch100_state;

  // Bandpass filter (2nd order = 2 biquad sections)
  // High-pass section
  BiquadCoeffs hp_coeffs;
  BiquadState hp_state;

  // Low-pass section
  BiquadCoeffs lp_coeffs;
  BiquadState lp_state;

  // Calculate notch filter coefficients
  void calculateNotchCoeffs(BiquadCoeffs *coeffs, float f0, float fs, float Q) {
    float w0 = 2.0f * PI * f0 / fs;
    float cosw0 = cos(w0);
    float sinw0 = sin(w0);
    float alpha = sinw0 / (2.0f * Q);

    float a0 = 1.0f + alpha;

    coeffs->b0 = 1.0f / a0;
    coeffs->b1 = -2.0f * cosw0 / a0;
    coeffs->b2 = 1.0f / a0;
    coeffs->a1 = -2.0f * cosw0 / a0;
    coeffs->a2 = (1.0f - alpha) / a0;
  }

  // Calculate 2nd order Butterworth high-pass coefficients
  void calculateHighPassCoeffs(BiquadCoeffs *coeffs, float fc, float fs) {
    float w0 = 2.0f * PI * fc / fs;
    float cosw0 = cos(w0);
    float sinw0 = sin(w0);
    float alpha = sinw0 / (2.0f * 0.7071f); // Q = 1/sqrt(2) for Butterworth

    float a0 = 1.0f + alpha;

    coeffs->b0 = ((1.0f + cosw0) / 2.0f) / a0;
    coeffs->b1 = -(1.0f + cosw0) / a0;
    coeffs->b2 = ((1.0f + cosw0) / 2.0f) / a0;
    coeffs->a1 = -2.0f * cosw0 / a0;
    coeffs->a2 = (1.0f - alpha) / a0;
  }

  // Calculate 2nd order Butterworth low-pass coefficients
  void calculateLowPassCoeffs(BiquadCoeffs *coeffs, float fc, float fs) {
    float w0 = 2.0f * PI * fc / fs;
    float cosw0 = cos(w0);
    float sinw0 = sin(w0);
    float alpha = sinw0 / (2.0f * 0.7071f); // Q = 1/sqrt(2) for Butterworth

    float a0 = 1.0f + alpha;

    coeffs->b0 = ((1.0f - cosw0) / 2.0f) / a0;
    coeffs->b1 = (1.0f - cosw0) / a0;
    coeffs->b2 = ((1.0f - cosw0) / 2.0f) / a0;
    coeffs->a1 = -2.0f * cosw0 / a0;
    coeffs->a2 = (1.0f - alpha) / a0;
  }

  // Apply biquad filter (Direct Form II Transposed)
  float applyBiquad(float x, BiquadCoeffs *coeffs, BiquadState *state) {
    float y = coeffs->b0 * x + coeffs->b1 * state->x1 + coeffs->b2 * state->x2 -
              coeffs->a1 * state->y1 - coeffs->a2 * state->y2;

    // Update state
    state->x2 = state->x1;
    state->x1 = x;
    state->y2 = state->y1;
    state->y1 = y;

    return y;
  }

  void resetState(BiquadState *state) {
    state->x1 = state->x2 = 0;
    state->y1 = state->y2 = 0;
  }

public:
  SignalFilter() { reset(); }

  void init(float sampleRate = FILTER_SAMPLE_RATE) {
    // Calculate all filter coefficients
    calculateNotchCoeffs(&notch50_coeffs, NOTCH_50HZ_FREQ, sampleRate,
                         NOTCH_Q_FACTOR);
    calculateNotchCoeffs(&notch100_coeffs, NOTCH_100HZ_FREQ, sampleRate,
                         NOTCH_Q_FACTOR);
    calculateHighPassCoeffs(&hp_coeffs, BANDPASS_LOW_FREQ, sampleRate);
    calculateLowPassCoeffs(&lp_coeffs, BANDPASS_HIGH_FREQ, sampleRate);

    reset();
  }

  void reset() {
    dc_x1 = dc_y1 = 0;
    resetState(&notch50_state);
    resetState(&notch100_state);
    resetState(&hp_state);
    resetState(&lp_state);
  }

  // Apply DC blocker only
  float applyDCBlocker(float x) {
    float y = x - dc_x1 + DC_BLOCKER_ALPHA * dc_y1;
    dc_x1 = x;
    dc_y1 = y;
    return y;
  }

  // Apply notch filters only (50Hz + 100Hz)
  float applyNotchFilters(float x) {
    float y = applyBiquad(x, &notch50_coeffs, &notch50_state);
    y = applyBiquad(y, &notch100_coeffs, &notch100_state);
    return y;
  }

  // Apply bandpass only
  float applyBandpass(float x) {
    float y = applyBiquad(x, &hp_coeffs, &hp_state);
    y = applyBiquad(y, &lp_coeffs, &lp_state);
    return y;
  }

  // Full filter pipeline: DC Blocker -> Notch 50Hz -> Notch 100Hz -> Bandpass
  float process(float x) {
    // Check for invalid input
    if (isnan(x) || isinf(x))
      return 0;

    float y = x;

    // 1. DC Blocker
    y = applyDCBlocker(y);

    // 2. Notch filters (remove 50Hz and 100Hz)
    y = applyNotchFilters(y);

    // 3. Bandpass [1-100Hz]
    y = applyBandpass(y);

    // Check for invalid output
    if (isnan(y) || isinf(y))
      return 0;

    return y;
  }
};

// ============================================================================
// AUDIO FILTER CLASS (optimized for voice/audio frequencies)
// ============================================================================
class AudioFilter {
private:
  // High-pass to remove DC and low frequency noise
  BiquadCoeffs hp_coeffs;
  BiquadState hp_state;

  float dc_x1, dc_y1;

  void calculateHighPassCoeffs(BiquadCoeffs *coeffs, float fc, float fs) {
    float w0 = 2.0f * PI * fc / fs;
    float cosw0 = cos(w0);
    float sinw0 = sin(w0);
    float alpha = sinw0 / (2.0f * 0.7071f);

    float a0 = 1.0f + alpha;

    coeffs->b0 = ((1.0f + cosw0) / 2.0f) / a0;
    coeffs->b1 = -(1.0f + cosw0) / a0;
    coeffs->b2 = ((1.0f + cosw0) / 2.0f) / a0;
    coeffs->a1 = -2.0f * cosw0 / a0;
    coeffs->a2 = (1.0f - alpha) / a0;
  }

  float applyBiquad(float x, BiquadCoeffs *coeffs, BiquadState *state) {
    float y = coeffs->b0 * x + coeffs->b1 * state->x1 + coeffs->b2 * state->x2 -
              coeffs->a1 * state->y1 - coeffs->a2 * state->y2;
    state->x2 = state->x1;
    state->x1 = x;
    state->y2 = state->y1;
    state->y1 = y;
    return y;
  }

public:
  AudioFilter() { reset(); }

  void init(float sampleRate = AUDIO_SAMPLE_RATE) {
    // High-pass at 80Hz to remove low frequency noise
    calculateHighPassCoeffs(&hp_coeffs, 80.0f, sampleRate);
    reset();
  }

  void reset() {
    dc_x1 = dc_y1 = 0;
    hp_state.x1 = hp_state.x2 = 0;
    hp_state.y1 = hp_state.y2 = 0;
  }

  float process(float x) {
    if (isnan(x) || isinf(x))
      return 0;

    // DC blocker
    float y = x - dc_x1 + 0.995f * dc_y1;
    dc_x1 = x;
    dc_y1 = y;

    // High-pass filter
    y = applyBiquad(y, &hp_coeffs, &hp_state);

    if (isnan(y) || isinf(y))
      return 0;
    return y;
  }
};

#endif // FILTERS_H
