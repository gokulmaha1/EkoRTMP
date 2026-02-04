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
    fetchConfig();
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

// --- Layout Config ---
async function fetchConfig() {
    try {
        const res = await fetch(`${API_BASE}/config`);
        const conf = await res.json();

        document.getElementById('inpColorPrimary').value = conf.brand_color_primary || "#c0392b";
        document.getElementById('inpColorSecondary').value = conf.brand_color_secondary || "#f1c40f";
        document.getElementById('inpColorDark').value = conf.brand_color_dark || "#2c3e50";
        document.getElementById('inpLogoUrl').value = conf.logo_url || "/media/logo.gif";
        document.getElementById('inpTickerSpeed').value = conf.ticker_speed || 30;
        document.getElementById('lblTickerSpeed').innerText = (conf.ticker_speed || 30) + 's';

        // Text Labels
        document.getElementById('inpDefaultHeadline').value = conf.default_headline || "Welcome to EKO Professional News System...";
        document.getElementById('inpTickerLabel').value = conf.ticker_label || "NEWS UPDATES";
        document.getElementById('inpBreakingLabel').value = conf.breaking_label || "BREAKING";
        document.getElementById('inpLiveLabel').value = conf.live_label || "LIVE";

        // L-Bar Config
        currentLayoutMode = conf.layout_mode || 'FULL';
        setLayoutMode(currentLayoutMode);
        document.getElementById('inpLBarPos').value = conf.lbar_position || 'RIGHT';
        document.getElementById('inpLBarWidth').value = conf.lbar_width || 25;
        document.getElementById('lblLBarWidth').innerText = (conf.lbar_width || 25) + '%';
        document.getElementById('inpLBarBgColor').value = conf.lbar_bg_color || '#000000';
        document.getElementById('inpLBarType').value = conf.lbar_content_type || 'IMAGE';
        document.getElementById('inpLBarData').value = conf.lbar_content_data || '';

    } catch (e) { console.error(e); }
}

let currentLayoutMode = 'FULL';
function setLayoutMode(mode) {
    currentLayoutMode = mode;
    const btnFull = document.getElementById('btnLayoutFULL');
    const btnLBar = document.getElementById('btnLayoutL_BAR');
    const configArea = document.getElementById('lbarConfigArea');

    if (mode === 'FULL') {
        btnFull.classList.add('border-indigo-600', 'bg-indigo-50', 'text-indigo-700');
        btnFull.classList.remove('border-gray-200');
        btnLBar.classList.remove('border-indigo-600', 'bg-indigo-50', 'text-indigo-700');
        btnLBar.classList.add('border-gray-200');

        configArea.classList.add('opacity-50', 'pointer-events-none');
    } else {
        btnLBar.classList.add('border-indigo-600', 'bg-indigo-50', 'text-indigo-700');
        btnLBar.classList.remove('border-gray-200');
        btnFull.classList.remove('border-indigo-600', 'bg-indigo-50', 'text-indigo-700');
        btnFull.classList.add('border-gray-200');

        configArea.classList.remove('opacity-50', 'pointer-events-none');
    }
}

// L-Bar Width Listener
document.getElementById('inpLBarWidth').addEventListener('input', (e) => {
    document.getElementById('lblLBarWidth').innerText = e.target.value + '%';
});

