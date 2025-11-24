"""
Professional audio restoration functions.
Separated for modularity and clarity.
"""
import numpy as np
import librosa
import soundfile as sf
from scipy import signal, interpolate
from pedalboard import Pedalboard, Compressor, Limiter, HighpassFilter, LowpassFilter, PeakFilter, Gain
import noisereduce as nr
import pyloudnorm as pyln


def declip_audio(y, sr, threshold=0.95):
    """
    Restore clipped audio using cubic spline interpolation.
    
    Args:
        y: Audio signal
        sr: Sample rate
        threshold: Threshold for detecting clipping (0-1)
    
    Returns:
        Declipped audio signal
    """
    try:
        # Find clipped regions
        clipped_mask = np.abs(y) > threshold
        
        if not np.any(clipped_mask):
            return y  # No clipping detected
        
        # Find edges of clipped regions
        clipped_diff = np.diff(np.concatenate(([False], clipped_mask, [False])).astype(int))
        clip_starts = np.where(clipped_diff == 1)[0]
        clip_ends = np.where(clipped_diff == -1)[0]
        
        y_restored = y.copy()
        
        # Interpolate each clipped region
        for start, end in zip(clip_starts, clip_ends):
            # Extend region slightly for better interpolation
            region_start = max(0, start - 3)
            region_end = min(len(y), end + 3)
            
            # Points before and after clip
            good_indices = []
            good_values = []
            
            for i in range(region_start, region_end):
                if not clipped_mask[i]:
                    good_indices.append(i)
                    good_values.append(y[i])
            
            if len(good_indices) >= 4:  # Need at least 4 points for cubic spline
                # Create interpolation function
                f = interpolate.CubicSpline(good_indices, good_values)
                
                # Interpolate clipped region
                clipped_indices = range(start, end)
                y_restored[start:end] = f(clipped_indices)
            else:
                # Linear interpolation as fallback
                if len(good_indices) >= 2:
                    f = interpolate.interp1d(good_indices, good_values, kind='linear', fill_value='extrapolate')
                    y_restored[start:end] = f(range(start, end))
        
        return y_restored
        
    except Exception as e:
        print(f"Declipping error: {e}")
        return y


def remove_clicks(y, sr, sensitivity=0.5):
    """
    Remove clicks and pops using Z-score detection.
    
    Args:
        y: Audio signal
        sr: Sample rate
        sensitivity: Detection sensitivity (0-1), higher = more aggressive
    
    Returns:
        Deglitched audio signal
    """
    try:
        # Calculate first derivative (emphasizes transients)
        diff = np.diff(y, prepend=y[0])
        
        # Calculate Z-score (standard deviations from mean)
        # We use median absolute deviation (MAD) for robustness against outliers
        median = np.median(diff)
        mad = np.median(np.abs(diff - median))
        
        if mad == 0:
            return y
            
        z_scores = 0.6745 * (diff - median) / mad
        
        # Threshold based on sensitivity
        # Sensitivity 0.0 -> 10 sigma (very conservative)
        # Sensitivity 1.0 -> 3 sigma (aggressive)
        threshold_sigma = 10 - (sensitivity * 7)
        
        # Detect clicks
        click_mask = np.abs(z_scores) > threshold_sigma
        
        # Expand mask slightly to cover the whole click
        click_mask = signal.binary_dilation(click_mask, iterations=2)
        
        if not np.any(click_mask):
            return y
            
        # Replace clicks with interpolation
        y_clean = y.copy()
        
        # Simple linear interpolation for short clicks
        x = np.arange(len(y))
        y_clean[click_mask] = np.interp(x[click_mask], x[~click_mask], y[~click_mask])
        
        return y_clean
        
    except Exception as e:
        print(f"Click removal error: {e}")
        return y


def remove_hum(y, sr, hum_freq=50, harmonics=3, q_factor=30):
    """
    Remove hum and harmonics using notch filters.
    
    Args:
        y: Audio signal
        sr: Sample rate
        hum_freq: Fundamental hum frequency (50 or 60 Hz)
        harmonics: Number of harmonics to remove
        q_factor: Quality factor for notch filters (higher = narrower)
    
    Returns:
        Dehum audio signal
    """
    try:
        y_clean = y.copy()
        
        # Remove fundamental and harmonics
        for h in range(1, harmonics + 1):
            freq = hum_freq * h
            
            # Skip if frequency is above Nyquist
            if freq >= sr / 2:
                break
            
            # Design notch filter
            w0 = freq / (sr / 2)  # Normalized frequency
            b, a = signal.iirnotch(w0, q_factor)
            
            # Apply filter
            y_clean = signal.filtfilt(b, a, y_clean)
        
        return y_clean
        
    except Exception as e:
        print(f"Hum removal error: {e}")
        return y


