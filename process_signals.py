"""
ECG, PPG & PCG (Audio) Signal Processing Pipeline for ESP32
Features:
- ECG: Bandpass (0.5-40Hz) + Notch (50Hz) + Wavelet Denoising (db6)
- PPG: Bandpass (0.5-8Hz) + Wavelet Denoising (sym8, specific cA/cD handling)
- PCG: Bandpass (25-400Hz) for Heart Sounds
- Feature Extraction: R-peaks (ECG), BPM Calculation
- Output: Professional 3-row layout plot
"""

import os
import sys
import glob
import re
import argparse
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
import pywt # Requires: pip install PyWavelets

# Cấu hình Default
DEFAULT_FS_ECG = 500
DEFAULT_FS_PPG = 500
DEFAULT_FS_AUDIO = 16000

def parse_log_file(filepath):
    """Đọc file log và phân loại dữ liệu, đồng thời ước tính FS"""
    data = {'ecg_raw': [], 'ppg_ir_raw': [], 'ppg_red_raw': [], 'audio_raw': []}
    
    # Track duration per sensor type (Sequential Mode)
    # We assume runtime_sec implies the duration of the *currently active* measurement
    current_active_sensor = None 
    timestamps = collections.defaultdict(list) # store (line, val) per sensor
    
    # Tạm dùng max runtime_sec cho mỗi loại
    max_runtime = {'ecg': 0, 'ppg': 0, 'audio': 0}

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if line.startswith('>'):
                match = re.match(r'>(\w+):(-?[\d.]+)', line)
                if match:
                    name, value = match.group(1), float(match.group(2))
                    
                    if name == 'ecg_raw':
                        data['ecg_raw'].append(value)
                        current_active_sensor = 'ecg'
                    elif name == 'ppg_ir_raw':
                        data['ppg_ir_raw'].append(value)
                        current_active_sensor = 'ppg'
                    elif name == 'ppg_red_raw':
                        data['ppg_red_raw'].append(value)
                        current_active_sensor = 'ppg'
                    elif name in ['audio', 'audio_raw']:
                        data['audio_raw'].append(value)
                        current_active_sensor = 'audio'
                    
                    elif name == 'runtime_sec':
                        if current_active_sensor:
                            max_runtime[current_active_sensor] = max(max_runtime[current_active_sensor], value)

    # Convert to numpy array
    for key in data:
        data[key] = np.array(data[key])
        
    # Tính toán FS thực tế
    estimated_fs = {}
    
    # ECG FS
    if len(data['ecg_raw']) > 0 and max_runtime['ecg'] > 0:
        estimated_fs['ecg'] = len(data['ecg_raw']) / max_runtime['ecg']
    
    # PPG FS
    if len(data['ppg_ir_raw']) > 0 and max_runtime['ppg'] > 0:
        estimated_fs['ppg'] = len(data['ppg_ir_raw']) / max_runtime['ppg']
        
    # Audio FS
    if len(data['audio_raw']) > 0 and max_runtime['audio'] > 0:
        estimated_fs['audio'] = len(data['audio_raw']) / max_runtime['audio']
            
    print(f"Estimated FS: {estimated_fs}")
            
    return data, estimated_fs

# ==========================================================
# CÁC HÀM XỬ LÝ TÍN HIỆU (Signal Processing Functions)
# ==========================================================

def bandpass_filter(data, lowcut, highcut, fs, order=4):
    """Lọc thông dải Butterworth"""
    if len(data) == 0: return data
    nyq = 0.5 * fs
    
    # Check Nyquist
    if highcut >= nyq:
        print(f"Warning: Highcut ({highcut}Hz) >= Nyquist ({nyq}Hz). Adjusting to {nyq*0.9}Hz.")
        highcut = nyq * 0.99
    
    if lowcut >= highcut:
        print(f"Warning: Lowcut ({lowcut}Hz) >= Highcut ({highcut}Hz). Skipping Bandpass.")
        return data

    low = lowcut / nyq
    high = highcut / nyq
    
    # Clip to valid range
    low = max(0.001, min(0.999, low))
    high = max(0.001, min(0.999, high))
    
    try:
        b, a = signal.butter(order, [low, high], btype='band')
        return signal.filtfilt(b, a, data)
    except Exception as e:
        print(f"Bandpass Error: {e}")
        return data

