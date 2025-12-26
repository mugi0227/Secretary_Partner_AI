// API Configuration
const API_BASE = 'http://localhost:8000/api';
// The token we added to mock_auth.py
const AUTH_TOKEN = 'secret-token-123';

document.addEventListener('DOMContentLoaded', () => {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.getElementById('status-text');
    const captureBtn = document.getElementById('capture-btn');
    const resultMsg = document.getElementById('result-message');

    // Check connection initially (simple health check or just assume local)
    // For now, we assume if we are running effectively, we are 'Ready'
    statusDot.classList.add('connected');
    statusText.textContent = 'Connected (Local)';

    captureBtn.addEventListener('click', async () => {
        try {
            setLoading(true);

            // 1. Capture Visible Tab
            const dataUrl = await captureTab();

            // 2. Get Current URL & Title
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (!tab) throw new Error('No active tab found');

            // 3. Send to Backend
            await sendToBackend({
                image: dataUrl,
                url: tab.url,
                title: tab.title
            });

            showResult('Captutre sent successfully!', 'success');
        } catch (err) {
            console.error(err);
            showResult(`Error: ${err.message}`, 'error');
        } finally {
            setLoading(false);
        }
    });

    function setLoading(isLoading) {
        if (isLoading) {
            captureBtn.disabled = true;
            captureBtn.innerHTML = '<span class="icon">⏳</span> Sending...';
        } else {
            captureBtn.disabled = false;
            captureBtn.innerHTML = '<span class="icon">📸</span> Capture This Tab';
        }
    }

    function showResult(msg, type) {
        resultMsg.textContent = msg;
        resultMsg.className = type; // 'success' or 'error'
        resultMsg.classList.remove('hidden');

        setTimeout(() => {
            resultMsg.classList.add('hidden');
        }, 3000);
    }
});

/**
 * Capture the visible area of the currently active tab.
 * Returns a base64 Data URL (JPEG).
 */
async function captureTab() {
    return new Promise((resolve, reject) => {
        chrome.tabs.captureVisibleTab(null, { format: 'jpeg', quality: 80 }, (dataUrl) => {
            if (chrome.runtime.lastError) {
                return reject(chrome.runtime.lastError);
            }
            resolve(dataUrl);
        });
    });
}

/**
 * Send the captured data to the Secretary API.
 */
async function sendToBackend(data) {
    // Convert DataURL to Blob for upload if needed, 
    // but for now let's see if we can send it as a base64 string in the body 
    // or if the backend expects a specific format.
    // Looking at `CaptureCreate` model in backend (`content_url` or `raw_text`?), 
    // wait, the backend `CaptureCreate` has `content_url` (cloud) but not a field for raw image data yet?
    // Let's re-read backend model `capture.py` quickly.
    // Actually, for a quick MVP, we might need a way to upload the image or send base64.
    // If the backend doesn't support base64 fields yet, we might need to update the backend model 
    // OR temporarily just send the URL and Title as TEXT capture.

    // Strategy: Send as TEXT capture first containing JSON metadata, 
    // until we add image upload support.
    const payload = {
        content_type: 'TEXT', // Metadata is text
        base64_image: data.image, // Send separate from raw_text to avoid size limits
        raw_text: JSON.stringify({
            type: 'EXT_CAPTURE',
            url: data.url,
            title: data.title
        })
    };

    const res = await fetch(`${API_BASE}/captures`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${AUTH_TOKEN}`
        },
        body: JSON.stringify(payload)
    });

    if (!res.ok) {
        const errText = await res.text();
        throw new Error(`Server responded with ${res.status}: ${errText}`);
    }

    return res.json();
}
