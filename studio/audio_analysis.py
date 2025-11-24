import librosa
import numpy as np
import soundfile as sf
import os
import noisereduce as nr
import pyloudnorm as pyln
from django.conf import settings
import json
from scipy import signal, interpolate
from pedalboard import Pedalboard, Compressor, Limiter, HighpassFilter, LowpassFilter, PeakFilter, Gain
import warnings
import traceback
import sys
import io
warnings.filterwarnings('ignore')

def sanitize_for_json(data):
    """
    Recursively sanitize data for JSON serialization.
    Converts numpy types to Python types and replaces NaN/Infinity with None.
    """
    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_for_json(v) for v in data]
    elif isinstance(data, (float, np.floating)):
        if np.isnan(data) or np.isinf(data):
            return None
        return float(data)
    elif isinstance(data, (int, np.integer)):
        return int(data)
    elif isinstance(data, np.ndarray):
        return sanitize_for_json(data.tolist())
    return data

def analyze_audio(file_path):
    """
    Analyze audio file for comprehensive metrics including LUFS, true peaks,
    spectral features, dynamic range, and artifacts.
    """
    try:
        y, sr = librosa.load(file_path, sr=None, mono=False)
        
        # Handle stereo vs mono
        is_stereo = len(y.shape) == 2
        if is_stereo:
            y_mono = librosa.to_mono(y)
        else:
            y_mono = y
        
        # === AMPLITUDE METRICS ===
        # Peak amplitude (dB)
        peak_amp = np.max(np.abs(y_mono))
        peak_db = librosa.amplitude_to_db(np.array([peak_amp]))[0] if peak_amp > 0 else -np.inf
        
        # True Peak (interpolated) - more accurate for limiting purposes
        # Upsample by 4x and find peak
        y_upsampled = signal.resample(y_mono, len(y_mono) * 4)
        true_peak_amp = np.max(np.abs(y_upsampled))
        true_peak_db = librosa.amplitude_to_db(np.array([true_peak_amp]))[0] if true_peak_amp > 0 else -np.inf
        
        # RMS (Root Mean Square) energy
        rms = librosa.feature.rms(y=y_mono)[0]
        avg_rms = np.mean(rms)
        rms_db = librosa.amplitude_to_db(np.array([avg_rms]))[0] if avg_rms > 0 else -np.inf
        
        # Dynamic Range (peak to RMS)
        dynamic_range = peak_db - rms_db
        
        # Crest Factor (peak to average ratio)
        crest_factor = peak_db - rms_db  # Same as dynamic range in dB
        
        # Estimate noise floor (10th percentile of RMS energy)
        noise_floor_db = librosa.amplitude_to_db(np.array([np.percentile(rms, 10)]))[0]
        
        # === SPECTRAL ANALYSIS ===
        # Spectral centroid (brightness)
        spectral_centroids = librosa.feature.spectral_centroid(y=y_mono, sr=sr)[0]
        spectral_centroid_mean = float(np.mean(spectral_centroids))
        
        # Spectral bandwidth (spread of frequencies)
        spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y_mono, sr=sr)[0]
        spectral_bandwidth_mean = float(np.mean(spectral_bandwidth))
        
        # Frequency bins analysis (bass, mids, highs)
        D = np.abs(librosa.stft(y_mono))
        freqs = librosa.fft_frequencies(sr=sr)
        mean_spectrum = np.mean(D, axis=1)
        
        # Define frequency bands
        bass = np.mean(mean_spectrum[(freqs >= 20) & (freqs < 250)])
        low_mids = np.mean(mean_spectrum[(freqs >= 250) & (freqs < 500)])
        mids = np.mean(mean_spectrum[(freqs >= 500) & (freqs < 2000)])
        high_mids = np.mean(mean_spectrum[(freqs >= 2000) & (freqs < 4000)])
        presence = np.mean(mean_spectrum[(freqs >= 4000) & (freqs < 6000)])
        highs = np.mean(mean_spectrum[(freqs >= 6000)])
        
        frequency_balance = {
            'bass_db': float(librosa.amplitude_to_db(np.array([bass]))[0]) if bass > 0 else -np.inf,
            'low_mids_db': float(librosa.amplitude_to_db(np.array([low_mids]))[0]) if low_mids > 0 else -np.inf,
            'mids_db': float(librosa.amplitude_to_db(np.array([mids]))[0]) if mids > 0 else -np.inf,
            'high_mids_db': float(librosa.amplitude_to_db(np.array([high_mids]))[0]) if high_mids > 0 else -np.inf,
            'presence_db': float(librosa.amplitude_to_db(np.array([presence]))[0]) if presence > 0 else -np.inf,
            'highs_db': float(librosa.amplitude_to_db(np.array([highs]))[0]) if highs > 0 else -np.inf,
        }
        
        # === CLIPPING & TRANSIENT ANALYSIS ===
        clipping_threshold = 0.99
        clipping_samples = np.abs(y_mono) > clipping_threshold
        clipping_count = int(np.sum(clipping_samples))
        
        sustained_clips = 0
        if clipping_count > 0:
            clipping_diff = np.diff(np.concatenate(([0], clipping_samples.astype(int), [0])))
            clip_starts = np.where(clipping_diff == 1)[0]
            clip_ends = np.where(clipping_diff == -1)[0]
            sustained_clips = int(np.sum((clip_ends - clip_starts) > 3))
        
        onset_env = librosa.onset.onset_strength(y=y_mono, sr=sr)
        transient_density = float(np.mean(onset_env))
        
        # === LOUDNESS MEASUREMENT ===
        try:
            meter = pyln.Meter(sr)
            if is_stereo:
                lufs = meter.integrated_loudness(y.T)
            else:
                lufs = meter.integrated_loudness(y_mono)
        except Exception as e:
            print(f"LUFS calculation error: {e}")
            lufs = -99.0
        
        # === STEREO ANALYSIS ===
        phase_correlation = None
        stereo_width = None
        if is_stereo:
            try:
                left = y[0]
                right = y[1]
                phase_correlation = float(np.corrcoef(left, right)[0, 1])
                mid = (left + right) / 2
                side = (left - right) / 2
                mid_energy = np.mean(mid**2)
                side_energy = np.mean(side**2)
                stereo_width = float(side_energy / (mid_energy + 1e-10))
            except Exception as e:
                print(f"Stereo analysis error: {e}")
        
        # === ARTIFACT DETECTION ===
        artifacts = detect_artifacts(y_mono, sr, is_stereo, y if is_stereo else None)
        
        raw_results = {
            'duration': float(librosa.get_duration(y=y_mono, sr=sr)),
            'sample_rate': int(sr),
            'channels': 2 if is_stereo else 1,
            'peak_db': float(peak_db),
            'true_peak_db': float(true_peak_db),
            'rms_db': float(rms_db),
            'dynamic_range_db': float(dynamic_range),
            'crest_factor_db': float(crest_factor),
            'noise_floor_db': float(noise_floor_db),
            'spectral_centroid_hz': spectral_centroid_mean,
            'spectral_bandwidth_hz': spectral_bandwidth_mean,
            'frequency_balance': frequency_balance,
            'clipping_count': clipping_count,
            'sustained_clips': sustained_clips,
            'transient_density': transient_density,
            'lufs': float(lufs),
            'phase_correlation': phase_correlation,
            'stereo_width': stereo_width,
            'artifacts': artifacts
        }
        
        return sanitize_for_json(raw_results), None
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        f = io.StringIO()
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
        return None, f"Error analyzing audio: {e}\n\nTraceback:\n{f.getvalue()}"

