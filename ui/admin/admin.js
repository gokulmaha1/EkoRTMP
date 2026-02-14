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
        'ads': 'Ad Manager',
        'ads': 'Ad Manager',
        'config': 'Layout Configuration',
        'schedule': 'Program Schedule'
    };
    pageTitle.innerText = titles[viewName] || 'Control Room';

    // Lazy Load
    if (viewName === 'media') fetchMedia();
    if (viewName === 'ads') fetchAds();
    if (viewName === 'schedule') fetchSchedule();
}

// --- API Interactions ---

async function fetchNews() {
    try {
        // Use Admin Endpoint to get ALL items (Active + Pending)
        const res = await fetch(`${API_BASE}/admin/news`);
        newsQueue = await res.json();
        renderQueue();
        updateStats();
    } catch (err) {
        console.error("Failed to fetch news:", err);
    }
}

async function submitNews(asDraft = false) {
    const title = inpTitleTamil.value.trim();
    if (!title) return alert("Please enter a headline");

    const payload = {
        title_tamil: title,
        type: inpType.value,
        category: inpCategory.value,
        is_active: !asDraft, // Active if not draft
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
        } else {
            const err = await res.json();
            alert("Failed to publish: " + (err.detail || "Unknown error"));
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
        // Speed Logic Removed

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
// --- News Tabs & External Fetching ---
function setNewsTab(tab) {
    // Buttons
    document.getElementById('tab-manual').className = tab === 'manual'
        ? 'flex-1 py-3 bg-slate-800 text-white font-bold text-sm'
        : 'flex-1 py-3 bg-gray-100 text-gray-500 font-bold text-sm hover:bg-gray-200';

    document.getElementById('tab-external').className = tab === 'external'
        ? 'flex-1 py-3 bg-slate-800 text-white font-bold text-sm'
        : 'flex-1 py-3 bg-gray-100 text-gray-500 font-bold text-sm hover:bg-gray-200';

    document.getElementById('tab-filters').className = tab === 'filters'
        ? 'flex-1 py-3 bg-slate-800 text-white font-bold text-sm'
        : 'flex-1 py-3 bg-gray-100 text-gray-500 font-bold text-sm hover:bg-gray-200';

    // Content
    if (tab === 'manual') {
        document.getElementById('content-manual').classList.remove('hidden');
        document.getElementById('content-external').classList.add('hidden');
        document.getElementById('content-filters').classList.add('hidden');
    } else if (tab === 'external') {
        document.getElementById('content-manual').classList.add('hidden');
        document.getElementById('content-external').classList.remove('hidden');
        document.getElementById('content-filters').classList.add('hidden');
        fetchFeeds(); // Load saved feeds
    } else {
        document.getElementById('content-manual').classList.add('hidden');
        document.getElementById('content-external').classList.add('hidden');
        document.getElementById('content-filters').classList.remove('hidden');
        loadFilters();
    }
}

// --- Filter Management ---
async function loadFilters() {
    try {
        const res = await fetch(`${API_BASE}/config/filters`);
        const filters = await res.json();
        const text = filters.join(', ');
        document.getElementById('inpFilterList').value = text;
    } catch (e) {
        console.error("Failed to load filters", e);
    }
}

async function saveFilters() {
    const raw = document.getElementById('inpFilterList').value;
    const filters = raw.split(',').map(s => s.trim()).filter(s => s.length > 0);

    try {
        await fetch(`${API_BASE}/config/filters`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filters: filters })
        });
        alert('Filters Saved!');
    } catch (e) {
        console.error("Failed to save filters", e);
        alert('Error saving filters');
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
    //document.getElementById('inpSourceType').value = "RSS";
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
        is_active: false, // Default to Draft/Pending
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
        elQueue.innerHTML = '<div class="text-center text-gray-400 italic p-4">No news items</div>';
        return;
    }

    // Split into Pending and Active
    const pendingItems = newsQueue.filter(i => !i.is_active);
    const activeItems = newsQueue.filter(i => i.is_active);

    // --- RENDER PENDING ---
    if (pendingItems.length > 0) {
        elQueue.innerHTML += `<div class="font-bold text-gray-500 text-xs uppercase tracking-wider mb-2 mt-4 ml-1">Pending Approval (${pendingItems.length})</div>`;
        pendingItems.forEach(item => elQueue.innerHTML += renderItemCard(item, true));
    }

    // --- RENDER ACTIVE ---
    if (activeItems.length > 0) {
        elQueue.innerHTML += `<div class="font-bold text-green-600 text-xs uppercase tracking-wider mb-2 mt-6 ml-1">Live On Air (${activeItems.length})</div>`;
        activeItems.forEach(item => elQueue.innerHTML += renderItemCard(item, false));
    }
}

