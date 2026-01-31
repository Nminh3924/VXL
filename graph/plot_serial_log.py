"""
Script vẽ biểu đồ từ file serial log.
Chỉ cần thay đổi biến LOG_FILE_PATH để vẽ file mới.

Sử dụng: python plot_serial_log.py
"""

import os
import re
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np

# CẤU HÌNH - THAY ĐỔI ĐƯỜNG DẪN TẠI ĐÂY
LOG_FILE_PATH = r"c:\Users\Admin\Documents\PlatformIO\Projects\VXL_20251\data_logs\serial_log_20260114_161919.txt"

# Thư mục lưu ảnh output (mặc định là cùng folder với script)
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# HÀM PARSE DỮ LIỆU

def parse_serial_log(file_path):
    """
    Parse file serial log và trả về dictionary chứa các chuỗi dữ liệu.
    """
    data = {
        # PPG IR
        'ppg_ir_raw': [],
        'ppg_ir_filtered': [],
        'ppg_ir_wavelet': [],
        
        # ECG
        'ecg_raw': [],
        'ecg_filtered': [],
        'ecg_wavelet': [],
        'ecg_saturated': [],
        
        # Audio
        'audio_raw': [],
        'audio_filtered': [],
        
        # Health metrics
        'heartrate': [],
        'spo2': [],
        'finger_detected': [],
    }
    
    # Pattern để parse các dòng dạng ">key:value"
    pattern = re.compile(r'^>(\w+):(-?\d+\.?\d*)$')
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            
            match = pattern.match(line)
            if match:
                key = match.group(1)
                value_str = match.group(2)
                
                try:
                    # Chuyển đổi giá trị
                    if '.' in value_str:
                        value = float(value_str)
                    else:
                        value = int(value_str)
                    
                    # Thêm vào data nếu key tồn tại
                    if key in data:
                        data[key].append(value)
                except ValueError:
                    pass
    
    return data


