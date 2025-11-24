document.addEventListener('DOMContentLoaded', () => {
    // Splash Screen with Sound Effects
    const splashScreen = document.getElementById('splashScreen');
    if (splashScreen) {
        // Create Audio Context for sound effects
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        const audioCtx = new AudioContext();

        // Turntable crackle sound (white noise with low-pass filter)
        function playCrackle() {
            const duration = 4;
            const bufferSize = audioCtx.sampleRate * duration;
            const buffer = audioCtx.createBuffer(1, bufferSize, audioCtx.sampleRate);
            const data = buffer.getChannelData(0);

            // Generate white noise
            for (let i = 0; i < bufferSize; i++) {
                data[i] = (Math.random() * 2 - 1) * 0.1; // Low volume crackle
            }

            const source = audioCtx.createBufferSource();
            source.buffer = buffer;

            // Low-pass filter for vintage vinyl sound
            const filter = audioCtx.createBiquadFilter();
            filter.type = 'lowpass';
            filter.frequency.value = 2000;
            filter.Q.value = 1;

            // Volume control
            const gainNode = audioCtx.createGain();
            gainNode.gain.value = 0.15;

            source.connect(filter);
            filter.connect(gainNode);
            gainNode.connect(audioCtx.destination);

            source.start();
        }

        // Pop beat sound (kick drums)
        function playPopBeat(time) {
            const osc = audioCtx.createOscillator();
            const gainNode = audioCtx.createGain();

            osc.frequency.value = 150; // Bass frequency
            gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime + time);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + time + 0.1);

            osc.connect(gainNode);
            gainNode.connect(audioCtx.destination);

            osc.start(audioCtx.currentTime + time);
            osc.stop(audioCtx.currentTime + time + 0.1);
        }

        // Play sounds
        playCrackle(); // Background crackle throughout
        playPopBeat(0.3); // First beat when logo appears
        playPopBeat(1.2); // Second beat when title slides in
        playPopBeat(2.0); // Third beat when visualizer appears
        playPopBeat(3.5); // Final beat before fade

        // Hide splash screen after 4 seconds
        setTimeout(() => {
            splashScreen.classList.add('fade-out');
            setTimeout(() => {
                splashScreen.style.display = 'none';
            }, 800);
        }, 4000);
    }

    let wavesurfer;
    let currentProjectId = null;
    let currentRestorationPlan = [];

    // Initialize WaveSurfer
    // Initialize WaveSurfer
    wavesurfer = WaveSurfer.create({
        container: '#waveform',
        waveColor: '#333333', // Dark Grey (Carbon)
        progressColor: '#FFD700', // Yellow (Accent)
        cursorColor: '#FFD700',
        barWidth: 2,
        barGap: 2,
        barRadius: 0, // Sharp edges for hardware feel
        height: 120, // Fixed height
        responsive: true,
        normalize: true,
        backend: 'WebAudio'
    });

    // Initialize Spectrogram (Hidden by default)
    let spectrogramPlugin = null;
    if (window.WaveSurfer.Spectrogram) {
        spectrogramPlugin = window.WaveSurfer.Spectrogram.create({
            container: '#spectrogram',
            labels: true,
            height: 200,
            splitChannels: false,
        });
        // Don't register yet, toggle it
    }

    // Initialize Regions
    let regionsPlugin = null;
    if (window.WaveSurfer.Regions) {
        regionsPlugin = window.WaveSurfer.Regions.create();
        wavesurfer.registerPlugin(regionsPlugin);

        regionsPlugin.enableDragSelection({
            color: 'rgba(0, 255, 157, 0.2)',
        });
    }

    // Toggle Spectrogram
    document.getElementById('toggleSpectrogram').addEventListener('click', () => {
        if (!spectrogramPlugin) return;

        const container = document.getElementById('spectrogram');

        // Check if currently visible (display is not 'none' or empty string means visible)
        const isVisible = container.style.display === 'block' || container.style.display === '';

        if (isVisible) {
            container.style.display = 'none';
        } else {
            container.style.display = 'block';
            if (!wavesurfer.plugins.find(p => p === spectrogramPlugin)) {
                wavesurfer.registerPlugin(spectrogramPlugin);
            }
        }
    });
    // Hide initially
    document.getElementById('spectrogram').style.display = 'none';


    // Transport Controls
    document.getElementById('playPauseBtn').addEventListener('click', () => {
        wavesurfer.playPause();
    });

    document.getElementById('stopBtn').addEventListener('click', () => {
        wavesurfer.stop();
    });

    // File Upload
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#00ff9d';
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.style.borderColor = '#32323e';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#32323e';
        if (e.dataTransfer.files.length) {
            uploadFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            uploadFile(e.target.files[0]);
        }
    });

    function uploadFile(file) {
        const formData = new FormData();
        formData.append('audio_file', file);

        // Get CSRF token
        const csrftoken = getCookie('csrftoken');

        // Show loading state
        document.getElementById('dropZone').innerHTML = '<p>Uploading...</p>';

        fetch('/upload/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': csrftoken
            }
        })
            .then(response => response.json())
            .then(data => {
                document.getElementById('dropZone').innerHTML = '<i class="fas fa-cloud-upload-alt"></i><p>Drop Audio Here</p>';
                if (data.status === 'success') {
                    currentProjectId = data.project_id;
                    loadAudio(data.url);
                    addFileToList(file.name, data.project_id, data.url);

                    // Update Status Bar
                    document.getElementById('currentFileName').textContent = file.name;

                    // Auto-analyze
                    triggerAnalysis();
                }
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('dropZone').innerHTML = '<p>Error!</p>';
            });
    }

    function loadAudio(url) {
        wavesurfer.load(url);
        // Clear regions
        if (regionsPlugin) regionsPlugin.clearRegions();

        wavesurfer.once('ready', () => {
            // Update basic info from wavesurfer decoded buffer
            const buffer = wavesurfer.getDecodedData();
            if (buffer) {
                document.getElementById('sampleRateBadge').textContent = `${buffer.sampleRate} Hz`;
                document.getElementById('durationBadge').textContent = `${buffer.duration.toFixed(2)} s`;
                document.getElementById('channelsBadge').textContent = `${buffer.numberOfChannels} Ch`;
            }
        });
    }

    // Analysis
    document.getElementById('analyzeBtn').addEventListener('click', triggerAnalysis);

    function triggerAnalysis() {
        if (!currentProjectId) {
            alert("Please select a file first.");
            return;
        }

        const csrftoken = getCookie('csrftoken');
        const btn = document.getElementById('analyzeBtn');
        const progressContainer = document.getElementById('analysisProgress');
        const progressFill = progressContainer.querySelector('.progress-fill');

        // Show progress bar
        progressContainer.style.display = 'block';
        progressFill.style.width = '30%';
        btn.disabled = true;

        fetch(`/analyze/${currentProjectId}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken
            }
        })
            .then(response => {
                progressFill.style.width = '60%';
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(data => {
                progressFill.style.width = '100%';

                if (data.status === 'success') {
                    updateAnalysisUI(data);
                    updateSuggestions(data.suggestions || []);
                } else {
                    alert('Error analyzing audio: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Analysis error:', error);
                alert('Error analyzing audio. Please try again.');
            })
            .finally(() => {
                // Always re-enable button and hide progress, even if there's an error
                setTimeout(() => {
                    progressContainer.style.display = 'none';
                    progressFill.style.width = '0%';
                    btn.disabled = false;
                    btn.textContent = 'Run Analysis';
                }, 500);
            });

        // Timeout safety - re-enable button after 30 seconds if stuck
        setTimeout(() => {
            if (btn.disabled) {
                btn.disabled = false;
                btn.textContent = 'Run Analysis';
                progressContainer.style.display = 'none';
                console.warn('Analysis timed out - button re-enabled');
            }
        }, 30000);
    }

    function updateAnalysisUI(data) {
        // LUFS
        if (data.lufs) {
            document.getElementById('lufsValue').textContent = `${data.lufs.toFixed(1)} LUFS`;
        }

        // True Peak
        const truePeak = data.true_peak_db !== undefined ? data.true_peak_db : data.peak_db;
        document.getElementById('truePeakValue').textContent = `${truePeak.toFixed(1)} dB`;

        // Noise Floor
        document.getElementById('noiseValue').textContent = `${data.noise_floor_db.toFixed(1)} dB`;

        // Clipping
        document.getElementById('clipValue').textContent = data.clipping_count;

        // Artifacts
        if (data.artifacts) {
            document.getElementById('clicksValue').textContent = data.artifacts.clicks_detected;
            document.getElementById('humValue').textContent = data.artifacts.hum_frequency ? `${data.artifacts.hum_frequency} Hz` : 'None';
            document.getElementById('silenceValue').textContent = `${data.artifacts.silence_percentage.toFixed(1)} %`;
            document.getElementById('dcValue').textContent = data.artifacts.dc_offset.toFixed(4);

            // Color coding
            document.getElementById('clicksValue').style.color = data.artifacts.clicks_detected > 0 ? '#ff4a4a' : 'var(--accent)';
            document.getElementById('humValue').style.color = data.artifacts.hum_frequency ? '#ff4a4a' : 'var(--accent)';
        }
    }

    function updateSuggestions(suggestions) {
        const container = document.getElementById('suggestionsContainer');
        container.innerHTML = ''; // Clear existing

        if (!suggestions || suggestions.length === 0) {
            container.innerHTML = '<p class="placeholder-text">No suggestions available.</p>';
            return;
        }

        suggestions.forEach(suggestion => {
            const item = document.createElement('div');
            item.className = `suggestion-item ${suggestion.severity}`;
            item.innerHTML = `
                <i class="fas ${suggestion.icon}"></i>
                <span class="suggestion-text">${suggestion.text}</span>
            `;
            container.appendChild(item);
        });
    }

    // Download Report
    const downloadReportBtn = document.getElementById('downloadReport');
    if (downloadReportBtn) {
        downloadReportBtn.addEventListener('click', () => {
            if (!currentProjectId) {
                alert("Please select a file first.");
                return;
            }
            window.location.href = `/download-report/${currentProjectId}/`;
        });
    }

    // Auto Restoration Button
    const autoRestoreBtn = document.getElementById('autoRestoreBtn');
    const autoRestoreSteps = document.getElementById('autoRestoreSteps');
    const autoRestoreActions = document.querySelector('.auto-restore-actions');

    if (autoRestoreBtn) {
        autoRestoreBtn.addEventListener('click', async () => {
            if (!currentProjectId) {
                alert("Please select a file and run analysis first.");
                return;
            }

            autoRestoreBtn.textContent = 'Analyzing...';
            autoRestoreBtn.disabled = true;

            try {
                // First trigger analysis if not done
                const analyzeResponse = await fetch(`/analyze/${currentProjectId}/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken')
                    }
                });

                const analyzeData = await analyzeResponse.json();

                if (analyzeData.status === 'success') {
                    // Generate restoration plan based on analysis
                    const plan = generateRestorationPlan(analyzeData);
                    currentRestorationPlan = plan;

                    // Display plan
                    if (plan.length > 0) {
                        autoRestoreSteps.innerHTML = plan.map((step, idx) => `
                            <div class="auto-step-item">
                                <strong>Step ${idx + 1}: ${step.title}</strong>
                                <em>${step.reason}</em>
                            </div>
                        `).join('');
                        autoRestoreActions.style.display = 'block';
                    } else {
                        autoRestoreSteps.innerHTML = '<p class="placeholder-text">No issues detected. Audio is already optimized!</p>';
                        autoRestoreActions.style.display = 'none';
                    }

                    autoRestoreBtn.textContent = 'Auto Fix';
                    autoRestoreBtn.disabled = false;
                } else {
                    alert('Error analyzing audio: ' + analyzeData.message);
                    autoRestoreBtn.textContent = 'Auto Fix';
                    autoRestoreBtn.disabled = false;
                }
            } catch (error) {
                console.error(error);
                alert('Error generating restoration plan: ' + error.message);
                autoRestoreBtn.textContent = 'Auto Fix';
                autoRestoreBtn.disabled = false;
            }
        });
    }

    // Apply All Fixes button
    const applyAllBtn = document.getElementById('applyAllBtn');
    if (applyAllBtn) {
        applyAllBtn.addEventListener('click', async () => {
            if (!currentProjectId) {
                alert("No active project.");
                return;
            }

            applyAllBtn.textContent = 'Applying fixes...';
            applyAllBtn.disabled = true;

            console.log('Current restoration plan:', currentRestorationPlan);

            // If no plan exists, generate one from current analysis
            if (currentRestorationPlan.length === 0) {
                console.log('No plan found, fetching analysis...');
                try {
                    const analyzeResponse = await fetch(`/analyze/${currentProjectId}/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    });
                    const analyzeData = await analyzeResponse.json();
                    if (analyzeData.status === 'success') {
                        currentRestorationPlan = generateRestorationPlan(analyzeData);
                        console.log('Generated plan:', currentRestorationPlan);
                    }
                } catch (error) {
                    console.error('Error fetching analysis:', error);
                    alert('Please run analysis first.');
                    applyAllBtn.textContent = 'Apply All Fixes';
                    applyAllBtn.disabled = false;
                    return;
                }
            }

            // Get the restoration plan from analysis
            const steps = currentRestorationPlan.map(item => item.action);
            console.log('Steps to execute:', steps);

            if (steps.length === 0) {
                alert("No repairs needed according to the plan.");
                applyAllBtn.textContent = 'Apply All Fixes';
                applyAllBtn.disabled = false;
                return;
            }

            let lastUrl = null;

            // Apply each fix in sequence
            for (const action of steps) {
                try {
                    const response = await fetch(`/repair/${currentProjectId}/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: JSON.stringify({ action: action, params: {} })
                    });

                    const data = await response.json();
                    if (data.status === 'success') {
                        if (data.url) {
                            lastUrl = data.url;
                        }
                    } else {
                        console.warn(`${action} failed:`, data.message);
                    }
                } catch (error) {
                    console.error(`Error applying ${action}:`, error);
                }
            }

            // Reload audio if we have a new URL
            if (lastUrl) {
                // Add timestamp to force browser to reload the file (bust cache)
                const urlWithTimestamp = `${lastUrl}?t=${Date.now()}`;
                loadAudio(urlWithTimestamp);

                // Update file list URL
                const activeItem = document.querySelector(`.file-item[data-id="${currentProjectId}"]`);
                if (activeItem) {
                    activeItem.dataset.url = urlWithTimestamp;
                }
            }

            // Re-analyze after all fixes
            await triggerAnalysis();

            alert('Auto-restoration complete!');
            applyAllBtn.textContent = 'Apply All Fixes';
            applyAllBtn.disabled = false;
        });
    }

    // Helper function to generate restoration plan
    function generateRestorationPlan(analyzeData) {
        const plan = [];
        const artifacts = analyzeData.artifacts || {};

        // DC Offset - always first
        if (Math.abs(artifacts.dc_offset || 0) > 0.01) {
            plan.push({
                action: 'remove_dc',
                title: 'Remove DC Offset',
                reason: 'Must be fixed before other processing'
            });
        }

        // Clipping
        if (analyzeData.clipping_count > 10) {
            plan.push({
                action: 'declip',
                title: 'Declipping',
                reason: `${analyzeData.clipping_count} clipped samples detected`
            });
        }

        // Clicks
        if (artifacts.clicks_detected > 10) {
            plan.push({
                action: 'remove_clicks',
                title: 'Remove Clicks',
                reason: `${artifacts.clicks_detected} clicks detected`
            });
        }

        // Hum
        if (artifacts.hum_frequency) {
            plan.push({
                action: 'remove_hum',
                title: 'Remove Hum',
                reason: `${artifacts.hum_frequency} Hz hum detected`
            });
        }

        // Noise
        if (analyzeData.noise_floor_db > -40) {
            plan.push({
                action: 'denoise',
                title: 'Spectral Denoise',
                reason: `High noise floor (${analyzeData.noise_floor_db.toFixed(1)} dB)`
            });
        }

        // Normalization - only if significantly off target
        if (analyzeData.lufs < -18 || analyzeData.lufs > -10) {
            plan.push({
                action: 'normalize',
                title: 'Normalize to -14 LUFS',
                reason: `Current level: ${analyzeData.lufs.toFixed(1)} LUFS`
            });
        }

        return plan;
    }

    // Repair Tools
    document.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            if (!currentProjectId) {
                alert("Please select a file first.");
                return;
            }

            const action = e.target.dataset.action;
            if (!action) return;

            const csrftoken = getCookie('csrftoken');
            let params = {};

            if (action === 'normalize') {
                const input = document.getElementById('targetLufs');
                params.target_lufs = input ? parseFloat(input.value) : -14;
            } else if (action === 'learn_noise') {
                // Get selected region
                if (!regionsPlugin) {
                    alert("Region plugin not initialized");
                    return;
                }
                const regions = regionsPlugin.getRegions();
                if (regions.length > 0) {
                    params.start_time = regions[0].start;
                    params.end_time = regions[0].end;
                } else {
                    alert("Please select a region first to learn noise profile.");
                    return;
                }
            } else if (action === 'remove_hum') {
                const humFreqSelect = document.getElementById('humFreq');
                params.hum_freq = humFreqSelect ? parseInt(humFreqSelect.value) : 50;
            } else if (action === 'stereo_width') {
                const widthInput = document.getElementById('stereoWidth');
                params.width = widthInput ? parseFloat(widthInput.value) : 1.0;
            }
            // All other actions use default parameters

            // Visual feedback
            const originalText = btn.textContent;
            btn.textContent = 'Processing...';
            btn.disabled = true;

            fetch(`/repair/${currentProjectId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken
                },
                body: JSON.stringify({ action: action, params: params })
            })
                .then(response => response.json())
                .then(data => {
                    btn.textContent = originalText;
                    btn.disabled = false;
                    if (data.status === 'success') {
                        if (data.url) {
                            loadAudio(data.url);
                            // Re-trigger analysis after restoration
                            triggerAnalysis();
                        } else {
                            alert(data.message);
                        }
                    } else {
                        alert("Error: " + data.message);
                    }
                })
                .catch(err => {
                    console.error(err);
                    btn.textContent = originalText;
                    btn.disabled = false;
                    alert("Error processing audio: " + err.message);
                });
        });
    });

    // File List Interaction
    document.getElementById('fileList').addEventListener('click', (e) => {
        const item = e.target.closest('.file-item');
        if (item) {
            document.querySelectorAll('.file-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            currentProjectId = item.dataset.id;
            loadAudio(item.dataset.url);
        }
    });

    // Add file to list helper
    function addFileToList(name, id, url) {
        const list = document.getElementById('fileList');
        const item = document.createElement('div');
        item.className = 'file-item active';
        item.dataset.id = id;
        item.dataset.url = url;
        item.innerHTML = `
            <div class="file-icon"><i class="fas fa-music"></i></div>
            <div class="file-details">
                <span class="file-name">${name}</span>
                <span class="file-date">Just now</span>
            </div>
        `;

        item.addEventListener('click', () => {
            currentProjectId = id;
            loadAudio(url);
            document.getElementById('currentFileName').textContent = name;
            triggerAnalysis();
        });

        document.querySelectorAll('.file-item').forEach(i => i.classList.remove('active'));
        list.prepend(item);
    }

    // Helper for CSRF
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
});
