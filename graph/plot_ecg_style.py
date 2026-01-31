"""
Script vẽ biểu đồ ECG/PPG/Audio theo style đẹp
Giống với ảnh mẫu: ECG đỏ, PPG xanh lá, Audio xanh dương

CÁCH SỬ DỤNG:
    python plot_ecg_style.py                    # Vẽ file mới nhất
    python plot_ecg_style.py path/to/log.txt    # Vẽ file cụ thể
"""

import os
import sys
import glob
import re
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np

# CẤU HÌNH
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data_logs")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Màu sắc giống ảnh mẫu
COLORS = {
    'ecg': '#e74c3c',      # Đỏ
    'ppg': '#27ae60',      # Xanh lá
    'audio': '#3498db',    # Xanh dương
    'filtered': '#e67e22', # Cam (denoised)
    'grid': '#ecf0f1'
}


def parse_log_file(filepath):
    """Parse file serial log"""
    data = {
        'ecg_raw': [], 'ecg_filtered': [], 'ecg_wavelet': [],
        'ppg_ir_raw': [], 'ppg_ir_filtered': [], 'ppg_ir_wavelet': [],
        'ppg_red_raw': [],
        'heartrate': [], 'spo2': [], 'finger_detected': [],
        'red_dc': [], 'ir_dc': [], 'red_ac': [], 'ir_ac': [],
        'audio_raw': [], 'audio_filtered': [],
        'ecg_saturated': [], 'ir_current': [], 'runtime_sec': [],
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
    """Tìm file log mới nhất"""
    pattern = os.path.join(DATA_DIR, "serial_log_*.txt")
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def create_ecg_style_plot(data, output_file, log_filename):
    """
    Tạo biểu đồ theo style đẹp giống ảnh mẫu
    3 hàng: ECG, PPG, Audio (nếu có) hoặc Health Metrics
    """
    # Xác định số hàng cần vẽ
    has_audio = len(data['audio_raw']) > 0 and np.any(data['audio_raw'] != 0)
    
    # Tạo figure với style đẹp
    plt.style.use('seaborn-v0_8-whitegrid')
    
    if has_audio:
        fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    else:
        fig, axes = plt.subplots(4, 1, figsize=(14, 12))
    
    fig.suptitle(f'Biophysical Signal Data\n({os.path.basename(log_filename)})', 
                 fontsize=14, fontweight='bold')
    
    # ============================================
    # 1. ECG SIGNAL
    # ============================================
    ax = axes[0]
    if len(data['ecg_raw']) > 0:
        samples = np.arange(len(data['ecg_raw']))
        ax.plot(samples, data['ecg_raw'], color=COLORS['ecg'], linewidth=0.6, alpha=0.9)
        ax.set_ylabel('Amplitude', fontsize=10)
        ax.set_title('ECG', fontsize=12, fontweight='bold', color=COLORS['ecg'])
        ax.grid(True, alpha=0.3)
        
        # Thêm đường baseline
        baseline = np.median(data['ecg_raw'])
        ax.axhline(y=baseline, color='gray', linestyle='--', alpha=0.5, linewidth=0.5)
    
    # ============================================
    # 2. PPG SIGNAL (IR)
    # ============================================
    ax = axes[1]
    if len(data['ppg_ir_raw']) > 0:
        samples = np.arange(len(data['ppg_ir_raw']))
        ax.plot(samples, data['ppg_ir_raw'], color=COLORS['ppg'], linewidth=0.8)
        ax.set_ylabel('Amplitude', fontsize=10)
        ax.set_title('PPG (IR)', fontsize=12, fontweight='bold', color=COLORS['ppg'])
        ax.grid(True, alpha=0.3)
    
    # ============================================
    # 3. AUDIO hoặc HEALTH METRICS
    # ============================================
    if has_audio:
        ax = axes[2]
        samples = np.arange(len(data['audio_raw']))
        ax.plot(samples, data['audio_raw'], color=COLORS['audio'], linewidth=0.5)
        ax.set_ylabel('Amplitude', fontsize=10)
        ax.set_xlabel('Sample Index', fontsize=10)
        ax.set_title('PCG (Audio)', fontsize=12, fontweight='bold', color=COLORS['audio'])
        ax.grid(True, alpha=0.3)
    else:
        # Vẽ Heart Rate
        ax = axes[2]
        if len(data['heartrate']) > 0:
            valid_indices = data['heartrate'] > 0
            samples = np.arange(len(data['heartrate']))
            ax.plot(samples, data['heartrate'], color='#9b59b6', linewidth=1.2, 
                   marker='o', markersize=3, markerfacecolor='white')
            
            valid_hr = data['heartrate'][valid_indices]
            if len(valid_hr) > 0:
                avg_hr = np.mean(valid_hr)
                ax.axhline(y=avg_hr, color='red', linestyle='--', alpha=0.7,
                          label=f'Mean: {avg_hr:.1f} BPM')
                ax.legend(loc='upper right')
            
            ax.set_ylabel('BPM', fontsize=10)
            ax.set_title('Heart Rate', fontsize=12, fontweight='bold', color='#9b59b6')
            ax.set_ylim([40, 160])
            ax.grid(True, alpha=0.3)
        
        # Vẽ SpO2
        ax = axes[3]
        if len(data['spo2']) > 0:
            valid_indices = data['spo2'] > 0
            samples = np.arange(len(data['spo2']))
            ax.plot(samples, data['spo2'], color='#1abc9c', linewidth=1.2,
                   marker='s', markersize=3, markerfacecolor='white')
            
            valid_spo2 = data['spo2'][valid_indices]
            if len(valid_spo2) > 0:
                avg_spo2 = np.mean(valid_spo2)
                ax.axhline(y=avg_spo2, color='red', linestyle='--', alpha=0.7,
                          label=f'Mean: {avg_spo2:.1f}%')
                ax.legend(loc='lower right')
            
            ax.set_ylabel('%', fontsize=10)
            ax.set_xlabel('Sample Index', fontsize=10)
            ax.set_title('SpO2', fontsize=12, fontweight='bold', color='#1abc9c')
            ax.set_ylim([85, 102])
            ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Lưu file
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(output_file, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"✓ Đã lưu: {output_file}")
    plt.show()


def create_comparison_plot(data, output_file, log_filename):
    """
    Tạo biểu đồ so sánh Raw vs Filtered vs Wavelet
    Giống ảnh mẫu thứ 2 (input vs denoised)
    """
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle(f'Signal Comparison: Raw vs Denoised\n({os.path.basename(log_filename)})', 
                 fontsize=14, fontweight='bold')
    
    # ECG Comparison
    ax = axes[0]
    if len(data['ecg_raw']) > 0:
        # Normalize ECG raw để so sánh
        ecg_raw = data['ecg_raw'] - np.mean(data['ecg_raw'])
        samples = np.arange(len(ecg_raw))
        
        ax.plot(samples, ecg_raw, color='#3498db', linewidth=0.3, alpha=0.6, label='input (raw)')
        
        if len(data['ecg_wavelet']) > 0:
            ax.plot(samples[:len(data['ecg_wavelet'])], data['ecg_wavelet'], 
                   color='#e67e22', linewidth=1.2, label='denoised (wavelet)')
        
        ax.set_ylabel('Amplitude', fontsize=10)
        ax.set_title('ECG Signal', fontsize=12, fontweight='bold')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
    
    # PPG Comparison
    ax = axes[1]
    if len(data['ppg_ir_raw']) > 0:
        # Normalize PPG raw
        ppg_raw = data['ppg_ir_raw'] - np.mean(data['ppg_ir_raw'])
        samples = np.arange(len(ppg_raw))
        
        ax.plot(samples, ppg_raw, color='#3498db', linewidth=0.3, alpha=0.6, label='input (raw)')
        
        if len(data['ppg_ir_wavelet']) > 0:
            ax.plot(samples[:len(data['ppg_ir_wavelet'])], data['ppg_ir_wavelet'], 
                   color='#e67e22', linewidth=1.2, label='denoised (wavelet)')
        
        ax.set_ylabel('Amplitude', fontsize=10)
        ax.set_xlabel('Sample Index', fontsize=10)
        ax.set_title('PPG Signal', fontsize=12, fontweight='bold')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_comparison = output_file.replace('.png', '_comparison.png')
    plt.savefig(output_comparison, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"✓ Đã lưu: {output_comparison}")
    plt.show()


def print_statistics(data, log_filename):
    """In thống kê dữ liệu"""
    print("\n" + "="*50)
    print(f"📊 THỐNG KÊ: {os.path.basename(log_filename)}")
    print("="*50)
    
    print(f"\n📈 Số lượng mẫu:")
    print(f"   ECG: {len(data['ecg_raw'])} samples")
    print(f"   PPG: {len(data['ppg_ir_raw'])} samples")
    print(f"   Audio: {len(data['audio_raw'])} samples")
    
    if len(data['heartrate']) > 0:
        valid_hr = data['heartrate'][data['heartrate'] > 0]
        if len(valid_hr) > 0:
            print(f"\n❤️  Heart Rate:")
            print(f"   Min: {np.min(valid_hr):.1f} BPM")
            print(f"   Max: {np.max(valid_hr):.1f} BPM")
            print(f"   Mean: {np.mean(valid_hr):.1f} BPM")
    
    if len(data['spo2']) > 0:
        valid_spo2 = data['spo2'][data['spo2'] > 0]
        if len(valid_spo2) > 0:
            print(f"\n🩸 SpO2:")
            print(f"   Min: {np.min(valid_spo2):.1f}%")
            print(f"   Max: {np.max(valid_spo2):.1f}%")
            print(f"   Mean: {np.mean(valid_spo2):.1f}%")
    
    if len(data['finger_detected']) > 0:
        finger_pct = np.mean(data['finger_detected']) * 100
        print(f"\n🖐️  Finger Detected: {finger_pct:.1f}% of samples")


def main():
    print("="*50)
    print("🔬 ECG/PPG/Audio Signal Plotter")
    print("="*50)
    
    # Xác định file log
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
        if not os.path.exists(log_file):
            print(f"\n❌ File không tồn tại: {log_file}")
            return
    else:
        log_file = find_latest_log()
        if not log_file:
            print(f"\n❌ Không tìm thấy file log trong '{DATA_DIR}'!")
            return
    
    print(f"\n📂 File: {log_file}")
    print("⏳ Đang đọc dữ liệu...")
    
    # Parse dữ liệu
    data = parse_log_file(log_file)
    
    # In thống kê
    print_statistics(data, log_file)
    
    # Tạo output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"ecg_plot_{timestamp}.png")
    
    # Vẽ biểu đồ chính
    print("\n⏳ Đang vẽ biểu đồ...")
    create_ecg_style_plot(data, output_file, log_file)
    
    # Vẽ biểu đồ so sánh
    create_comparison_plot(data, output_file, log_file)
    
    print("\n✅ Hoàn thành!")


if __name__ == "__main__":
    main()
