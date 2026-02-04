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

# CẤU HÌNH
DEFAULT_FS_ECG = 1000    
DEFAULT_FS_PPG = 100     
DEFAULT_FS_AUDIO = 1000   
OUTPUT_DIR = "processed_data"
WINDOW_SEC = 10.0        

# ĐỌC FILE LOG
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
    
    # Ước tính sample rate thực tế dựa trên runtime cuối cùng
    estimated_fs = {}
    
    # Lấy runtime lớn nhất (thường là runtime cuối cùng ghi được)
    max_runtime_val = 0
    if max_runtime:
        max_runtime_val = max(max_runtime.values())
    
    if max_runtime_val > 0:
        if len(data['ecg_raw']) > 0:
            estimated_fs['ecg'] = len(data['ecg_raw']) / max_runtime_val
        if len(data['ppg_ir_raw']) > 0:
            estimated_fs['ppg'] = len(data['ppg_ir_raw']) / max_runtime_val
            
    print(f"  [Auto-Detect FS] Runtime: {max_runtime_val}s")
    if 'ecg' in estimated_fs:
        print(f"  [Auto-Detect FS] ECG: {estimated_fs['ecg']:.2f} Hz (Samples: {len(data['ecg_raw'])})")
    if 'ppg' in estimated_fs:
        print(f"  [Auto-Detect FS] PPG: {estimated_fs['ppg']:.2f} Hz (Samples: {len(data['ppg_ir_raw'])})")
    
    return data, estimated_fs

# XỬ LÝ ARTIFACT ECG
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

# CÁC BỘ LỌC (FILTERS)
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

# PIPELINE XỬ LÝ ECG
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
   # filtered = notch_filter(cleaned, 50.0, 30.0, fs)
    filtered = cleaned
    # Step 4: Bandpass 0.5-40Hz (Reduced order to minimize ringing)
    filtered = butter_bandpass(filtered, 0.5, 40.0, fs, order=2)
    
    # Step 5: Wavelet denoise (optional)
    #if HAS_PYWT:
     #   filtered = wavelet_denoise(filtered, 'db6', 4)
    
    return filtered

# PIPELINE XỬ LÝ PPG
def remove_ppg_artifacts(data):
    """
    Loại bỏ artifact trong PPG (giá trị bất thường).
    MAX30102 output thường trong khoảng ổn định, outliers = artifact.
    """
    if len(data) < 10:
        return data
    
    data = np.array(data, dtype=float)
    
    # Bỏ 15% đầu (thường có transient lớn khi bắt đầu đo)
    skip_samples = int(len(data) * 0.15)
    stable_region = data[skip_samples:]
    
    if len(stable_region) < 10:
        stable_region = data
    
    # Tính ngưỡng dựa trên phần ổn định
    q1 = np.percentile(stable_region, 10)
    q3 = np.percentile(stable_region, 90)
    iqr = q3 - q1
    
    # Ngưỡng chặt hơn
    low_thresh = q1 - 1.5 * iqr
    high_thresh = q3 + 1.5 * iqr
    
    # Tìm artifact trên toàn bộ dữ liệu
    artifact_mask = (data < low_thresh) | (data > high_thresh)
    
    # Mở rộng vùng artifact (trước 5, sau 10)
    indices = np.where(artifact_mask)[0]
    for idx in indices:
        start = max(0, idx - 5)
        end = min(len(data), idx + 10)
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
    smoothed = uniform_filter1d(filtered, size=2)
    
    # Step 6: Invert signal (Because Absorption increases -> Reflection decreases)
    # We want peaks to represent pulsation (high blood volume)
    return -smoothed

def calculate_spo2(red_raw, red_clean, ir_raw, ir_clean):
    """
    Tính SpO2 từ tín hiệu PPG Red và IR (Ratio of Ratios).
    AC được tính từ tín hiệu đã lọc (STD), DC được tính từ tín hiệu thô (MEAN).
    """
    if len(red_raw) < 10 or len(ir_raw) < 10:
        return 0.0
    
    # DC: Giá trị trung bình của tín hiệu thô
    dc_red = np.mean(red_raw)
    dc_ir = np.mean(ir_raw)
    
    # AC: Standard deviation của tín hiệu đã qua lọc
    ac_red = np.std(red_clean)
    ac_ir = np.std(ir_clean)
    
    if dc_red > 100 and dc_ir > 100 and ac_ir > 0:
        # Tỷ số R
        R = (ac_red / dc_red) / (ac_ir / dc_ir)
        
        # Công thức thực nghiệm (MAX30102 chuẩn)
        spo2 = 110 - 25 * R
        
        # Giới hạn thực tế
        return max(50.0, min(100.0, spo2))
    
    return 0.0

# TÌM ĐỈNH R VÀ TÍNH NHỊP TIM
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

