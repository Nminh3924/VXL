"""
Ve bieu do du lieu cam bien sinh ly ESP32
"""

import os
import glob
import re
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = "data_logs"
OUTPUT_DIR = "plots"

def parse_log_file(filepath):
    data = {
        'ecg_raw': [], 'ecg_filtered': [], 'ecg_wavelet': [],
        'ppg_ir_raw': [], 'ppg_ir_filtered': [], 'ppg_ir_wavelet': [],
        'heartrate': [], 'spo2': [], 'finger_detected': [],
        'red_dc': [], 'ir_dc': [],
        'audio_raw': [], 'audio_filtered': [],
        'ecg_saturated': [],
    }
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            if line.startswith('>'):
                match = re.match(r'>(\w+):(-?[\d.]+)', line)
                if match:
                    name = match.group(1)
                    try:
                        value = float(match.group(2))
                        if name in data:
                            data[name].append(value)
                    except:
                        pass
    
    for key in data:
        data[key] = np.array(data[key])
    
    return data

def find_latest_log():
    pattern = os.path.join(DATA_DIR, "serial_log_*.txt")
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def create_plots(data, output_file, log_filename):
    fig, axes = plt.subplots(4, 2, figsize=(14, 12))
    fig.suptitle(f'Du Lieu Cam Bien Tim Mach\n({os.path.basename(log_filename)})', 
                 fontsize=14, fontweight='bold')
    
    colors = {'raw': '#e74c3c', 'filtered': '#3498db', 'wavelet': '#2ecc71'}
    
    # ECG Raw
    ax = axes[0, 0]
    if len(data['ecg_raw']) > 0:
        ax.plot(data['ecg_raw'], color=colors['raw'], linewidth=0.5)
        ax.set_title('ECG Raw')
        ax.set_xlabel('Mau')
        ax.set_ylabel('Gia tri')
        ax.grid(True, alpha=0.3)
    
    # ECG Filtered
    ax = axes[0, 1]
    if len(data['ecg_filtered']) > 0:
        ax.plot(data['ecg_filtered'], color=colors['filtered'], linewidth=0.8, label='Filtered')
    if len(data['ecg_wavelet']) > 0:
        ax.plot(data['ecg_wavelet'], color=colors['wavelet'], linewidth=0.8, alpha=0.7, label='Wavelet')
    ax.set_title('ECG Filtered & Wavelet')
    ax.set_xlabel('Mau')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # PPG Raw
    ax = axes[1, 0]
    if len(data['ppg_ir_raw']) > 0:
        ax.plot(data['ppg_ir_raw'], color=colors['raw'], linewidth=0.5)
        ax.set_title('PPG IR Raw')
        ax.set_xlabel('Mau')
        ax.grid(True, alpha=0.3)
    
    # PPG Filtered
    ax = axes[1, 1]
    if len(data['ppg_ir_filtered']) > 0:
        ax.plot(data['ppg_ir_filtered'], color=colors['filtered'], linewidth=0.8, label='Filtered')
    if len(data['ppg_ir_wavelet']) > 0:
        ax.plot(data['ppg_ir_wavelet'], color=colors['wavelet'], linewidth=0.8, alpha=0.7, label='Wavelet')
    ax.set_title('PPG IR Filtered & Wavelet')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Heart Rate
    ax = axes[2, 0]
    if len(data['heartrate']) > 0:
        valid_hr = data['heartrate'][data['heartrate'] > 0]
        ax.plot(data['heartrate'], color='#9b59b6', linewidth=1.5, marker='o', markersize=2)
        if len(valid_hr) > 0:
            avg_hr = np.mean(valid_hr)
            ax.axhline(y=avg_hr, color='red', linestyle='--', alpha=0.7, 
                       label=f'TB: {avg_hr:.1f} BPM')
            ax.legend()
        ax.set_title('Nhip Tim (BPM)')
        ax.set_ylim([40, 150])
        ax.grid(True, alpha=0.3)
    
    # SpO2
    ax = axes[2, 1]
    if len(data['spo2']) > 0:
        valid_spo2 = data['spo2'][data['spo2'] > 0]
        ax.plot(data['spo2'], color='#1abc9c', linewidth=1.5, marker='o', markersize=2)
        if len(valid_spo2) > 0:
            avg_spo2 = np.mean(valid_spo2)
            ax.axhline(y=avg_spo2, color='red', linestyle='--', alpha=0.7, 
                       label=f'TB: {avg_spo2:.1f}%')
            ax.legend()
        ax.set_title('SpO2 (%)')
        ax.set_ylim([85, 102])
        ax.grid(True, alpha=0.3)
    
    # Audio
    ax = axes[3, 0]
    if len(data['audio_raw']) > 0 or len(data['audio_filtered']) > 0:
        if len(data['audio_raw']) > 0:
            ax.plot(data['audio_raw'], color='orange', linewidth=0.5, alpha=0.7, label='Raw')
        if len(data['audio_filtered']) > 0:
            ax.plot(data['audio_filtered'], color='purple', linewidth=0.8, label='Filtered')
        ax.set_title('Audio')
        ax.legend()
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, 'Khong co du lieu Audio', ha='center', va='center')
        ax.set_title('Audio')
    
    # DC Values
    ax = axes[3, 1]
    if len(data['red_dc']) > 0 or len(data['ir_dc']) > 0:
        ax2 = ax.twinx()
        if len(data['red_dc']) > 0:
            ax.plot(data['red_dc'], color='red', linewidth=1, label='Red DC')
        if len(data['ir_dc']) > 0:
            ax2.plot(data['ir_dc'], color='blue', linewidth=1, label='IR DC')
        ax.set_title('DC Values')
        ax.set_ylabel('Red DC', color='red')
        ax2.set_ylabel('IR DC', color='blue')
        ax.legend(loc='upper left')
        ax2.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, 'Khong co du lieu DC', ha='center', va='center')
        ax.set_title('DC Values')
    
    plt.tight_layout()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Da luu: {output_file}")
    plt.show()

def print_statistics(data):
    print("\nTHONG KE DU LIEU")
    print("-" * 40)
    
    if len(data['ecg_raw']) > 0:
        print(f"ECG: {len(data['ecg_raw'])} mau")
    
    if len(data['heartrate']) > 0:
        valid_hr = data['heartrate'][data['heartrate'] > 0]
        if len(valid_hr) > 0:
            print(f"Nhip tim: TB={np.mean(valid_hr):.1f} BPM")
    
    if len(data['spo2']) > 0:
        valid_spo2 = data['spo2'][data['spo2'] > 0]
        if len(valid_spo2) > 0:
            print(f"SpO2: TB={np.mean(valid_spo2):.1f}%")

def main():
    print("=" * 40)
    print("ESP32 Signal Plotter")
    print("=" * 40)
    
    log_file = find_latest_log()
    
    if not log_file:
        print(f"\nKhong tim thay file log trong '{DATA_DIR}'!")
        print("Chay serial_logger.py truoc.")
        return
    
    print(f"\nFile: {log_file}")
    print("Dang doc du lieu...")
    data = parse_log_file(log_file)
    
    print_statistics(data)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"plot_{timestamp}.png")
    
    print("\nDang ve bieu do...")
    create_plots(data, output_file, log_file)
    print("Hoan thanh!")

if __name__ == "__main__":
    main()