def notch_filter(data, cutoff, q, fs):
    """Lọc chắn dải (Notch) để loại bỏ nhiễu nguồn (50Hz)"""
    if len(data) == 0: return data
    nyq = 0.5 * fs
    
    if cutoff >= nyq:
        print(f"Warning: Notch freq ({cutoff}Hz) >= Nyquist ({nyq}Hz). Skipping Notch.")
        return data

    freq = cutoff / nyq
    try:
        b, a = signal.iirnotch(freq, q)
        return signal.filtfilt(b, a, data)
    except Exception as e:
        print(f"Notch Error: {e}")
        return data

def wavelet_denoise_ecg(data, wavelet='db6', level=4):
    """Wavelet Denoising cho ECG (db6)"""
    if len(data) == 0: return data
    
    # Max level check
    max_level = pywt.dwt_max_level(len(data), pywt.Wavelet(wavelet).dec_len)
    level = min(level, max_level)
    if level == 0: return data

    coeffs = pywt.wavedec(data, wavelet, level=level)
    sigma = np.median(np.abs(coeffs[-1])) / 0.6745
    threshold = sigma * np.sqrt(2 * np.log(len(data)))
    new_coeffs = [coeffs[0]]
    for i in range(1, len(coeffs)):
        new_coeffs.append(pywt.threshold(coeffs[i], threshold, mode='soft'))
    return pywt.waverec(new_coeffs, wavelet)

def wavelet_denoise_ppg(data, wavelet='sym8', level=4):
    """Wavelet Denoising cho PPG (sym8)"""
    if len(data) == 0: return data
    # Giới hạn level phân rã nếu dữ liệu ngắn
    max_level = pywt.dwt_max_level(len(data), pywt.Wavelet(wavelet).dec_len)
    level = min(level, max_level)
    
    coeffs = pywt.wavedec(data, wavelet, level=level)
    new_coeffs = []
    new_coeffs.append(coeffs[0]) # Giữ cA
    for i in range(1, len(coeffs)):
        # Loại bỏ mạnh tay hơn các chi tiết cao tần để làm mịn (smooth)
        if i >= len(coeffs) - 2: 
             new_coeffs.append(np.zeros_like(coeffs[i]))
        else:
             threshold = np.std(coeffs[i]) * 2.0 # Tăng threshold lên gấp đôi
             new_coeffs.append(pywt.threshold(coeffs[i], threshold, mode='soft'))
    return pywt.waverec(new_coeffs, wavelet)

# ==========================================================
# FEATURE EXTRACTION
# ==========================================================

# ==========================================================
# FEATURE EXTRACTION
# ==========================================================

def detect_r_peaks(ecg_signal, fs):
    """Tìm đỉnh R và tính nhịp tim"""
    # Tìm đỉnh (distance=0.4s tương đương max 150bpm, height tuỳ biên độ)
    # Quy chuẩn biên độ về 0-1 để dễ set threshold
    if len(ecg_signal) == 0: return [], 0
    
    # Normalize tạm thời
    sig_norm = (ecg_signal - np.min(ecg_signal)) / (np.max(ecg_signal) - np.min(ecg_signal) + 1e-6)
    
    # Khoảng cách tối thiểu giữa các đỉnh (0.25s -> max 240bpm)
    min_dist = max(1, int(0.25 * fs))
    
    peaks, _ = signal.find_peaks(sig_norm, distance=min_dist, prominence=0.3)
    
    bpm = 0
    if len(peaks) > 1:
        # Tính khoảng cách trung bình các đỉnh (samples)
        intervals = np.diff(peaks)
        avg_interval = np.mean(intervals)
        bpm = (60.0 * fs) / avg_interval
        
    return peaks, bpm

def find_stable_window(data, fs, window_sec=6.0):
    """Tìm khoảng thời gian ổn định nhất (6 giây)"""
    N = len(data)
    window_len = int(window_sec * fs)
    
    if N <= window_len:
        return 0, N # Lấy hết nếu ngắn hơn window
        
    # Bỏ qua 15% đầu và cuối (transient)
    start_search = int(N * 0.15)
    end_search = int(N * 0.85)
    
    if end_search - start_search < window_len:
        start_search = 0
        end_search = N - window_len
        
    best_start = start_search
    min_std_diff = float('inf')
    
    # Scan từng bước (step = 0.5s)
    step = int(0.5 * fs)
    target_std = np.std(data) # Std chung của cả file
    
    for i in range(start_search, end_search - window_len, step):
        segment = data[i : i + window_len]
        local_std = np.std(segment)
        # Tìm đoạn có độ lệch chuẩn gần với trung bình nhất (không quá phẳng, không quá nhiễu)
        diff = abs(local_std - target_std)
        if diff < min_std_diff:
            min_std_diff = diff
            best_start = i
            
    return best_start, best_start + window_len

