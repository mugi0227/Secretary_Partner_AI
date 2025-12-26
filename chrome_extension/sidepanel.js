// Side Panel Chat Logic - Premium Overhaul with History support

const API_BASE = 'http://localhost:8000/api';

// State
let currentCapture = null; // { base64, url, title }
let isThinking = false;
let currentSessionId = localStorage.getItem('session_id');

// Elements
const messagesDiv = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const captureBtn = document.getElementById('capture-btn');
const newChatBtn = document.getElementById('new-chat-btn');
const historyBtn = document.getElementById('history-btn');
const closeHistoryBtn = document.getElementById('close-history');
const thinkingIndicator = document.getElementById('thinking');
const previewContainer = document.getElementById('preview-container');
const screenshotPreview = document.getElementById('screenshot-preview');
const removeScreenshotBtn = document.getElementById('remove-screenshot');
const historyPanel = document.getElementById('history-panel');
const sessionList = document.getElementById('session-list');

/**
 * Initialize
 */
async function init() {
    validateInput();

    if (currentSessionId) {
        await loadHistory(currentSessionId);
    } else {
        addMessage('assistant', "Hello, Shuhei! I'm your Secretary Agent. How can I help you today?");
    }
}

// --- Event Listeners ---

captureBtn.addEventListener('click', async () => {
    try {
        setCaptureLoading(true);
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'jpeg', quality: 70 });

        currentCapture = {
            base64: dataUrl,
            url: tab.url,
            title: tab.title
        };

        showPreview(dataUrl);
        validateInput();

    } catch (err) {
        console.error('Capture failed:', err);
        addSystemMessage('Failed to capture screen: ' + err.message);
    } finally {
        setCaptureLoading(false);
    }
});

removeScreenshotBtn.addEventListener('click', () => {
    currentCapture = null;
    hidePreview();
    validateInput();
});

newChatBtn.addEventListener('click', () => {
    if (confirm('Start a new chat? This will clear the current view.')) {
        clearView();
        currentSessionId = null;
        localStorage.removeItem('session_id');
        addMessage('assistant', "New session started. How can I help you?");
    }
});

historyBtn.addEventListener('click', () => {
    toggleHistory(true);
    fetchSessions();
});

closeHistoryBtn.addEventListener('click', () => {
    toggleHistory(false);
});

sendBtn.addEventListener('click', sendMessage);

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

userInput.addEventListener('input', () => {
    userInput.style.height = 'auto';
    userInput.style.height = (userInput.scrollHeight) + 'px';
    validateInput();
});

// --- Core Functions ---