def remove_dc_offset(y):
    """
    Remove DC offset by centering waveform around zero.
    
    Args:
        y: Audio signal
    
    Returns:
        DC-corrected audio signal
    """
    return y - np.mean(y)


def apply_parametric_eq(y, sr, bands):
    """
    Apply parametric EQ with multiple bands.
    
    Args:
        y: Audio signal
        sr: Sample rate
        bands: List of dicts with 'freq', 'gain_db', 'q' keys
    
    Returns:
        EQ'd audio signal
    """
    try:
        board = Pedalboard()
        
        for band in bands:
            freq = float(band.get('freq', 1000))
            gain_db = float(band.get('gain_db', 0))
            q = float(band.get('q', 1.0))
            
            if abs(gain_db) > 0.1:  # Only add if gain is significant
                board.append(PeakFilter(frequency_hz=freq, gain_db=gain_db, q=q))
        
        if len(board) > 0:
            # Convert to float32 for pedalboard
            y_float32 = y.astype(np.float32)
            y_processed = board(y_float32, sr)
            return y_processed.astype(y.dtype)
        else:
            return y
            
    except Exception as e:
        print(f"EQ error: {e}")
        return y


def apply_compression(y, sr, threshold_db=-20, ratio=4.0, attack_ms=5.0, release_ms=50.0):
    """
    Apply compression for dynamic range control.
    
    Args:
        y: Audio signal
        sr: Sample rate
        threshold_db: Compression threshold in dB
        ratio: Compression ratio
        attack_ms: Attack time in milliseconds
        release_ms: Release time in milliseconds
    
    Returns:
        Compressed audio signal
    """
    try:
        board = Pedalboard([
            Compressor(
                threshold_db=threshold_db,
                ratio=ratio,
                attack_ms=attack_ms,
                release_ms=release_ms
            )
        ])
        
        y_float32 = y.astype(np.float32)
        y_compressed = board(y_float32, sr)
        return y_compressed.astype(y.dtype)
        
    except Exception as e:
        print(f"Compression error: {e}")
        return y


def apply_deesser(y, sr, freq=6000, threshold_db=-20):
    """
    Reduce sibilance in vocals.
    
    Args:
        y: Audio signal
        sr: Sample rate
        freq: Center frequency for de-essing (typically 5-8 kHz)
        threshold_db: Threshold for sibilance reduction
    
    Returns:
        De-essed audio signal
    """
    try:
        # Extract high frequency content
        sos = signal.butter(4, freq / (sr / 2), btype='high', output='sos')
        y_high = signal.sosfilt(sos, y)
        
        # Detect sibilant regions
        rms_high = librosa.feature.rms(y=y_high)[0]
        threshold = np.percentile(rms_high, 90)  # Adaptive threshold
        
        # Create envelope for reduction
        hop_length = 512
        reduction_envelope = np.ones_like(rms_high)
        reduction_envelope[rms_high > threshold] = 0.5  # 6dB reduction
        
        # Interpolate envelope to match signal length
        reduction_full = np.interp(
            np.arange(len(y)),
            np.arange(len(reduction_envelope)) * hop_length,
            reduction_envelope
        )
        
        # Apply reduction to high frequencies only
        y_high_reduced = y_high * reduction_full
        
        # Reconstruct signal
        y_low = y - y_high
        y_deessed = y_low + y_high_reduced
        
        return y_deessed
        
    except Exception as e:
        print(f"De-esser error: {e}")
        return y


