"""
Python Signal Processing for ECG/PPG Raw Data
Lọc và xử lý tín hiệu ECG/PPG từ file raw data thu thập bởi ESP32

CÁCH SỬ DỤNG:
    python process_signals.py                    # Xử lý file mới nhất
    python process_signals.py path/to/log.txt   # Xử lý file cụ thể
"""

import os
import sys
import glob
import re
from datetime import datetime
import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter1d
import matplotlib.pyplot as plt

# ============================================
# CẤU HÌNH
# ============================================
DATA_DIR = "data_logs"
OUTPUT_DIR = "processed_data"

# Sample rates (dựa trên code ESP32 v2.0)
ECG_SAMPLE_RATE = 500   # Hz (1000Hz / 2 decimation = 500Hz output)
PPG_SAMPLE_RATE = 500   # Hz (1000Hz / 2 decimation = 500Hz output)

# ECG Filter parameters - ĐÃ TỐI ƯU
ECG_LOWCUT = 0.5        # Hz - loại bỏ baseline drift  
ECG_HIGHCUT = 45.0      # Hz - tăng để giữ R-peak sắc nét (was 40)
ECG_NOTCH_FREQ = 50.0   # Hz - loại bỏ nhiễu điện lưới

# PPG Filter parameters - ĐÃ TỐI ƯU
PPG_LOWCUT = 0.4        # Hz - giảm để bắt baseline tốt hơn (was 0.5)
PPG_HIGHCUT = 8.0       # Hz - tăng để giữ chi tiết sóng (was 5.0)

# Wavelet parameters - ĐÃ TỐI ƯU
ECG_WAVELET = 'db6'     # Daubechies 6 - tốt hơn db4 cho ECG với R-peak
PPG_WAVELET = 'sym5'    # Symlet 5 - phù hợp cho PPG
WAVELET_LEVEL = 5       # Mức decomposition (tăng để khử nhiễu tốt hơn)
THRESHOLD_MULTIPLIER = 0.8  # Hệ số threshold (giảm để giữ nhiều chi tiết hơn)


# ============================================
# BỘ LỌC TÍN HIỆU
# ============================================

def butter_bandpass(lowcut, highcut, fs, order=4):
    """Tạo bộ lọc Butterworth bandpass"""
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = signal.butter(order, [low, high], btype='band')
    return b, a


def butter_lowpass(cutoff, fs, order=4):
    """Tạo bộ lọc Butterworth lowpass"""
    nyq = 0.5 * fs
    normalized_cutoff = cutoff / nyq
    b, a = signal.butter(order, normalized_cutoff, btype='low')
    return b, a


def notch_filter(freq, fs, Q=30):
    """Tạo bộ lọc notch để loại bỏ nhiễu điện lưới"""
    nyq = 0.5 * fs
    w0 = freq / nyq
    b, a = signal.iirnotch(w0, Q)
    return b, a


def remove_baseline_wander(data, fs, cutoff=0.5):
    """Loại bỏ baseline wander bằng high-pass filter"""
    nyq = 0.5 * fs
    normalized_cutoff = cutoff / nyq
    b, a = signal.butter(2, normalized_cutoff, btype='high')
    return signal.filtfilt(b, a, data)


def wavelet_denoise(data, wavelet='db4', level=4, threshold_mode='soft', threshold_mult=1.0):
    """
    Khử nhiễu bằng Wavelet Transform
    
    Args:
        data: Tín hiệu đầu vào
        wavelet: Loại wavelet ('db4', 'db6' cho ECG, 'sym5' cho PPG)
        level: Số mức decomposition
        threshold_mode: 'soft' hoặc 'hard'
        threshold_mult: Hệ số nhân threshold (nhỏ hơn = giữ nhiều chi tiết hơn)
    
    Returns:
        Tín hiệu đã khử nhiễu
    """
    try:
        import pywt
    except ImportError:
        print("⚠ pywt chưa cài đặt. Chạy: pip install PyWavelets")
        return data
    
    # Decompose
    coeffs = pywt.wavedec(data, wavelet, level=level)
    
    # Tính ngưỡng sử dụng MAD (Median Absolute Deviation)
    # Công thức: threshold = sigma * sqrt(2 * log(n)) * threshold_mult
    sigma = np.median(np.abs(coeffs[-1])) / 0.6745
    threshold = sigma * np.sqrt(2 * np.log(len(data))) * threshold_mult
    
    # Áp dụng threshold cho các detail coefficients (giữ nguyên approximation)
    denoised_coeffs = [coeffs[0]]  # Giữ nguyên approximation
    for i in range(1, len(coeffs)):
        if threshold_mode == 'soft':
            denoised = pywt.threshold(coeffs[i], threshold, mode='soft')
        else:
            denoised = pywt.threshold(coeffs[i], threshold, mode='hard')
        denoised_coeffs.append(denoised)
    
    # Reconstruct
    denoised_signal = pywt.waverec(denoised_coeffs, wavelet)
    
    return denoised_signal[:len(data)]
    
    # Reconstruct
    denoised_signal = pywt.waverec(denoised_coeffs, wavelet)
    
    # Đảm bảo độ dài khớp
    return denoised_signal[:len(data)]


