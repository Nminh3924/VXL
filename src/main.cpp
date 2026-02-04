#include "MAX30105.h"
#include "config.h"
#include <Arduino.h>
#include <Wire.h>
#include <driver/i2s.h>

// --- ĐỐI TƯỢNG (OBJECTS) ---
MAX30105 ppg;
hw_timer_t *timer = NULL;
portMUX_TYPE timerMux = portMUX_INITIALIZER_UNLOCKED; // Khóa spinlock cho ngắt

// --- CẤU HÌNH (CONFIGURATION) ---
#define SERIAL_BAUD 460800 // Tốc độ truyền Serial cao để tránh nghẽn dữ liệu
#define SAMPLE_DURATION_MS 180000 // Thời gian đo tối đa 3 phút (180s)
#define ECG_BUFFER_SIZE 512       // Kích thước bộ đệm vòng cho ECG
#define PPG_QUEUE_SIZE 512        // Kích thước hàng đợi PPG
#define AUDIO_QUEUE_SIZE 256      // Kích thước hàng đợi Audio

// --- FreeRTOS ---
TaskHandle_t ppgTaskHandle = NULL;
QueueHandle_t ppgQueue = NULL;   // Hàng đợi chứa dữ liệu PPG từ Task -> Loop
QueueHandle_t audioQueue = NULL; // Hàng đợi chứa dữ liệu Audio từ Task -> Loop

// Cấu trúc dữ liệu PPG
struct PPGSample {
  uint32_t ir;
  uint32_t red;
};

// --- BIẾN DÙNG CHUNG (SHARED DATA) ---
volatile int ecgBuffer[ECG_BUFFER_SIZE];
volatile int ecgHead = 0;
volatile int ecgTail = 0;
volatile bool measurementActive = false; // Cờ báo hiệu trạng thái đo

// Các biến đếm để debug tốc độ lấy mẫu
volatile uint32_t ppgSampleCount = 0;
volatile uint32_t audioSampleCount = 0;