# ==========================================================
# MAIN PROCESSING PIPELINES
# ==========================================================

def process_ecg(raw_data, fs):
    """Quy trình xử lý ECG"""
    filtered = notch_filter(raw_data, 50.0, 30.0, fs)
    filtered = bandpass_filter(filtered, 0.5, 40.0, fs)
    filtered = wavelet_denoise_ecg(filtered)
    return filtered

def process_ppg(raw_data, fs):
    """Quy trình xử lý PPG"""
    inverted_data = -1 * raw_data
    filtered = bandpass_filter(inverted_data, 0.5, 5.0, fs) 
    filtered = wavelet_denoise_ppg(filtered, level=4)
    return filtered

def process_pcg(raw_data, fs):
    """Quy trình xử lý PCG"""
    return bandpass_filter(raw_data, 25.0, 400.0, fs)

# ==========================================================
# PLOTTING
# ==========================================================

def create_plots(data, output_file, log_filename, fs_config):
    ecg = data['ecg_raw']
    ppg_ir = data['ppg_ir_raw']
    ppg_red = data['ppg_red_raw']
    audio = data['audio_raw']
    
    fs_ecg = fs_config['ecg']
    fs_ppg = fs_config['ppg']
    fs_audio = fs_config['audio']
    
    # Xử lý
    ecg_clean = process_ecg(ecg, fs_ecg)
    ppg_ir_clean = process_ppg(ppg_ir, fs_ppg)
    ppg_red_clean = process_ppg(ppg_red, fs_ppg)
    pcg_clean = process_pcg(audio, fs_audio) if len(audio) > 0 else np.zeros(100)
    
    # --- SMART ZOOM (INDEPENDENT) ---
    WINDOW_SEC = 30.0
    
    # Helper to get view slice
    def get_best_view(data, fs, name):
        if len(data) == 0: return [], 0, WINDOW_SEC
        s_idx, e_idx = find_stable_window(data, fs, WINDOW_SEC)
        s_time = s_idx / fs
        e_time = e_idx / fs
        print(f"Best Window for {name}: {s_time:.1f}s - {e_time:.1f}s")
        return data[s_idx:e_idx], s_time, e_time

    # Slice Data Independently
    ecg_view, t_start_ecg, t_end_ecg = get_best_view(ecg_clean, fs_ecg, "ECG")
    red_view, t_start_ppg, t_end_ppg = get_best_view(ppg_red_clean, fs_ppg, "PPG Red")
    
    # Sync IR to Red (same time domain)
    s_ppg = int(t_start_ppg * fs_ppg)
    e_ppg = int(t_end_ppg * fs_ppg)
    ir_view = ppg_ir_clean[s_ppg:e_ppg] if len(ppg_ir_clean) > s_ppg else []
    
    pcg_view, t_start_pcg, t_end_pcg = get_best_view(pcg_clean, fs_audio, "Audio")

    # Tìm đỉnh ECG trong vùng view
    peaks, bpm_ecg = detect_r_peaks(ecg_view, fs_ecg)

    # --- VẼ BIỂU ĐỒ (4 Hàng) ---
    fig, axes = plt.subplots(4, 1, figsize=(12, 14), sharex=False)
    
    # 1. ECG Plot
    ax1 = axes[0]
    t_ecg = np.linspace(t_start_ecg, t_end_ecg, len(ecg_view))
    
    # ax1.plot(t_ecg, ecg[s_ecg:e_ecg], color='gray', alpha=0.3, linewidth=0.5, label='Raw')
    ax1.plot(t_ecg, ecg_view, color='#f39c12', linewidth=1.5, label='Filtered ECG')
    
    if len(peaks) > 0:
        peak_times = t_ecg[peaks]
        ax1.plot(peak_times, ecg_view[peaks], 'r+', markersize=10, label=f'R-Peaks')
    
    ax1.set_title(f"ECG Signal ({t_start_ecg:.0f}-{t_end_ecg:.0f}s) - HR: {bpm_ecg:.1f} BPM", fontweight='bold')
    ax1.set_ylabel("Amplitude")
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.5)
    
    # 2. PPG Red Plot
    ax2 = axes[1]
    t_ppg = np.linspace(t_start_ppg, t_end_ppg, len(red_view))
    
    ax2.plot(t_ppg, red_view, color='#c0392b', linewidth=1.5)
    ax2.set_title(f"PPG RED Signal ({t_start_ppg:.0f}-{t_end_ppg:.0f}s)", fontweight='bold')
    ax2.set_ylabel("Amplitude")
    ax2.grid(True, alpha=0.5)

    # 3. PPG IR Plot
    ax3 = axes[2]
    # Use same time axis as Red
    if len(ir_view) != len(t_ppg):
         # Resize if mismatch due to rounding
         t_ppg_ir = np.linspace(t_start_ppg, t_end_ppg, len(ir_view))
         ax3.plot(t_ppg_ir, ir_view, color='#27ae60', linewidth=1.5)
    else:
         ax3.plot(t_ppg, ir_view, color='#27ae60', linewidth=1.5)
         
    ax3.set_title(f"PPG IR Signal ({t_start_ppg:.0f}-{t_end_ppg:.0f}s)", fontweight='bold')
    ax3.set_ylabel("Amplitude")
    ax3.grid(True, alpha=0.5)

    # 4. PCG Plot
    ax4 = axes[3]
    t_pcg = np.linspace(t_start_pcg, t_end_pcg, len(pcg_view))
    if np.max(np.abs(pcg_view)) > 0:
        ax4.plot(t_pcg, pcg_view, color='#2980b9', linewidth=0.8)
    else:
        ax4.text(t_start_pcg + WINDOW_SEC/2, 0, "NO AUDIO DATA", ha='center', fontsize=12)
        
    ax4.set_title(f"PCG ({t_start_pcg:.0f}-{t_end_pcg:.0f}s)", fontweight='bold')
    ax4.set_xlabel("Time (seconds)")
    ax4.set_ylabel("Amplitude")
    ax4.grid(True, alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    print(f"Saved plot: {output_file}")
    plt.close()

def find_latest_log(data_dir):
    files = glob.glob(os.path.join(data_dir, "serial_log_*.txt"))
    return max(files, key=os.path.getmtime) if files else None

def main():
    parser = argparse.ArgumentParser(description="ESP32 Signal Processing")
    parser.add_argument("logfile", nargs='?', help="Path to log file")
    parser.add_argument("--fs-ecg", type=int, default=DEFAULT_FS_ECG, help=f"ECG Sampling Rate (default: {DEFAULT_FS_ECG})")
    parser.add_argument("--fs-audio", type=int, default=DEFAULT_FS_AUDIO, help="Audio Sampling Rate")
    
    args = parser.parse_args()
    
    # Determine Log File
    log_file = args.logfile
    if not log_file:
        log_file = find_latest_log("data_logs")
        
    if not log_file:
        print("Error: No log file found!")
        return

    print(f"Reading: {log_file}")
    print(f"Settings (Input): FS_ECG={args.fs_ecg}Hz, FS_AUDIO={args.fs_audio}Hz")

    # Parse and Estimate FS
    data, estimated_fs = parse_log_file(log_file)
    print(f"Samples - ECG: {len(data['ecg_raw'])}, PPG IR: {len(data['ppg_ir_raw'])}, PPG Red: {len(data['ppg_red_raw'])}")
    
    # Use estimated FS if available (Priority)
    fs_config = {
        'ecg': estimated_fs.get('ecg', args.fs_ecg),
        'ppg': estimated_fs.get('ppg', DEFAULT_FS_PPG),
        'audio': args.fs_audio
    }
    
    if 'ppg' in estimated_fs:
        print(f"*** USING ESTIMATED FS FROM LOG FILE ***")
        print(f"   -> PPG FS: {fs_config['ppg']:.1f} Hz (instead of {DEFAULT_FS_PPG})")
        print(f"   -> ECG FS: {fs_config['ecg']:.1f} Hz")
    
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(DEFAULT_OUTPUT_DIR, f"result_{timestamp}.png")
    
    create_plots(data, output_file, log_file, fs_config)
    print("Done.")

# Directory Config moved here to be accessible
DEFAULT_OUTPUT_DIR = "processed_data"

if __name__ == "__main__":
    main()