def detect_ppg_peaks(ppg, fs):
    """
    Phát hiện đỉnh systolic và tính nhịp tim từ PPG
    Thận trọng hơn ECG để tránh dicrotic notch.
    """
    if len(ppg) < 100:
        return [], 0
        
    # Normalize Min-Max
    ppg_norm = (ppg - np.min(ppg)) / (np.max(ppg) - np.min(ppg) + 1e-6)
    
    # Distance lớn hơn (0.4s) để né nhiễu dội
    min_dist = int(0.4 * fs)
    
    # Prominence thấp hơn (0.2) do biên độ PPG biến thiên
    peaks, _ = signal.find_peaks(ppg_norm, distance=min_dist, prominence=0.2)
    
    hr = 0
    if len(peaks) > 1:
        intervals = np.diff(peaks)
        avg_interval_sec = np.mean(intervals) / fs
        hr = 60.0 / avg_interval_sec
        
    return peaks, hr


def find_stable_segment(data, fs, window_sec):
    """Tìm đoạn tín hiệu ổn định nhất trong data"""
    N = len(data)
    win_len = int(window_sec * fs)
    
    if N <= win_len:
        return 0, N
    
    # Skip 30% đầu (transient khi cảm biến ổn định) và 10% cuối
    start_range = int(N * 0.3)
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