def create_graphs(data, output_dir, log_filename):
    """
    Tạo các biểu đồ từ dữ liệu đã parse.
    """
    # Tạo tên file dựa trên tên log
    base_name = os.path.splitext(os.path.basename(log_filename))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Thiết lập style
    plt.style.use('seaborn-v0_8-darkgrid')
    plt.rcParams['figure.facecolor'] = '#1e1e2e'
    plt.rcParams['axes.facecolor'] = '#1e1e2e'
    plt.rcParams['axes.edgecolor'] = '#cdd6f4'
    plt.rcParams['axes.labelcolor'] = '#cdd6f4'
    plt.rcParams['text.color'] = '#cdd6f4'
    plt.rcParams['xtick.color'] = '#cdd6f4'
    plt.rcParams['ytick.color'] = '#cdd6f4'
    plt.rcParams['grid.color'] = '#45475a'
    plt.rcParams['figure.figsize'] = (14, 10)
    
    saved_files = []
    
    # ============================================
    # 1. BIỂU ĐỒ PPG IR (3 đường: raw, filtered, wavelet)
    # ============================================
    if data['ppg_ir_raw'] and data['ppg_ir_filtered'] and data['ppg_ir_wavelet']:
        fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
        fig.suptitle(f'PPG IR Signals - {base_name}', fontsize=16, fontweight='bold', color='#f5c2e7')
        
        # Raw
        axes[0].plot(data['ppg_ir_raw'], color='#f38ba8', linewidth=0.8, alpha=0.9)
        axes[0].set_ylabel('Raw', fontsize=11)
        axes[0].set_title('PPG IR Raw', fontsize=12, color='#f38ba8')
        axes[0].fill_between(range(len(data['ppg_ir_raw'])), data['ppg_ir_raw'], alpha=0.2, color='#f38ba8')
        
        # Filtered
        axes[1].plot(data['ppg_ir_filtered'], color='#89b4fa', linewidth=0.8, alpha=0.9)
        axes[1].set_ylabel('Filtered', fontsize=11)
        axes[1].set_title('PPG IR Filtered', fontsize=12, color='#89b4fa')
        axes[1].fill_between(range(len(data['ppg_ir_filtered'])), data['ppg_ir_filtered'], alpha=0.2, color='#89b4fa')
        
        # Wavelet
        axes[2].plot(data['ppg_ir_wavelet'], color='#a6e3a1', linewidth=0.8, alpha=0.9)
        axes[2].set_ylabel('Wavelet', fontsize=11)
        axes[2].set_xlabel('Sample Index', fontsize=11)
        axes[2].set_title('PPG IR Wavelet Denoised', fontsize=12, color='#a6e3a1')
        axes[2].fill_between(range(len(data['ppg_ir_wavelet'])), data['ppg_ir_wavelet'], alpha=0.2, color='#a6e3a1')
        
        plt.tight_layout()
        output_path = os.path.join(output_dir, f'{base_name}_ppg_ir.png')
        plt.savefig(output_path, dpi=150, facecolor='#1e1e2e', edgecolor='none')
        plt.close()
        saved_files.append(output_path)
        print(f"✓ Đã lưu: {output_path}")
    
    # ============================================
    # 2. BIỂU ĐỒ ECG (3 đường: raw, filtered, wavelet)
    # ============================================
    if data['ecg_raw'] and data['ecg_filtered'] and data['ecg_wavelet']:
        fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
        fig.suptitle(f'ECG Signals - {base_name}', fontsize=16, fontweight='bold', color='#f5c2e7')
        
        # Raw
        axes[0].plot(data['ecg_raw'], color='#fab387', linewidth=0.8, alpha=0.9)
        axes[0].set_ylabel('Raw', fontsize=11)
        axes[0].set_title('ECG Raw', fontsize=12, color='#fab387')
        axes[0].fill_between(range(len(data['ecg_raw'])), data['ecg_raw'], alpha=0.2, color='#fab387')
        
        # Filtered
        axes[1].plot(data['ecg_filtered'], color='#89dceb', linewidth=0.8, alpha=0.9)
        axes[1].set_ylabel('Filtered', fontsize=11)
        axes[1].set_title('ECG Filtered', fontsize=12, color='#89dceb')
        axes[1].fill_between(range(len(data['ecg_filtered'])), data['ecg_filtered'], alpha=0.2, color='#89dceb')
        
        # Wavelet
        axes[2].plot(data['ecg_wavelet'], color='#cba6f7', linewidth=0.8, alpha=0.9)
        axes[2].set_ylabel('Wavelet', fontsize=11)
        axes[2].set_xlabel('Sample Index', fontsize=11)
        axes[2].set_title('ECG Wavelet Denoised', fontsize=12, color='#cba6f7')
        axes[2].fill_between(range(len(data['ecg_wavelet'])), data['ecg_wavelet'], alpha=0.2, color='#cba6f7')
        
        plt.tight_layout()
        output_path = os.path.join(output_dir, f'{base_name}_ecg.png')
        plt.savefig(output_path, dpi=150, facecolor='#1e1e2e', edgecolor='none')
        plt.close()
        saved_files.append(output_path)
        print(f"✓ Đã lưu: {output_path}")
    
    # ============================================
    # 3. BIỂU ĐỒ AUDIO (nếu có dữ liệu)
    # ============================================
    if data['audio_raw'] and any(v != 0 for v in data['audio_raw']):
        fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
        fig.suptitle(f'Audio Signals - {base_name}', fontsize=16, fontweight='bold', color='#f5c2e7')
        
        axes[0].plot(data['audio_raw'], color='#f9e2af', linewidth=0.8, alpha=0.9)
        axes[0].set_ylabel('Raw', fontsize=11)
        axes[0].set_title('Audio Raw', fontsize=12, color='#f9e2af')
        
        axes[1].plot(data['audio_filtered'], color='#94e2d5', linewidth=0.8, alpha=0.9)
        axes[1].set_ylabel('Filtered', fontsize=11)
        axes[1].set_xlabel('Sample Index', fontsize=11)
        axes[1].set_title('Audio Filtered', fontsize=12, color='#94e2d5')
        
        plt.tight_layout()
        output_path = os.path.join(output_dir, f'{base_name}_audio.png')
        plt.savefig(output_path, dpi=150, facecolor='#1e1e2e', edgecolor='none')
        plt.close()
        saved_files.append(output_path)
        print(f"✓ Đã lưu: {output_path}")
    
    # ============================================
    # 4. BIỂU ĐỒ HEALTH METRICS (HeartRate, SpO2)
    # ============================================
    if data['heartrate'] or data['spo2']:
        fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
        fig.suptitle(f'Health Metrics - {base_name}', fontsize=16, fontweight='bold', color='#f5c2e7')
        
        # Heart Rate
        axes[0].plot(data['heartrate'], color='#f38ba8', linewidth=1.5, marker='o', markersize=2, alpha=0.9)
        axes[0].set_ylabel('BPM', fontsize=11)
        axes[0].set_title('Heart Rate', fontsize=12, color='#f38ba8')
        axes[0].axhline(y=np.mean(data['heartrate']) if data['heartrate'] else 0, 
                        color='#f38ba8', linestyle='--', alpha=0.5, label='Mean')
        
        # SpO2
        axes[1].plot(data['spo2'], color='#89b4fa', linewidth=1.5, marker='o', markersize=2, alpha=0.9)
        axes[1].set_ylabel('%', fontsize=11)
        axes[1].set_title('SpO2', fontsize=12, color='#89b4fa')
        axes[1].axhline(y=np.mean(data['spo2']) if data['spo2'] else 0,
                        color='#89b4fa', linestyle='--', alpha=0.5, label='Mean')
        
        # Finger Detected
        axes[2].fill_between(range(len(data['finger_detected'])), data['finger_detected'],
                             color='#a6e3a1', alpha=0.7, step='mid')
        axes[2].set_ylabel('Detected', fontsize=11)
        axes[2].set_xlabel('Sample Index', fontsize=11)
        axes[2].set_title('Finger Detected', fontsize=12, color='#a6e3a1')
        axes[2].set_ylim(-0.1, 1.1)
        
        plt.tight_layout()
        output_path = os.path.join(output_dir, f'{base_name}_health_metrics.png')
        plt.savefig(output_path, dpi=150, facecolor='#1e1e2e', edgecolor='none')
        plt.close()
        saved_files.append(output_path)
        print(f"✓ Đã lưu: {output_path}")
    
    # ============================================
    # 5. BIỂU ĐỒ TỔNG HỢP (So sánh Raw vs Filtered vs Wavelet)
    # ============================================
    fig, axes = plt.subplots(2, 1, figsize=(16, 10))
    fig.suptitle(f'Signal Comparison (Raw vs Filtered vs Wavelet) - {base_name}', 
                 fontsize=16, fontweight='bold', color='#f5c2e7')
    
    # PPG Comparison
    if data['ppg_ir_raw']:
        # Normalize cho dễ so sánh
        ppg_raw_norm = np.array(data['ppg_ir_raw']) - np.mean(data['ppg_ir_raw'])
        axes[0].plot(ppg_raw_norm, color='#f38ba8', linewidth=0.6, alpha=0.5, label='Raw')
    if data['ppg_ir_filtered']:
        axes[0].plot(data['ppg_ir_filtered'], color='#89b4fa', linewidth=0.8, alpha=0.8, label='Filtered')
    if data['ppg_ir_wavelet']:
        axes[0].plot(data['ppg_ir_wavelet'], color='#a6e3a1', linewidth=1.0, alpha=1.0, label='Wavelet')
    axes[0].set_title('PPG IR Signal Comparison', fontsize=12, color='#cdd6f4')
    axes[0].set_ylabel('Amplitude', fontsize=11)
    axes[0].legend(loc='upper right', facecolor='#313244', edgecolor='#45475a')
    
    # ECG Comparison  
    if data['ecg_raw']:
        ecg_raw_norm = np.array(data['ecg_raw']) - np.mean(data['ecg_raw'])
        axes[1].plot(ecg_raw_norm, color='#fab387', linewidth=0.6, alpha=0.5, label='Raw')
    if data['ecg_filtered']:
        axes[1].plot(data['ecg_filtered'], color='#89dceb', linewidth=0.8, alpha=0.8, label='Filtered')
    if data['ecg_wavelet']:
        axes[1].plot(data['ecg_wavelet'], color='#cba6f7', linewidth=1.0, alpha=1.0, label='Wavelet')
    axes[1].set_title('ECG Signal Comparison', fontsize=12, color='#cdd6f4')
    axes[1].set_xlabel('Sample Index', fontsize=11)
    axes[1].set_ylabel('Amplitude', fontsize=11)
    axes[1].legend(loc='upper right', facecolor='#313244', edgecolor='#45475a')
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, f'{base_name}_comparison.png')
    plt.savefig(output_path, dpi=150, facecolor='#1e1e2e', edgecolor='none')
    plt.close()
    saved_files.append(output_path)
    print(f"✓ Đã lưu: {output_path}")
    
    return saved_files


