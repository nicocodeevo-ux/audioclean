import numpy as np
import soundfile as sf

sr = 44100
t = np.linspace(0, 5, 5 * sr)
# Generate a sine wave with some noise
y = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.05 * np.random.normal(0, 1, len(t))

# Add a peak
y[10000:10100] = 1.0

sf.write('test_audio.wav', y, sr)
print("Created test_audio.wav")
