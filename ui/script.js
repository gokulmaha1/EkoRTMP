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

let pollingInterval = null;

// Init
document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchOverlayData();

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
        webview_url: inpWebview.value
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