function renderItemCard(item, isPending) {
    const isBreaking = item.type === 'BREAKING';
    const cardClass = isPending
        ? 'bg-yellow-50 border-l-4 border-yellow-400 opacity-90'
        : (isBreaking ? 'border-l-4 border-red-500 bg-red-50' : 'bg-white border-l-4 border-gray-300');

    // Action Buttons
    let actionButtons = '';

    if (isPending) {
        actionButtons = `
            <button onclick="approveNews(${item.id})" class="px-3 py-1 rounded bg-green-600 text-white text-xs font-bold hover:bg-green-700 transition shadow-sm">
                <i class="fas fa-check mr-1"></i> Approve
            </button>
            <button onclick="rejectNews(${item.id})" class="px-3 py-1 rounded bg-red-100 text-red-600 text-xs font-bold hover:bg-red-200 transition">
                <i class="fas fa-times"></i>
            </button>
        `;
    } else {
        actionButtons = `
            <button onclick="showNewsOnScreen(${item.id})" class="w-8 h-8 rounded-full bg-blue-100 text-blue-600 hover:bg-blue-200 flex items-center justify-center transition" title="Show on Main Screen">
                <i class="fas fa-tv"></i>
            </button>
            <button onclick="toggleActive(${item.id}, ${item.is_active})" class="w-8 h-8 rounded-full bg-green-100 text-green-600 hover:bg-green-200 flex items-center justify-center transition" title="Unpublish">
                <i class="fas fa-power-off"></i>
            </button>
            <button onclick="deleteNews(${item.id})" class="w-8 h-8 rounded-full bg-red-100 text-red-600 hover:bg-red-200 flex items-center justify-center transition">
                <i class="fas fa-trash"></i>
            </button>
        `;
    }

    return `
        <div class="p-3 rounded shadow-sm flex justify-between items-center ${cardClass} mb-2">
            <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                    <span class="text-[10px] font-bold uppercase tracking-wider ${isBreaking ? 'text-red-600 bg-red-100 px-1 rounded' : 'text-gray-500'}">
                        ${item.type} • ${item.category}
                    </span>
                    ${item.source === 'RSS' ? `<span class="bg-blue-100 text-blue-600 text-[9px] font-bold px-1 rounded uppercase"><i class="fas fa-rss"></i> RSS</span>` : ''}
                    ${isPending ? `<span class="bg-yellow-200 text-yellow-800 text-[9px] font-bold px-1 rounded uppercase"><i class="fas fa-clock"></i> WAIT</span>` : ''}
                </div>
                <h4 class="font-bold text-lg text-slate-800 leading-tight mt-1">${item.title_tamil}</h4>
                <p class="text-[10px] text-gray-400 mt-1">ID: ${item.id} • ${new Date(item.created_at).toLocaleTimeString()}</p>
            </div>
            <div class="flex space-x-2 ml-4 items-center">
                ${actionButtons}
            </div>
        </div>
    `;
}

async function approveNews(id) {
    try {
        await fetch(`${API_BASE}/admin/news/${id}/approve`, { method: 'POST' });
        // WebSocket will update UI
    } catch (e) {
        console.error(e);
        alert("Failed to approve");
    }
}

async function rejectNews(id) {
    if (!confirm("Reject/Remove this draft?")) return;
    try {
        await fetch(`${API_BASE}/admin/news/${id}/reject`, { method: 'POST' });
    } catch (e) { console.error(e); }
}