def detect_artifacts(y_mono, sr, is_stereo=False, stereo_data=None):
    """
    Detect specific audio artifacts: Clicks, Hum, Sibilance, Silence, DC Offset, Phase Issues.
    Enhanced with better algorithms and more comprehensive detection.
    """
    artifacts = {
        'clicks_detected': 0,
        'hum_frequency': None,
        'hum_harmonics': [],
        'sibilance_detected': False,
        'sibilance_level_db': -np.inf,
        'silence_percentage': 0.0,
        'dc_offset': 0.0,
        'phase_issues': False
    }
    try:
        # Click detection using MAD
        diff = np.diff(y_mono)
        median_diff = np.median(np.abs(diff))
        mad = np.median(np.abs(diff - np.median(diff)))
        threshold = np.median(diff) + 6 * mad * 1.4826
        clicks = np.sum(np.abs(diff) > threshold)
        artifacts['clicks_detected'] = int(clicks)
        # Hum detection
        n_fft = 8192
        D = np.abs(librosa.stft(y_mono, n_fft=n_fft))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
        mean_spectrum = np.mean(D, axis=1)
        hum_detected = False
        fundamental_freq = None
        for target_freq in [50, 60]:
            idx_min = np.argmax(freqs > target_freq - 3)
            idx_max = np.argmax(freqs > target_freq + 3)
            if idx_max > idx_min:
                band_spectrum = mean_spectrum[idx_min:idx_max]
                band_freqs = freqs[idx_min:idx_max]
                peak_idx = np.argmax(band_spectrum)
                peak_freq = band_freqs[peak_idx]
                peak_val = band_spectrum[peak_idx]
                if peak_val > 2.5 * np.mean(band_spectrum):
                    hum_detected = True
                    fundamental_freq = target_freq
                    artifacts['hum_frequency'] = target_freq
                    break
        if hum_detected and fundamental_freq:
            harmonics = []
            for harmonic_num in [2, 3, 4]:
                harmonic_freq = fundamental_freq * harmonic_num
                if harmonic_freq > sr / 2:
                    break
                idx_min = np.argmax(freqs > harmonic_freq - 5)
                idx_max = np.argmax(freqs > harmonic_freq + 5)
                if idx_max > idx_min:
                    band_spectrum = mean_spectrum[idx_min:idx_max]
                    peak_val = np.max(band_spectrum)
                    if peak_val > 1.5 * np.mean(band_spectrum):
                        harmonics.append(int(harmonic_freq))
            artifacts['hum_harmonics'] = harmonics
        # Sibilance detection
        idx_sib_min = np.argmax(freqs > 5000)
        idx_sib_max = np.argmax(freqs > 10000)
        if idx_sib_max > idx_sib_min:
            sibilance_spectrum = mean_spectrum[idx_sib_min:idx_sib_max]
            mid_spectrum = mean_spectrum[(freqs >= 500) & (freqs < 2000)]
            sib_energy = np.mean(sibilance_spectrum)
            mid_energy = np.mean(mid_spectrum)
            if mid_energy > 0:
                sib_ratio = sib_energy / mid_energy
                if sib_ratio > 0.3:
                    artifacts['sibilance_detected'] = True
                    artifacts['sibilance_level_db'] = float(librosa.amplitude_to_db(np.array([sib_energy]))[0])
        # Silence detection
        rms = librosa.feature.rms(y=y_mono)[0]
        rms_db = librosa.amplitude_to_db(rms)
        silence_frames = np.sum(rms_db < -60)
        total_frames = len(rms)
        artifacts['silence_percentage'] = float((silence_frames / total_frames) * 100)
        # DC offset
        artifacts['dc_offset'] = float(np.mean(y_mono))
        # Phase issues
        if is_stereo and stereo_data is not None:
            try:
                left = stereo_data[0]
                right = stereo_data[1]
                correlation = np.corrcoef(left, right)[0, 1]
                if correlation < -0.5:
                    artifacts['phase_issues'] = True
            except Exception as e:
                print(f"Phase detection error: {e}")
    except Exception as e:
        print(f"Artifact detection error: {e}")
        traceback.print_exc()
    return artifacts

