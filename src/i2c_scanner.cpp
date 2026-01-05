// I2C Scanner - Kiểm tra MAX30102 có bị detect không
// Upload file này, mở Serial Monitor 115200

#include <Arduino.h>
#include <Wire.h>

void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(21, 22); // SDA=21, SCL=22

  Serial.println("\n================================");
  Serial.println("I2C Scanner - Finding devices...");
  Serial.println("================================");
}

void loop() {
  byte count = 0;

  Serial.println("\nScanning I2C bus...");

  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    byte error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Found device at 0x");
      if (addr < 16)
        Serial.print("0");
      Serial.print(addr, HEX);

      if (addr == 0x57) {
        Serial.println(" <-- MAX30102!");
      } else {
        Serial.println();
      }
      count++;
    }
  }

  if (count == 0) {
    Serial.println("No I2C devices found!");
    Serial.println("Check wiring: SDA->GPIO21, SCL->GPIO22, GND->GND");
  } else {
    Serial.print("Found ");
    Serial.print(count);
    Serial.println(" device(s)");
  }

  Serial.println("\nWaiting 5 seconds...");
  delay(5000);
}