def process_ecg(raw_ecg, fs=ECG_SAMPLE_RATE, use_wavelet=True):
    """
    Xử lý tín hiệu ECG raw - PHƯƠNG PHÁP TỐI ƯU
    Pipeline: Baseline removal → Wavelet denoise → Notch filter → Lowpass filter
    """
    if len(raw_ecg) < 10:
        return raw_ecg
    
    # 1. Loại bỏ baseline wander (high-pass 0.5Hz)
    ecg_no_baseline = remove_baseline_wander(raw_ecg, fs, ECG_LOWCUT)
    
    # 2. Wavelet denoising (db6 tốt hơn với R-peak)
    if use_wavelet:
        level = min(WAVELET_LEVEL, int(np.log2(len(ecg_no_baseline))) - 1)
        ecg_denoised = wavelet_denoise(ecg_no_baseline, wavelet=ECG_WAVELET, 
                                        level=level, threshold_mode='soft',
                                        threshold_mult=THRESHOLD_MULTIPLIER)
    else:
        ecg_denoised = ecg_no_baseline
    
    # 3. Notch filter 50Hz (loại bỏ nhiễu điện lưới)
    if fs > 2 * ECG_NOTCH_FREQ:
        b, a = notch_filter(ECG_NOTCH_FREQ, fs)
        ecg_notched = signal.filtfilt(b, a, ecg_denoised)
    else:
        ecg_notched = ecg_denoised
    
    # 4. Lowpass filter (loại bỏ noise còn lại)
    b, a = butter_lowpass(ECG_HIGHCUT, fs, order=4)
    ecg_filtered = signal.filtfilt(b, a, ecg_notched)
    
    return ecg_filtered


def process_ppg(raw_ppg, fs=PPG_SAMPLE_RATE, use_wavelet=True):
    """
    Xử lý tín hiệu PPG raw - PHƯƠNG PHÁP TỐI ƯU
    Pipeline: Baseline removal → Wavelet denoise → Lowpass filter
    """
    if len(raw_ppg) < 10:
        return raw_ppg
    
    # 1. Loại bỏ baseline (high-pass 0.4Hz)
    ppg_no_baseline = remove_baseline_wander(raw_ppg, fs, PPG_LOWCUT)
    
    # 2. Wavelet denoising (sym5 phù hợp với PPG)
    if use_wavelet:
        level = min(WAVELET_LEVEL, int(np.log2(len(ppg_no_baseline))) - 1)
        ppg_denoised = wavelet_denoise(ppg_no_baseline, wavelet=PPG_WAVELET, 
                                        level=level, threshold_mode='soft',
                                        threshold_mult=THRESHOLD_MULTIPLIER)
    else:
        ppg_denoised = ppg_no_baseline
    
    # 3. Lowpass filter (PPG chậm, 8Hz giữ chi tiết tốt hơn)
    b, a = butter_lowpass(PPG_HIGHCUT, fs, order=3)
    ppg_filtered = signal.filtfilt(b, a, ppg_denoised)
    
    return ppg_filtered


def calculate_heart_rate(ppg_signal, fs=PPG_SAMPLE_RATE):
    """
    Tính nhịp tim từ PPG signal bằng phương pháp peak detection
    """
    if len(ppg_signal) < fs * 2:  # Cần ít nhất 2 giây
        return None
    
    # Tìm peaks
    distance = int(fs * 0.5)  # Minimum 0.5s between peaks (max 120 BPM)
    peaks, _ = signal.find_peaks(ppg_signal, distance=distance, prominence=np.std(ppg_signal) * 0.3)
    
    if len(peaks) < 2:
        return None
    
    # Tính RR intervals
    rr_intervals = np.diff(peaks) / fs  # Seconds
    
    # Tính heart rate
    heart_rates = 60.0 / rr_intervals
    
    # Lọc các giá trị bất thường
    valid_hr = heart_rates[(heart_rates > 40) & (heart_rates < 180)]
    
    if len(valid_hr) == 0:
        return None
    
    return np.mean(valid_hr), np.std(valid_hr), peaks


