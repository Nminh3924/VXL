#include "MAX30105.h"
#include "config.h"
#include <Arduino.h>
#include <Wire.h>
#include <driver/i2s.h>

// KHAI BÁO CÁC THIẾT BỊ VÀ CÔNG CỤ QUẢN LÝ
MAX30105 ppg; // Đây là biến đại diện cho cảm biến đo nhịp tim/Oxy MAX30102
hw_timer_t *timer = NULL; // Biến dùng để tạo ra một "đồng hồ" ngắt quãng chính xác
portMUX_TYPE timerMux =
    portMUX_INITIALIZER_UNLOCKED; // Công cụ giúp tránh xung đột khi ghi dữ liệu trong lúc máy đang bận

// CÁC THÔNG SỐ CÀI ĐẶT CHO HỆ THỐNG
#define SERIAL_BAUD 460800 // Tốc độ gửi dữ liệu lên máy tính (rất nhanh để không bị nghẽn)
#define SAMPLE_DURATION_MS 180000 // Sau 3 phút (180.000ms) máy sẽ dừng đo
#define ECG_BUFFER_SIZE 512       // Chỗ chứa tạm cho dữ liệu Tim (ECG)
#define PPG_QUEUE_SIZE 512        // Chỗ chứa tạm cho dữ liệu Mạch (PPG)
#define AUDIO_QUEUE_SIZE 256      // Chỗ chứa tạm cho dữ liệu Âm thanh

// CÁC BIẾN QUẢN LÝ TÁC VỤ (TASK) VÀ HÀNG ĐỢI (QUEUE)
TaskHandle_t ppgTaskHandle = NULL; // Quản lý việc đo mạch
QueueHandle_t ppgQueue = NULL; // Cái "ống" dẫn dữ liệu mạch đi in ra màn hình
QueueHandle_t audioQueue = NULL; // Cái "ống" dẫn dữ liệu âm thanh đi in ra màn hình

// Cách sắp xếp dữ liệu cho một mẫu tin PPG (gồm tia Hồng ngoại và tia Đỏ)
struct PPGSample {
  uint32_t ir;
  uint32_t red;
};

// CÁC BIẾN DÙNG CHUNG TRONG TOÀN BỘ CHƯƠNG TRÌNH
volatile int ecgBuffer[ECG_BUFFER_SIZE]; // Bộ nhớ tạm chứa tín hiệu tim
volatile int ecgHead = 0;                // Vị trí đang ghi dữ liệu vào
volatile int ecgTail = 0;                // Vị trí đang đọc dữ liệu ra
volatile bool measurementActive = false; // Biến kiểm tra xem máy có đang đo hay không

// Các biến dùng để đếm xem mỗi giây máy đo được bao nhiêu mẫu (để kiểm tra tốc độ)
volatile uint32_t ppgSampleCount = 0;
volatile uint32_t audioSampleCount = 0;

// HÀM KHỞI TẠO ÂM THANH (I2S)
void initI2S() {
  i2s_config_t i2s_config = {
      .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = 16000, // Máy sẽ thu âm ở tốc độ 16.000 lần mỗi giây
      .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT, // Độ phân giải âm thanh 32-bit
      .channel_format = I2S_CHANNEL_FMT_ONLY_RIGHT, // Chỉ thu âm ở mic bên phải
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 4,
      .dma_buf_len = 256,
      .use_apll = false,
      .tx_desc_auto_clear = false,
      .fixed_mclk = 0};

  // Cài đặt các chân cắm cho Mic INMP441
  i2s_pin_config_t pin_config = {.bck_io_num = INMP441_SCK_PIN,
                                 .ws_io_num = INMP441_WS_PIN,
                                 .data_out_num = I2S_PIN_NO_CHANGE,
                                 .data_in_num = INMP441_SD_PIN};

  i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pin_config);
  i2s_zero_dma_buffer(I2S_NUM_0);
}

