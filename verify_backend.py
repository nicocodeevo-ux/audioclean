import requests
import os

BASE_URL = 'http://127.0.0.1:8000'
FILE_PATH = 'test_audio.wav'

def verify():
    # 1. Upload
    print("Uploading file...")
    with open(FILE_PATH, 'rb') as f:
        files = {'audio_file': f}
        # We need to handle CSRF. For this script, we might need to use a session 
        # and get the token first, or disable CSRF for testing (not recommended), 
        # or just use the fact that we are running locally.
        # Actually, requests.Session() handles cookies.
        
        session = requests.Session()
        # Get the main page to get the CSRF cookie
        response = session.get(BASE_URL)
        csrftoken = session.cookies['csrftoken']
        
        headers = {'X-CSRFToken': csrftoken, 'Referer': BASE_URL}
        
        response = session.post(f'{BASE_URL}/upload/', files=files, headers=headers)
        
        if response.status_code != 200:
            print(f"Upload failed: {response.text}")
            return
        
        data = response.json()
        project_id = data['project_id']
        print(f"Upload successful. Project ID: {project_id}")
        
    # 2. Analyze
    print("Analyzing...")
    response = session.post(f'{BASE_URL}/analyze/{project_id}/', headers=headers)
    if response.status_code != 200:
        print(f"Analysis failed: {response.text}")
        return
    
    analysis_data = response.json()['data']
    print(f"Analysis results: {analysis_data}")
    
    # 3. Repair (Normalize)
    print("Repairing (Normalize)...")
    payload = {'action': 'normalize'}
    response = session.post(f'{BASE_URL}/repair/{project_id}/', json=payload, headers=headers)
    if response.status_code != 200:
        print(f"Repair failed: {response.text}")
        return
    
    repair_data = response.json()
    print(f"Repair successful: {repair_data}")

if __name__ == '__main__':
    verify()