# ============================================
# PARSE DỮ LIỆU
# ============================================

def parse_log_file(filepath):
    """Parse file serial log"""
    data = {
        'ecg_raw': [],
        'ppg_ir_raw': [],
        'ppg_red_raw': [],
        'ecg_leadoff': [],
        'runtime_sec': [],
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


# ============================================
# VẼ BIỂU ĐỒ
# ============================================

def create_plots(raw_data, processed_data, output_file, log_filename):
    """Tạo biểu đồ so sánh raw vs processed"""
    
    fig, axes = plt.subplots(4, 1, figsize=(14, 12))
    fig.suptitle(f'Signal Processing Results\n({os.path.basename(log_filename)})', 
                 fontsize=14, fontweight='bold')
    
    # 1. ECG Raw
    ax = axes[0]
    if len(raw_data['ecg_raw']) > 0:
        time_ecg = np.arange(len(raw_data['ecg_raw'])) / ECG_SAMPLE_RATE
        ax.plot(time_ecg, raw_data['ecg_raw'], color='lightcoral', linewidth=0.5, alpha=0.7, label='Raw')
        if len(processed_data['ecg_filtered']) > 0:
            ax.plot(time_ecg[:len(processed_data['ecg_filtered'])], 
                   processed_data['ecg_filtered'], color='red', linewidth=0.8, label='Filtered')
        ax.set_ylabel('Amplitude')
        ax.set_title('ECG Signal', fontweight='bold')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
    
    # 2. ECG Filtered (zoomed)
    ax = axes[1]
    if len(processed_data['ecg_filtered']) > 0:
        # Zoom vào 10 giây giữa
        start_idx = len(processed_data['ecg_filtered']) // 3
        end_idx = start_idx + ECG_SAMPLE_RATE * 10
        if end_idx > len(processed_data['ecg_filtered']):
            end_idx = len(processed_data['ecg_filtered'])
        
        time_zoom = np.arange(end_idx - start_idx) / ECG_SAMPLE_RATE
        ax.plot(time_zoom, processed_data['ecg_filtered'][start_idx:end_idx], 
               color='red', linewidth=0.8)
        ax.set_ylabel('Amplitude')
        ax.set_title('ECG Filtered (10s zoom)', fontweight='bold')
        ax.grid(True, alpha=0.3)
    
    # 3. PPG Raw vs Filtered
    ax = axes[2]
    if len(raw_data['ppg_ir_raw']) > 0:
        time_ppg = np.arange(len(raw_data['ppg_ir_raw'])) / PPG_SAMPLE_RATE
        
        # Normalize raw để so sánh
        ppg_raw_norm = raw_data['ppg_ir_raw'] - np.mean(raw_data['ppg_ir_raw'])
        ax.plot(time_ppg, ppg_raw_norm, color='lightgreen', linewidth=0.5, alpha=0.7, label='Raw (normalized)')
        
        if len(processed_data['ppg_filtered']) > 0:
            ax.plot(time_ppg[:len(processed_data['ppg_filtered'])], 
                   processed_data['ppg_filtered'], color='green', linewidth=0.8, label='Filtered')
        ax.set_ylabel('Amplitude')
        ax.set_title('PPG IR Signal', fontweight='bold')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
    
    # 4. Heart Rate từ PPG
    ax = axes[3]
    if 'heart_rate' in processed_data and processed_data['heart_rate'] is not None:
        hr_mean, hr_std, peaks = processed_data['heart_rate']
        
        if len(processed_data['ppg_filtered']) > 0:
            time_ppg = np.arange(len(processed_data['ppg_filtered'])) / PPG_SAMPLE_RATE
            ax.plot(time_ppg, processed_data['ppg_filtered'], color='green', linewidth=0.5, alpha=0.5)
            ax.scatter(peaks / PPG_SAMPLE_RATE, processed_data['ppg_filtered'][peaks], 
                      color='red', s=50, zorder=5, label=f'Peaks (HR: {hr_mean:.1f}±{hr_std:.1f} BPM)')
        
        ax.set_ylabel('Amplitude')
        ax.set_xlabel('Time (seconds)')
        ax.set_title(f'PPG Peak Detection - Heart Rate: {hr_mean:.1f} BPM', fontweight='bold')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, 'Không đủ dữ liệu để tính Heart Rate', ha='center', va='center')
        ax.set_title('PPG Peak Detection')
    
    plt.tight_layout()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(output_file, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"✓ Đã lưu biểu đồ: {output_file}")
    plt.show()