// --- CẤU HÌNH I2S AUDIO ---
void initI2S() {
  i2s_config_t i2s_config = {
      .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = 16000, // Tốc độ lấy mẫu phần cứng: 16kHz
      .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
      .channel_format = I2S_CHANNEL_FMT_ONLY_RIGHT, // Chỉ dùng kênh phải
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

// --- NGẮT TIMER (ISR) CHO ECG --- Tần số gọi: 1000Hz (Mỗi 1ms một lần)
void IRAM_ATTR onTimer() {
  if (measurementActive) {
    int val = analogRead(AD8232_OUTPUT_PIN);

    // Vào vùng tới hạn (Critical Section) để ghi buffer an toàn
    portENTER_CRITICAL_ISR(&timerMux);
    int nextHead = (ecgHead + 1) % ECG_BUFFER_SIZE;
    if (nextHead != ecgTail) { // Nếu buffer chưa đầy
      ecgBuffer[ecgHead] = val;
      ecgHead = nextHead;
    }
    portEXIT_CRITICAL_ISR(&timerMux);
  }
}

// --- TÁC VỤ PPG (Chạy trên Core 0) ---
void ppgTask(void *pvParameters) {
  Serial.println("# PPG Task đã bắt đầu trên Core 0");

  while (true) {
    if (measurementActive) {
      ppg.check(); // Kiểm tra dữ liệu mới từ cảm biến

      while (ppg.available()) {
        PPGSample sample;
        sample.ir = ppg.getIR();
        sample.red = ppg.getRed();
        ppg.nextSample(); // Chuyển sang mẫu tiếp theo trong FIFO
        ppgSampleCount++;

        // Gửi dữ liệu vào Queue (không chờ nếu đầy)
        xQueueSend(ppgQueue, &sample, 0);
      }

      taskYIELD(); // Nhường CPU cho các tác vụ khác (quan trọng!)
    } else {
      vTaskDelay(pdMS_TO_TICKS(50)); // Nếu không đo, ngủ 50ms
    }
  }
}

// --- TÁC VỤ AUDIO (Chạy trên Core 0) ---
void audioTask(void *pvParameters) {
  Serial.println("# Audio Task đã bắt đầu trên Core 0");

  int32_t audioBuffer[64];
  size_t bytesRead;

  while (true) {
    if (measurementActive) {
      // 1. Đọc 64 mẫu từ I2S (Hàm này BLOCKING - sẽ chờ đủ 64 mẫu mới chạy
      // tiếp)
      //    Với Fs=16000Hz, thời gian chờ là 64/16000 = 0.004s (4ms)
      //    => Tốc độ vòng lặp tự nhiên là ~250Hz.
      i2s_read(I2S_NUM_0, audioBuffer, sizeof(audioBuffer), &bytesRead,
               portMAX_DELAY);

      if (bytesRead > 0) {
        // 2. Tính trung bình (Downsampling) để giảm dữ liệu
        int32_t sum = 0;
        int numSamples = bytesRead / 4; // Mỗi mẫu I2S là 4 bytes
        for (int i = 0; i < numSamples; i++) {
          sum += (audioBuffer[i] >>
                  14); // Dịch bit để giảm biên độ từ 32-bit về mức vừa phải
        }
        int32_t avgSample = sum / numSamples;

        xQueueSend(audioQueue, &avgSample, 0);
        audioSampleCount++;
      }

      // Đã xoá vTaskDelay(1) ở đây để Tốc độ đạt tối đa theo phần cứng (250Hz)
      // Không cần delay thêm vì i2s_read đã tự động chờ (blocking) rồi.

    } else {
      vTaskDelay(pdMS_TO_TICKS(100)); // Nghỉ lâu hơn khi không đo
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);

  pinMode(AD8232_LO_PLUS_PIN, INPUT);
  pinMode(AD8232_LO_MINUS_PIN, INPUT);

  // Khởi tạo MAX30102
  Wire.begin();

  if (!ppg.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("# Lỗi: Không thể khởi tạo MAX30102!");
  } else {
    // Cấu hình: độ sáng led, mẫu trung bình, mode, sample rate, độ rộng
    // xung,dải ADC
    ppg.setup(0x1F, 1, 2, 1600, 411, 16384);
    Serial.println("# MAX30102 OK:");
  }

  // Khởi tạo I2S Audio
  initI2S();
  Serial.println("# INMP441 Audio OK:");

  // Tạo các hàng đợi (Queue)
  ppgQueue = xQueueCreate(PPG_QUEUE_SIZE, sizeof(PPGSample));
  audioQueue = xQueueCreate(AUDIO_QUEUE_SIZE, sizeof(int32_t));

  // Tạo tác vụ PPG (Core 0, ưu tiên cao hơn chút)
  xTaskCreatePinnedToCore(ppgTask, "PPG_Task", 4096, NULL,
                          configMAX_PRIORITIES - 1, &ppgTaskHandle, 0);

  // Tạo tác vụ Audio (Core 0, ưu tiên thấp hơn)
  xTaskCreatePinnedToCore(audioTask, "Audio_Task", 4096, NULL,
                          configMAX_PRIORITIES - 2, NULL, 0);

  // Khởi tạo Timer cho ECG (500Hz -> Sửa thành 1000Hz)
  timer = timerBegin(0, 80, true);             // Timer 0, div 80 (1MHz tick)
  timerAttachInterrupt(timer, &onTimer, true); // Gán hàm ngắt onTimer
  timerAlarmWrite(timer, 1000, true); // Ngắt mỗi 1000 ticks (1ms) -> 1000Hz
  timerAlarmEnable(timer);

  Serial.println("# SẴN SÀNG: ECG@1000Hz, PPG@~160Hz, Audio@250Hz");

  // TỰ ĐỘNG BẮT ĐẦU ĐO
  Serial.println("# TỰ ĐỘNG BẮT ĐẦU ĐO...");
  ecgHead = 0;
  ecgTail = 0;
  ppgSampleCount = 0;
  audioSampleCount = 0;
  xQueueReset(ppgQueue);
  xQueueReset(audioQueue);
  measurementActive = true;
}

void loop() {
  static unsigned long startTime = millis();
  static unsigned long lastLog = 0;
  static uint32_t lastPPGCount = 0;
  static uint32_t lastAudioCount = 0;

  // Đã xóa phần kiểm tra Serial.available() để tự động chạy

  if (measurementActive) {
    unsigned long now = millis();

    // 1. Đọc dữ liệu PPG từ Queue và in ra
    PPGSample sample;
    while (xQueueReceive(ppgQueue, &sample, 0) == pdTRUE) {
      Serial.print(">ppg_ir_raw:");
      Serial.println(sample.ir);
      Serial.print(">ppg_red_raw:");
      Serial.println(sample.red);
    }

    // 2. Đọc dữ liệu Audio từ Queue và in ra
    int32_t audioSample;
    while (xQueueReceive(audioQueue, &audioSample, 0) == pdTRUE) {
      Serial.print(">audio_raw:");
      Serial.println(audioSample);
    }

    // 3. Đọc dữ liệu ECG từ Buffer vòng và in ra
    int ecgPrinted = 0;
    while (ecgPrinted < 50) { // Giới hạn số lượng in mỗi vòng lặp để tránh treo
      int val = -1;
      portENTER_CRITICAL(&timerMux); // Khóa ngắt để đọc an toàn
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
        break; // Hết dữ liệu
      }
    }

    // 4. Log thời gian chạy và tốc độ lấy mẫu (Mỗi 1 giây)
    if (now - lastLog >= 1000) {
      uint32_t ppgDelta = ppgSampleCount - lastPPGCount;
      uint32_t audioDelta = audioSampleCount - lastAudioCount;
      lastPPGCount = ppgSampleCount;
      lastAudioCount = audioSampleCount;

      Serial.print(">runtime_sec:");
      Serial.println((now - startTime) / 1000);
      Serial.print("# Tốc độ thực tế: PPG=");
      Serial.print(ppgDelta);
      Serial.print("Hz, Audio=");
      Serial.print(audioDelta);
      Serial.println("Hz");

      lastLog = now;
    }

    // Kiểm tra thời gian đo, dừng nếu quá hạn
    if (now - startTime > SAMPLE_DURATION_MS) {
      measurementActive = false;
      Serial.println("# ĐÃ XONG.");
    }
  }
}
