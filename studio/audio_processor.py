import os
import librosa
import soundfile as sf
import numpy as np
from django.conf import settings
from datetime import datetime
import traceback

# Import analysis functions
from .audio_analysis import (
    analyze_audio as _analyze,
    detect_artifacts as _detect,
    generate_suggestions as _gen_suggestions,
    generate_engineer_report as _gen_report
)

# Import restoration functions
from .audio_processor_restoration import (
    declip_audio,
    remove_clicks,
    remove_hum,
    remove_dc_offset,
    apply_parametric_eq,
    apply_compression,
    apply_deesser,
    apply_limiter,
    adjust_stereo_width,
    normalize_audio,
    denoise_audio
)

def analyze_audio(file_path):
    """Delegate to audio_analysis.analyze_audio"""
    return _analyze(file_path)

def detect_artifacts(y_mono, sr, is_stereo=False, stereo_data=None):
    """Delegate to audio_analysis.detect_artifacts"""
    return _detect(y_mono, sr, is_stereo, stereo_data)

def generate_suggestions(analysis_data):
    """Delegate to audio_analysis.generate_suggestions"""
    return _gen_suggestions(analysis_data)

def generate_engineer_report(analysis_data, filename="audio_file"):
    """Delegate to audio_analysis.generate_engineer_report"""
    return _gen_report(analysis_data, filename)

