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
# Global state
stream_process = None
OVERLAY_FILE = os.path.abspath("overlay_data.json")

# Ensure overlay data file exists (Legacy support)
def init_overlay_file():
    if not os.path.exists(OVERLAY_FILE):
        with open(OVERLAY_FILE, "w") as f:
             json.dump({
                "title": "Live Stream", 
                "subtitle": "Welcome!", 
                "info": "Starting soon...", 
                "webview_url": "",
                "stream_key": ""
            }, f)

init_overlay_file()

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
        # Sanitize filename
        clean_name = re.sub(r'[^\w\.-]', '_', file.filename)
        file_location = f"media/{clean_name}"
        
        with open(file_location, "wb+") as f:
            f.write(file.file.read())
            
        return {"info": f"File saved", "url": f"/media/{clean_name}"}
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
    try:
        if os.path.exists(OVERLAY_FILE):
            with open(OVERLAY_FILE, "r") as f:
                current_data = json.load(f)
        else:
            current_data = {}
        
        if data.webview_url is not None: current_data["webview_url"] = data.webview_url
        if data.title is not None: current_data["title"] = data.title
        if data.subtitle is not None: current_data["subtitle"] = data.subtitle
        
        with open(OVERLAY_FILE, "w") as f:
            json.dump(current_data, f)
        
        return current_data
    except Exception as e:
        print(f"Error updating overlay: {e}")
        return {"status": "error"}

# --- Layout Config API ---
class ConfigUpdate(BaseModel):
    brand_color_primary: Optional[str] = None # e.g. #c0392b
    brand_color_secondary: Optional[str] = None # e.g. #f1c40f
    brand_color_dark: Optional[str] = None # e.g. #2c3e50
    logo_url: Optional[str] = None
    ticker_speed: Optional[int] = None # 10-100 (seconds)
    # Text Labels
    default_headline: Optional[str] = None
    ticker_label: Optional[str] = None
    breaking_label: Optional[str] = None
    live_label: Optional[str] = None
    # L-Bar Layout
    layout_mode: Optional[str] = None # FULL, L_BAR
    lbar_position: Optional[str] = None # LEFT, RIGHT
    lbar_width: Optional[int] = None # Percentage 15-40
    lbar_bg_color: Optional[str] = None
    lbar_bg_image: Optional[str] = None
    lbar_content_type: Optional[str] = None # IMAGE, URL, HTML
    lbar_content_data: Optional[str] = None

@app.get("/api/config")
def get_config(db: Session = Depends(get_db)):
    # Helper to get value or default
    def get_val(key, default):
        item = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        return item.value if item else default

    return {
        "brand_color_primary": get_val("brand_color_primary", "#c0392b"),
        "brand_color_secondary": get_val("brand_color_secondary", "#f1c40f"),
        "brand_color_dark": get_val("brand_color_dark", "#2c3e50"),
        "logo_url": get_val("logo_url", "/media/logo.gif"),
        "ticker_speed": int(get_val("ticker_speed", "30")),
        "default_headline": get_val("default_headline", "Welcome to EKO Professional News System..."),
        "ticker_label": get_val("ticker_label", "NEWS UPDATES"),
        "breaking_label": get_val("breaking_label", "BREAKING"),
        "live_label": get_val("live_label", "LIVE"),
        # L-Bar Defaults
        "layout_mode": get_val("layout_mode", "FULL"),
        "lbar_position": get_val("lbar_position", "RIGHT"),
        "lbar_width": int(get_val("lbar_width", "25")),
        "lbar_bg_color": get_val("lbar_bg_color", "#000000"),
        "lbar_bg_image": get_val("lbar_bg_image", ""),
        "lbar_content_type": get_val("lbar_content_type", "IMAGE"),
        "lbar_content_data": get_val("lbar_content_data", "")
    }