def create_plot(data, fs_config, output_file, window_sec=30.0):
    """Tạo biểu đồ 4 hàng: ECG, PPG Red, PPG IR, Audio"""
    
    ecg = data['ecg_raw']
    ppg_ir = data['ppg_ir_raw']
    ppg_red = data['ppg_red_raw']
    audio = data['audio_raw']
    
    fs_ecg = fs_config.get('ecg', DEFAULT_FS_ECG)
    fs_ppg = fs_config.get('ppg', DEFAULT_FS_PPG)
    fs_audio = fs_config.get('audio', 100)  # Audio logging rate
    
    # Xử lý tín hiệu
    ecg_clean = process_ecg(ecg, fs_ecg) if len(ecg) > 0 else np.array([])
    ppg_ir_clean = process_ppg(ppg_ir, fs_ppg) if len(ppg_ir) > 0 else np.array([])
    ppg_red_clean = process_ppg(ppg_red, fs_ppg) if len(ppg_red) > 0 else np.array([])
    
    # Simple audio processing: remove DC and normalize
    audio_clean = np.array([])
    if len(audio) > 0:
        audio_clean = audio - np.mean(audio)  # Remove DC
        audio_max = np.max(np.abs(audio_clean))
        if audio_max > 0:
            audio_clean = audio_clean / audio_max  # Normalize
    
    # Tìm đoạn ổn định nhất cho ECG
    if len(ecg_clean) > 0:
        s_ecg, e_ecg = find_stable_segment(ecg_clean, fs_ecg, window_sec)
        t_start = s_ecg / fs_ecg
        t_end = e_ecg / fs_ecg
    else:
        t_start, t_end = 0, window_sec
        s_ecg, e_ecg = 0, 0
    
    print(f"  [Best Window] ECG: {t_start:.1f}s - {t_end:.1f}s (best {window_sec}s)")
    
    # Cắt ECG
    ecg_view = ecg_clean[s_ecg:e_ecg] if len(ecg_clean) > 0 else np.zeros(100)
    ecg_raw_view = ecg[s_ecg:e_ecg] if len(ecg) > 0 else np.zeros(100)
    
    # Cắt PPG
    s_ppg = int(t_start * fs_ppg)
    e_ppg = int(t_end * fs_ppg)
    
    def safe_slice(arr, start, end):
        if len(arr) == 0: return np.zeros(100)
        start = max(0, min(start, len(arr)-1))
        end = max(start, min(end, len(arr)))
        return arr[start:end]

    ppg_red_view = safe_slice(ppg_red_clean, s_ppg, e_ppg)
    ppg_ir_view = safe_slice(ppg_ir_clean, s_ppg, e_ppg)
    ppg_red_raw_view = safe_slice(ppg_red, s_ppg, e_ppg)
    ppg_ir_raw_view = safe_slice(ppg_ir, s_ppg, e_ppg)
    
    # Cắt Audio
    s_audio = int(t_start * fs_audio)
    e_audio = int(t_end * fs_audio)
    audio_view = safe_slice(audio_clean, s_audio, e_audio)
    audio_raw_view = safe_slice(audio, s_audio, e_audio)
    
    # Tính HR
    ecg_peaks, ecg_hr = detect_r_peaks(ecg_view, fs_ecg)
    ppg_peaks, ppg_hr = detect_ppg_peaks(ppg_red_view, fs_ppg)
    
    # Tính SpO2 (Sử dụng đoạn tín hiệu hiển thị)
    spo2_val = calculate_spo2(ppg_red_raw_view, ppg_red_view, ppg_ir_raw_view, ppg_ir_view)
    
    # Tạo trục thời gian
    t_ecg = np.linspace(t_start, t_end, len(ecg_view))
    t_ppg = np.linspace(t_start, t_end, len(ppg_red_view))
    t_audio = np.linspace(t_start, t_end, len(audio_view))
    
    # === PLOT 1: FILTERED ===
    fig_filt, ax_filt = plt.subplots(4, 1, figsize=(14, 12))
    
    # ECG Filtered
    ax_filt[0].plot(t_ecg, ecg_view, 'orange', linewidth=1, label='ECG Filtered')
    if len(ecg_peaks) > 0:
        ax_filt[0].plot(t_ecg[ecg_peaks], ecg_view[ecg_peaks], 'r+', markersize=10, label='R-peaks')
    ax_filt[0].set_title(f"ECG Filtered | Heart Rate: {ecg_hr:.0f} BPM", fontweight='bold')
    ax_filt[0].set_ylabel("Amplitude")
    ax_filt[0].legend(loc='upper right')
    ax_filt[0].grid(True, alpha=0.4)
    
    # PPG Red Filtered
    ax_filt[1].plot(t_ppg, ppg_red_view, 'red', linewidth=1)
    if len(ppg_peaks) > 0:
        ax_filt[1].plot(t_ppg[ppg_peaks], ppg_red_view[ppg_peaks], 'b*', markersize=8, label='Peaks')
    ax_filt[1].set_title(f"PPG Red Filtered (660nm) | HR: {ppg_hr:.0f} BPM | SpO2: {spo2_val:.1f}%", fontweight='bold')
    ax_filt[1].set_ylabel("Amplitude")
    ax_filt[1].grid(True, alpha=0.4)
    # ax_filt[1].invert_xaxis() # Removed inversion in plot display to match detect_r_peaks logic
    
    # PPG IR Filtered
    ax_filt[2].plot(t_ppg, ppg_ir_view, 'green', linewidth=1)
    ax_filt[2].set_title(f"PPG IR Filtered (880nm) | SpO2 Estimate: {spo2_val:.1f}%", fontweight='bold')
    ax_filt[2].set_ylabel("Amplitude")
    ax_filt[2].grid(True, alpha=0.4)
    # ax_filt[2].invert_xaxis()
    
    # Audio 
    ax_filt[3].plot(t_audio, audio_view, 'blue', linewidth=0.5)
    ax_filt[3].set_title(f"Audio (INMP441) | Samples: {len(audio)}", fontweight='bold')
    ax_filt[3].set_xlabel("Time (seconds)")
    ax_filt[3].set_ylabel("Amplitude")
    ax_filt[3].grid(True, alpha=0.4)

    plt.tight_layout()
    file_filt = output_file.replace(".png", "_filtered.png")
    fig_filt.savefig(file_filt, dpi=150)
    print(f"\n[OK] Saved Filtered Plot: {file_filt}")
    plt.close(fig_filt)

    # === PLOT 2: RAW ===
    fig_raw, ax_raw = plt.subplots(4, 1, figsize=(14, 12))
    
    # ECG Raw
    ax_raw[0].plot(t_ecg, ecg_raw_view, 'gray', linewidth=1)
    ax_raw[0].set_title(f"ECG Raw (ADC Value)", fontweight='bold')
    ax_raw[0].set_ylabel("ADC Value")
    ax_raw[0].grid(True, alpha=0.4)
    
    # PPG Red Raw (Inverted)
    ax_raw[1].plot(t_ppg, -ppg_red_raw_view, 'gray', linewidth=1)
    ax_raw[1].set_title(f"PPG Red Raw (Inverted ADC)", fontweight='bold')
    ax_raw[1].set_ylabel("Inverted ADC")
    ax_raw[1].grid(True, alpha=0.4)
    ax_raw[1].invert_xaxis()
    
    # PPG IR Raw (Inverted)
    ax_raw[2].plot(t_ppg, -ppg_ir_raw_view, 'gray', linewidth=1)
    ax_raw[2].set_title(f"PPG IR Raw (Inverted ADC)", fontweight='bold')
    ax_raw[2].set_ylabel("Inverted ADC")
    ax_raw[2].grid(True, alpha=0.4)
    ax_raw[2].invert_xaxis()
    
    # Audio Raw
    ax_raw[3].plot(t_audio, audio_raw_view, 'gray', linewidth=0.5)
    ax_raw[3].set_title(f"Audio Raw (INMP441)", fontweight='bold')
    ax_raw[3].set_xlabel("Time (seconds)")
    ax_raw[3].set_ylabel("Raw Value")
    ax_raw[3].grid(True, alpha=0.4)
    
    plt.tight_layout()
    file_raw = output_file.replace(".png", "_raw.png")
    fig_raw.savefig(file_raw, dpi=150)
    print(f"[OK] Saved Raw Plot:      {file_raw}")
    plt.close(fig_raw)

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
    print(f"[INFO] Samples - ECG: {len(data['ecg_raw'])}, PPG IR: {len(data['ppg_ir_raw'])}, PPG Red: {len(data['ppg_red_raw'])}, Audio: {len(data['audio_raw'])}")
    
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
    create_plot(data, fs_config, output_file, window_sec)
    print("[DONE]")

if __name__ == "__main__":
    main()