async function showNewsOnScreen(id) {
    try {
        await fetch(`${API_BASE}/news/${id}/show`, { method: 'POST' });
    } catch (e) { console.error(e); }
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
    const streamKey = document.getElementById('inpStreamKey').value.trim();
    if (!streamKey) return alert("Please enter a Stream Key");

    // Construct Main RTMP URL (Assumption: YouTube default ingest)
    // Or allow user to override the whole URL? 
    // The previous code assumed passing stream key updates the persistent config or is just used.
    // The Server uses RTMP_URL env var if set, or constructs it?
    // Let's assume user wants to use standard YouTube ingest with this key.
    const rtmpUrl = "rtmp://a.rtmp.youtube.com/live2/" + streamKey;

    const backupUrlInput = document.getElementById('inpBackupUrl').value.trim();
    // If backup URL is provided but doesn't have the key, user might need to append it.
    // Usually Backup URL is rtmp://b.rtmp.youtube.com/live2?backup=1 and key is PART of it or sent as stream name.
    // YouTube Backup URL convention: rtmp://b.rtmp.youtube.com/live2/STREAM_KEY?backup=1
    // The user provided prompt "rtmp://b.rtmp.youtube.com/live2?backup=1" implies they might paste the WHOLE thing.
    // Let's rely on the user pasting the FULL backup URL if they use the field, OR construct it if it looks like a base.

    // Simplest: Send whatever they typed as backup_rtmp_url. 
    // If they typed nothing, send null.
    let backupUrl = null;
    if (backupUrlInput) {
        // If it looks like a base URL (no slash or key), append key?
        // Let's trust the user to paste the full URL including Key or use the provided logic if needed.
        // User Prompt: "rtmp://b.rtmp.youtube.com/live2?backup=1" -> This usually needs the key before ?backup=1
        // Actually YouTube gives: rtmp://b.rtmp.youtube.com/live2
        // And Stream Key: xxxx
        // So we should construct it: rtmp://b.rtmp.youtube.com/live2/STREAM_KEY?backup=1

        if (backupUrlInput.includes('youtube') && !backupUrlInput.includes(streamKey)) {
            // Basic heuristic: if it doesn't contain the key, try to insert it?
            // Safest is to just use what they type IF they type a full RTMP.
            // BUT, if they paste "rtmp://b.rtmp.youtube.com/live2?backup=1", we need to insert key.
            // Let's just pass it raw for now, assuming user knows, or update later if broken.
            // BETTER: Construct it properly if it's the standard YT backup.
            if (backupUrlInput === 'rtmp://b.rtmp.youtube.com/live2?backup=1') {
                backupUrl = "rtmp://b.rtmp.youtube.com/live2/" + streamKey + "?backup=1";
            } else {
                backupUrl = backupUrlInput;
            }
        } else {
            backupUrl = backupUrlInput;
        }
    }

    const payload = {
        rtmp_url: rtmpUrl,
        stream_key: streamKey,
        backup_rtmp_url: backupUrl
    };

    // UI Loading state
    btnStart.innerText = "STARTING...";
    btnStart.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/stream/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
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

// --- Utilities ---
function toggleFullscreen(elemId) {
    const elem = document.getElementById(elemId);
    if (!document.fullscreenElement) {
        elem.requestFullscreen().catch(err => {
            alert(`Error attempting to enable fullscreen: ${err.message}`);
        });
    } else {
        document.exitFullscreen();
    }
}
// --- Ad Management ---

async function fetchAds() {
    try {
        const resCamps = await fetch(`${API_BASE}/ads/campaigns`);
        const camps = await resCamps.json();
        const resItems = await fetch(`${API_BASE}/ads/items`);
        const items = await resItems.json();

        renderAdManager(camps, items);
    } catch (err) {
        console.error("Failed to fetch ads:", err);
    }
}

function renderAdManager(camps, items) {
    const list = document.getElementById('adCampaignList');
    if (!list) return; // Guard clause if element doesn't exist yet

    list.innerHTML = "";

    camps.forEach(camp => {
        const campItems = items.filter(i => i.campaign_id === camp.id);

        const div = document.createElement('div');
        div.className = "ad-campaign-card";
        div.innerHTML = `
            <div class="campaign-header">
                <h3>${camp.name} <span class="badge badge-secondary">${camp.client || 'Internal'}</span></h3>
                <span class="badge ${camp.is_active ? 'badge-success' : 'badge-danger'}">
                    ${camp.is_active ? 'Active' : 'Paused'}
                </span>
            </div>
            <div class="campaign-items">
                ${campItems.map(item => `
                    <div class="ad-item-row">
                        <span class="badge badge-info">${item.type}</span>
                        <span class="ad-content-preview">${item.content}</span>
                        <button class="btn btn-sm btn-danger" onclick="deleteAdItem(${item.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `).join('')}
                <div class="add-item-row">
                    <button class="btn btn-sm btn-outline-primary" onclick="showAddItemModal(${camp.id})">
                        <i class="fas fa-plus"></i> Add Item
                    </button>
                </div>
            </div>
        `;
        list.appendChild(div);
    });
}


async function createCampaign() {
    const name = prompt("Enter Campaign Name:");
    if (!name) return;
    const client = prompt("Enter Client Name (Optional):");

    try {
        await fetch(`${API_BASE}/ads/campaigns`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, client, is_active: true })
        });
        fetchAds();
    } catch (e) { alert("Failed to create campaign"); }
}

async function createAdItem(campId, type, content) {
    try {
        await fetch(`${API_BASE}/ads/items`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                campaign_id: campId,
                type: type,
                content: content,
                is_active: true
            })
        });
        fetchAds();
    } catch (e) { alert("Failed to create ad item"); }
}

async function deleteAdItem(id) {
    if (!confirm("Delete this ad?")) return;
    try {
        await fetch(`${API_BASE}/ads/items/${id}`, { method: 'DELETE' });
        fetchAds();
    } catch (e) { console.error(e); }
}


function showAddItemModal(campId) {
    // Simple prompt for now, or dedicated modal
    const type = prompt("Enter Type (TICKER, L_BAR, FULLSCREEN):", "TICKER");
    if (!type) return;

    let content = "";
    if (type === 'TICKER') {
        content = prompt("Enter Ad Text:");
    } else {
        content = prompt("Enter Media URL (or upload first and paste /media/...):");
    }

    if (content) createAdItem(campId, type, content);
}

// --- Schedule Management ---

const programModal = document.getElementById('programModal');

async function fetchSchedule() {
    const el = document.getElementById('scheduleList');
    el.innerHTML = '<tr><td colspan="5" class="text-center p-4 text-gray-400">Loading schedule...</td></tr>';

    try {
        const res = await fetch(`${API_BASE}/programs`);
        const items = await res.json();
        renderSchedule(items);
    } catch (e) {
        console.error(e);
        el.innerHTML = '<tr><td colspan="5" class="text-center p-4 text-red-400">Error loading schedule</td></tr>';
    }
}

function renderSchedule(items) {
    const el = document.getElementById('scheduleList');
    el.innerHTML = "";

    if (items.length === 0) {
        el.innerHTML = '<tr><td colspan="5" class="text-center p-4 text-gray-400">No scheduled programs.</td></tr>';
        return;
    }

    const now = new Date();

    items.forEach(p => {
        const start = new Date(p.start_time);
        const end = new Date(p.end_time);

        let status = '<span class="px-2 py-1 rounded bg-gray-100 text-gray-500 text-xs font-bold">UPCOMING</span>';
        if (now >= start && now <= end) {
            status = '<span class="px-2 py-1 rounded bg-green-100 text-green-600 text-xs font-bold animate-pulse">ON AIR</span>';
        } else if (now > end) {
            status = '<span class="px-2 py-1 rounded bg-gray-100 text-gray-400 text-xs font-bold">ENDED</span>';
        }

        const tr = document.createElement('tr');
        tr.className = "border-b hover:bg-slate-50";
        tr.innerHTML = `
            <td class="p-3">${start.toLocaleString()}</td>
            <td class="p-3">${end.toLocaleString()}</td>
            <td class="p-3 font-bold text-slate-700">${p.title}</td>
            <td class="p-3">${status}</td>
            <td class="p-3 text-right">
                <button onclick="deleteProgram(${p.id})" class="text-red-400 hover:text-red-600">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        el.appendChild(tr);
    });
}

function openProgramModal() {
    programModal.classList.remove('hidden');
    // Set default times (next hour)
    const now = new Date();
    now.setMinutes(0, 0, 0); // round to hour
    now.setHours(now.getHours() + 1);

    // Format for datetime-local (YYYY-MM-DDTHH:mm)
    const fmt = (d) => {
        const offset = d.getTimezoneOffset() * 60000;
        return new Date(d.getTime() - offset).toISOString().slice(0, 16);
    }

    document.getElementById('progStart').value = fmt(now);

    const end = new Date(now);
    end.setHours(end.getHours() + 1);
    document.getElementById('progEnd').value = fmt(end);
}

function closeProgramModal() {
    programModal.classList.add('hidden');
}

async function submitProgram() {
    const title = document.getElementById('progTitle').value.trim();
    if (!title) return alert("Enter a title");

    const start = document.getElementById('progStart').value;
    const end = document.getElementById('progEnd').value;

    if (!start || !end) return alert("Enter start and end times");

    // File Handling
    const file = document.getElementById('progFile').files[0];
    let videoPath = document.getElementById('progVideoPath').value.trim();

    if (!file && !videoPath) return alert("Please select a video file or enter a path/URL");

    // If file selected, upload it first
    if (file) {
        // Change button state
        const btn = document.querySelector('#programModal button.bg-blue-600');
        const originalText = btn.innerText;
        btn.innerText = "Uploading...";
        btn.disabled = true;

        try {
            const formData = new FormData();
            formData.append("file", file);
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (data.url) {
                videoPath = data.url; // Relative URL e.g. /media/video.mp4
            } else {
                throw new Error("Upload failed");
            }

        } catch (e) {
            console.error(e);
            alert("Upload failed: " + e.message);
            btn.innerText = originalText;
            btn.disabled = false;
            return;
        }
    }

    if (videoPath.startsWith('/media/')) {
        videoPath = videoPath.substring(1); // Remove leading slash -> "media/foo.mp4"
    }

    const payload = {
        title: title,
        video_path: videoPath,
        start_time: new Date(start).toISOString(),
        end_time: new Date(end).toISOString(),
        is_active: true
    };

    try {
        const res = await fetch(`${API_BASE}/programs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            closeProgramModal();
            fetchSchedule();
            alert("Program Scheduled!");
        } else {
            const err = await res.json();
            alert("Error: " + err.detail);
        }
    } catch (e) {
        console.error(e);
        alert("Failed to save program");
    } finally {
        // Reset button
        const btn = document.querySelector('#programModal button.bg-blue-600');
        if (btn) {
            btn.innerText = "Save Program";
            btn.disabled = false;
        }
    }
}

async function deleteProgram(id) {
    if (!confirm("Are you sure you want to delete this program?")) return;
    try {
        await fetch(`${API_BASE}/programs/${id}`, { method: 'DELETE' });
        fetchSchedule();
    } catch (e) { console.error(e); }
}

 
 / /   - - -   S c h e d u l e   M a n a g e m e n t   - - - 
 
 c o n s t   p r o g r a m M o d a l   =   d o c u m e n t . g e t E l e m e n t B y I d ( ' p r o g r a m M o d a l ' ) ; 
 
 
 
 a s y n c   f u n c t i o n   f e t c h S c h e d u l e ( )   { 
 
         c o n s t   e l   =   d o c u m e n t . g e t E l e m e n t B y I d ( ' s c h e d u l e L i s t ' ) ; 
 
         e l . i n n e r H T M L   =   ' < t r > < t d   c o l s p a n = " 5 "   c l a s s = " t e x t - c e n t e r   p - 4   t e x t - g r a y - 4 0 0 " > L o a d i n g   s c h e d u l e . . . < / t d > < / t r > ' ; 
 
         
 
         t r y   { 
 
                 c o n s t   r e s   =   a w a i t   f e t c h ( ` $ { A P I _ B A S E } / p r o g r a m s ` ) ; 
 
                 c o n s t   i t e m s   =   a w a i t   r e s . j s o n ( ) ; 
 
                 r e n d e r S c h e d u l e ( i t e m s ) ; 
 
         
    }   c a t c h   ( e )   { 
 
                 c o n s o l e . e r r o r ( e ) ; 
 
                 e l . i n n e r H T M L   =   ' < t r > < t d   c o l s p a n = " 5 "   c l a s s = " t e x t - c e n t e r   p - 4   t e x t - r e d - 4 0 0 " > E r r o r   l o a d i n g   s c h e d u l e < / t d > < / t r > ' ; 
 
         
    } 
 
 
} 
 
 
 
 f u n c t i o n   r e n d e r S c h e d u l e ( i t e m s )   { 
 
         c o n s t   e l   =   d o c u m e n t . g e t E l e m e n t B y I d ( ' s c h e d u l e L i s t ' ) ; 
 
         e l . i n n e r H T M L   =   " " ; 
 
         
 
         i f   ( i t e m s . l e n g t h   = = =   0 )   { 
 
                 e l . i n n e r H T M L   =   ' < t r > < t d   c o l s p a n = " 5 "   c l a s s = " t e x t - c e n t e r   p - 4   t e x t - g r a y - 4 0 0 " > N o   s c h e d u l e d   p r o g r a m s . < / t d > < / t r > ' ; 
 
                 r e t u r n ; 
 
         
    } 
 
 
 
         c o n s t   n o w   =   n e w   D a t e ( ) ; 
 
 
 
         i t e m s . f o r E a c h ( p   = >   { 
 
                 c o n s t   s t a r t   =   n e w   D a t e ( p . s t a r t _ t i m e ) ; 
 
                 c o n s t   e n d   =   n e w   D a t e ( p . e n d _ t i m e ) ; 
 
                 
 
                 l e t   s t a t u s   =   ' < s p a n   c l a s s = " p x - 2   p y - 1   r o u n d e d   b g - g r a y - 1 0 0   t e x t - g r a y - 5 0 0   t e x t - x s   f o n t - b o l d " > U P C O M I N G < / s p a n > ' ; 
 
                 i f   ( n o w   > =   s t a r t   & &   n o w   < =   e n d )   { 
 
                         s t a t u s   =   ' < s p a n   c l a s s = " p x - 2   p y - 1   r o u n d e d   b g - g r e e n - 1 0 0   t e x t - g r e e n - 6 0 0   t e x t - x s   f o n t - b o l d   a n i m a t e - p u l s e " > O N   A I R < / s p a n > ' ; 
 
                 
        }   e l s e   i f   ( n o w   >   e n d )   { 
 
                         s t a t u s   =   ' < s p a n   c l a s s = " p x - 2   p y - 1   r o u n d e d   b g - g r a y - 1 0 0   t e x t - g r a y - 4 0 0   t e x t - x s   f o n t - b o l d " > E N D E D < / s p a n > ' ; 
 
                 
        } 
 
 
 
                 c o n s t   t r   =   d o c u m e n t . c r e a t e E l e m e n t ( ' t r ' ) ; 
 
                 t r . c l a s s N a m e   =   " b o r d e r - b   h o v e r : b g - s l a t e - 5 0 " ; 
 
                 t r . i n n e r H T M L   =   ` 
 
                         < t d   c l a s s = " p - 3 " > $ { s t a r t . t o L o c a l e S t r i n g ( ) } < / t d > 
 
                         < t d   c l a s s = " p - 3 " > $ { e n d . t o L o c a l e S t r i n g ( ) } < / t d > 
 
                         < t d   c l a s s = " p - 3   f o n t - b o l d   t e x t - s l a t e - 7 0 0 " > $ { p . t i t l e } < / t d > 
 
                         < t d   c l a s s = " p - 3 " > $ { s t a t u s } < / t d > 
 
                         < t d   c l a s s = " p - 3   t e x t - r i g h t " > 
 
                                 < b u t t o n   o n c l i c k = " d e l e t e P r o g r a m ( $ { p . i d } ) "   c l a s s = " t e x t - r e d - 4 0 0   h o v e r : t e x t - r e d - 6 0 0 " > 
 
                                         < i   c l a s s = " f a s   f a - t r a s h " > < / i > 
 
                                 < / b u t t o n > 
 
                         < / t d > 
 
                 ` ; 
 
                 e l . a p p e n d C h i l d ( t r ) ; 
 
         
    } ) ; 
 
 
} 
 
 
 
 f u n c t i o n   o p e n P r o g r a m M o d a l ( )   { 
 
         p r o g r a m M o d a l . c l a s s L i s t . r e m o v e ( ' h i d d e n ' ) ; 
 
         / /   S e t   d e f a u l t   t i m e s   ( n e x t   h o u r ) 
 
         c o n s t   n o w   =   n e w   D a t e ( ) ; 
 
         n o w . s e t M i n u t e s ( 0 ,   0 ,   0 ) ;   / /   r o u n d   t o   h o u r 
 
         n o w . s e t H o u r s ( n o w . g e t H o u r s ( )   +   1 ) ; 
 
         
 
         / /   F o r m a t   f o r   d a t e t i m e - l o c a l   ( Y Y Y Y - M M - D D T H H : m m ) 
 
         c o n s t   f m t   =   ( d )   = >   { 
 
                 c o n s t   o f f s e t   =   d . g e t T i m e z o n e O f f s e t ( )   *   6 0 0 0 0 ; 
 
                 r e t u r n   n e w   D a t e ( d . g e t T i m e ( )   -   o f f s e t ) . t o I S O S t r i n g ( ) . s l i c e ( 0 ,   1 6 ) ; 
 
         
    } 
 
 
 
         d o c u m e n t . g e t E l e m e n t B y I d ( ' p r o g S t a r t ' ) . v a l u e   =   f m t ( n o w ) ; 
 
         
 
         c o n s t   e n d   =   n e w   D a t e ( n o w ) ; 
 
         e n d . s e t H o u r s ( e n d . g e t H o u r s ( )   +   1 ) ; 
 
         d o c u m e n t . g e t E l e m e n t B y I d ( ' p r o g E n d ' ) . v a l u e   =   f m t ( e n d ) ; 
 
 
} 
 
 
 
 f u n c t i o n   c l o s e P r o g r a m M o d a l ( )   { 
 
         p r o g r a m M o d a l . c l a s s L i s t . a d d ( ' h i d d e n ' ) ; 
 
 
} 
 
 
 
 a s y n c   f u n c t i o n   s u b m i t P r o g r a m ( )   { 
 
         c o n s t   t i t l e   =   d o c u m e n t . g e t E l e m e n t B y I d ( ' p r o g T i t l e ' ) . v a l u e . t r i m ( ) ; 
 
         i f   ( ! t i t l e )   r e t u r n   a l e r t ( " E n t e r   a   t i t l e " ) ; 
 
 
 
         c o n s t   s t a r t   =   d o c u m e n t . g e t E l e m e n t B y I d ( ' p r o g S t a r t ' ) . v a l u e ; 
 
         c o n s t   e n d   =   d o c u m e n t . g e t E l e m e n t B y I d ( ' p r o g E n d ' ) . v a l u e ; 
 
         
 
         i f   ( ! s t a r t   | |   ! e n d )   r e t u r n   a l e r t ( " E n t e r   s t a r t   a n d   e n d   t i m e s " ) ; 
 
 
 
         / /   F i l e   H a n d l i n g 
 
         c o n s t   f i l e   =   d o c u m e n t . g e t E l e m e n t B y I d ( ' p r o g F i l e ' ) . f i l e s [ 0 ] ; 
 
         l e t   v i d e o P a t h   =   d o c u m e n t . g e t E l e m e n t B y I d ( ' p r o g V i d e o P a t h ' ) . v a l u e . t r i m ( ) ; 
 
 
 
         i f   ( ! f i l e   & &   ! v i d e o P a t h )   r e t u r n   a l e r t ( " P l e a s e   s e l e c t   a   v i d e o   f i l e   o r   e n t e r   a   p a t h / U R L " ) ; 
 
 
 
         / /   I f   f i l e   s e l e c t e d ,   u p l o a d   i t   f i r s t 
 
         i f   ( f i l e )   { 
 
                 / /   C h a n g e   b u t t o n   s t a t e 
 
                 c o n s t   b t n   =   d o c u m e n t . q u e r y S e l e c t o r ( ' # p r o g r a m M o d a l   b u t t o n . b g - b l u e - 6 0 0 ' ) ; 
 
                 c o n s t   o r i g i n a l T e x t   =   b t n . i n n e r T e x t ; 
 
                 b t n . i n n e r T e x t   =   " U p l o a d i n g . . . " ; 
 
                 b t n . d i s a b l e d   =   t r u e ; 
 
 
 
                 t r y   { 
 
                         c o n s t   f o r m D a t a   =   n e w   F o r m D a t a ( ) ; 
 
                         f o r m D a t a . a p p e n d ( " f i l e " ,   f i l e ) ; 
 
                         c o n s t   r e s   =   a w a i t   f e t c h ( ' / a p i / u p l o a d ' ,   { 
 
                                 m e t h o d :   ' P O S T ' , 
 
                                 b o d y :   f o r m D a t a 
 
                         
            } ) ; 
 
                         c o n s t   d a t a   =   a w a i t   r e s . j s o n ( ) ; 
 
                         i f   ( d a t a . u r l )   { 
 
                                 v i d e o P a t h   =   d a t a . u r l ;   / /   R e l a t i v e   U R L   e . g .   / m e d i a / v i d e o . m p 4 
 
                         
            }   e l s e   { 
 
                                 t h r o w   n e w   E r r o r ( " U p l o a d   f a i l e d " ) ; 
 
                         
            } 
 
                 
        }   c a t c h   ( e )   { 
 
                         c o n s o l e . e r r o r ( e ) ; 
 
                         a l e r t ( " U p l o a d   f a i l e d :   "   +   e . m e s s a g e ) ; 
 
                         b t n . i n n e r T e x t   =   o r i g i n a l T e x t ; 
 
                         b t n . d i s a b l e d   =   f a l s e ; 
 
                         r e t u r n ; 
 
                 
        } 
 
         
    } 
 
 
 
         / /   D e t e r m i n e   a b s o l u t e   p a t h   f o r   b a c k e n d   i f   i t   l o o k s   l i k e   a   l o c a l   m e d i a   f i l e 
 
         / /   T h e   b a c k e n d   s t o r e s   " v i d e o _ p a t h " .   
 
         / /   I f   i t   s t a r t s   w i t h   / m e d i a / ,   t h e   b a c k e n d   n e e d s   t o   k n o w   h o w   t o   r e s o l v e   i t   o r   m a i n . p y   n e e d s   t o   h a n d l e   i t . 
 
         / /   m a i n . p y   w o r k s   w i t h   a b s o l u t e   p a t h s   o r   U R L s . 
 
         / /   I f   w e   s e n d   " / m e d i a / f o o . m p 4 " ,   m a i n . p y   m i g h t   n o t   f i n d   i t   i f   c h e c k i n g   c w d . 
 
         / /   L e t ' s   a s s u m e   s e r v e r . p y   o r   m a i n . p y   h a n d l e s   " / m e d i a / "   p r e f i x   o r   w e   m a k e   i t   a b s o l u t e   h e r e . 
 
         / /   A c t u a l l y ,   ` u p l o a d _ f i l e `   s a v e s   t o   ` m e d i a / f i l e n a m e ` . 
 
         / /   S o   i f   w e   s e n d   " m e d i a / f i l e n a m e " ,   m a i n . p y   c a n   f i n d   i t   i f   C W D   i s   p r o j e c t   r o o t . 
 
         
 
         i f   ( v i d e o P a t h . s t a r t s W i t h ( ' / m e d i a / ' ) )   { 
 
                 v i d e o P a t h   =   v i d e o P a t h . s u b s t r i n g ( 1 ) ;   / /   R e m o v e   l e a d i n g   s l a s h   - >   " m e d i a / f o o . m p 4 " 
 
         
    } 
 
 
 
         c o n s t   p a y l o a d   =   { 
 
                 t i t l e :   t i t l e , 
 
                 v i d e o _ p a t h :   v i d e o P a t h , 
 
                 s t a r t _ t i m e :   n e w   D a t e ( s t a r t ) . t o I S O S t r i n g ( ) , 
 
                 e n d _ t i m e :   n e w   D a t e ( e n d ) . t o I S O S t r i n g ( ) , 
 
                 i s _ a c t i v e :   t r u e 
 
         
    } ; 
 
 
 
         t r y   { 
 
                 c o n s t   r e s   =   a w a i t   f e t c h ( ` $ { A P I _ B A S E } / p r o g r a m s ` ,   { 
 
                         m e t h o d :   ' P O S T ' , 
 
                         h e a d e r s :   {   ' C o n t e n t - T y p e ' :   ' a p p l i c a t i o n / j s o n '    } , 
 
                         b o d y :   J S O N . s t r i n g i f y ( p a y l o a d ) 
 
                 
        } ) ; 
 
                 
 
                 i f   ( r e s . o k )   { 
 
                         c l o s e P r o g r a m M o d a l ( ) ; 
 
                         f e t c h S c h e d u l e ( ) ; 
 
                         a l e r t ( " P r o g r a m   S c h e d u l e d ! " ) ; 
 
                 
        }   e l s e   { 
 
                         c o n s t   e r r   =   a w a i t   r e s . j s o n ( ) ; 
 
                         a l e r t ( " E r r o r :   "   +   e r r . d e t a i l ) ; 
 
                 
        } 
 
         
    }   c a t c h   ( e )   { 
 
                 c o n s o l e . e r r o r ( e ) ; 
 
                 a l e r t ( " F a i l e d   t o   s a v e   p r o g r a m " ) ; 
 
         
    }   f i n a l l y   { 
 
                 / /   R e s e t   b u t t o n 
 
                 c o n s t   b t n   =   d o c u m e n t . q u e r y S e l e c t o r ( ' # p r o g r a m M o d a l   b u t t o n . b g - b l u e - 6 0 0 ' ) ; 
 
                 i f   ( b t n )   { 
 
                         b t n . i n n e r T e x t   =   " S a v e   P r o g r a m " ; 
 
                         b t n . d i s a b l e d   =   f a l s e ; 
 
                 
        } 
 
         
    } 
 
 
} 
 
 
 
 a s y n c   f u n c t i o n   d e l e t e P r o g r a m ( i d )   { 
 
         i f   ( ! c o n f i r m ( " A r e   y o u   s u r e   y o u   w a n t   t o   d e l e t e   t h i s   p r o g r a m ? " ) )   r e t u r n ; 
 
         t r y   { 
 
                 a w a i t   f e t c h ( ` $ { A P I _ B A S E } / p r o g r a m s / $ { i d } ` ,   {   m e t h o d :   ' D E L E T E '    } ) ; 
 
                 f e t c h S c h e d u l e ( ) ; 
 
         
    }   c a t c h   ( e )   {   c o n s o l e . e r r o r ( e ) ;    } 
 
 
} 
 
 