def print_statistics(data):
    """
    In thống kê dữ liệu.
    """
    print("\n" + "="*60)
    print("📊 THỐNG KÊ DỮ LIỆU")
    print("="*60)
    
    for key, values in data.items():
        if values:
            arr = np.array(values)
            print(f"\n{key.upper()}:")
            print(f"  • Số mẫu: {len(values)}")
            print(f"  • Min: {arr.min():.2f}")
            print(f"  • Max: {arr.max():.2f}")
            print(f"  • Mean: {arr.mean():.2f}")
            print(f"  • Std: {arr.std():.2f}")


# MAIN
if __name__ == "__main__":
    print("="*60)
    print("🔬 SERIAL LOG GRAPH PLOTTER")
    print("="*60)
    print(f"\n📂 File input: {LOG_FILE_PATH}")
    print(f"📁 Output dir: {OUTPUT_DIR}")
    
    # Kiểm tra file tồn tại
    if not os.path.exists(LOG_FILE_PATH):
        print(f"\n❌ Lỗi: File không tồn tại: {LOG_FILE_PATH}")
        exit(1)
    
    # Parse dữ liệu
    print("\n⏳ Đang parse dữ liệu...")
    data = parse_serial_log(LOG_FILE_PATH)
    
    # In thống kê
    print_statistics(data)
    
    # Tạo biểu đồ
    print("\n⏳ Đang tạo biểu đồ...")
    saved_files = create_graphs(data, OUTPUT_DIR, LOG_FILE_PATH)
    
    print("\n" + "="*60)
    print(f"✅ HOÀN THÀNH! Đã tạo {len(saved_files)} biểu đồ.")
    print("="*60)
