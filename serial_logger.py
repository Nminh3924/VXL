import serial
import serial.tools.list_ports
import time
import threading
import sys
import os
from datetime import datetime

# Cấu hình
BAUD_RATE = 921600
OUTPUT_DIR = "data_logs"
running = True
ser = None

def list_ports():
    ports = serial.tools.list_ports.comports()
    print("\n--- Available Ports ---")
    for i, port in enumerate(ports):
        print(f"[{i}] {port.device} - {port.description}")
    return ports

def reader_thread(filename):
    """Luồng đọc dữ liệu từ Serial và ghi vào file"""
    global running, ser
    print(f"\n[Logging to {filename}]")
    print("[Press ENTER to send commands to ESP32]")
    print("[Press Ctrl+C to exit]\n")
    
    with open(filename, 'w', encoding='utf-8') as f:
        # Header
        f.write(f"# Log Start: {datetime.now()}\n")
        
        while running:
            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        # Print to console
                        print(line)
                        # Write to file
                        f.write(line + "\n")
                        f.flush()
                else:
                    time.sleep(0.005)
            except Exception as e:
                print(f"Error reading: {e}")
                break

def main():
    global running, ser
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    ports = list_ports()
    if not ports:
        print("No ports found!")
        return

    try:
        idx = int(input("\nSelect Port Index (default 0): ") or 0)
        port_name = ports[idx].device
    except:
        port_name = ports[0].device

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"serial_log_{timestamp}.txt")

    try:
        ser = serial.Serial(port_name, BAUD_RATE, timeout=0.1)
        # Reset ESP32
        ser.setDTR(False)
        time.sleep(0.1)
        ser.setDTR(True) # Toggle might reset some boards
        
        # Start reader thread
        t = threading.Thread(target=reader_thread, args=(filename,))
        t.daemon = True
        t.start()
        
        # Main loop: Listen for keyboard input and send to Serial
        while True:
            cmd = input() # Blocking wait for Enter
            if ser and ser.is_open:
                ser.write(b'\n') # Send newline to trigger ESP32
                print(">> Sent ENTER to ESP32")
                
    except KeyboardInterrupt:
        print("\nStopping...")
        running = False
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if ser: ser.close()

if __name__ == "__main__":
    main()