def save_processed_data(raw_data, processed_data, output_csv):
    """Lưu dữ liệu đã xử lý ra file CSV"""
    import csv
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow(['sample', 'time_sec', 'ecg_raw', 'ecg_filtered', 
                        'ppg_ir_raw', 'ppg_ir_filtered', 'ppg_red_raw'])
        
        # Data
        max_len = max(len(raw_data['ecg_raw']), len(raw_data['ppg_ir_raw']))
        
        for i in range(max_len):
            row = [
                i,
                i / ECG_SAMPLE_RATE,
                raw_data['ecg_raw'][i] if i < len(raw_data['ecg_raw']) else '',
                processed_data['ecg_filtered'][i] if i < len(processed_data['ecg_filtered']) else '',
                raw_data['ppg_ir_raw'][i] if i < len(raw_data['ppg_ir_raw']) else '',
                processed_data['ppg_filtered'][i] if i < len(processed_data['ppg_filtered']) else '',
                raw_data['ppg_red_raw'][i] if i < len(raw_data['ppg_red_raw']) else '',
            ]
            writer.writerow(row)
    
    print(f"✓ Đã lưu dữ liệu CSV: {output_csv}")


# ============================================
# MAIN
# ============================================

def main():
    print("="*50)
    print("🔬 Python Signal Processing for ECG/PPG")
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
    
    # Parse raw data
    raw_data = parse_log_file(log_file)
    
    print(f"\n📊 Thống kê dữ liệu raw:")
    print(f"   ECG: {len(raw_data['ecg_raw'])} samples")
    print(f"   PPG IR: {len(raw_data['ppg_ir_raw'])} samples")
    print(f"   PPG Red: {len(raw_data['ppg_red_raw'])} samples")
    
    # Xử lý tín hiệu
    print("\n⏳ Đang xử lý tín hiệu...")
    processed_data = {}
    
    # Xử lý ECG
    if len(raw_data['ecg_raw']) > 10:
        # Loại bỏ các mẫu leadoff (= 0)
        ecg_valid = raw_data['ecg_raw'][raw_data['ecg_raw'] > 0]
        print(f"   ECG valid samples: {len(ecg_valid)}")
        
        if len(ecg_valid) > 10:
            processed_data['ecg_filtered'] = process_ecg(ecg_valid, ECG_SAMPLE_RATE)
            print(f"   ✓ ECG filtered: {len(processed_data['ecg_filtered'])} samples")
        else:
            processed_data['ecg_filtered'] = np.array([])
    else:
        processed_data['ecg_filtered'] = np.array([])
    
    # Xử lý PPG
    if len(raw_data['ppg_ir_raw']) > 10:
        processed_data['ppg_filtered'] = process_ppg(raw_data['ppg_ir_raw'], PPG_SAMPLE_RATE)
        print(f"   ✓ PPG filtered: {len(processed_data['ppg_filtered'])} samples")
        
        # Tính heart rate
        hr_result = calculate_heart_rate(processed_data['ppg_filtered'], PPG_SAMPLE_RATE)
        if hr_result:
            processed_data['heart_rate'] = hr_result
            print(f"   ✓ Heart Rate: {hr_result[0]:.1f} ± {hr_result[1]:.1f} BPM")
        else:
            processed_data['heart_rate'] = None
            print(f"   ⚠ Không thể tính Heart Rate")
    else:
        processed_data['ppg_filtered'] = np.array([])
        processed_data['heart_rate'] = None
    
    # Tạo output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_plot = os.path.join(OUTPUT_DIR, f"processed_{timestamp}.png")
    output_csv = os.path.join(OUTPUT_DIR, f"processed_{timestamp}.csv")
    
    # Vẽ biểu đồ
    print("\n⏳ Đang vẽ biểu đồ...")
    create_plots(raw_data, processed_data, output_plot, log_file)
    
    # Lưu CSV
    save_processed_data(raw_data, processed_data, output_csv)
    
    print("\n✅ Hoàn thành!")


if __name__ == "__main__":
    main()