def generate_suggestions(analysis_data):
    """
    Generate actionable suggestions based on analysis data.
    """
    suggestions = []
    
    # Helper to add suggestion
    def add_suggestion(severity, text, restoration_step=None):
        suggestions.append({
            'severity': severity,
            'text': text,
            'restoration_step': restoration_step
        })

    # === LOUDNESS & DYNAMICS ===
    lufs = analysis_data.get('lufs', -99)
    if lufs > -9:
        add_suggestion('high', 
            f"Loudness is very high ({lufs:.1f} LUFS). This will be heavily penalized by streaming services.",
            "Reduce Limiter gain or lower mix bus volume. Aim for -14 LUFS.")
    elif lufs > -12:
        add_suggestion('medium', 
            f"Loudness is slightly high ({lufs:.1f} LUFS). Target -14 LUFS for optimal streaming dynamics.",
            "Adjust final Limiter ceiling or threshold.")
    elif lufs < -18:
        add_suggestion('medium', 
            f"Loudness is low ({lufs:.1f} LUFS). Your track may sound quiet compared to others.",
            "Use a Limiter or Maximizer to increase integrated loudness to at least -16 LUFS.")

    dr = analysis_data.get('dynamic_range_db', 0)
    if dr < 6:
        add_suggestion('high', 
            f"Dynamic Range is very low ({dr:.1f} dB). The mix is over-compressed and lacks punch.",
            "Reduce compression ratios on the mix bus or individual groups. Allow transients to breathe.")
    elif dr > 16:
        add_suggestion('low', 
            f"Dynamic Range is high ({dr:.1f} dB). Good for classical/jazz, but may be too dynamic for pop/rock.",
            "Apply gentle compression (2:1 ratio) to glue the mix together.")

    # === CLIPPING ===
    clipping = analysis_data.get('clipping_count', 0)
    true_peak = analysis_data.get('true_peak_db', -99)
    if clipping > 0:
        add_suggestion('critical', 
            f"Detected {clipping} clipped samples. Digital distortion is likely audible.",
            "Use the 'De-clip' tool immediately. Ensure True Peak is below -1.0 dBTP.")
    elif true_peak > -1.0:
        add_suggestion('medium', 
            f"True Peak is {true_peak:.2f} dBTP, which is close to clipping (0 dB).",
            "Set your Limiter ceiling to -1.0 dBTP to prevent inter-sample peaks during transcoding.")

    # === FREQUENCY BALANCE ===
    freq_bal = analysis_data.get('frequency_balance', {})
    bass = freq_bal.get('bass_db', -99)
    mids = freq_bal.get('mids_db', -99)
    highs = freq_bal.get('highs_db', -99)
    
    if bass > -99 and mids > -99:
        bass_mid_ratio = bass - mids
        if bass_mid_ratio > 8:
            add_suggestion('medium', 
                "Low-end energy is significantly higher than mids. The mix may sound muddy or boomy.",
                "Apply a High-Pass Filter (HPF) at 30-40Hz. Cut 2-3dB at 250Hz on bass instruments.")
        elif bass_mid_ratio < -6:
            add_suggestion('medium', 
                "Low-end is weak compared to mids. The mix may lack warmth and body.",
                "Boost bass frequencies (60-100Hz) or check kick/bass levels.")

    if highs > -99 and mids > -99:
        high_mid_ratio = highs - mids
        if high_mid_ratio > 6:
            add_suggestion('medium', 
                "High frequencies are dominant. The mix may sound harsh or brittle.",
                "Use a De-esser on vocals/cymbals. Apply a gentle High-Cut (LPF) above 16kHz.")
        elif high_mid_ratio < -12:
            add_suggestion('low', 
                "High frequencies are recessed. The mix may sound dull or muffled.",
                "Add a 'High Shelf' boost at 10kHz or use an Exciter to add brilliance.")

    # === STEREO IMAGE ===
    width = analysis_data.get('stereo_width')
    phase = analysis_data.get('phase_correlation')
    
    if phase is not None and phase < 0:
        add_suggestion('high', 
            "Negative phase correlation detected. Major mono-compatibility issues.",
            "Check for stereo widening effects on bass/kick. Flip phase on one channel to test.")
    elif phase is not None and phase < 0.5:
        add_suggestion('medium', 
            "Phase correlation is low. Elements may disappear when summed to mono.",
            "Reduce stereo width on low-end elements (< 200Hz). Keep kick and bass mono.")

    if width is not None and width < 0.2:
        add_suggestion('low', 
            "Stereo image is very narrow (mostly mono).",
            "Pan instruments (guitars, synths) wider. Use stereo reverb or delay for space.")

    # === ARTIFACTS ===
    artifacts = analysis_data.get('artifacts', {})
    
    if artifacts.get('clicks_detected', 0) > 0:
        add_suggestion('high', 
            f"Detected {artifacts['clicks_detected']} clicks/pops.",
            "Use the 'Remove Clicks' tool to repair digital errors or vinyl crackle.")
            
    if artifacts.get('hum_frequency'):
        add_suggestion('medium', 
            f"Detected {artifacts['hum_frequency']}Hz electrical hum.",
            f"Use the 'Remove Hum' tool set to {artifacts['hum_frequency']}Hz.")
            
    noise = analysis_data.get('noise_floor_db', -100)
    if noise > -50:
        add_suggestion('high', 
            f"Noise floor is very high ({noise:.1f} dB). Hiss/background noise is audible.",
            "Use 'Spectral Denoise'. Learn the noise profile from a silent section first.")
    elif noise > -65:
        add_suggestion('medium', 
            f"Noise floor is audible ({noise:.1f} dB).",
            "Apply gentle noise reduction or use a Noise Gate on noisy tracks.")

    if artifacts.get('dc_offset', 0) > 0.001:
        add_suggestion('medium', 
            "DC Offset detected. Can reduce headroom and cause clicks.",
            "Use the 'Remove DC' tool.")

    if not suggestions:
        add_suggestion('low', 
            "Great job! Your audio analysis looks clean and balanced.",
            "Ready for mastering or release.")
        
    return suggestions

