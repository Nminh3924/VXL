#!/bin/bash
# Simple serial logger using cat
# Usage: ./capture_serial.sh [duration_seconds]

PORT="/dev/cu.usbserial-0001"
DURATION=${1:-30}
OUTPUT_DIR="data_logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/serial_log_$TIMESTAMP.txt"

mkdir -p $OUTPUT_DIR

echo "========================================"
echo "ESP32 Serial Capture"
echo "========================================"
echo "Port: $PORT"
echo "Duration: $DURATION seconds"
echo "Output: $OUTPUT_FILE"
echo "========================================"
echo ""
echo "Starting capture in 3 seconds..."
echo "Press Ctrl+C to stop early."
sleep 3

# Configure serial port (try different settings)
stty -f $PORT 115200 cs8 -cstopb -parenb raw -echo 2>/dev/null

# Capture with timeout using subprocess
echo "Capturing..."
(
  cat $PORT &
  PID=$!
  sleep $DURATION
  kill $PID 2>/dev/null
) > "$OUTPUT_FILE" 2>&1

echo ""
echo "========================================"
LINES=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
echo "Captured $LINES lines"
echo "Saved to: $OUTPUT_FILE"
echo "========================================"
