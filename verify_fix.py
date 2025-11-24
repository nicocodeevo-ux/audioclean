import requests
import os

BASE_URL = 'http://127.0.0.1:8000'
FILE_PATH = 'test_audio.wav'

def verify_fix():
    print("Verifying Restoration Fix...")
    
    # 1. Upload
    with open(FILE_PATH, 'rb') as f:
        session = requests.Session()
        response = session.get(BASE_URL)
        csrftoken = session.cookies['csrftoken']
        headers = {'X-CSRFToken': csrftoken, 'Referer': BASE_URL}
        
        response = session.post(f'{BASE_URL}/upload/', files={'audio_file': f}, headers=headers)
        if response.status_code != 200:
            print("Upload failed")
            return
        
        project_id = response.json()['project_id']
        print(f"Project ID: {project_id}")

    # 2. Normalize (Restoration)
    payload = {
        'action': 'normalize',
        'params': {'target_lufs': -16.0}
    }
    response = session.post(f'{BASE_URL}/repair/{project_id}/', json=payload, headers=headers)
    print(f"Restoration Response: {response.json()}")
    
    if response.json().get('status') == 'success':
        print("PASS: Restoration successful")
    else:
        print("FAIL: Restoration failed")

if __name__ == '__main__':
    verify_fix()
