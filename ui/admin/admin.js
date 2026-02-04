const API_BASE = '/api';
const WS_URL = 'ws://' + window.location.host + '/ws/news';

// State
let newsQueue = [];

// Elements
const elQueue = document.getElementById('newsQueue');
const inpTitleTamil = document.getElementById('inpTitleTamil');
const inpType = document.getElementById('inpType');
const inpCategory = document.getElementById('inpCategory');
const statTickers = document.getElementById('statTickers');
const statBreaking = document.getElementById('statBreaking');
const statMainScreen = document.getElementById('statMainScreen');
const inpWebviewUrl = document.getElementById('inpWebviewUrl');
const inpFile = document.getElementById('inpFile');
const uploadStatus = document.getElementById('uploadStatus');
const mediaGallery = document.getElementById('mediaGallery');
const pageTitle = document.getElementById('pageTitle');

// Init
document.addEventListener('DOMContentLoaded', () => {
    fetchNews();
    connectWebSocket();
    document.getElementById('startTime').innerText = new Date().toLocaleTimeString();
});

// --- Navigation ---
function switchView(viewName) {
    // Hide all
    document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-link').forEach(el => el.classList.remove('active'));

    // Show target
    document.getElementById(`view-${viewName}`).classList.add('active');
    document.getElementById(`nav-${viewName}`).classList.add('active');

    // Update Title
    const titles = {
        'dashboard': 'Live Overview',
        'news': 'News Manager',
        'media': 'Media Library',
        'config': 'Layout Configuration'
    };
    pageTitle.innerText = titles[viewName] || 'Control Room';

    // Lazy Load
    if (viewName === 'media') fetchMedia();
}

// --- API Interactions ---

async function fetchNews() {
    try {
        const res = await fetch(`${API_BASE}/news`);
        newsQueue = await res.json();
        renderQueue();
        updateStats();
    } catch (err) {
        console.error("Failed to fetch news:", err);
    }
}

async function submitNews() {
    const title = inpTitleTamil.value.trim();
    if (!title) return alert("Please enter a headline");

    const payload = {
        title_tamil: title,
        type: inpType.value,
        category: inpCategory.value,
        is_active: true, // Default to active
        priority: 0
    };

    try {
        const res = await fetch(`${API_BASE}/news`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            inpTitleTamil.value = ""; // Clear input
            // List will auto-update via WebSocket
            // Switch to queue view if not there?
        } else {
            alert("Failed to publish");
        }
    } catch (err) {
        console.error("Publish error:", err);
    }
}

async function deleteNews(id) {
    if (!confirm("Are you sure you want to remove this item?")) return;
    try {
        await fetch(`${API_BASE}/news/${id}`, { method: 'DELETE' });
    } catch (err) {
        console.error("Delete error:", err);
    }
}

async function toggleActive(id, currentState) {
    try {
        await fetch(`${API_BASE}/news/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: !currentState })
        });
    } catch (err) {
        console.error("Toggle error:", err);
    }
}

async function publishBreaking() {
    const title = prompt("Enter Breaking News Headline:");
    if (!title) return;

    const payload = {
        title_tamil: title,
        type: "BREAKING",
        category: "GENERAL",
        is_active: true,
        priority: 10
    };

    await fetch(`${API_BASE}/news`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    switchView('news');
}


// --- Media & Screen ---

async function updateMainScreen() {
    const url = inpWebviewUrl.value.trim();
    setMainScreen(url);
}

async function setMainScreen(url) {
    try {
        await fetch('/api/overlay/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ webview_url: url })
        });
        if (url) alert("Main screen updated!");
        statMainScreen.innerText = url ? "Active" : "Cleared";
    } catch (e) {
        console.error(e);
    }
}

async function uploadMedia() {
    const file = inpFile.files[0];
    if (!file) return alert("Select a file first");

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (data.url) {
            inpWebviewUrl.value = window.location.origin + data.url; // Auto-fill URL input
            uploadStatus.style.display = 'block';
            setTimeout(() => uploadStatus.style.display = 'none', 3000);
            fetchMedia(); // Refresh Gallery
        }
    } catch (e) {
        console.error("Upload error", e);
        alert("Upload failed");
    }
}

async function fetchMedia() {
    try {
        const res = await fetch('/api/media');
        const files = await res.json();
        renderMedia(files);
    } catch (e) { console.error(e); }
}

function renderMedia(files) {
    mediaGallery.innerHTML = "";
    if (files.length === 0) {
        mediaGallery.innerHTML = "<p class='text-gray-400 col-span-4 text-center'>No media found.</p>";
        return;
    }

    files.forEach(f => {
        const isImg = f.name.match(/\.(jpeg|jpg|gif|png)$/) != null;
        const preview = isImg ?
            `<img src="${f.url}" class="h-24 w-full object-cover rounded mb-2">` :
            `<div class="h-24 w-full bg-gray-200 rounded mb-2 flex items-center justify-center"><i class="fas fa-video text-gray-400 text-2xl"></i></div>`;

        const html = `
            <div class="bg-gray-50 border border-gray-200 rounded p-2 text-sm hover:shadow transition">
                ${preview}
                <div class="truncate font-bold mb-2" title="${f.name}">${f.name}</div>
                <button onclick="setMainScreen('${window.location.origin}${f.url}')" class="w-full bg-slate-700 text-white py-1 rounded text-xs hover:bg-slate-600">
                    <i class="fas fa-play mr-1"></i> Play On Screen
                </button>
            </div>
        `;
        mediaGallery.innerHTML += html;
    });
}


// --- WebSocket ---

function connectWebSocket() {
    const ws = new WebSocket(WS_URL);

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        // On any update, just re-fetch the list for simplicity (for now)
        if (msg.type.startsWith("NEWS")) {
            fetchNews();
        }
    };

    ws.onclose = () => {
        setTimeout(connectWebSocket, 3000); // Reconnect
    };
}

// --- Rendering ---

function renderQueue() {
    elQueue.innerHTML = "";

    if (newsQueue.length === 0) {
        elQueue.innerHTML = '<div class="text-center text-gray-400 italic p-4">No active news</div>';
        return;
    }

    newsQueue.forEach(item => {
        const isBreaking = item.type === 'BREAKING';
        const cardClass = isBreaking ? 'border-l-4 border-red-500 bg-red-50' : 'bg-white border-l-4 border-gray-300';

        const html = `
            <div class="p-3 rounded shadow-sm flex justify-between items-center ${cardClass}">
                <div class="flex-1">
                    <span class="text-[10px] font-bold uppercase tracking-wider ${isBreaking ? 'text-red-600 bg-red-100 px-1 rounded' : 'text-gray-500'}">
                        ${item.type} • ${item.category}
                    </span>
                    <h4 class="font-bold text-lg text-slate-800 leading-tight mt-1">${item.title_tamil}</h4>
                    <p class="text-[10px] text-gray-400 mt-1">ID: ${item.id} • ${new Date(item.created_at).toLocaleTimeString()}</p>
                </div>
                <div class="flex space-x-2 ml-4">
                    <button onclick="toggleActive(${item.id}, ${item.is_active})" class="w-8 h-8 rounded-full flex items-center justify-center transition ${item.is_active ? 'bg-green-100 text-green-600 hover:bg-green-200' : 'bg-gray-200 text-gray-400 hover:bg-gray-300'}">
                        <i class="fas fa-power-off"></i>
                    </button>
                    <button onclick="deleteNews(${item.id})" class="w-8 h-8 rounded-full bg-red-100 text-red-600 hover:bg-red-200 flex items-center justify-center transition">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        elQueue.innerHTML += html;
    });
}

