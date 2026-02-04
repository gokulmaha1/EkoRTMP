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
const inpWebviewUrl = document.getElementById('inpWebviewUrl');
const inpFile = document.getElementById('inpFile');
const uploadStatus = document.getElementById('uploadStatus');

// Init
document.addEventListener('DOMContentLoaded', () => {
    fetchNews();
    connectWebSocket();
});

// --- Media & Screen ---

async function updateMainScreen() {
    const url = inpWebviewUrl.value.trim();
    if (!url) return;

    try {
        await fetch('/api/overlay/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ webview_url: url })
        });
        alert("Main screen updated!");
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
        }
    } catch (e) {
        console.error("Upload error", e);
        alert("Upload failed");
    }
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

// --- WebSocket ---

function connectWebSocket() {
    const ws = new WebSocket(WS_URL);

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        console.log("WS Update:", msg);
        // On any update, just re-fetch the list for simplicity (for now)
        // Optimization: Handle payload types to update local state without fetch
        fetchNews();
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
        const cardClass = isBreaking ? 'border-l-4 border-red-500 bg-red-50' : 'bg-gray-50 border-l-4 border-gray-300';

        const html = `
            <div class="p-3 rounded shadow-sm flex justify-between items-center ${cardClass}">
                <div class="flex-1">
                    <span class="text-xs font-bold uppercase ${isBreaking ? 'text-red-600' : 'text-gray-500'}">
                        ${item.type} • ${item.category}
                    </span>
                    <h4 class="font-bold text-lg text-slate-800">${item.title_tamil}</h4>
                    <p class="text-xs text-gray-400">ID: ${item.id} • ${new Date(item.created_at).toLocaleTimeString()}</p>
                </div>
                <div class="flex space-x-2 ml-4">
                    <button onclick="toggleActive(${item.id}, ${item.is_active})" class="w-8 h-8 rounded-full flex items-center justify-center ${item.is_active ? 'bg-green-100 text-green-600 hover:bg-green-200' : 'bg-gray-200 text-gray-400'}">
                        <i class="fas fa-power-off"></i>
                    </button>
                    <button onclick="deleteNews(${item.id})" class="w-8 h-8 rounded-full bg-red-100 text-red-600 hover:bg-red-200 flex items-center justify-center">
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
