#include "MAX30105.h"
#include "config.h"
#include <Arduino.h>
#include <Wire.h>
#include <driver/i2s.h>

// --- OBJECTS ---
MAX30105 ppg;
hw_timer_t *timer = NULL;
portMUX_TYPE timerMux = portMUX_INITIALIZER_UNLOCKED;

// --- CONFIGURATION ---
#define SERIAL_BAUD 460800
#define SAMPLE_DURATION_MS 180000
#define ECG_BUFFER_SIZE 512
#define PPG_QUEUE_SIZE 512
#define AUDIO_QUEUE_SIZE 256
#define AUDIO_SAMPLE_INTERVAL_MS 1 // 1000Hz audio sampling for logging

// --- FreeRTOS ---
TaskHandle_t ppgTaskHandle = NULL;
QueueHandle_t ppgQueue = NULL;
QueueHandle_t audioQueue = NULL;

// PPG Data Structure
struct PPGSample {
  uint32_t ir;
  uint32_t red;
};

// --- SHARED DATA ---
volatile int ecgBuffer[ECG_BUFFER_SIZE];
volatile int ecgHead = 0;
volatile int ecgTail = 0;
volatile bool measurementActive = false;

// Debug counters
volatile uint32_t ppgSampleCount = 0;
volatile uint32_t audioSampleCount = 0;

// --- I2S AUDIO SETUP ---
void initI2S() {
  i2s_config_t i2s_config = {
      .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = 16000,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
      .channel_format =
          I2S_CHANNEL_FMT_ONLY_RIGHT, // Try RIGHT channel if LEFT is silent
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 4,
      .dma_buf_len = 256,
      .use_apll = false,
      .tx_desc_auto_clear = false,
      .fixed_mclk = 0};

  i2s_pin_config_t pin_config = {.bck_io_num = INMP441_SCK_PIN,
                                 .ws_io_num = INMP441_WS_PIN,
                                 .data_out_num = I2S_PIN_NO_CHANGE,
                                 .data_in_num = INMP441_SD_PIN};

  i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pin_config);
  i2s_zero_dma_buffer(I2S_NUM_0);
}

// --- ISR: TIMER INTERRUPT (500Hz) for ECG ---
void IRAM_ATTR onTimer() {
  if (measurementActive) {
    int val = analogRead(AD8232_OUTPUT_PIN);

    portENTER_CRITICAL_ISR(&timerMux);
    int nextHead = (ecgHead + 1) % ECG_BUFFER_SIZE;
    if (nextHead != ecgTail) {
      ecgBuffer[ecgHead] = val;
      ecgHead = nextHead;
    }
    portEXIT_CRITICAL_ISR(&timerMux);
  }
}

// --- PPG TASK (runs on Core 0) ---
void ppgTask(void *pvParameters) {
  Serial.println("# PPG Task started on Core 0");

  while (true) {
    if (measurementActive) {
      ppg.check();

      while (ppg.available()) {
        PPGSample sample;
        sample.ir = ppg.getIR();
        sample.red = ppg.getRed();
        ppg.nextSample();
        ppgSampleCount++;

        xQueueSend(ppgQueue, &sample, 0);
      }

      taskYIELD();
    } else {
      vTaskDelay(pdMS_TO_TICKS(50));
    }
  }
}