function updateStats() {
    const activeTicker = newsQueue.filter(i => i.is_active && i.type === 'TICKER').length;
    const activeBreaking = newsQueue.filter(i => i.is_active && i.type === 'BREAKING').length;

    statTickers.innerText = activeTicker;

    if (activeBreaking > 0) {
        statBreaking.innerText = "ACTIVE";
        statBreaking.classList.remove('text-gray-500');
        statBreaking.classList.add('text-red-600', 'animate-pulse');
    } else {
        statBreaking.innerText = "NONE";
        statBreaking.classList.add('text-gray-500');
        statBreaking.classList.remove('text-red-600', 'animate-pulse');
    }
}

// --- Stream Control ---
const btnStart = document.getElementById('btnStart');
const btnStop = document.getElementById('btnStop');
const inpStreamKey = document.getElementById('inpStreamKey');
const previewBadge = document.getElementById('previewLiveBadge');

async function startStream() {
    const key = inpStreamKey.value.trim();

    // UI Loading state
    btnStart.innerText = "STARTING...";
    btnStart.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/stream/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stream_key: key })
        });
        const d = await res.json();

        if (d.status === 'started' || d.status === 'already_running') {
            setStreamState(true);
        } else {
            alert("Error: " + d.message);
            setStreamState(false);
        }
    } catch (e) {
        console.error(e);
        alert("Failed to start stream");
        setStreamState(false);
    }
}

async function stopStream() {
    if (!confirm("Stop the broadcast?")) return;

    try {
        await fetch(`${API_BASE}/stream/stop`, { method: 'POST' });
        setStreamState(false);
    } catch (e) {
        console.error(e);
    }
}

function setStreamState(isRunning) {
    if (isRunning) {
        btnStart.classList.add('opacity-50', 'cursor-not-allowed');
        btnStart.disabled = true;
        btnStart.innerHTML = '<i class="fas fa-check mr-2"></i> ON AIR';

        btnStop.classList.remove('opacity-50', 'cursor-not-allowed');
        btnStop.disabled = false;

        previewBadge.style.display = 'block';
        document.getElementById('streamStatus').innerHTML =
            '<span class="w-3 h-3 rounded-full bg-red-600 animate-pulse"></span><span class="text-sm font-bold text-red-600">LIVE</span>';
    } else {
        btnStart.classList.remove('opacity-50', 'cursor-not-allowed');
        btnStart.disabled = false;
        btnStart.innerHTML = '<i class="fas fa-play mr-2"></i> START';

        btnStop.classList.add('opacity-50', 'cursor-not-allowed');
        btnStop.disabled = true;

        previewBadge.style.display = 'none';
        document.getElementById('streamStatus').innerHTML =
            '<span class="w-3 h-3 rounded-full bg-gray-400"></span><span class="text-sm font-semibold text-gray-500">OFF AIR</span>';
    }
}

// Poll Status
setInterval(async () => {
    try {
        const res = await fetch(`${API_BASE}/stream/status`);
        const d = await res.json();
        setStreamState(d.running);
    } catch (e) { }
}, 2000);

// Logs
const logWindow = document.getElementById('logWindow');
function clearLogs() {
    logWindow.innerHTML = '<div>> Logs cleared...</div>';
}

// Log WebSocket (re-use existing WS logic simply or add separate channel)
// For now, we mix logs into same WS or assuming separate. 
// Server has /ws/logs. Let's process it.

const wsLogs = new WebSocket('ws://' + window.location.host + '/ws/logs');
wsLogs.onmessage = (e) => {
    const d = JSON.parse(e.data);
    if (d.log) {
        const line = document.createElement('div');
        line.innerText = `> ${d.log}`;
        logWindow.prepend(line);
        // prune
        if (logWindow.children.length > 50) logWindow.lastChild.remove();
    }
};