async function saveConfig() {
    const payload = {
        brand_color_primary: document.getElementById('inpColorPrimary').value,
        brand_color_secondary: document.getElementById('inpColorSecondary').value,
        brand_color_dark: document.getElementById('inpColorDark').value,
        logo_url: document.getElementById('inpLogoUrl').value,
        ticker_speed: parseInt(document.getElementById('inpTickerSpeed').value),
        default_headline: document.getElementById('inpDefaultHeadline').value,
        ticker_label: document.getElementById('inpTickerLabel').value,
        breaking_label: document.getElementById('inpBreakingLabel').value,
        live_label: document.getElementById('inpLiveLabel').value,

        // L-Bar
        layout_mode: currentLayoutMode,
        lbar_position: document.getElementById('inpLBarPos').value,
        lbar_width: parseInt(document.getElementById('inpLBarWidth').value),
        lbar_bg_color: document.getElementById('inpLBarBgColor').value,
        lbar_content_type: document.getElementById('inpLBarType').value,
        lbar_content_data: document.getElementById('inpLBarData').value
    };

    try {
        await fetch(`${API_BASE}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        alert("Configuration Saved & Broadcasted!");
    } catch (e) {
        console.error(e);
        alert("Failed to save config");
    }
}

// Init speed listener
document.getElementById('inpTickerSpeed').addEventListener('input', (e) => {
    document.getElementById('lblTickerSpeed').innerText = e.target.value + 's';
});

// --- News Tabs & External Fetching ---
function setNewsTab(tab) {
    // Buttons
    document.getElementById('tab-manual').className = tab === 'manual'
        ? 'flex-1 py-3 bg-slate-800 text-white font-bold text-sm'
        : 'flex-1 py-3 bg-gray-100 text-gray-500 font-bold text-sm hover:bg-gray-200';

    document.getElementById('tab-external').className = tab === 'external'
        ? 'flex-1 py-3 bg-slate-800 text-white font-bold text-sm'
        : 'flex-1 py-3 bg-gray-100 text-gray-500 font-bold text-sm hover:bg-gray-200';

    // Content
    if (tab === 'manual') {
        document.getElementById('content-manual').classList.remove('hidden');
        document.getElementById('content-external').classList.add('hidden');
    } else {
        document.getElementById('content-manual').classList.add('hidden');
        document.getElementById('content-external').classList.remove('hidden');
        fetchFeeds(); // Load saved feeds
    }
}

// --- Feed Management ---
async function fetchFeeds() {
    const el = document.getElementById('savedFeedsList');
    el.innerHTML = '<div class="text-xs text-gray-400">Loading feeds...</div>';

    try {
        const res = await fetch(`${API_BASE}/feeds`);
        const feeds = await res.json();

        el.innerHTML = "";
        if (feeds.length === 0) {
            el.innerHTML = '<div class="text-xs text-gray-400 italic">No saved feeds.</div>';
            return;
        }

        feeds.forEach(feed => {
            const item = document.createElement('div');
            item.className = "flex justify-between items-center bg-gray-50 p-2 rounded border hover:bg-blue-50 cursor-pointer group";
            item.innerHTML = `
                <div class="flex-1 overflow-hidden" onclick="loadFeed('${feed.url}')">
                    <div class="font-bold text-xs text-slate-700">${feed.name}</div>
                    <div class="text-[10px] text-gray-400 truncate">${feed.url}</div>
                </div>
                <button onclick="deleteFeed(${feed.id})" class="text-red-400 hover:text-red-600 px-2 hidden group-hover:block">
                    <i class="fas fa-trash"></i>
                </button>
            `;
            el.appendChild(item);
        });
    } catch (e) {
        console.error(e);
        el.innerHTML = '<div class="text-xs text-red-400">Error loading feeds</div>';
    }
}

async function addNewFeed() {
    const name = prompt("Enter Feed Name (e.g. Google News):");
    if (!name) return;
    const url = prompt("Enter RSS Feed URL:");
    if (!url) return;

    try {
        await fetch(`${API_BASE}/feeds`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, url, source_type: "RSS" })
        });
        fetchFeeds();
    } catch (e) {
        console.error(e);
        alert("Failed to save feed");
    }
}

async function deleteFeed(id) {
    if (!confirm("Remove this feed?")) return;
    try {
        await fetch(`${API_BASE}/feeds/${id}`, { method: 'DELETE' });
        fetchFeeds();
    } catch (e) { console.error(e); }
}

function loadFeed(url) {
    document.getElementById('inpExtUrl').value = url;
    document.getElementById('inpSourceType').value = "RSS";
    fetchExternalNews();
}

// --- Fetch & Insert Logic ---
async function fetchExternalNews() {
    const url = document.getElementById('inpExtUrl').value.trim();
    if (!url) return alert("Please enter a URL");

    const sourceType = document.getElementById('inpSourceType').value;
    const previewArea = document.getElementById('extPreviewArea');

    previewArea.innerHTML = '<div class="text-center text-gray-400">Fetching...</div>';
    previewArea.classList.remove('hidden');

    try {
        const res = await fetch(`${API_BASE}/news/fetch-external`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, source_type: sourceType })
        });
        const data = await res.json();

        previewArea.innerHTML = "";

        if (data.status === 'success' && data.items.length > 0) {
            data.items.forEach(item => {
                const el = document.createElement('div');
                el.className = 'bg-gray-50 border p-2 rounded flex justify-between items-start text-xs';
                el.innerHTML = `
                    <div class="flex-1 mr-2">
                        <div class="font-bold mb-1">${item.title}</div>
                        <div class="text-gray-500 truncate">${item.summary}</div>
                    </div>
                    <button class="bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700 font-bold">
                        <i class="fas fa-plus"></i> Add
                    </button>
                `;
                el.querySelector('button').onclick = () => insertExternalNews(item);
                previewArea.appendChild(el);
            });
        } else {
            previewArea.innerHTML = '<div class="text-center text-red-400">No items found</div>';
        }
    } catch (e) {
        console.error(e);
        previewArea.innerHTML = '<div class="text-center text-red-400">Error fetching content</div>';
    }
}

async function insertExternalNews(item) {
    // Pre-fill manual tab with data (or save directly? Let's save directly for speed)
    const category = prompt("Select Category (GENERAL, POLITICS, ELECTION, DISTRICT):", "GENERAL");
    if (!category) return;

    const payload = {
        title_tamil: item.title, // Assuming content handles lang or is acceptable
        title_english: item.title,
        type: "TICKER",
        category: category.toUpperCase(),
        is_active: true,
        priority: 0,
        source: item.source,
        source_url: item.link,
        media_url: item.image
    };

    try {
        await fetch(`${API_BASE}/news`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        alert("News item added to queue!");
    } catch (e) {
        console.error(e);
        alert("Failed to add news");
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
                    <div class="flex items-center gap-2 mb-1">
                        <span class="text-[10px] font-bold uppercase tracking-wider ${isBreaking ? 'text-red-600 bg-red-100 px-1 rounded' : 'text-gray-500'}">
                            ${item.type} • ${item.category}
                        </span>
                        ${item.source === 'RSS' ? `<span class="bg-blue-100 text-blue-600 text-[9px] font-bold px-1 rounded uppercase"><i class="fas fa-rss"></i> RSS</span>` : ''}
                    </div>
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
