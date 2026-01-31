"""
Serial Logger cho ESP32 - High-Throughput Version
Tối ưu cho tốc độ cao (500Hz+ signals)
"""

import serial
import serial.tools.list_ports
import time
import threading
import sys
import os
from datetime import datetime

# Cấu hình
BAUD_RATE = 460800
OUTPUT_DIR = "data_logs"
FLUSH_INTERVAL = 1.0  # Flush mỗi 1 giây thay vì mỗi dòng
PRINT_EVERY_N = 100   # Chỉ in 1/100 dòng ra console (giảm overhead)
running = True
ser = None
line_count = 0
data_count = {"ecg": 0, "ppg": 0, "audio": 0}

def list_ports():
    """Liệt kê tất cả các cổng serial"""
    ports = serial.tools.list_ports.comports()
    print("\n--- Các Cổng Có Sẵn ---")
    for i, port in enumerate(ports):
        desc = port.description or ""
        hwid = port.hwid or ""
        print(f"[{i}] {port.device}")
        print(f"    Mô tả: {desc}")
        if 'USB' in hwid.upper() or 'VID' in hwid.upper():
            print(f"    HWID: {hwid}")
    return ports

def find_esp32_port():
    """Tự động tìm cổng ESP32 trên macOS và Windows"""
    ports = serial.tools.list_ports.comports()
    
    for port in ports:
        device = port.device.lower()
        desc = (port.description or "").lower()
        
        # macOS
        if sys.platform == 'darwin':
            if 'cu.usbserial' in device or 'cu.slab' in device or 'cu.wchusbserial' in device:
                return port.device
        # Windows
        elif sys.platform == 'win32':
            if 'com' in device and ('cp210' in desc or 'ch340' in desc or 'usb' in desc):
                return port.device
        # Linux
        else:
            if 'ttyusb' in device or 'ttyacm' in device:
                return port.device
    
    return None

def reader_thread_fast(filename):
    """Luồng đọc dữ liệu tối ưu - High Throughput"""
    global running, ser, line_count, data_count
    print(f"\n[Đang ghi vào {filename}]")
    print("[Nhấn Ctrl+C để thoát]\n")
    
    buffer = ""
    last_flush = time.time()
    last_stats = time.time()
    
    with open(filename, 'w', encoding='utf-8', buffering=8192) as f:
        f.write(f"# Log Start: {datetime.now()}\n")
        
        while running:
            try:
                # Đọc tất cả bytes có sẵn (không blocking)
                if ser and ser.in_waiting > 0:
                    chunk = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                    buffer += chunk
                    
                    # Xử lý từng dòng hoàn chỉnh
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line:
                            # Ghi vào file (không flush ngay)
                            f.write(line + "\n")
                            line_count += 1
                            
                            # Đếm loại dữ liệu
                            if line.startswith(">ecg"):
                                data_count["ecg"] += 1
                            elif line.startswith(">ppg"):
                                data_count["ppg"] += 1
                            elif line.startswith(">audio"):
                                data_count["audio"] += 1
                            
                            # In mẫu (giảm overhead console)
                            if line_count % PRINT_EVERY_N == 0:
                                print(f"[{line_count}] {line[:60]}...")
                            
                            # Tự động thoát
                            if "# DONE." in line:
                                print(f"\n[INFO] Measurement Complete!")
                                print(f"[STATS] ECG: {data_count['ecg']}, PPG: {data_count['ppg']//2} pairs")
                                running = False
                                break
                    
                    # Flush định kỳ
                    now = time.time()
                    if now - last_flush >= FLUSH_INTERVAL:
                        f.flush()
                        last_flush = now
                    
                    # In thống kê định kỳ
                    if now - last_stats >= 5.0:
                        elapsed = now - last_stats
                        ecg_rate = data_count["ecg"] / elapsed if elapsed > 0 else 0
                        ppg_rate = (data_count["ppg"] / 2) / elapsed if elapsed > 0 else 0
                        print(f"[LIVE] ECG: ~{ecg_rate:.0f} Hz, PPG: ~{ppg_rate:.0f} Hz")
                        data_count = {"ecg": 0, "ppg": 0, "audio": 0}
                        last_stats = now
                else:
                    time.sleep(0.001)  # Giảm sleep time, tăng responsiveness
                    
            except Exception as e:
                if running:
                    print(f"Lỗi đọc: {e}")
                break
        
        # Final flush
        f.flush()

def open_serial_macos(port_name):
    """Mở serial port trên macOS"""
    global ser
    
    ser = serial.Serial()
    ser.port = port_name
    ser.baudrate = BAUD_RATE
    ser.timeout = 0.01  # Giảm timeout
    ser.dtr = False
    ser.rts = False
    
    try:
        ser.open()
        time.sleep(0.5)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        print(f"[OK] Đã mở cổng {port_name}")
        return True
    except Exception as e:
        print(f"[LỖI] Không mở được cổng: {e}")
        print("[INFO] Thử dùng 'screen' hoặc 'pio device monitor' thay thế")
        return False

def main():
    global running, ser
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("=" * 50)
    print("ESP32 Serial Logger - HIGH THROUGHPUT MODE")
    print("=" * 50)
    
    # Tự động tìm cổng
    auto_port = find_esp32_port()
    if auto_port:
        print(f"\n[Auto] Tìm thấy ESP32: {auto_port}")
    
    # Hiển thị tất cả cổng
    ports = list_ports()
    if not ports:
        print("\nKhông tìm thấy cổng nào!")
        return
    
    # Chọn cổng
    try:
        if auto_port:
            use_auto = input(f"\nSử dụng {auto_port}? (Y/n): ").strip().lower()
            if use_auto != 'n':
                port_name = auto_port
            else:
                idx = int(input("Chọn số cổng: "))
                port_name = ports[idx].device
        else:
            idx = int(input("\nChọn số cổng (mặc định 0): ") or 0)
            port_name = ports[idx].device
    except:
        port_name = ports[0].device
    
    print(f"\n[INFO] Đang mở cổng: {port_name}")
    print(f"[INFO] Baud rate: {BAUD_RATE}")
    
    # Tạo tên file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"serial_log_{timestamp}.txt")
    
    try:
        # Mở serial port
        if sys.platform == 'darwin':
            if not open_serial_macos(port_name):
                return
        else:
            ser = serial.Serial(port_name, BAUD_RATE, timeout=0.01)
            ser.setDTR(False)
            time.sleep(0.1)
        
        # Bắt đầu luồng đọc
        t = threading.Thread(target=reader_thread_fast, args=(filename,))
        t.daemon = True
        t.start()
        
        # Vòng lặp chính
        print("\n[READY] Nhấn ENTER để bắt đầu đo (gửi lệnh đến ESP32)")
        while running:
            try:
                cmd = input()
                if ser and ser.is_open:
                    ser.write(b'\n')
                    print(">> Đã gửi ENTER đến ESP32")
            except EOFError:
                break
                
    except KeyboardInterrupt:
        print("\n\nĐang dừng...")
        running = False
    except serial.SerialException as e:
        print(f"\n[LỖI SERIAL] {e}")
        print("\nGợi ý:")
        print("  1. Kiểm tra cáp USB")  
        print("  2. Thử: pio device monitor")
        print("  3. Thử: screen /dev/cu.usbserial-0001 460800")
    except Exception as e:
        print(f"\n[LỖI] {e}")
    finally:
        running = False
        time.sleep(0.2)
        if ser and ser.is_open:
            ser.close()
            print("[OK] Đã đóng cổng serial")

if __name__ == "__main__":
    main()