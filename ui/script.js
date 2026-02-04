const API_BASE = '/api';

// Elements
const btnStart = document.getElementById('btnStart');
const btnStop = document.getElementById('btnStop');
const statusRing = document.getElementById('streamStatusRing');
const statusText = document.getElementById('streamStatusText');
const btnUpdateOverlay = document.getElementById('btnUpdateOverlay');

const inpTitle = document.getElementById('inpTitle');
const inpSubtitle = document.getElementById('inpSubtitle');
const inpInfo = document.getElementById('inpInfo');
const inpWebview = document.getElementById('inpWebview');
const chkHideOverlays = document.getElementById('chkHideOverlays');

const consoleWindow = document.getElementById('consoleWindow');
const btnClearLogs = document.getElementById('btnClearLogs');

let pollingInterval = null;
let logSocket = null;

// Init
document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchOverlayData();
    connectLogSocket();

    // Load saved stream key
    const savedKey = localStorage.getItem('eko_stream_key');
    if (savedKey) {
        document.getElementById('inpRtmpUrl').value = savedKey;
    }

    // Poll status every 2 seconds
    pollingInterval = setInterval(fetchStatus, 2000);
});

// Stream Controls
btnStart.addEventListener('click', async () => {
    const streamKey = document.getElementById('inpRtmpUrl').value;
    if (!streamKey) {
        alert("Please enter your Stream Key");
        return;
    }

    // Save to localStorage
    localStorage.setItem('eko_stream_key', streamKey);

    // Automatically prepend YouTube URL
    const rtmpUrl = `rtmp://a.rtmp.youtube.com/live2/${streamKey}`;

    setLoading(true);
    try {
        const res = await fetch(`${API_BASE}/stream/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rtmp_url: rtmpUrl })
        });
        const data = await res.json();
        console.log('Start stream:', data);
        setTimeout(fetchStatus, 1000); // Check status shortly after
    } catch (err) {
        console.error('Error starting stream:', err);
        addLog(`Error starting stream: ${err}`, "system");
    } finally {
        setLoading(false);
    }
});

btnStop.addEventListener('click', async () => {
    setLoading(true);
    try {
        const res = await fetch(`${API_BASE}/stream/stop`, { method: 'POST' });
        const data = await res.json();
        console.log('Stop stream:', data);
        setTimeout(fetchStatus, 1000);
    } catch (err) {
        console.error('Error stopping stream:', err);
    } finally {
        setLoading(false);
    }
});

// Overlay Updates
btnUpdateOverlay.addEventListener('click', async () => {
    const payload = {
        title: inpTitle.value,
        subtitle: inpSubtitle.value,
        info: inpInfo.value,
        webview_url: inpWebview.value,
        hide_overlays: chkHideOverlays.checked
    };

    // Visual feedback
    const originalText = btnUpdateOverlay.innerHTML;
    btnUpdateOverlay.innerHTML = '<span class="icon">⏳</span> Updating...';

    try {
        await fetch(`${API_BASE}/overlay`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        // Success feedback
        btnUpdateOverlay.innerHTML = '<span class="icon">✔</span> Updated!';
        setTimeout(() => {
            btnUpdateOverlay.innerHTML = originalText;
        }, 1500);

    } catch (err) {
        console.error('Error updating overlay:', err);
        btnUpdateOverlay.innerHTML = '<span class="icon">⚠</span> Error';
    }
});

// WebSocket Logs
function connectLogSocket() {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${proto}://${window.location.host}/ws/logs`;

    console.log("Connecting to WebSocket:", wsUrl);
    logSocket = new WebSocket(wsUrl);

    logSocket.onopen = () => {
        addLog("Connected to log stream.", "system");
    };

    logSocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.log) {
                addLog(data.log);
            }
        } catch (e) {
            console.error("Log parse error", e);
        }
    };

    logSocket.onclose = () => {
        console.warn("WebSocket closed. Reconnecting...");
        setTimeout(connectLogSocket, 3000);
    };

    logSocket.onerror = (err) => {
        console.error("WebSocket error:", err);
    };
}

function addLog(msg, type = "") {
    if (!consoleWindow) return;
    const div = document.createElement('div');
    div.className = `log-line ${type}`;
    div.innerText = msg;
    consoleWindow.appendChild(div);
    consoleWindow.scrollTop = consoleWindow.scrollHeight;
}

if (btnClearLogs) {
    btnClearLogs.addEventListener('click', () => {
        consoleWindow.innerHTML = '';
    });
}

// Data Fetching
async function fetchStatus() {
    try {
        const res = await fetch(`${API_BASE}/stream/status`);
        const data = await res.json();
        updateUIStatus(data.running);
    } catch (err) {
        console.error('Status check failed:', err);
        updateUIStatus(false);
    }
}

async function fetchOverlayData() {
    try {
        const res = await fetch('/overlay/data');
        const data = await res.json();

        if (data.title) inpTitle.value = data.title;
        if (data.subtitle) inpSubtitle.value = data.subtitle;
        if (data.info) inpInfo.value = data.info;
        if (data.webview_url) inpWebview.value = data.webview_url;
        if (data.hide_overlays !== undefined) chkHideOverlays.checked = data.hide_overlays;
    } catch (err) {
        console.error('Error fetching overlay data:', err);
    }
}

// UI Helpers
function updateUIStatus(isRunning) {
    if (isRunning) {
        statusRing.classList.add('active');
        statusText.innerText = 'ON AIR';
        statusText.style.color = 'var(--danger)';
        btnStart.disabled = true;
        btnStop.disabled = false;
    } else {
        statusRing.classList.remove('active');
        statusText.innerText = 'OFFLINE';
        statusText.style.color = 'var(--text-muted)';
        btnStart.disabled = false;
        btnStop.disabled = true;
    }
}

function setLoading(isLoading) {
    if (isLoading) {
        document.body.style.cursor = 'wait';
        btnStart.style.opacity = '0.7';
        btnStop.style.opacity = '0.7';
    } else {
        document.body.style.cursor = 'default';
        btnStart.style.opacity = '1';
        btnStop.style.opacity = '1';
    }
}
