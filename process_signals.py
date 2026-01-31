"""
ECG & PPG Signal Processing Script
=================================
Đọc dữ liệu từ file log, lọc tín hiệu, và vẽ biểu đồ.

ECG Pipeline:
  1. Loại bỏ artifact (giá trị < 500 ADC = saturation thấp)
  2. Nội suy lại các điểm artifact
  3. Notch filter 50Hz (loại nhiễu điện lưới)
  4. Bandpass filter 0.5-40Hz
  5. Wavelet denoising (tùy chọn)

PPG Pipeline:
  1. Bandpass filter 0.5-5Hz
  2. Wavelet denoising
"""

import os
import sys
import glob
import re
import argparse
import collections
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.ndimage import median_filter

# Thử import pywt, nếu không có thì bỏ qua wavelet
try:
    import pywt
    HAS_PYWT = True
except ImportError:
    HAS_PYWT = False
    print("[WARN] PyWavelets not installed. Wavelet denoising disabled.")

# ============================================================
# CẤU HÌNH
# ============================================================
DEFAULT_FS_ECG = 500      # Tần số lấy mẫu ECG (Hz)
DEFAULT_FS_PPG = 100      # Tần số lấy mẫu PPG (Hz)
DEFAULT_FS_AUDIO = 16000  # Tần số lấy mẫu Audio (Hz)
OUTPUT_DIR = "processed_data"
WINDOW_SEC = 10.0         # Cửa sổ hiển thị (giây)

# ============================================================
# ĐỌC FILE LOG
# ============================================================
def parse_log_file(filepath):
    """Đọc file log và trích xuất dữ liệu ECG, PPG, Audio"""
    data = {
        'ecg_raw': [],
        'ppg_ir_raw': [],
        'ppg_red_raw': [],
        'audio_raw': []
    }
    
    max_runtime = {'ecg': 0, 'ppg': 0, 'audio': 0}
    current_sensor = None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Parse format: >name:value
            if line.startswith('>'):
                match = re.match(r'>(\w+):(-?[\d.]+)', line)
                if match:
                    name, value = match.group(1), float(match.group(2))
                    
                    if name == 'ecg_raw':
                        data['ecg_raw'].append(value)
                        current_sensor = 'ecg'
                    elif name == 'ppg_ir_raw':
                        data['ppg_ir_raw'].append(value)
                        current_sensor = 'ppg'
                    elif name == 'ppg_red_raw':
                        data['ppg_red_raw'].append(value)
                    elif name in ['audio', 'audio_raw']:
                        data['audio_raw'].append(value)
                        current_sensor = 'audio'
                    elif name == 'runtime_sec':
                        if current_sensor:
                            max_runtime[current_sensor] = max(max_runtime[current_sensor], value)
    
    # Convert to numpy arrays
    for key in data:
        data[key] = np.array(data[key])
    
    # Ước tính sample rate thực tế
    estimated_fs = {}
    if len(data['ecg_raw']) > 0 and max_runtime['ecg'] > 0:
        estimated_fs['ecg'] = len(data['ecg_raw']) / max_runtime['ecg']
    if len(data['ppg_ir_raw']) > 0 and max_runtime['ppg'] > 0:
        estimated_fs['ppg'] = len(data['ppg_ir_raw']) / max_runtime['ppg']
    if len(data['audio_raw']) > 0 and max_runtime['audio'] > 0:
        estimated_fs['audio'] = len(data['audio_raw']) / max_runtime['audio']
    
    return data, estimated_fs

# ============================================================
# XỬ LÝ ARTIFACT ECG
# ============================================================
def remove_ecg_artifacts(data, threshold=500):
    """
    Loại bỏ artifact (tín hiệu tụt về 0).
    ECG từ AD8232 bình thường dao động 1400-2800 ADC.
    Giá trị < 500 = artifact chắc chắn.
    
    Returns: cleaned data with artifacts interpolated
    """
    if len(data) < 10:
        return data
    
    data = np.array(data, dtype=float)
    
    # Tìm các điểm artifact (< threshold)
    artifact_mask = data < threshold
    
    # Mở rộng vùng artifact (trước 5, sau 10 mẫu)
    indices = np.where(artifact_mask)[0]
    for idx in indices:
        start = max(0, idx - 5)
        end = min(len(data), idx + 10)
        artifact_mask[start:end] = True
    
    artifact_count = np.sum(artifact_mask)
    if artifact_count > 0:
        pct = artifact_count / len(data) * 100
        print(f"  [Artifact] Detected {artifact_count} samples ({pct:.1f}%) below {threshold} ADC")
    
    # Nội suy các điểm artifact
    if 0 < artifact_count < len(data) * 0.3:
        good_idx = np.where(~artifact_mask)[0]
        bad_idx = np.where(artifact_mask)[0]
        
        if len(good_idx) > 10:
            clean = data.copy()
            clean[bad_idx] = np.interp(bad_idx, good_idx, data[good_idx])
            return clean
    
    return data