// HÀM TỰ ĐỘNG CHẠY KHI ĐẾN GIỜ (NGẮT TIMER) - DÀNH CHO ECG
// Cái này như một cái chuông báo thức, cứ mỗi 1ms (1000 lần/giây) nó sẽ rung đến máy đo tim một lần
void IRAM_ATTR onTimer() {
  if (measurementActive) {
    int val = analogRead(AD8232_OUTPUT_PIN); // Đọc giá trị điện tim từ chân cắm

    // Bảo vệ dữ liệu không bị ghi đè sai cách
    portENTER_CRITICAL_ISR(&timerMux);
    int nextHead = (ecgHead + 1) % ECG_BUFFER_SIZE;
    if (nextHead != ecgTail) { // Nếu còn chỗ trống thì mới ghi vào
      ecgBuffer[ecgHead] = val;
      ecgHead = nextHead;
    }
    portEXIT_CRITICAL_ISR(&timerMux);
  }
}

// TÁC VỤ ĐO MẠCH (PPG) - Chạy ngầm liên tục
void ppgTask(void *pvParameters) {
  Serial.println("# PPG Task đã bắt đầu trên Core 0");

  while (true) {
    if (measurementActive) {
      ppg.check(); // Bảo cảm biến kiểm tra xem có dữ liệu mới chưa

      while (ppg.available()) { // Nếu có dữ liệu mới thì lấy ra ngay
        PPGSample sample;
        sample.ir = ppg.getIR();
        sample.red = ppg.getRed();
        ppg.nextSample(); // Chuẩn bị cho mẫu tiếp theo
        ppgSampleCount++;

        // Gửi dữ liệu vào hàng đợi để Loop chính lấy ra in
        xQueueSend(ppgQueue, &sample, 0);
      }

      taskYIELD(); // Tạm nghỉ một chút để các việc khác cùng chạy
    } else {
      vTaskDelay(pdMS_TO_TICKS(50)); // Nếu chưa đo thì ngủ 50ms cho đỡ tốn điện
    }
  }
}