def repair_audio(file_path, action, params=None, project=None):
    """
    Apply professional repair functions to audio file.
    Returns path to processed file or None if action is metadata-only (like learn_noise).
    
    Supported actions:
    - normalize: LUFS normalization
    - learn_noise: Learn noise profile for spectral denoise
    - denoise: Spectral noise reduction
    - declip: Restore clipped audio
    - remove_clicks: Remove clicks and pops
    - remove_hum: Remove hum and harmonics
    - remove_dc: Remove DC offset
    - eq: Apply parametric EQ
    - compress: Apply compression
    - deess: Apply de-esser
    - limit: Apply limiter
    - stereo_width: Adjust stereo width
    """
    if params is None:
        params = {}
    
    try:
        # Load audio (preserve stereo if present)
        y, sr = librosa.load(file_path, sr=None, mono=False)
        is_stereo = len(y.shape) == 2
        
        # Process based on action
        if action == 'normalize':
            target_lufs = float(params.get('target_lufs', -14.0))
            y = normalize_audio(y, sr, target_lufs)
            
        elif action == 'learn_noise':
            # Extract noise profile from selection and save to project
            start_time = float(params.get('start_time', 0))
            end_time = float(params.get('end_time', 1))
            
            # Use mono for noise profile
            y_mono = librosa.to_mono(y) if is_stereo else y
            
            start_sample = int(start_time * sr)
            end_sample = int(end_time * sr)
            
            # Ensure bounds
            start_sample = max(0, start_sample)
            end_sample = min(len(y_mono), end_sample)
            
            if end_sample > start_sample:
                noise_clip = y_mono[start_sample:end_sample]
                # Save noise clip to a file
                noise_filename = f"noise_profile_{project.id}.wav"
                noise_path = os.path.join(settings.MEDIA_ROOT, 'audio', 'profiles', noise_filename)
                os.makedirs(os.path.dirname(noise_path), exist_ok=True)
                sf.write(noise_path, noise_clip, sr)
                
                # Update project metadata
                if project.analysis_data is None:
                    project.analysis_data = {}
                project.analysis_data['noise_profile_path'] = noise_path
                project.save()
                return "METADATA_UPDATE_ONLY"
            else:
                raise ValueError("Invalid selection for noise profile")

        elif action == 'denoise':
            prop_decrease = float(params.get('prop_decrease', 0.8))
            stationary = params.get('stationary', True)
            
            # Get noise profile if available
            noise_clip = None
            if project and project.analysis_data:
                noise_profile_path = project.analysis_data.get('noise_profile_path')
                if noise_profile_path and os.path.exists(noise_profile_path):
                    noise_clip, _ = librosa.load(noise_profile_path, sr=sr)
            
            y = denoise_audio(y, sr, noise_clip, prop_decrease, stationary)
        
        elif action == 'declip':
            threshold = float(params.get('threshold', 0.95))
            if is_stereo:
                y[0] = declip_audio(y[0], sr, threshold)
                y[1] = declip_audio(y[1], sr, threshold)
            else:
                y = declip_audio(y, sr, threshold)
        
        elif action == 'remove_clicks':
            sensitivity = float(params.get('sensitivity', 0.5))
            if is_stereo:
                y[0] = remove_clicks(y[0], sr, sensitivity)
                y[1] = remove_clicks(y[1], sr, sensitivity)
            else:
                y = remove_clicks(y, sr, sensitivity)
        
        elif action == 'remove_hum':
            hum_freq = int(params.get('hum_freq', 50))
            harmonics = int(params.get('harmonics', 3))
            if is_stereo:
                y[0] = remove_hum(y[0], sr, hum_freq, harmonics)
                y[1] = remove_hum(y[1], sr, hum_freq, harmonics)
            else:
                y = remove_hum(y, sr, hum_freq, harmonics)
        
        elif action == 'remove_dc':
            if is_stereo:
                y[0] = remove_dc_offset(y[0])
                y[1] = remove_dc_offset(y[1])
            else:
                y = remove_dc_offset(y)
        
        elif action == 'eq':
            bands = params.get('bands', [])
            if is_stereo:
                y[0] = apply_parametric_eq(y[0], sr, bands)
                y[1] = apply_parametric_eq(y[1], sr, bands)
            else:
                y = apply_parametric_eq(y, sr, bands)
        
        elif action == 'compress':
            threshold_db = float(params.get('threshold_db', -20))
            ratio = float(params.get('ratio', 4.0))
            attack_ms = float(params.get('attack_ms', 5.0))
            release_ms = float(params.get('release_ms', 50.0))
            if is_stereo:
                y[0] = apply_compression(y[0], sr, threshold_db, ratio, attack_ms, release_ms)
                y[1] = apply_compression(y[1], sr, threshold_db, ratio, attack_ms, release_ms)
            else:
                y = apply_compression(y, sr, threshold_db, ratio, attack_ms, release_ms)
        
        elif action == 'deess':
            freq = int(params.get('freq', 6000))
            threshold_db = float(params.get('threshold_db', -20))
            if is_stereo:
                y[0] = apply_deesser(y[0], sr, freq, threshold_db)
                y[1] = apply_deesser(y[1], sr, freq, threshold_db)
            else:
                y = apply_deesser(y, sr, freq, threshold_db)
        
        elif action == 'limit':
            ceiling_db = float(params.get('ceiling_db', -1.0))
            release_ms = float(params.get('release_ms', 50.0))
            if is_stereo:
                y[0] = apply_limiter(y[0], sr, ceiling_db, release_ms)
                y[1] = apply_limiter(y[1], sr, ceiling_db, release_ms)
            else:
                y = apply_limiter(y, sr, ceiling_db, release_ms)
        
        elif action == 'stereo_width':
            width = float(params.get('width', 1.0))
            if is_stereo:
                y = adjust_stereo_width(y, width)
        
        else:
            raise ValueError(f"Unknown action: {action}")
        
        # Save processed file with timestamp to avoid overwrites
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = os.path.basename(file_path)
        name, ext = os.path.splitext(filename)
        # Clean up previous timestamps if present to avoid long filenames
        import re
        name = re.sub(r'_\d{8}_\d{6}_\d+$', '', name)
        name = re.sub(r'_\d{8}_\d{6}$', '', name)
        
        new_filename = f"{name}_{action}_{timestamp}{ext}"
        processed_dir = os.path.join(settings.MEDIA_ROOT, 'audio', 'processed')
        os.makedirs(processed_dir, exist_ok=True)
        output_path = os.path.join(processed_dir, new_filename)
        
        # Save with proper format
        if is_stereo:
            sf.write(output_path, y.T, sr)  # Transpose for soundfile
        else:
            sf.write(output_path, y, sr)
        
        # Return relative path for Django FileField
        return f"audio/processed/{new_filename}"
        
    except Exception as e:
        print(f"Error repairing audio: {e}")
        traceback.print_exc()
        return None
