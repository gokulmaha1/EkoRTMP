import os
import subprocess
import signal
import json
import sys
from fastapi import FastAPI, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
stream_process = None
OVERLAY_FILE = "overlay_data.json"

# Ensure overlay data file exists
if not os.path.exists(OVERLAY_FILE):
    with open(OVERLAY_FILE, "w") as f:
        json.dump({"title": "Live Stream", "subtitle": "Welcome!", "info": "Starting soon...", "webview_url": ""}, f)

# Mount static files for UI
# We will create a 'ui' directory for the frontend
if not os.path.exists("ui"):
    os.makedirs("ui")
app.mount("/static", StaticFiles(directory="ui"), name="static")

class OverlayUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    info: Optional[str] = None
    webview_url: Optional[str] = None

@app.get("/")
def read_root():
    return FileResponse("ui/index.html")

@app.get("/overlay")
def get_overlay_page():
    # Serve the overlay.html but potentially we can template it here if needed.
    # For now, we serve the static file, but the file itself will fetch /overlay/data
    return FileResponse("overlay.html")

@app.get("/overlay/data")
def get_overlay_data():
    if os.path.exists(OVERLAY_FILE):
        with open(OVERLAY_FILE, "r") as f:
            return json.load(f)
    return {}

@app.post("/api/overlay")
def update_overlay(data: OverlayUpdate):
    current_data = {}
    if os.path.exists(OVERLAY_FILE):
        with open(OVERLAY_FILE, "r") as f:
            try:
                current_data = json.load(f)
            except json.JSONDecodeError:
                pass
    
    # Update fields
    if data.title is not None: current_data["title"] = data.title
    if data.subtitle is not None: current_data["subtitle"] = data.subtitle
    if data.info is not None: current_data["info"] = data.info
    if data.webview_url is not None: current_data["webview_url"] = data.webview_url

    with open(OVERLAY_FILE, "w") as f:
        json.dump(current_data, f)
    
    return {"status": "updated", "data": current_data}

class StreamConfig(BaseModel):
    rtmp_url: Optional[str] = None

@app.post("/api/stream/start")
def start_stream(config: StreamConfig):
    global stream_process
    if stream_process and stream_process.poll() is None:
        return {"status": "already_running"}
    
    # Run main.py using the same python interpreter
    # We set an env var so main.py knows it's being run from server if needed, 
    # but more importantly we need to make sure main.py requests the overlay from THIS server.
    env = os.environ.copy()
    env["OVERLAY_URL"] = "http://127.0.0.1:8000/overlay"
    
    if config.rtmp_url:
        env["RTMP_URL"] = config.rtmp_url
    
    try:
        # Popen is non-blocking
        stream_process = subprocess.Popen([sys.executable, "main.py"], env=env)
        return {"status": "started", "pid": stream_process.pid}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/stream/stop")
def stop_stream():
    global stream_process
    if stream_process:
        if stream_process.poll() is None:
            # Try polite terminate first
            stream_process.terminate()
            try:
                stream_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                stream_process.kill()
        
        stream_process = None
        return {"status": "stopped"}
    return {"status": "not_running"}

@app.get("/api/stream/status")
def get_status():
    global stream_process
    is_running = stream_process is not None and stream_process.poll() is None
    return {"running": is_running}