// TÁC VỤ THU ÂM (AUDIO) - Chạy ngầm liên tục
void audioTask(void *pvParameters) {
  Serial.println("# Audio Task đã bắt đầu trên Core 0");

  int32_t audioBuffer[64]; // Bộ nhớ tạm chứa 64 mẫu âm thanh
  size_t bytesRead;

  while (true) {
    if (measurementActive) {
      // 1. Máy đứng đợi cho đến khi thu đủ 64 mẫu âm thanh từ Mic
      // Vì Mic thu 16.000 mẫu/giây nên chỉ mất khoảng 4ms là thu đủ 64 mẫu này
      i2s_read(I2S_NUM_0, audioBuffer, sizeof(audioBuffer), &bytesRead,
               portMAX_DELAY);

      if (bytesRead > 0) {
        // 2. Tính trung bình cộng của 64 mẫu này để ra 1 con số đại diện (Downsampling) Việc này giúp dữ liệu gọn nhẹ hơn khi gửi lên máy tính
        int32_t sum = 0;
        int numSamples = bytesRead / 4;
        for (int i = 0; i < numSamples; i++) {
          sum += (audioBuffer[i] >> 14); // Giảm độ lớn của số 32-bit cho dễ xử lý
        }
        int32_t avgSample = sum / numSamples;

        // Gửi con số trung bình này vào hàng đợi
        xQueueSend(audioQueue, &avgSample, 0);
        audioSampleCount++;
      }
      // Task này không cần lệnh nghỉ (delay) vì hàm i2s_read ở trên đã tự đợi rồi
    } else {
      vTaskDelay(pdMS_TO_TICKS(100)); // Nghỉ 100ms khi chưa bắt đầu đo
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD); // Mở cổng giao tiếp với máy tính

  // Thiết lập các chân cắm cho thiết bị đo ECG
  pinMode(AD8232_LO_PLUS_PIN, INPUT);
  pinMode(AD8232_LO_MINUS_PIN, INPUT);

  // Khởi động kết nối I2C và cảm biến đo mạch MAX30102
  Wire.begin();
  if (!ppg.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("# LỖI: Không tìm thấy cảm biến nhịp tim MAX30102!");
  } else {
    // Cấu hình: độ sáng led, mẫu trung bình, mode, sample rate, độ rộng xung,dải ADC. Cài đặt thông số cho cảm biến: tốc độ 1600Hz, lấy trung bình 1 mẫu
    ppg.setup(0x1F, 1, 2, 1600, 411, 16384);
    Serial.println("# Cảm biến MAX30102 đã sẵn sàng!");
  }

  // Khởi động Mic thu âm
  initI2S();
  Serial.println("# Microphone đã sẵn sàng!");

  // Tạo ra các "ống dẫn" dữ liệu (Queue)
  ppgQueue = xQueueCreate(PPG_QUEUE_SIZE, sizeof(PPGSample));
  audioQueue = xQueueCreate(AUDIO_QUEUE_SIZE, sizeof(int32_t));

  // Kích hoạt các tác vụ chạy ngầm trên nhân (Core) 0 của chip ESP32
  xTaskCreatePinnedToCore(ppgTask, "PPG_Task", 4096, NULL,
                          configMAX_PRIORITIES - 1, &ppgTaskHandle, 0);
  xTaskCreatePinnedToCore(audioTask, "Audio_Task", 4096, NULL,
                          configMAX_PRIORITIES - 2, NULL, 0);

  // Thiết lập đồng hồ báo thức (Timer) để máy đo tim đúng 1000 lần mỗi giây
  timer = timerBegin(0, 80, true);             // Timer 0, div 80 (1MHz tick)
  timerAttachInterrupt(timer, &onTimer, true); // Gán hàm ngắt onTimer
  timerAlarmWrite(timer, 1000, true); // Ngắt mỗi 1000 ticks (1ms) -> 1000Hz
  timerAlarmEnable(timer);

  Serial.println("# HỆ THỐNG ĐÃ SẴN SÀNG!");

  // TỰ ĐỘNG BẮT ĐẦU ĐO LUÔN
  Serial.println("# ĐANG BẮT ĐẦU ĐO DỮ LIỆU...");
  ecgHead = 0;
  ecgTail = 0;
  ppgSampleCount = 0;
  audioSampleCount = 0;
  xQueueReset(ppgQueue);
  xQueueReset(audioQueue);
  measurementActive = true; // Bật cờ cho phép các tác vụ bắt đầu làm việc
}

// VÒNG LẶP CHÍNH (Chạy lặp đi lặp lại liên tục)
void loop() {
  static unsigned long startTime = millis(); // Lưu lại thời điểm bắt đầu
  static unsigned long lastLog = 0; // Dùng để canh giờ in thông báo mỗi giây
  static uint32_t lastPPGCount = 0;
  static uint32_t lastAudioCount = 0;

  if (measurementActive) {
    unsigned long now = millis(); // Thời gian hiện tại

    // 1. Kiểm tra xem có dữ liệu Mạch (PPG) mới không, nếu có thì in ra
    PPGSample sample;
    while (xQueueReceive(ppgQueue, &sample, 0) == pdTRUE) {
      Serial.print(">ppg_ir_raw:");
      Serial.println(sample.ir);
      Serial.print(">ppg_red_raw:");
      Serial.println(sample.red);
    }

    // 2. Kiểm tra xem có dữ liệu Âm thanh mới không, nếu có thì in ra
    int32_t audioSample;
    while (xQueueReceive(audioQueue, &audioSample, 0) == pdTRUE) {
      Serial.print(">audio_raw:");
      Serial.println(audioSample);
    }

    // 3. Kiểm tra xem có dữ liệu Tim (ECG) mới không, nếu có thì in ra
    int ecgPrinted = 0;
    while (ecgPrinted < 50) { // Giới hạn số lượng in mỗi vòng lặp để tránh treo
      int val = -1;
      portENTER_CRITICAL(&timerMux); // Khóa lại để lấy dữ liệu an toàn
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
        break; // Hết dữ liệu để in
      }
    }

    // 4. Cứ mỗi 1 giây thì in ra tốc độ đo được thực tế để kiểm tra
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

    // Nếu đã đo đủ thời gian (3 phút) thì dừng lại
    if (now - startTime > SAMPLE_DURATION_MS) {
      measurementActive = false;
      Serial.println("# QUÁ TRÌNH ĐO ĐÃ KẾT THÚC.");
    }
  }
}
