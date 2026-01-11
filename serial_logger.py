"""
Ghi dữ liệu Serial từ ESP32
Tự động xóa file cũ trước khi ghi mới
"""

import serial
import serial.tools.list_ports
import time
from datetime import datetime
import os
import glob

BAUD_RATE = 115200
DURATION_SECONDS = 60
OUTPUT_DIR = "data_logs"

def list_ports():
    ports = serial.tools.list_ports.comports()
    print("\nCac cong co san:")
    for i, port in enumerate(ports):
        print(f"  [{i}] {port.device} - {port.description}")
    return ports

def find_esp32_port():
    ports = list_ports()
    for port in ports:
        desc = port.description.lower()
        if 'cp210' in desc or 'ch340' in desc or 'usb' in desc:
            return port.device
    return None

def delete_old_logs():
    if os.path.exists(OUTPUT_DIR):
        old_files = glob.glob(os.path.join(OUTPUT_DIR, "serial_log_*.txt"))
        for f in old_files:
            try:
                os.remove(f)
                print(f"  Da xoa: {os.path.basename(f)}")
            except:
                pass
        if old_files:
            print(f"  -> Da xoa {len(old_files)} file cu")

def record_serial(port_name, duration, filename):
    print(f"\nGhi du lieu tu {port_name}")
    print(f"Thoi gian: {duration} giay")
    print("-" * 40)
    
    try:
        ser = serial.Serial()
        ser.port = port_name
        ser.baudrate = BAUD_RATE
        ser.timeout = 0.1
        ser.dsrdtr = False
        ser.rtscts = False
        ser.dtr = False
        ser.rts = False
        ser.open()
        ser.setDTR(False)
        ser.setRTS(False)
        
        print("Dang kiem tra du lieu...")
        time.sleep(0.5)
        
        test_lines = []
        test_start = time.time()
        while time.time() - test_start < 3:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    test_lines.append(line)
                    if len(test_lines) >= 5:
                        break
        
        if test_lines:
            print(f"Da phat hien du lieu!")
        else:
            print("Chua co du lieu, van thu ghi...")
        
        ser.reset_input_buffer()
        
        print(f"Dang ghi trong {duration} giay...")
        start_time = time.time()
        lines = []
        last_print = 0
        
        while (time.time() - start_time) < duration:
            while ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        lines.append(line)
                except:
                    pass
            
            elapsed = int(time.time() - start_time)
            if elapsed != last_print and elapsed % 10 == 0:
                last_print = elapsed
                remaining = duration - elapsed
                print(f"  Con {remaining}s... ({len(lines)} dong)")
            
            time.sleep(0.01)
        
        ser.close()
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Ghi tu {port_name}\n")
            f.write(f"# Ngay: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Thoi gian: {duration} giay\n")
            f.write(f"# Tong dong: {len(lines)}\n")
            f.write("#" + "-" * 40 + "\n")
            for line in lines:
                f.write(line + "\n")
        
        print(f"\nDa luu {len(lines)} dong vao {filename}")
        return len(lines) > 0
        
    except Exception as e:
        print(f"Loi: {e}")
        return False

def main():
    print("=" * 40)
    print("ESP32 Serial Logger v4.0")
    print("=" * 40)
    
    print("\nDang xoa file cu...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    delete_old_logs()
    
    port_name = find_esp32_port()
    
    if not port_name:
        ports = list_ports()
        if not ports:
            print("\nKhong tim thay cong!")
            return
        try:
            idx = int(input("\nChon so cong: "))
            port_name = ports[idx].device
        except:
            port_name = ports[0].device
    
    print(f"\nCong: {port_name}")
    print(f"Thoi gian: {DURATION_SECONDS} giay")
    
    input("\nNhan ENTER de bat dau...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"serial_log_{timestamp}.txt")
    
    success = record_serial(port_name, DURATION_SECONDS, filename)
    
    if success:
        print("\nDe ve bieu do, chay:")
        print("  ./venv/bin/python plot_data.py")

if __name__ == "__main__":
    main()