# ============================================================
# CÁC BỘ LỌC (FILTERS)
# ============================================================
def butter_bandpass(data, lowcut, highcut, fs, order=4):
    """Butterworth Bandpass Filter"""
    if len(data) == 0:
        return data
    
    nyq = 0.5 * fs
    
    # Kiểm tra Nyquist
    if highcut >= nyq:
        highcut = nyq * 0.95
    if lowcut >= highcut:
        return data
    
    low = lowcut / nyq
    high = highcut / nyq
    
    try:
        b, a = signal.butter(order, [low, high], btype='band')
        return signal.filtfilt(b, a, data)
    except Exception as e:
        print(f"  [Filter Error] Bandpass: {e}")
        return data

def notch_filter(data, freq, q, fs):
    """Notch Filter để loại nhiễu 50Hz/60Hz"""
    if len(data) == 0:
        return data
    
    nyq = 0.5 * fs
    if freq >= nyq:
        return data
    
    try:
        b, a = signal.iirnotch(freq / nyq, q)
        return signal.filtfilt(b, a, data)
    except Exception as e:
        print(f"  [Filter Error] Notch: {e}")
        return data

def wavelet_denoise(data, wavelet='db6', level=4):
    """Wavelet Denoising (soft thresholding)"""
    if not HAS_PYWT or len(data) < 100:
        return data
    
    try:
        max_level = pywt.dwt_max_level(len(data), pywt.Wavelet(wavelet).dec_len)
        level = min(level, max_level)
        if level == 0:
            return data
        
        coeffs = pywt.wavedec(data, wavelet, level=level)
        sigma = np.median(np.abs(coeffs[-1])) / 0.6745
        threshold = sigma * np.sqrt(2 * np.log(len(data)))
        
        new_coeffs = [coeffs[0]]
        for c in coeffs[1:]:
            new_coeffs.append(pywt.threshold(c, threshold, mode='soft'))
        
        return pywt.waverec(new_coeffs, wavelet)[:len(data)]
    except:
        return data

# ============================================================
# PIPELINE XỬ LÝ ECG
# ============================================================
def process_ecg(raw_data, fs):
    """
    ECG Processing Pipeline:
    1. Remove artifacts (values < 500)
    2. Median filter (remove spikes)
    3. Notch filter 50Hz
    4. Bandpass 0.5-40Hz
    5. (Optional) Wavelet denoise
    """
    if len(raw_data) == 0:
        return raw_data
    
    print("  [ECG] Processing...")
    
    # Step 1: Remove artifacts
    cleaned = remove_ecg_artifacts(raw_data, threshold=500)
    
    # Step 2: Light median filter
    cleaned = median_filter(cleaned, size=3)
    
    # Step 3: Notch filter 50Hz
    filtered = notch_filter(cleaned, 50.0, 30.0, fs)
    
    # Step 4: Bandpass 0.5-40Hz
    filtered = butter_bandpass(filtered, 0.5, 40.0, fs)
    
    # Step 5: Wavelet denoise (optional)
    if HAS_PYWT:
        filtered = wavelet_denoise(filtered, 'db6', 4)
    
    return filtered

# ============================================================
# PIPELINE XỬ LÝ PPG
# ============================================================
def remove_ppg_artifacts(data):
    """
    Loại bỏ artifact trong PPG (giá trị bất thường).
    MAX30102 output thường trong khoảng ổn định, outliers = artifact.
    """
    if len(data) < 10:
        return data
    
    data = np.array(data, dtype=float)
    
    # Tính ngưỡng dựa trên IQR
    q1 = np.percentile(data, 5)
    q3 = np.percentile(data, 95)
    iqr = q3 - q1
    
    low_thresh = q1 - 2.0 * iqr
    high_thresh = q3 + 2.0 * iqr
    
    # Tìm artifact
    artifact_mask = (data < low_thresh) | (data > high_thresh)
    
    # Mở rộng vùng artifact
    indices = np.where(artifact_mask)[0]
    for idx in indices:
        start = max(0, idx - 3)
        end = min(len(data), idx + 5)
        artifact_mask[start:end] = True
    
    artifact_count = np.sum(artifact_mask)
    if artifact_count > 0:
        pct = artifact_count / len(data) * 100
        print(f"  [PPG Artifact] Removed {artifact_count} samples ({pct:.1f}%)")
        
        # Nội suy
        good_idx = np.where(~artifact_mask)[0]
        bad_idx = np.where(artifact_mask)[0]
        if len(good_idx) > 10:
            clean = data.copy()
            clean[bad_idx] = np.interp(bad_idx, good_idx, data[good_idx])
            return clean
    
    return data

