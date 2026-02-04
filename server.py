import os
import subprocess
import signal
import json
import sys
import threading
import queue
import asyncio
from typing import Optional, List
from fastapi import FastAPI, UploadFile, Form, WebSocket, WebSocketDisconnect, Depends, HTTPException, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Import our new database module
import database
from database import NewsItem, SystemConfig, NewsType, NewsCategory, get_db

app = FastAPI()

# Log Management
log_queue = queue.Queue()
connected_websockets: List[WebSocket] = []
news_websockets: List[WebSocket] = [] # New list for news updates

def log_reader(proc):
    """Reads stdout from the subprocess and pushes to the log queue."""
    for line in iter(proc.stdout.readline, b''):
        decoded_line = line.decode('utf-8').strip()
        if decoded_line:
            print(f"[STREAM] {decoded_line}")  # Also print to server console
            log_queue.put(decoded_line)
    proc.stdout.close()

async def broadcast_logs():
    """Background task to broadcast logs to all connected websockets."""
    while True:
        try:
            try:
                log_line = log_queue.get_nowait()
                msg = json.dumps({"log": log_line})
                to_remove = []
                for ws in connected_websockets:
                    try:
                        await ws.send_text(msg)
                    except Exception:
                        to_remove.append(ws)
                
                for ws in to_remove:
                    if ws in connected_websockets:
                        connected_websockets.remove(ws)
            except queue.Empty:
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Error in broadcast loop: {e}")
            await asyncio.sleep(1)

# Broadcast helper for news
async def broadcast_news_update(type: str, data: dict):
    payload = json.dumps({"type": type, "payload": data})
    to_remove = []
    for ws in news_websockets:
        try:
            await ws.send_text(payload)
        except Exception:
            to_remove.append(ws)
    for ws in to_remove:
        news_websockets.remove(ws)

@app.on_event("startup")
async def startup_event():
    # Initialize DB
    database.init_db()
    asyncio.create_task(broadcast_logs())

# WebSocket for Logs
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)

# WebSocket for News Updates (Real-time Overlay)
@app.websocket("/ws/news")
async def news_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    news_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in news_websockets:
            news_websockets.remove(websocket)

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

# Ensure overlay data file exists (Legacy support)
if not os.path.exists(OVERLAY_FILE):
    with open(OVERLAY_FILE, "w") as f:
         json.dump({
            "title": "Live Stream", 
            "subtitle": "Welcome!", 
            "info": "Starting soon...", 
            "webview_url": "",
            "stream_key": ""
        }, f)

# Mount static files for UI (and eventually Admin)
if not os.path.exists("ui"):
    os.makedirs("ui")
app.mount("/static", StaticFiles(directory="ui"), name="static")

if not os.path.exists("media"):
    os.makedirs("media")
app.mount("/media", StaticFiles(directory="media"), name="media")

# --- Media API ---
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        file_location = f"media/{file.filename}"
        with open(file_location, "wb+") as f:
            f.write(file.file.read())
        return {"info": f"file '{file.filename}' saved at '{file_location}'", "url": f"/media/{file.filename}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/media")
def list_media():
    files = []
    if os.path.exists("media"):
        for f in os.listdir("media"):
            files.append({"name": f, "url": f"/media/{f}"})
    return files

class OverlayUpdate(BaseModel):
    webview_url: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    info: Optional[str] = None
    hide_overlays: Optional[bool] = None

@app.post("/api/overlay/update")
def update_overlay(data: OverlayUpdate):
    if os.path.exists(OVERLAY_FILE):
        with open(OVERLAY_FILE, "r") as f:
            try:
                current_data = json.load(f)
            except:
                current_data = {}
    else:
        current_data = {}
    
    if data.webview_url is not None: current_data["webview_url"] = data.webview_url
    # Only update what's passed
    
    with open(OVERLAY_FILE, "w") as f:
        json.dump(current_data, f)
    
    return current_data

# --- Pydantic Models for News API ---
class NewsCreate(BaseModel):
    title_tamil: str
    title_english: Optional[str] = None
    type: str = "TICKER" # BREAKING, TICKER, etc
    category: str = "GENERAL"
    location: Optional[str] = None
    is_active: bool = True
    priority: int = 0

