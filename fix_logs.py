
import os
import re

LOG_DIR = "data_logs"

def fix_file(filepath):
    print(f"Processing {filepath}...")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")
        return
    
    new_lines = []
    ecg_count = 0
    modified = False
    
    for line in lines:
        if line.startswith(">ecg_raw:"):
            ecg_count += 1
            new_lines.append(line)
        elif line.startswith("# Rates:"):
            # Check if ECG is already in there
            if "ECG=" in line:
                new_lines.append(line)
                ecg_count = 0 
            else:
                # Insert ECG entry
                # Current: # Rates: PPG=160Hz, Audio=250Hz
                # New:     # Rates: ECG=XXXHz, PPG=160Hz, Audio=250Hz
                parts = line.strip().split("# Rates: ")
                if len(parts) > 1:
                    content = parts[1]
                    new_content = f"ECG={ecg_count}Hz, {content}"
                    new_lines.append(f"# Rates: {new_content}\n")
                    modified = True
                else:
                    new_lines.append(line)
                
                ecg_count = 0 # Reset for next second
        else:
            new_lines.append(line)
            
    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"  [FIXED] Updated rates in {filepath}")
    else:
        print(f"  [SKIP] No changes needed for {filepath}")

if __name__ == "__main__":
    if not os.path.exists(LOG_DIR):
        print(f"Directory {LOG_DIR} not found.")
    else:
        print(f"Scanning {LOG_DIR}...")
        for filename in os.listdir(LOG_DIR):
            if filename.endswith(".txt") and filename.startswith("serial_log_"):
                fix_file(os.path.join(LOG_DIR, filename))