def apply_limiter(y, sr, ceiling_db=-1.0, release_ms=50.0):
    """
    Apply brickwall limiter to prevent peaks.
    
    Args:
        y: Audio signal
        sr: Sample rate
        ceiling_db: Maximum peak level in dB
        release_ms: Release time in milliseconds
    
    Returns:
        Limited audio signal
    """
    try:
        board = Pedalboard([
            Limiter(threshold_db=ceiling_db, release_ms=release_ms)
        ])
        
        y_float32 = y.astype(np.float32)
        y_limited = board(y_float32, sr)
        return y_limited.astype(y.dtype)
        
    except Exception as e:
        print(f"Limiter error: {e}")
        return y


def adjust_stereo_width(y_stereo, width=1.0):
    """
    Adjust stereo width using mid-side processing.
    
    Args:
        y_stereo: Stereo audio signal (2 x n_samples)
        width: Width factor (0 = mono, 1 = normal, >1 = wider)
    
    Returns:
        Width-adjusted stereo signal
    """
    try:
        if len(y_stereo.shape) != 2 or y_stereo.shape[0] != 2:
            return y_stereo  # Not stereo
        
        left = y_stereo[0]
        right = y_stereo[1]
        
        # Convert to mid-side
        mid = (left + right) / 2
        side = (left - right) / 2
        
        # Adjust side component
        side = side * width
        
        # Convert back to left-right
        left_new = mid + side
        right_new = mid - side
        
        return np.array([left_new, right_new])
        
    except Exception as e:
        print(f"Stereo width error: {e}")
        return y_stereo

def normalize_audio(y, sr, target_lufs=-14.0):
    """
    Normalize audio to target LUFS.
    
    Args:
        y: Audio signal
        sr: Sample rate
        target_lufs: Target integrated loudness in LUFS
    
    Returns:
        Normalized audio signal
    """
    try:
        meter = pyln.Meter(sr)
        is_stereo = len(y.shape) == 2
        
        if is_stereo:
            # Transpose for pyloudnorm (expects samples x channels)
            y_t = y.T
            loudness = meter.integrated_loudness(y_t)
            y_norm_t = pyln.normalize.loudness(y_t, loudness, target_lufs)
            return y_norm_t.T
        else:
            loudness = meter.integrated_loudness(y)
            return pyln.normalize.loudness(y, loudness, target_lufs)
            
    except Exception as e:
        print(f"Normalization error: {e}")
        return y


def denoise_audio(y, sr, noise_clip=None, prop_decrease=0.8, stationary=True):
    """
    Apply spectral noise reduction.
    
    Args:
        y: Audio signal
        sr: Sample rate
        noise_clip: Optional noise profile audio data
        prop_decrease: Proportion of noise to reduce (0-1)
        stationary: Whether noise is stationary
    
    Returns:
        Denoised audio signal
    """
    try:
        is_stereo = len(y.shape) == 2
        
        if is_stereo:
            left = y[0]
            right = y[1]
            
            if noise_clip is not None:
                # Ensure noise clip matches channel count or use mono for both?
                # noisereduce handles this but let's be explicit
                # If noise_clip is mono, use it for both. If stereo, split.
                noise_left = noise_clip
                noise_right = noise_clip
                if len(noise_clip.shape) == 2:
                    noise_left = noise_clip[0]
                    noise_right = noise_clip[1]
                
                left_clean = nr.reduce_noise(y=left, sr=sr, y_noise=noise_left, 
                                             prop_decrease=prop_decrease, stationary=stationary)
                right_clean = nr.reduce_noise(y=right, sr=sr, y_noise=noise_right, 
                                              prop_decrease=prop_decrease, stationary=stationary)
            else:
                left_clean = nr.reduce_noise(y=left, sr=sr, stationary=stationary, 
                                            prop_decrease=prop_decrease)
                right_clean = nr.reduce_noise(y=right, sr=sr, stationary=stationary, 
                                             prop_decrease=prop_decrease)
            
            return np.array([left_clean, right_clean])
        else:
            # Mono
            if noise_clip is not None:
                # Ensure noise clip is mono if y is mono
                if len(noise_clip.shape) == 2:
                    noise_clip = librosa.to_mono(noise_clip)
                    
                return nr.reduce_noise(y=y, sr=sr, y_noise=noise_clip, 
                                      prop_decrease=prop_decrease, stationary=stationary)
            else:
                return nr.reduce_noise(y=y, sr=sr, stationary=stationary, 
                                      prop_decrease=prop_decrease)
                
    except Exception as e:
        print(f"Denoise error: {e}")
        return y
