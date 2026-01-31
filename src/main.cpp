#include "MAX30105.h"
#include "config.h"
#include <Arduino.h>
#include <Wire.h>

// --- OBJECTS ---
MAX30105 ppg;
hw_timer_t *timer = NULL;
portMUX_TYPE timerMux = portMUX_INITIALIZER_UNLOCKED;

// --- CONFIGURATION ---
#define SERIAL_BAUD 460800
#define SAMPLE_DURATION_MS 180000
#define ECG_BUFFER_SIZE 512
#define PPG_QUEUE_SIZE 512

// --- FreeRTOS ---
TaskHandle_t ppgTaskHandle = NULL;
QueueHandle_t ppgQueue = NULL;

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

// PPG debug counter
volatile uint32_t ppgSampleCount = 0;

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

// --- PPG TASK (runs on Core 0) - AGGRESSIVE VERSION ---
void ppgTask(void *pvParameters) {
  Serial.println("# PPG Task started on Core 0");

  TickType_t lastWakeTime = xTaskGetTickCount();

  while (true) {
    if (measurementActive) {
      // Poll MAX30102 FIFO as fast as possible
      ppg.check();

      // Read ALL available samples from FIFO
      while (ppg.available()) {
        PPGSample sample;
        sample.ir = ppg.getIR();
        sample.red = ppg.getRed();
        ppg.nextSample();
        ppgSampleCount++;

        // Send to queue (non-blocking, drop if full)
        xQueueSend(ppgQueue, &sample, 0);
      }

      // Yield to other tasks but don't waste time
      taskYIELD();

    } else {
      // Idle mode - check less frequently
      vTaskDelay(pdMS_TO_TICKS(50));
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);

  pinMode(AD8232_LO_PLUS_PIN, INPUT);
  pinMode(AD8232_LO_MINUS_PIN, INPUT);

  // Init MAX30102 with Fast I2C
  Wire.begin();
  Wire.setClock(400000);

  if (!ppg.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("# Error: MAX30102 Init Failed!");
  } else {
    // FINAL TEST: No averaging (sampleAvg=1), max internal rate
    // 1600Hz internal / 1 avg = 1600Hz theoretical output
    ppg.setup(0x1F, 1, 2, 1600, 411, 16384);
    Serial.println("# MAX30102: 1600Hz/1avg = MAX SPEED TEST");
  }

  // Create PPG Queue (larger)
  ppgQueue = xQueueCreate(PPG_QUEUE_SIZE, sizeof(PPGSample));

  // Create PPG Task on Core 0 with HIGH priority
  xTaskCreatePinnedToCore(ppgTask, "PPG_Task", 4096, NULL,
                          configMAX_PRIORITIES - 1, // Highest priority
                          &ppgTaskHandle,
                          0 // Core 0
  );

  // Init Timer (500Hz) for ECG
  timer = timerBegin(0, 80, true);
  timerAttachInterrupt(timer, &onTimer, true);
  timerAlarmWrite(timer, 2000, true);
  timerAlarmEnable(timer);

  Serial.println("# DUAL-CORE: PPG@Core0 (high prio), ECG@Core1");
  Serial.println("# Press ENTER to start.");
}

void loop() {
  static unsigned long startTime = 0;
  static unsigned long lastLog = 0;
  static uint32_t lastPPGCount = 0;

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
      xQueueReset(ppgQueue);
      measurementActive = true;
    }
  }

  if (measurementActive) {
    unsigned long now = millis();

    // 1. Read PPG samples from queue
    PPGSample sample;
    int ppgPrinted = 0;
    while (xQueueReceive(ppgQueue, &sample, 0) == pdTRUE) {
      Serial.print(">ppg_ir_raw:");
      Serial.println(sample.ir);
      Serial.print(">ppg_red_raw:");
      Serial.println(sample.red);
      ppgPrinted++;
    }

    // 2. Read ECG from buffer (limit to prevent Serial blocking)
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

    // 3. Log Runtime + PPG rate debug
    if (now - lastLog >= 1000) {
      uint32_t ppgDelta = ppgSampleCount - lastPPGCount;
      lastPPGCount = ppgSampleCount;

      Serial.print(">runtime_sec:");
      Serial.println((now - startTime) / 1000);
      Serial.print("# PPG Rate: ");
      Serial.print(ppgDelta);
      Serial.println(" Hz");

      lastLog = now;
    }

    // Check Done
    if (now - startTime > SAMPLE_DURATION_MS) {
      measurementActive = false;
      Serial.println("# DONE.");
    }
  }
}