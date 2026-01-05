"""
Serial Data Logger for ESP32
Reads serial data and saves to timestamped file
"""

import serial
import serial.tools.list_ports
import time
from datetime import datetime
import os

# Configuration
BAUD_RATE = 115200
DURATION_SECONDS = 30  # Recording duration (30 seconds)
OUTPUT_DIR = "data_logs"
DEFAULT_PORT = "COM5"  # Your ESP32 port

def list_ports():
    """List available COM ports"""
    ports = serial.tools.list_ports.comports()
    print("\nAvailable COM ports:")
    for i, port in enumerate(ports):
        print(f"  [{i}] {port.device} - {port.description}")
    return ports

def record_serial(port_name, duration, filename):
    """Record serial data for specified duration"""
    print(f"\nRecording from {port_name} for {duration} seconds...")
    print(f"Output file: {filename}")
    print("-" * 50)
    
    try:
        ser = serial.Serial(port_name, BAUD_RATE, timeout=1)
        time.sleep(2)  # Wait for ESP32 to reset
        
        # Clear buffer
        ser.flushInput()
        
        start_time = time.time()
        lines = []
        
        while (time.time() - start_time) < duration:
            if ser.in_waiting:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        lines.append(line)
                        print(line)  # Also print to console
                except:
                    pass
        
        ser.close()
        
        # Save to file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Recording from {port_name}\n")
            f.write(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Duration: {duration} seconds\n")
            f.write(f"# Baud rate: {BAUD_RATE}\n")
            f.write(f"# Total lines: {len(lines)}\n")
            f.write("#" + "-" * 50 + "\n")
            for line in lines:
                f.write(line + "\n")
        
        print("-" * 50)
        print(f"Saved {len(lines)} lines to {filename}")
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    print("=" * 50)
    print("ESP32 Serial Data Logger")
    print("=" * 50)
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Use default port (COM5)
    port_name = DEFAULT_PORT
    print(f"\nUsing port: {port_name}")
    print(f"Recording for {DURATION_SECONDS} seconds...")
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"serial_log_{timestamp}.txt")
    
    # Record
    record_serial(port_name, DURATION_SECONDS, filename)
    
    print("\nDone! File saved in data_logs/ folder.")

if __name__ == "__main__":
    main()