def generate_engineer_report(analysis_data, filename="audio_file"):
    """
    Generate a detailed technical report for sound engineers.
    """
    from datetime import datetime
    
    report_lines = []
    report_lines.append(f"AUDIO ENGINEER REPORT - {filename}")
    report_lines.append("=" * 70)
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Engine: AudioClean Evo v1.0")
    report_lines.append("=" * 70)
    
    # 1. Executive Summary
    report_lines.append("\n[1] EXECUTIVE SUMMARY")
    suggestions = generate_suggestions(analysis_data)
    critical_issues = [s for s in suggestions if s['severity'] in ['critical', 'high']]
    if critical_issues:
        report_lines.append(f"STATUS: ATTENTION REQUIRED ({len(critical_issues)} critical/high issues)")
    else:
        report_lines.append("STATUS: PASSED (Clean Analysis)")
    
    # 2. Technical Specifications
    report_lines.append("\n[2] TECHNICAL SPECIFICATIONS")
    report_lines.append(f"{'Sample Rate':<20}: {analysis_data.get('sample_rate', 'N/A')} Hz")
    report_lines.append(f"{'Bit Depth':<20}: 32-bit Float (Internal)")
    report_lines.append(f"{'Channels':<20}: {analysis_data.get('channels', 'N/A')}")
    report_lines.append(f"{'Duration':<20}: {analysis_data.get('duration', 0):.2f} sec")
    
    # 3. Loudness & Dynamics
    report_lines.append("\n[3] LOUDNESS & DYNAMICS")
    report_lines.append(f"{'Integrated LUFS':<20}: {analysis_data.get('lufs', 'N/A'):.2f} LUFS")
    report_lines.append(f"{'True Peak':<20}: {analysis_data.get('true_peak_db', 'N/A'):.2f} dBTP")
    report_lines.append(f"{'RMS Level':<20}: {analysis_data.get('rms_db', 'N/A'):.2f} dB")
    report_lines.append(f"{'Dynamic Range':<20}: {analysis_data.get('dynamic_range_db', 'N/A'):.2f} dB")
    report_lines.append(f"{'Crest Factor':<20}: {analysis_data.get('crest_factor_db', 'N/A'):.2f} dB")
    report_lines.append(f"{'Noise Floor':<20}: {analysis_data.get('noise_floor_db', 'N/A'):.2f} dB")
    
    # 4. Spectral Analysis
    report_lines.append("\n[4] SPECTRAL BALANCE")
    freq = analysis_data.get('frequency_balance', {})
    report_lines.append(f"{'Sub/Bass (<250Hz)':<20}: {freq.get('bass_db', 'N/A'):.2f} dB")
    report_lines.append(f"{'Mids (250-2kHz)':<20}: {freq.get('mids_db', 'N/A'):.2f} dB")
    report_lines.append(f"{'Highs (>6kHz)':<20}: {freq.get('highs_db', 'N/A'):.2f} dB")
    report_lines.append(f"{'Spectral Centroid':<20}: {analysis_data.get('spectral_centroid_hz', 0):.0f} Hz (Brightness)")
    
    # 5. Stereo Image
    report_lines.append("\n[5] STEREO IMAGE")
    report_lines.append(f"{'Phase Correlation':<20}: {analysis_data.get('phase_correlation', 'N/A')}")
    report_lines.append(f"{'Stereo Width':<20}: {analysis_data.get('stereo_width', 'N/A')}")
    
    # 6. Detailed Restoration Plan
    report_lines.append("\n" + "=" * 70)
    report_lines.append("[6] DETAILED RESTORATION PLAN")
    report_lines.append("=" * 70)
    
    if not suggestions:
        report_lines.append("\nNo restoration required. File meets quality standards.")
    else:
        for i, suggestion in enumerate(suggestions, 1):
            severity = suggestion['severity'].upper()
            text = suggestion['text']
            step = suggestion.get('restoration_step', 'No specific action.')
            
            report_lines.append(f"\nISSUE #{i} [{severity}]")
            report_lines.append(f"Problem: {text}")
            report_lines.append(f"Action : {step}")
            
    # 7. Compliance Check
    report_lines.append("\n" + "-" * 70)
    report_lines.append("[7] STREAMING COMPLIANCE")
    lufs = analysis_data.get('lufs', -99)
    tp = analysis_data.get('true_peak_db', 99)
    
    def check(target_lufs, target_tp, val_lufs, val_tp):
        lufs_ok = abs(val_lufs - target_lufs) <= 2
        tp_ok = val_tp <= target_tp
        return "PASS" if lufs_ok and tp_ok else "FAIL"
        
    report_lines.append(f"Spotify (-14 LUFS, -1 dBTP)    : {check(-14, -1, lufs, tp)}")
    report_lines.append(f"Apple Music (-16 LUFS, -1 dBTP): {check(-16, -1, lufs, tp)}")
    report_lines.append(f"Broadcast (-23 LUFS, -2 dBTP)  : {check(-23, -2, lufs, tp)}")
    
    report_lines.append("\n" + "=" * 70)
    report_lines.append("End of Report")
    
    return "\n".join(report_lines)