def process_ppg(raw_data, fs):
    """
    PPG Processing Pipeline (Improved):
    1. Remove artifacts (outliers)
    2. Baseline drift removal (detrend)
    3. Bandpass 0.5-8Hz (wider range)
    4. Wavelet denoise
    5. Moving average smoothing
    """
    if len(raw_data) == 0:
        return raw_data
    
    print("  [PPG] Processing...")
    
    # Step 1: Remove artifacts
    cleaned = remove_ppg_artifacts(raw_data)
    
    # Step 2: Remove baseline drift
    from scipy.signal import detrend
    cleaned = detrend(cleaned)
    
    # Step 3: Bandpass 0.5-8Hz (wider for more harmonics)
    filtered = butter_bandpass(cleaned, 0.5, 8.0, fs)
    
    # Step 4: Wavelet denoise
    if HAS_PYWT:
        filtered = wavelet_denoise(filtered, 'sym8', 4)
    
    # Step 5: Moving average smoothing
    from scipy.ndimage import uniform_filter1d
    smoothed = uniform_filter1d(filtered, size=5)
    
    return smoothed

# ============================================================
# TÌM ĐỈNH R VÀ TÍNH NHỊP TIM
# ============================================================
def detect_r_peaks(ecg, fs):
    """Tìm đỉnh R trong ECG và tính heart rate"""
    if len(ecg) < 100:
        return [], 0
    
    # Normalize
    ecg_norm = (ecg - np.min(ecg)) / (np.max(ecg) - np.min(ecg) + 1e-6)
    
    # Tìm peaks với distance tối thiểu 0.3s (max 200 bpm)
    min_dist = int(0.3 * fs)
    peaks, _ = signal.find_peaks(ecg_norm, distance=min_dist, prominence=0.3)
    
    # Tính heart rate
    hr = 0
    if len(peaks) > 1:
        intervals = np.diff(peaks)
        avg_interval = np.mean(intervals)
        hr = 60.0 * fs / avg_interval
    
    return peaks, hr

# ============================================================
# TÌM ĐOẠN ỔN ĐỊNH NHẤT
# ============================================================
def find_stable_segment(data, fs, window_sec):
    """Tìm đoạn tín hiệu ổn định nhất trong data"""
    N = len(data)
    win_len = int(window_sec * fs)
    
    if N <= win_len:
        return 0, N
    
    # Skip 10% đầu và cuối
    start_range = int(N * 0.1)
    end_range = int(N * 0.9)
    
    if end_range - start_range < win_len:
        return 0, min(win_len, N)
    
    best_start = start_range
    min_noise = float('inf')
    
    step = int(0.5 * fs)
    for i in range(start_range, end_range - win_len, step):
        seg = data[i:i + win_len]
        # Đánh giá độ ổn định bằng std của derivative
        noise = np.std(np.diff(seg))
        if noise < min_noise:
            min_noise = noise
            best_start = i
    
    return best_start, best_start + win_len

