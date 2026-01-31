"""
Serial Logger cho ESP32 - Ho tro macOS va Windows
Doc du lieu tu ESP32 qua Serial va luu vao file txt
"""

import serial
import serial.tools.list_ports
import time
import threading
import sys
import os
from datetime import datetime

# Cau hinh
BAUD_RATE = 115200
OUTPUT_DIR = "data_logs"
running = True
ser = None

def list_ports():
    """Liet ke tat ca cac cong serial"""
    ports = serial.tools.list_ports.comports()
    print("\n--- Cac Cong Co San ---")
    for i, port in enumerate(ports):
        desc = port.description or ""
        hwid = port.hwid or ""
        print(f"[{i}] {port.device}")
        print(f"    Mota: {desc}")
        if 'USB' in hwid.upper() or 'VID' in hwid.upper():
            print(f"    HWID: {hwid}")
    return ports

def find_esp32_port():
    """Tu dong tim cong ESP32 tren macOS va Windows"""
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

def reader_thread(filename):
    """Luong doc du lieu tu Serial va ghi vao file"""
    global running, ser
    print(f"\n[Dang ghi vao {filename}]")
    print("[Nhan Ctrl+C de thoat]\n")
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"# Log Start: {datetime.now()}\n")
        
        while running:
            try:
                if ser and ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        print(line)
                        f.write(line + "\n")
                        f.flush()
                else:
                    time.sleep(0.005)
            except Exception as e:
                if running:
                    print(f"Loi doc: {e}")
                break

def open_serial_macos(port_name):
    """Mo serial port tren macOS"""
    global ser
    
    ser = serial.Serial()
    ser.port = port_name
    ser.baudrate = BAUD_RATE
    ser.timeout = 0.1
    ser.dtr = False
    ser.rts = False
    
    try:
        ser.open()
        time.sleep(0.5)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        print(f"[OK] Da mo cong {port_name}")
        return True
    except Exception as e:
        print(f"[LOI] Khong mo duoc cong: {e}")
        print("[INFO] Thu dung 'screen' hoac 'pio device monitor' thay the")
        return False

def main():
    global running, ser
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("=" * 50)
    print("ESP32 Serial Logger (macOS/Windows)")
    print("=" * 50)
    
    # Tu dong tim cong
    auto_port = find_esp32_port()
    if auto_port:
        print(f"\n[Auto] Tim thay ESP32: {auto_port}")
    
    # Hien thi tat ca cong
    ports = list_ports()
    if not ports:
        print("\nKhong tim thay cong nao!")
        return
    
    # Chon cong
    try:
        if auto_port:
            use_auto = input(f"\nSu dung {auto_port}? (Y/n): ").strip().lower()
            if use_auto != 'n':
                port_name = auto_port
            else:
                idx = int(input("Chon so cong: "))
                port_name = ports[idx].device
        else:
            idx = int(input("\nChon so cong (mac dinh 0): ") or 0)
            port_name = ports[idx].device
    except:
        port_name = ports[0].device
    
    print(f"\n[INFO] Dang mo cong: {port_name}")
    print(f"[INFO] Baud rate: {BAUD_RATE}")
    
    # Tao ten file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"serial_log_{timestamp}.txt")
    
    try:
        # Mo serial port
        if sys.platform == 'darwin':
            if not open_serial_macos(port_name):
                return
        else:
            ser = serial.Serial(port_name, BAUD_RATE, timeout=0.1)
            ser.setDTR(False)
            time.sleep(0.1)
        
        # Bat dau luong doc
        t = threading.Thread(target=reader_thread, args=(filename,))
        t.daemon = True
        t.start()
        
        # Vong lap chinh
        print("\n[READY] Nhan ENTER de bat dau do (gui lenh den ESP32)")
        while True:
            try:
                cmd = input()
                if ser and ser.is_open:
                    ser.write(b'\n')
                    print(">> Da gui ENTER den ESP32")
            except EOFError:
                break
                
    except KeyboardInterrupt:
        print("\n\nDang dung...")
        running = False
    except serial.SerialException as e:
        print(f"\n[LOI SERIAL] {e}")
        print("\nGoi y:")
        print("  1. Kiem tra cap USB")  
        print("  2. Thu: pio device monitor")
        print("  3. Thu: screen /dev/cu.usbserial-0001 115200")
    except Exception as e:
        print(f"\n[LOI] {e}")
    finally:
        running = False
        time.sleep(0.2)
        if ser and ser.is_open:
            ser.close()
            print("[OK] Da dong cong serial")

if __name__ == "__main__":
    main()