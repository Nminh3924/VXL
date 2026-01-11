/*
 * Bộ lọc xử lý tín hiệu số cho ECG/PPG
 * DC Blocker, Notch 50Hz/100Hz, Bandpass Butterworth
 */

#ifndef FILTERS_H
#define FILTERS_H

#include "config.h"
#include <Arduino.h>
#include <math.h>

struct BiquadCoeffs {
  float b0, b1, b2;
  float a1, a2;
};

struct BiquadState {
  float x1, x2;
  float y1, y2;
};

class SignalFilter {
private:
  float dc_x1, dc_y1;
  BiquadCoeffs notch50_coeffs;
  BiquadState notch50_state;
  BiquadCoeffs notch100_coeffs;
  BiquadState notch100_state;
  BiquadCoeffs hp_coeffs;
  BiquadState hp_state;
  BiquadCoeffs lp_coeffs;
  BiquadState lp_state;

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

  void calculateLowPassCoeffs(BiquadCoeffs *coeffs, float fc, float fs) {
    float w0 = 2.0f * PI * fc / fs;
    float cosw0 = cos(w0);
    float sinw0 = sin(w0);
    float alpha = sinw0 / (2.0f * 0.7071f);
    float a0 = 1.0f + alpha;

    coeffs->b0 = ((1.0f - cosw0) / 2.0f) / a0;
    coeffs->b1 = (1.0f - cosw0) / a0;
    coeffs->b2 = ((1.0f - cosw0) / 2.0f) / a0;
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

  void resetState(BiquadState *state) {
    state->x1 = state->x2 = 0;
    state->y1 = state->y2 = 0;
  }

public:
  SignalFilter() { reset(); }

  void init(float sampleRate = FILTER_SAMPLE_RATE) {
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

  float applyDCBlocker(float x) {
    float y = x - dc_x1 + DC_BLOCKER_ALPHA * dc_y1;
    dc_x1 = x;
    dc_y1 = y;
    return y;
  }

  float applyNotchFilters(float x) {
    float y = applyBiquad(x, &notch50_coeffs, &notch50_state);
    y = applyBiquad(y, &notch100_coeffs, &notch100_state);
    return y;
  }

  float applyBandpass(float x) {
    float y = applyBiquad(x, &hp_coeffs, &hp_state);
    y = applyBiquad(y, &lp_coeffs, &lp_state);
    return y;
  }

  float process(float x) {
    if (isnan(x) || isinf(x))
      return 0;
    float y = x;
    y = applyDCBlocker(y);
    y = applyNotchFilters(y);
    y = applyBandpass(y);
    if (isnan(y) || isinf(y))
      return 0;
    return y;
  }
};

class AudioFilter {
private:
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
    float y = x - dc_x1 + 0.995f * dc_y1;
    dc_x1 = x;
    dc_y1 = y;
    y = applyBiquad(y, &hp_coeffs, &hp_state);
    if (isnan(y) || isinf(y))
      return 0;
    return y;
  }
};

#endif