class NewsUpdate(BaseModel):
    title_tamil: Optional[str] = None
    title_english: Optional[str] = None
    type: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None

# --- API Endpoints ---

@app.get("/")
def read_root():
    return FileResponse("ui/index.html")

@app.get("/admin")
def read_admin():
    # Ensure directory exists just in case
    if not os.path.exists("ui/admin/index.html"):
        return JSONResponse(status_code=404, content={"error": "Admin UI not found. Please create ui/admin/index.html"})
    return FileResponse("ui/admin/index.html")

@app.get("/overlay")
def get_overlay_page():
    return FileResponse("overlay.html")

# Legacy Overlay Endpoint
@app.get("/overlay/data")
def get_overlay_data():
    if os.path.exists(OVERLAY_FILE):
        with open(OVERLAY_FILE, "r") as f:
            return json.load(f)
    return {}

# --- News Management API ---

@app.get("/api/news")
def get_news(db: Session = Depends(get_db)):
    # Return all active news sorted by priority and date
    items = db.query(NewsItem).filter(NewsItem.is_active == True).order_by(NewsItem.priority.desc(), NewsItem.created_at.desc()).all()
    return items

@app.post("/api/news")
async def create_news(item: NewsCreate, db: Session = Depends(get_db)):
    db_item = NewsItem(
        title_tamil=item.title_tamil,
        title_english=item.title_english,
        type=item.type,
        category=item.category,
        location=item.location,
        is_active=item.is_active,
        priority=item.priority
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    
    # Notify Overlay via WebSocket
    await broadcast_news_update("NEWS_ADDED", {"id": db_item.id, "title": db_item.title_tamil, "type": db_item.type})
    
    return db_item

@app.put("/api/news/{news_id}")
async def update_news(news_id: int, item: NewsUpdate, db: Session = Depends(get_db)):
    db_item = db.query(NewsItem).filter(NewsItem.id == news_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="News item not found")
    
    if item.title_tamil is not None: db_item.title_tamil = item.title_tamil
    if item.is_active is not None: db_item.is_active = item.is_active
    # ... handle other fields
    
    db.commit()
    db.refresh(db_item)
    
    await broadcast_news_update("NEWS_UPDATED", {"id": db_item.id, "active": db_item.is_active})
    return db_item

@app.delete("/api/news/{news_id}")
async def delete_news(news_id: int, db: Session = Depends(get_db)):
    db_item = db.query(NewsItem).filter(NewsItem.id == news_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="News item not found")
    
    db.delete(db_item)
    db.commit()
    
    await broadcast_news_update("NEWS_DELETED", {"id": news_id})
    return {"status": "success"}

# --- Stream Control API ---
class StreamConfig(BaseModel):
    rtmp_url: Optional[str] = None
    stream_key: Optional[str] = None

@app.post("/api/stream/start")
def start_stream(config: StreamConfig):
    global stream_process
    
    # Persist the stream key if provided
    if config.stream_key:
        if os.path.exists(OVERLAY_FILE):
            with open(OVERLAY_FILE, "r") as f:
                try:
                    data = json.load(f)
                except:
                    data = {}
            
            data["stream_key"] = config.stream_key
            
            with open(OVERLAY_FILE, "w") as f:
                json.dump(data, f)
    
    if stream_process and stream_process.poll() is None:
        return {"status": "already_running"}
    
    env = os.environ.copy()
    env["OVERLAY_URL"] = "http://127.0.0.1:8123/overlay"
    
    if config.rtmp_url:
        env["RTMP_URL"] = config.rtmp_url
    
    try:
        stream_process = subprocess.Popen(
            [sys.executable, "-u", "main.py"], 
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1
        )
        
        t = threading.Thread(target=log_reader, args=(stream_process,), daemon=True)
        t.start()
        
        return {"status": "started", "pid": stream_process.pid}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/stream/stop")
def stop_stream():
    global stream_process
    if stream_process:
        if stream_process.poll() is None:
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