async function sendMessage() {
    const text = userInput.value.trim();
    if ((!text && !currentCapture) || isThinking) return;

    // 1. Add user message to UI
    addMessage('user', text, currentCapture ? currentCapture.base64 : null);

    // 2. Prepare for API
    const sendingCapture = currentCapture;
    const originalText = text;

    // reset UI
    userInput.value = '';
    userInput.style.height = 'auto';
    currentCapture = null;
    hidePreview();
    validateInput();
    setThinking(true);

    try {
        let imageUrl = null;

        // Step A: Upload capture if exists
        if (sendingCapture) {
            const capturePayload = {
                content_type: 'TEXT',
                base64_image: sendingCapture.base64,
                raw_text: JSON.stringify({
                    type: 'EXT_CAPTURE',
                    url: sendingCapture.url,
                    title: sendingCapture.title
                })
            };

            const captureResp = await fetch(`${API_BASE}/captures`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer dev_user'
                },
                body: JSON.stringify(capturePayload)
            });

            if (captureResp.ok) {
                const captureData = await captureResp.json();
                imageUrl = captureData.content_url;
            }
        }

        // Step B: Chat Stream
        const chatPayload = {
            text: originalText,
            image_base64: sendingCapture ? sendingCapture.base64 : null,
            image_url: imageUrl,
            mode: 'dump',
            session_id: currentSessionId
        };

        const response = await fetch(`${API_BASE}/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer dev_user'
            },
            body: JSON.stringify(chatPayload)
        });

        if (!response.ok) throw new Error('Chat failed');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let assistantContentDiv = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.slice(6);
                    try {
                        const chunk = JSON.parse(dataStr);

                        if (!assistantContentDiv && (chunk.chunk_type === 'text' || chunk.chunk_type === 'tool_start')) {
                            setThinking(false);
                            assistantContentDiv = createAssistantMessageContainer();
                        }

                        handleStreamingChunk(chunk, assistantContentDiv);
                    } catch (e) {
                        console.error('Error parsing chunk:', e);
                    }
                }
            }
        }

    } catch (err) {
        console.error('Send Error:', err);
        setThinking(false);
        addSystemMessage('Something went wrong. Please check your connection.');
    } finally {
        setThinking(false);
    }
}

function handleStreamingChunk(chunk, contentDiv) {
    if (chunk.chunk_type === 'text') {
        if (contentDiv) {
            contentDiv.textContent += chunk.content;
            scrollToBottom();
        }
    } else if (chunk.chunk_type === 'tool_start') {
        const toolDiv = document.createElement('div');
        toolDiv.className = 'tool-usage';
        toolDiv.innerHTML = `<span>🔨</span> <span>Using tool: ${chunk.tool_name}...</span>`;
        if (contentDiv) {
            contentDiv.parentElement.appendChild(toolDiv);
        }
        scrollToBottom();
    } else if (chunk.chunk_type === 'done') {
        if (chunk.session_id) {
            currentSessionId = chunk.session_id;
            localStorage.setItem('session_id', chunk.session_id);
        }
    }
}

async function fetchSessions() {
    sessionList.innerHTML = '<div class="loading-item">Fetching conversations...</div>';
    try {
        const resp = await fetch(`${API_BASE}/chat/sessions`, {
            headers: { 'Authorization': 'Bearer dev_user' }
        });
        if (!resp.ok) throw new Error('Failed to fetch sessions');
        const sessions = await resp.json();

        sessionList.innerHTML = '';
        if (sessions.length === 0) {
            sessionList.innerHTML = '<div class="loading-item">No recent chats found.</div>';
            return;
        }

        sessions.forEach(session => {
            const item = document.createElement('div');
            item.className = `session-item ${session.session_id === currentSessionId ? 'active' : ''}`;

            const dateStr = session.updated_at ? new Date(session.updated_at).toLocaleString() : 'Recent';

            item.innerHTML = `
                <span class="session-title">${session.title || 'Untitled Chat'}</span>
                <span class="session-date">${dateStr}</span>
            `;

            item.addEventListener('click', () => {
                toggleHistory(false);
                if (session.session_id !== currentSessionId) {
                    loadHistory(session.session_id);
                }
            });
            sessionList.appendChild(item);
        });
    } catch (err) {
        sessionList.innerHTML = `<div class="loading-item">Error: ${err.message}</div>`;
    }
}

async function loadHistory(sessionId) {
    clearView();
    currentSessionId = sessionId;
    localStorage.setItem('session_id', sessionId);
    setThinking(true);

    try {
        const resp = await fetch(`${API_BASE}/chat/history/${sessionId}`, {
            headers: { 'Authorization': 'Bearer dev_user' }
        });
        if (!resp.ok) throw new Error('Failed to load history');
        const messages = await resp.json();

        setThinking(false);
        if (messages.length === 0) {
            addMessage('assistant', "This session is empty. How can I help?");
            return;
        }

        messages.forEach(msg => {
            addMessage(msg.role, msg.content);
        });
    } catch (err) {
        setThinking(false);
        addSystemMessage("Could not restore conversation. Starting fresh.");
        currentSessionId = null;
        localStorage.removeItem('session_id');
    }
}

// --- UI Helpers ---

function toggleHistory(show) {
    if (show) {
        historyPanel.classList.remove('hidden');
    } else {
        historyPanel.classList.add('hidden');
    }
}

function addMessage(role, text, imageBase64) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (imageBase64) {
        const img = document.createElement('img');
        img.src = imageBase64;
        img.className = 'message-image';
        contentDiv.appendChild(img);
    }

    if (text) {
        const textNode = document.createTextNode(text);
        contentDiv.appendChild(textNode);
    }

    messageDiv.appendChild(contentDiv);
    messagesDiv.appendChild(messageDiv);
    scrollToBottom();
    return contentDiv;
}

function createAssistantMessageContainer() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    messageDiv.appendChild(contentDiv);
    messagesDiv.appendChild(messageDiv);
    scrollToBottom();
    return contentDiv;
}

function addSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'message system';
    div.textContent = text;
    messagesDiv.appendChild(div);
    scrollToBottom();
}

function setThinking(val) {
    isThinking = val;
    if (val) {
        // Ensure thinking indicator is always at the bottom
        messagesDiv.appendChild(thinkingIndicator);
        thinkingIndicator.classList.remove('hidden');
    } else {
        thinkingIndicator.classList.add('hidden');
    }
    scrollToBottom();
}

function validateInput() {
    const hasText = userInput.value.trim().length > 0;
    const hasImage = !!currentCapture;
    sendBtn.disabled = !(hasText || hasImage) || isThinking;
}

function showPreview(dataUrl) {
    screenshotPreview.src = dataUrl;
    previewContainer.classList.remove('hidden');
    scrollToBottom();
}

function hidePreview() {
    screenshotPreview.src = '';
    previewContainer.classList.add('hidden');
}

function setCaptureLoading(loading) {
    captureBtn.disabled = loading;
    captureBtn.style.opacity = loading ? '0.5' : '1';
}

function scrollToBottom() {
    const stream = document.getElementById('chat-stream');
    stream.scrollTop = stream.scrollHeight;
}

function clearView() {
    // Preserve thinking indicator while clearing messages
    const messages = Array.from(messagesDiv.children).filter(child => child.id !== 'thinking');
    messages.forEach(msg => msg.remove());

    userInput.value = '';
    userInput.style.height = 'auto';
    currentCapture = null;
    hidePreview();
    validateInput();
}

// Start
init();