// --- AUDIO TASK (runs on Core 0) ---
void audioTask(void *pvParameters) {
  Serial.println("# Audio Task started on Core 0");

  int32_t audioBuffer[64];
  size_t bytesRead;

  while (true) {
    if (measurementActive) {
      // Read audio samples from I2S
      i2s_read(I2S_NUM_0, audioBuffer, sizeof(audioBuffer), &bytesRead,
               portMAX_DELAY);

      if (bytesRead > 0) {
        // Average the samples and send to queue (reduces data rate)
        int32_t sum = 0;
        int numSamples = bytesRead / 4;
        for (int i = 0; i < numSamples; i++) {
          sum += (audioBuffer[i] >> 14); // Scale down 32-bit to usable range
        }
        int32_t avgSample = sum / numSamples;

        xQueueSend(audioQueue, &avgSample, 0);
        audioSampleCount++;
      }

      vTaskDelay(pdMS_TO_TICKS(AUDIO_SAMPLE_INTERVAL_MS));
    } else {
      vTaskDelay(pdMS_TO_TICKS(100));
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);

  pinMode(AD8232_LO_PLUS_PIN, INPUT);
  pinMode(AD8232_LO_MINUS_PIN, INPUT);

  // Init MAX30102
  Wire.begin();
  Wire.setClock(400000);

  if (!ppg.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("# Error: MAX30102 Init Failed!");
  } else {
    ppg.setup(0x1F, 1, 2, 1600, 411, 16384);
    Serial.println("# MAX30102 OK: 1600Hz/1avg");
  }

  // Init I2S Audio
  initI2S();
  Serial.println("# INMP441 Audio OK: 16kHz");

  // Create Queues
  ppgQueue = xQueueCreate(PPG_QUEUE_SIZE, sizeof(PPGSample));
  audioQueue = xQueueCreate(AUDIO_QUEUE_SIZE, sizeof(int32_t));

  // Create PPG Task on Core 0
  xTaskCreatePinnedToCore(ppgTask, "PPG_Task", 4096, NULL,
                          configMAX_PRIORITIES - 1, &ppgTaskHandle, 0);

  // Create Audio Task on Core 0
  xTaskCreatePinnedToCore(audioTask, "Audio_Task", 4096, NULL,
                          configMAX_PRIORITIES - 2, NULL, 0);

  // Init Timer (500Hz) for ECG
  timer = timerBegin(0, 80, true);
  timerAttachInterrupt(timer, &onTimer, true);
  timerAlarmWrite(timer, 1000, true); // 1000Hz
  timerAlarmEnable(timer);

  Serial.println("# READY: ECG@500Hz, PPG@~40Hz, Audio@100Hz");
  Serial.println("# Press ENTER to start.");
}

void loop() {
  static unsigned long startTime = 0;
  static unsigned long lastLog = 0;
  static uint32_t lastPPGCount = 0;
  static uint32_t lastAudioCount = 0;

  // CMD Handling
  if (Serial.available()) {
    while (Serial.available())
      Serial.read();
    if (!measurementActive) {
      Serial.println("# STARTING...");
      startTime = millis();
      ecgHead = 0;
      ecgTail = 0;
      ppgSampleCount = 0;
      audioSampleCount = 0;
      xQueueReset(ppgQueue);
      xQueueReset(audioQueue);
      measurementActive = true;
    }
  }

  if (measurementActive) {
    unsigned long now = millis();

    // 1. Read PPG samples from queue
    PPGSample sample;
    while (xQueueReceive(ppgQueue, &sample, 0) == pdTRUE) {
      Serial.print(">ppg_ir_raw:");
      Serial.println(sample.ir);
      Serial.print(">ppg_red_raw:");
      Serial.println(sample.red);
    }

    // 2. Read Audio samples from queue
    int32_t audioSample;
    while (xQueueReceive(audioQueue, &audioSample, 0) == pdTRUE) {
      Serial.print(">audio_raw:");
      Serial.println(audioSample);
    }

    // 3. Read ECG from buffer
    int ecgPrinted = 0;
    while (ecgPrinted < 50) {
      int val = -1;
      portENTER_CRITICAL(&timerMux);
      if (ecgHead != ecgTail) {
        val = ecgBuffer[ecgTail];
        ecgTail = (ecgTail + 1) % ECG_BUFFER_SIZE;
      }
      portEXIT_CRITICAL(&timerMux);

      if (val != -1) {
        Serial.print(">ecg_raw:");
        Serial.println(val);
        ecgPrinted++;
      } else {
        break;
      }
    }

    // 4. Log Runtime + rates
    if (now - lastLog >= 1000) {
      uint32_t ppgDelta = ppgSampleCount - lastPPGCount;
      uint32_t audioDelta = audioSampleCount - lastAudioCount;
      lastPPGCount = ppgSampleCount;
      lastAudioCount = audioSampleCount;

      Serial.print(">runtime_sec:");
      Serial.println((now - startTime) / 1000);
      Serial.print("# Rates: PPG=");
      Serial.print(ppgDelta);
      Serial.print("Hz, Audio=");
      Serial.print(audioDelta);
      Serial.println("Hz");

      lastLog = now;
    }

    // Check Done
    if (now - startTime > SAMPLE_DURATION_MS) {
      measurementActive = false;
      Serial.println("# DONE.");
    }
  }
}