@app.post("/api/config")
async def update_config(conf: ConfigUpdate, db: Session = Depends(get_db)):
    def set_val(key, val):
        if val is None: return
        item = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if not item:
            item = SystemConfig(key=key, value=str(val))
            db.add(item)
        else:
            item.value = str(val)
    
    set_val("brand_color_primary", conf.brand_color_primary)
    set_val("brand_color_secondary", conf.brand_color_secondary)
    set_val("brand_color_dark", conf.brand_color_dark)
    set_val("logo_url", conf.logo_url)
    set_val("ticker_speed", conf.ticker_speed)
    set_val("default_headline", conf.default_headline)
    set_val("ticker_label", conf.ticker_label)
    set_val("breaking_label", conf.breaking_label)
    set_val("live_label", conf.live_label)

    # L-Bar
    set_val("layout_mode", conf.layout_mode)
    set_val("lbar_position", conf.lbar_position)
    set_val("lbar_width", conf.lbar_width)
    set_val("lbar_bg_color", conf.lbar_bg_color)
    set_val("lbar_bg_image", conf.lbar_bg_image)
    set_val("lbar_content_type", conf.lbar_content_type)
    set_val("lbar_content_data", conf.lbar_content_data)

    db.commit()
    
    # Broadcast to Overlay
    await broadcast_news_update("CONFIG_UPDATED", conf.dict(exclude_none=True))
    
    return {"status": "success"}

# --- Pydantic Models for News API ---
class NewsCreate(BaseModel):
    title_tamil: str
    title_english: Optional[str] = None
    type: str = "TICKER" # BREAKING, TICKER, etc
    category: str = "GENERAL"
    location: Optional[str] = None
    is_active: bool = True
    priority: int = 0
    # Source Tracking
    source: str = "MANUAL"
    source_url: Optional[str] = None
    external_id: Optional[str] = None
    media_url: Optional[str] = None

class NewsUpdate(BaseModel):
    title_tamil: Optional[str] = None
    title_english: Optional[str] = None
    type: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
    # Source Tracking
    source: Optional[str] = None
    source_url: Optional[str] = None
    media_url: Optional[str] = None

class ExternalFetchRequest(BaseModel):
    url: str
    source_type: str = "RSS" # RSS or SCRAPER

# --- Services ---
import services.news_fetcher as news_fetcher

# --- API Endpoints ---

@app.post("/api/news/fetch-external")
async def fetch_external_news(req: ExternalFetchRequest):
    """
    Fetches news from an external source (RSS or URL) and returns 
    a list of items for the UI to preview/edit.
    """
    if req.source_type == "RSS":
        items = news_fetcher.fetch_rss_feed(req.url)
        return {"status": "success", "items": items}
    elif req.source_type == "SCRAPER":
        item = news_fetcher.scrape_url(req.url)
        if "error" in item:
            return JSONResponse(status_code=400, content=item)
        return {"status": "success", "items": [item]}
    else:
        return JSONResponse(status_code=400, content={"error": "Invalid source type"})

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
        try:
            with open(OVERLAY_FILE, "r") as f:
                return json.load(f)
        except:
            return {"webview_url": ""}
    return {"webview_url": ""}

# --- News Feed Management API (RSS Sources) ---
from database import NewsFeed

class FeedCreate(BaseModel):
    name: str
    url: str
    source_type: str = "RSS"

@app.get("/api/feeds")
def get_feeds(db: Session = Depends(get_db)):
    return db.query(NewsFeed).filter(NewsFeed.is_active == True).all()

@app.post("/api/feeds")
def create_feed(feed: FeedCreate, db: Session = Depends(get_db)):
    db_feed = NewsFeed(name=feed.name, url=feed.url, source_type=feed.source_type)
    db.add(db_feed)
    db.commit()
    db.refresh(db_feed)
    return db_feed

@app.delete("/api/feeds/{feed_id}")
def delete_feed(feed_id: int, db: Session = Depends(get_db)):
    db_feed = db.query(NewsFeed).filter(NewsFeed.id == feed_id).first()
    if db_feed:
        db.delete(db_feed)
        db.commit()
    return {"status": "success"}

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
        priority=item.priority,
        source=item.source,
        source_url=item.source_url,
        external_id=item.external_id,
        media_url=item.media_url
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
