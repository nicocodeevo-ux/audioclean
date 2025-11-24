import requests
import os
import time

BASE_URL = 'http://127.0.0.1:8000'
FILE_PATH = 'test_audio.wav'

def verify_advanced():
    print("Starting Advanced Verification...")
    
    # 1. Upload
    print("Uploading file...")
    with open(FILE_PATH, 'rb') as f:
        session = requests.Session()
        response = session.get(BASE_URL)
        csrftoken = session.cookies['csrftoken']
        headers = {'X-CSRFToken': csrftoken, 'Referer': BASE_URL}
        
        response = session.post(f'{BASE_URL}/upload/', files={'audio_file': f}, headers=headers)
        if response.status_code != 200:
            print(f"Upload failed: {response.text}")
            return
        
        project_id = response.json()['project_id']
        print(f"Upload successful. Project ID: {project_id}")

    # 2. Analyze (Check LUFS)
    print("Analyzing...")
    response = session.post(f'{BASE_URL}/analyze/{project_id}/', headers=headers)
    data = response.json()['data']
    print(f"Analysis: LUFS={data.get('lufs')}, Peak={data.get('peak_db')}")
    
    if 'lufs' not in data:
        print("FAIL: LUFS missing from analysis")
    
    # 3. Learn Noise Profile
    print("Learning Noise Profile...")
    # Simulate selecting the first 0.5 seconds (which we know is silence/noise in our test gen?)
    # Actually our test gen has noise everywhere.
    payload = {
        'action': 'learn_noise',
        'params': {'start_time': 0.0, 'end_time': 0.5}
    }
    response = session.post(f'{BASE_URL}/repair/{project_id}/', json=payload, headers=headers)
    print(f"Learn Noise Response: {response.json()}")
    
    if response.json().get('message') != 'Noise profile learned':
        print("FAIL: Learn noise failed")

    # 4. Denoise
    print("Applying Spectral Denoise...")
    payload = {'action': 'denoise'}
    response = session.post(f'{BASE_URL}/repair/{project_id}/', json=payload, headers=headers)
    print(f"Denoise Response: {response.json()}")
    
    if not response.json().get('url'):
        print("FAIL: Denoise failed to return URL")

    # 5. Normalize to Target LUFS
    print("Normalizing to -23 LUFS...")
    payload = {
        'action': 'normalize',
        'params': {'target_lufs': -23.0}
    }
    response = session.post(f'{BASE_URL}/repair/{project_id}/', json=payload, headers=headers)
    print(f"Normalize Response: {response.json()}")
    
    # Verify new analysis
    print("Verifying Normalization...")
    # We need to analyze the NEW file. The analyze view logic checks processed_file.
    response = session.post(f'{BASE_URL}/analyze/{project_id}/', headers=headers)
    new_lufs = response.json()['data']['lufs']
    print(f"New LUFS: {new_lufs}")
    
    if abs(new_lufs - (-23.0)) > 1.0: # Allow 1dB tolerance
        print(f"FAIL: Normalization target missed. Got {new_lufs}, expected -23.0")
    else:
        print("PASS: Normalization successful")

if __name__ == '__main__':
    verify_advanced()