# ============================================================
# VẼ BIỂU ĐỒ
# ============================================================
def create_plot(data, fs_config, output_file):
    """Tạo biểu đồ 3 hàng: ECG, PPG Red, PPG IR - ĐỒNG BỘ CÙNG THỜI GIAN"""
    
    ecg = data['ecg_raw']
    ppg_ir = data['ppg_ir_raw']
    ppg_red = data['ppg_red_raw']
    
    fs_ecg = fs_config.get('ecg', DEFAULT_FS_ECG)
    fs_ppg = fs_config.get('ppg', DEFAULT_FS_PPG)
    
    # Xử lý tín hiệu
    ecg_clean = process_ecg(ecg, fs_ecg) if len(ecg) > 0 else np.array([])
    ppg_ir_clean = process_ppg(ppg_ir, fs_ppg) if len(ppg_ir) > 0 else np.array([])
    ppg_red_clean = process_ppg(ppg_red, fs_ppg) if len(ppg_red) > 0 else np.array([])
    
    # Tính thời lượng của mỗi tín hiệu (giây)
    dur_ecg = len(ecg_clean) / fs_ecg if len(ecg_clean) > 0 else 0
    dur_ppg = len(ppg_red_clean) / fs_ppg if len(ppg_red_clean) > 0 else 0
    
    # Tìm thời lượng ngắn nhất
    min_duration = min(dur_ecg, dur_ppg) if dur_ecg > 0 and dur_ppg > 0 else max(dur_ecg, dur_ppg)
    
    # Lấy 10 giây Ở GIỮA
    window_sec = 10.0
    if min_duration > window_sec:
        # Tính điểm giữa
        mid_time = min_duration / 2
        t_start = mid_time - window_sec / 2
        t_end = mid_time + window_sec / 2
    else:
        # Nếu ngắn hơn 10s, lấy hết
        t_start = 0
        t_end = min_duration
    
    print(f"  [Sync] Using time window: {t_start:.1f}s - {t_end:.1f}s (middle 10s)")
    
    # Cắt từng tín hiệu theo cùng khoảng thời gian
    s_ecg = int(t_start * fs_ecg)
    e_ecg = int(t_end * fs_ecg)
    s_ppg = int(t_start * fs_ppg)
    e_ppg = int(t_end * fs_ppg)
    
    ecg_view = ecg_clean[s_ecg:e_ecg] if len(ecg_clean) > e_ecg else ecg_clean[s_ecg:]
    ppg_red_view = ppg_red_clean[s_ppg:e_ppg] if len(ppg_red_clean) > e_ppg else ppg_red_clean[s_ppg:]
    ppg_ir_view = ppg_ir_clean[s_ppg:e_ppg] if len(ppg_ir_clean) > e_ppg else ppg_ir_clean[s_ppg:]
    
    # Tính HR
    peaks, hr = detect_r_peaks(ecg_view, fs_ecg)
    
    # Tạo trục thời gian ĐỒNG BỘ
    t_ecg = np.linspace(t_start, t_end, len(ecg_view))
    t_ppg = np.linspace(t_start, t_end, len(ppg_red_view))
    
    # Vẽ biểu đồ
    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    
    # ECG
    ax1 = axes[0]
    ax1.plot(t_ecg, ecg_view, 'orange', linewidth=1, label='ECG Filtered')
    if len(peaks) > 0:
        ax1.plot(t_ecg[peaks], ecg_view[peaks], 'r+', markersize=10, label='R-peaks')
    ax1.set_title(f"ECG ({t_start:.0f}s - {t_end:.0f}s) | Heart Rate: {hr:.0f} BPM", fontweight='bold')
    ax1.set_ylabel("Amplitude")
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.4)
    
    # PPG Red
    ax2 = axes[1]
    ax2.plot(t_ppg, ppg_red_view, 'red', linewidth=1)
    ax2.set_title(f"PPG Red ({t_start:.0f}s - {t_end:.0f}s)", fontweight='bold')
    ax2.set_ylabel("Amplitude")
    ax2.grid(True, alpha=0.4)
    
    # PPG IR
    ax3 = axes[2]
    t_ir = np.linspace(t_start, t_end, len(ppg_ir_view))
    ax3.plot(t_ir, ppg_ir_view, 'green', linewidth=1)
    ax3.set_title(f"PPG IR ({t_start:.0f}s - {t_end:.0f}s)", fontweight='bold')
    ax3.set_xlabel("Time (seconds)")
    ax3.set_ylabel("Amplitude")
    ax3.grid(True, alpha=0.4)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    print(f"\n[OK] Saved: {output_file}")
    plt.close()

# ============================================================
# MAIN
# ============================================================
def find_latest_log(data_dir):
    """Tìm file log mới nhất"""
    files = glob.glob(os.path.join(data_dir, "serial_log_*.txt"))
    return max(files, key=os.path.getmtime) if files else None

def main():
    parser = argparse.ArgumentParser(description="ECG/PPG Signal Processor")
    parser.add_argument("logfile", nargs='?', help="Path to log file")
    parser.add_argument("--fs-ecg", type=int, default=DEFAULT_FS_ECG)
    parser.add_argument("--fs-ppg", type=int, default=DEFAULT_FS_PPG)
    parser.add_argument("--window", type=float, default=WINDOW_SEC, help="Display window (seconds)")
    args = parser.parse_args()
    
    window_sec = args.window
    
    # Tìm file log
    log_file = args.logfile or find_latest_log("data_logs")
    if not log_file:
        print("Error: No log file found!")
        return
    
    print(f"[INFO] Reading: {log_file}")
    
    # Parse data
    data, estimated_fs = parse_log_file(log_file)
    print(f"[INFO] Samples - ECG: {len(data['ecg_raw'])}, PPG IR: {len(data['ppg_ir_raw'])}, PPG Red: {len(data['ppg_red_raw'])}")
    
    # Configure sample rates
    fs_config = {
        'ecg': estimated_fs.get('ecg', args.fs_ecg),
        'ppg': estimated_fs.get('ppg', args.fs_ppg),
    }
    print(f"[INFO] Using FS - ECG: {fs_config['ecg']:.1f}Hz, PPG: {fs_config['ppg']:.1f}Hz")
    
    # Create output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"result_{timestamp}.png")
    
    # Process and plot
    create_plot(data, fs_config, output_file)
    print("[DONE]")

if __name__ == "__main__":
    main()