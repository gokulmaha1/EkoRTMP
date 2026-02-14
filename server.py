import os
import subprocess
import signal
import json
import re
import sys
import threading
import queue
import asyncio
import time
import datetime
import requests # Added for ntfy
from typing import Optional, List
from fastapi import FastAPI, UploadFile, Form, WebSocket, WebSocketDisconnect, Depends, HTTPException, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Import our new database module
import database
from database import NewsItem, SystemConfig, NewsType, NewsCategory, get_db, Program

# Notification Config
NTFY_TOPIC = os.environ.get('NTFY_TOPIC', 'eko_news_secret_123') # CHANGE THIS IN PRODUCTION
PUBLIC_URL = os.environ.get('PUBLIC_URL', 'http://127.0.0.1:8123') # CHANGE THIS

app = FastAPI()

# Log Management
log_queue = queue.Queue()
connected_websockets: List[WebSocket] = []
news_websockets: List[WebSocket] = [] # New list for news updates



class StreamManager:
    def __init__(self):
        self.process = None
        self.should_run = False
        self.rtmp_url = None
        self.backup_rtmp_url = None
        self.stream_key = None
        self.lock = threading.Lock()
        self.monitor_thread = None
        self.log_file = "stream_log.txt"
        self.last_heartbeat = 0


    def start(self, rtmp_url, backup_rtmp_url=None, stream_key=None):
        with self.lock:
            self.rtmp_url = rtmp_url
            self.backup_rtmp_url = backup_rtmp_url
            self.stream_key = stream_key
            self.should_run = True
            self.last_heartbeat = time.time() # Reset on start

            
            if self.monitor_thread is None or not self.monitor_thread.is_alive():
                self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
                self.monitor_thread.start()
                print("[StreamManager] Monitor loop started.")

    def stop(self):
        with self.lock:
            self.should_run = False
        self._kill_process()

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def _monitor_loop(self):
        while True:
            # Check if we should stop monitoring (only if main thread exits, but daemon handles that)
            # Actually we busy-wait check should_run
            if not self.should_run:
                if self.process:
                    self._kill_process()
                time.sleep(2)
                continue

            if self.process is None or self.process.poll() is not None:
                print(f"[StreamManager] Stream process not running. Restarting...")
                self._start_process()
            
            # Watchdog Check
            now = time.time()
            if self.process and self.process.poll() is None:
                # If no heartbeat/log for 30 seconds, restart
                if now - self.last_heartbeat > 30:
                    print(f"[StreamManager] Watchdog: No heartbeat for {now - self.last_heartbeat:.1f}s. Restarting stream...")
                    self._log_to_file("Watchdog triggered: Stream stuck.")
                    self._kill_process()
                    # Loop will restart it in next iteration
            
            time.sleep(5)

    def _start_process(self):
        env = os.environ.copy()
        env["OVERLAY_URL"] = "http://127.0.0.1:8123/overlay"
        
        if self.rtmp_url:
            env["RTMP_URL"] = self.rtmp_url
        if self.backup_rtmp_url:
            env["BACKUP_RTMP_URL"] = self.backup_rtmp_url
            
        self._log_to_file(f"Starting stream process... RTMP={self.rtmp_url}")

        try:
            self.process = subprocess.Popen(
                [sys.executable, "-u", "main.py"], 
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1
            )
            
            # Start Log Reader for this process
            t = threading.Thread(target=self._read_logs, args=(self.process,), daemon=True)
            t.start()
            
        except Exception as e:
            self._log_to_file(f"Failed to start process: {e}")
            print(f"[StreamManager] Start failed: {e}")

    def _read_logs(self, proc):
        try:
            for line in iter(proc.stdout.readline, b''):
                decoded_line = line.decode('utf-8').strip()
                if decoded_line:
                    # Update Heartbeat
                    self.last_heartbeat = time.time()
                    
                    # Console
                    print(f"[STREAM] {decoded_line}")
                    # WebSocket Queue
                    log_queue.put(decoded_line)
                    # File
                    self._log_to_file(decoded_line)
        except Exception as e:
            print(f"[StreamManager] Log reader error: {e}")
        finally:
            proc.stdout.close()

    def _kill_process(self):
        if self.process:
            print("[StreamManager] Stopping stream process...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def _log_to_file(self, message):
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            print(f"Failed to write to log file: {e}")

stream_manager = StreamManager()

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
                await asyncio.sleep(0.5)
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

def apply_content_filters(text: str, filters: List[str]) -> str:
    """Removes blocked words/symbols from text (case-insensitive)."""
    if not text: return ""
    if not filters: return text
    
    cleaned = text
    for f in filters:
        if not f.strip(): continue
        # Escape special chars in filter word and use IGNORECASE
        pattern = re.compile(re.escape(f.strip()), re.IGNORECASE)
        cleaned = pattern.sub("", cleaned)
    
    # Collapse multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

from database import NewsFeed, NewsItem, SystemConfig, BlockedNews, SessionLocal
async def sync_rss_feeds():
    """Background task to sync RSS feeds periodically."""
    while True:
        try:
            db = database.SessionLocal()
            feeds = db.query(NewsFeed).filter(NewsFeed.is_active == True).all()
            
            # Load Filters
            filter_config = db.query(SystemConfig).filter(SystemConfig.key == "news_filters").first()
            filter_list = []
            if filter_config and filter_config.value:
                try:
                    # stored as JSON list ["bad", "word"]
                    filter_list = json.loads(filter_config.value)
                except:
                    # Fallback to comma sep if JSON fails
                    filter_list = [x.strip() for x in filter_config.value.split(',') if x.strip()]
            
            new_items_count = 0
            
            for feed in feeds:
                print(f"[RSS] Fetching {feed.name}...")
                items = news_fetcher.fetch_rss_feed(feed.url)
                
                for item in items:
                    # Check if blocked
                    blocked = db.query(BlockedNews).filter(BlockedNews.external_id == item['id']).first()
                    if blocked:
                        continue # Skip blocked items

                    # Check if exists
                    exists = db.query(NewsItem).filter(NewsItem.external_id == item['id']).first()
                    if not exists:
                        # Apply Filtering
                        raw_title = item['title']
                        clean_title = apply_content_filters(raw_title, filter_list)
                        
                        if not clean_title:
                            print(f"[RSS] Skipped filtered item: {raw_title}")
                            continue

                        # Create new item
                        new_news = NewsItem(
                            title_tamil=clean_title, # Filtered Title
                            title_english="",
                            type="TICKER", # Default to Ticker so it scrolls
                            category="GENERAL",
                            source="RSS",
                            source_url=feed.name, # Use Feed Name as source label
                            external_id=item['id'],
                            media_url=item['image'],
                            is_active=True,
                            priority=5 # Normal priority
                        )
                        db.add(new_news)
                        new_items_count += 1
            
            if new_items_count > 0:
                db.commit()
                print(f"[RSS] Added {new_items_count} new items.")
                # Broadcast update
                await broadcast_news_update("NEWS_REFRESH", {"count": new_items_count})
            
            db.close()
            
        except Exception as e:
            print(f"[RSS] Sync Error: {e}")
        
        await asyncio.sleep(60) # Sync every 60 seconds

@app.on_event("startup")
async def startup_event():
    # Initialize DB
    database.init_db()
    
    # Add Default Google News Feed if not exists
    db = database.SessionLocal()
    if db.query(NewsFeed).count() == 0:
        default_feed = NewsFeed(
            name="Google News (Tamil)",
            url="https://news.google.com/rss?hl=ta&gl=IN&ceid=IN:ta",
            source_type="RSS"
        )
        db.add(default_feed)
        db.commit()
        print("[System] Added default Google News Feed.")
    
    # Add Daily Thanthi Feed (Requested by User)
    dt_feed = db.query(NewsFeed).filter(NewsFeed.name == "Daily Thanthi").first()
    if not dt_feed:
        new_feed = NewsFeed(
            name="Daily Thanthi",
            url="https://rss.app/feeds/Vr3sF7zb27kFP49l.xml",
            source_type="RSS",
            is_active=True
        )
        db.add(new_feed)
        db.commit()
        print("[System] Added Daily Thanthi Feed.")
    db.close()

    asyncio.create_task(broadcast_logs())
    asyncio.create_task(sync_rss_feeds()) # Start RSS Sync

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
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
        
        # Broadcast to Overlay (FIX: Added broadcast)
        asyncio.create_task(broadcast_news_update("OVERLAY_UPDATED", current_data))
        
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
from database import NewsFeed, BlockedNews

class FeedCreate(BaseModel):
    name: str
    url: str
    source_type: str = "RSS"

@app.get("/api/feeds")
def get_feeds(db: Session = Depends(get_db)):
    return db.query(NewsFeed).filter(NewsFeed.is_active == True).all()

@app.post("/api/feeds")
def create_feed(feed: FeedCreate, db: Session = Depends(get_db)):
    db_feed = NewsFeed(name=feed.name, url=feed.url, source_type=feed.source_type, is_active=True)
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
from database import AdCampaign, AdItem

class CampaignCreate(BaseModel):
    name: str
    client: Optional[str] = None
    priority: int = 1
    start_date: Optional[datetime.datetime] = None
    end_date: Optional[datetime.datetime] = None

class AdItemCreate(BaseModel):
    campaign_id: int
    type: str # TICKER, L_BAR, FULLSCREEN, POPUP
    content: str
    duration: int = 10
    interval: int = 5
    is_active: bool = True

@app.post("/api/ads/campaigns")
def create_campaign(camp: CampaignCreate, db: Session = Depends(get_db)):
    db_camp = AdCampaign(
        name=camp.name, 
        client=camp.client, 
        priority=camp.priority,
        start_date=camp.start_date or datetime.datetime.utcnow(),
        end_date=camp.end_date
    )
    db.add(db_camp)
    db.commit()
    db.refresh(db_camp)
    return db_camp

@app.get("/api/ads/campaigns")
def get_campaigns(db: Session = Depends(get_db)):
    return db.query(AdCampaign).filter(AdCampaign.is_active == True).all()

@app.post("/api/ads/items")
def create_ad_item(item: AdItemCreate, db: Session = Depends(get_db)):
    # Verify campaign exists
    camp = db.query(AdCampaign).filter(AdCampaign.id == item.campaign_id).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    db_item = AdItem(
        campaign_id=item.campaign_id,
        type=item.type,
        content=item.content,
        duration=item.duration,
        interval=item.interval,
        is_active=item.is_active
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@app.get("/api/ads/items")
def get_ad_items(db: Session = Depends(get_db)):
    return db.query(AdItem).filter(AdItem.is_active == True).all()

@app.delete("/api/ads/items/{item_id}")
def delete_ad_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(AdItem).filter(AdItem.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return {"status": "success"}

@app.get("/api/ads/active")
def get_active_ads(db: Session = Depends(get_db)):
    """
    Returns a list of ads that should be playing right now on the overlay.
    Logic: 
    1. Campaign must be active and within date range.
    2. Ad Item must be active.
    """
    now = datetime.datetime.utcnow()
    
    # Get active campaigns
    active_camps = db.query(AdCampaign).filter(
        AdCampaign.is_active == True,
        AdCampaign.start_date <= now,
        (AdCampaign.end_date == None) | (AdCampaign.end_date >= now)
    ).all()
    
    camp_ids = [c.id for c in active_camps]
    
    if not camp_ids:
        return []
        
    # Get items for these campaigns
    items = db.query(AdItem).filter(
        AdItem.campaign_id.in_(camp_ids),
        AdItem.is_active == True
    ).all()
    
    return items

# --- News Management API ---

@app.get("/api/news")
def get_news(db: Session = Depends(get_db)):
    # Return all active news sorted by priority and date
    items = db.query(NewsItem).filter(NewsItem.is_active == True).order_by(NewsItem.priority.desc(), NewsItem.created_at.desc()).all()
    return items

@app.post("/api/news")
async def create_news(item: NewsCreate, db: Session = Depends(get_db)):
    # Validate Title Length
    if len(item.title_tamil.split()) <= 3:
        raise HTTPException(status_code=400, detail="Headline too short (must be > 3 words)")

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
    
    # Notify Overlay via WebSocket (only if active)
    if db_item.is_active:
        await broadcast_news_update("NEWS_ADDED", {"id": db_item.id, "title": db_item.title_tamil, "type": db_item.type})
    else:
        # If Pending/Draft, send notification for approval
        send_ntfy_approval_request(db_item)
    
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
    return {"status": "deleted"}

# --- Admin API & Notification Logic ---

@app.get("/api/admin/news")
def get_admin_news(db: Session = Depends(get_db)):
    # Return ALL news (Active + Drafts) sorted by ID desc (newest first)
    items = db.query(NewsItem).order_by(NewsItem.id.desc()).all()
    return items

@app.post("/api/admin/news/{news_id}/approve")
async def approve_news_item(news_id: int, db: Session = Depends(get_db)):
    db_item = db.query(NewsItem).filter(NewsItem.id == news_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="News item not found")
    
    db_item.is_active = True
    db.commit()
    
    await broadcast_news_update("NEWS_ADDED", {"id": db_item.id, "title": db_item.title_tamil, "type": db_item.type})
    return {"status": "approved", "is_active": True}

@app.post("/api/admin/news/{news_id}/reject")
async def reject_news_item(news_id: int, db: Session = Depends(get_db)):
    db_item = db.query(NewsItem).filter(NewsItem.id == news_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="News item not found")
    
    # Rejecting = Deleting? Or checking as Inactive?
    # Let's keep it but mark inactive (effectively does nothing if already inactive)
    # OR delete from draft. Usually "Reject" implies "Kill it".
    # User said manage draft vs active. But "Reject" button suggests tossing it?
    # Let's just ensure it's inactive for now.
    db_item.is_active = False
    db.commit()
    
    await broadcast_news_update("NEWS_REMOVED", {"id": db_item.id}) # Just in case it was active
    return {"status": "rejected", "is_active": False}


# --- Coqui TTS Integration ---
try:
    import torch
except ImportError:
    torch = None
    print("WARNING: torch not installed. Coqui TTS will be disabled.")

try:
    from TTS.api import TTS
except ImportError:
    TTS = None
    print("WARNING: Coqui TTS not installed. Install with 'pip install TTS'")
except Exception as e:
    TTS = None
    print(f"WARNING: Error importing TTS: {e}")

class CoquiTTSWrapper:
    def __init__(self):
        self.tts = None
        self.model_name = "tts_models/ta/tamil_female" # Default Tamil model
        self.device = "cpu"
        if torch and torch.cuda.is_available():
            self.device = "cuda"

    def load_model(self):
        if self.tts is None and TTS is not None:
            print(f"Loading Coqui TTS Model: {self.model_name} on {self.device}...")
            try:
                self.tts = TTS(self.model_name).to(self.device)
                print("Model Loaded.")
            except Exception as e:
                print(f"Failed to load Coqui Model: {e}")
                self.tts = None

    def tts_to_file(self, text, file_path):
        if TTS is None:
            return False
            
        if self.tts is None:
            self.load_model()
        
        if self.tts:
            try:
                self.tts.tts_to_file(text=text, file_path=file_path)
                return True
            except Exception as e:
                print(f"Coqui Sync Gen Error: {e}")
                return False
        else:
            print("Coqui TTS not available.")
            return False

# Global TTS Instance
coqui_engine = CoquiTTSWrapper()

# Fallback (System Native)
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

class TTSRequest(BaseModel):
    text: str
    lang: str = "ta"

@app.post("/api/tts")
async def generate_tts(req: TTSRequest):
    print(f"DEBUG: /api/tts request received: {req.text}")
    try:
        # Define base directory (where server.py is)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        media_dir = os.path.join(base_dir, "media")
        
        if not os.path.exists(media_dir):
            os.makedirs(media_dir)
            
        # Use a unique name to avoid Windows file locking issues
        # Clean up old files? (Maybe later task)
        filename = f"tts_{int(time.time()*1000)}.wav"
        target_file = os.path.join(media_dir, filename)
        abs_target = os.path.abspath(target_file)
        
        print(f"DEBUG: Generating TTS to: {abs_target}")

        success = False
        
        # 1. Try Coqui TTS
        if TTS is not None:
            try:
                # Use Coqui
                print("DEBUG: Attempting Coqui TTS...")
                success = coqui_engine.tts_to_file(req.text, abs_target)
                if success:
                    print(f"DEBUG: Coqui TTS success")
            except Exception as e:
                print(f"DEBUG: Coqui TTS failed: {e}")
            
        # 2. Try Google TTS (gtranslate)
        if not success:
            print("Fallback: Using Google Translate TTS")
            try:
                text_enc = urllib.parse.quote(req.text)
                # Client 'tw-ob' sometimes blocked, try without or standard
                url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_enc}&tl={req.lang}&client=tw-ob"
                req_web = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req_web) as response, open(abs_target, 'wb') as out_file:
                    out_file.write(response.read())
                success = True
                print("DEBUG: Google TTS success")
            except Exception as ex:
                print(f"DEBUG: Google TTS failed: {ex}")

        # 3. Try pyttsx3 (System Native)
        if not success and pyttsx3 is not None:
            print("Fallback: Using pyttsx3 (System Native)")
            try:
                engine = pyttsx3.init()
                # Try to find a Tamil voice if possible, otherwise default
                # On Windows, Tamil might not be installed, but it will speak in default voice (maybe garbage for Tamil text)
                # But at least it won't crash the server.
                # Saving to file
                engine.save_to_file(req.text, abs_target)
                engine.runAndWait()
                success = True
                print("DEBUG: pyttsx3 success")
            except Exception as ex:
                print(f"DEBUG: pyttsx3 failed: {ex}")

        if not success:
             raise Exception("All TTS engines failed (Coqui, Google, System)")

        # Update trigger file for main.py (absolute path)
        trigger_file = os.path.join(base_dir, "tts_trigger.json")
        trigger_data = {
            "timestamp": time.time(),
            "file": abs_target,
            "action": "play" 
        }
        
        with open(trigger_file, "w") as f:
            json.dump(trigger_data, f)
            
        print(f"DEBUG: Written trigger to {trigger_file}")
            
        return {"status": "success", "file": abs_target}
        
    except Exception as e:
        print(f"TTS Error: {e}")
        # Return 500 but log it
        raise HTTPException(status_code=500, detail=str(e))

# --- Volume Ducking Trigger (Kept for manual control if needed) ---
class DuckRequest(BaseModel):
    state: str # "duck" or "unduck"

@app.post("/api/stream/duck")
def trigger_duck(req: DuckRequest):
    # Backward compatibility or manual ducking
    pass


def send_ntfy_approval_request(item):
    """
    Sends a push notification to ntfy.sh with interactive Approve/Reject buttons.
    """
    try:
        topic = NTFY_TOPIC
        url = f"https://ntfy.sh/{topic}"
        
        # Approve URL (POST)
        action_approve = f"action=http, Approve, {PUBLIC_URL}/api/admin/news/{item.id}/approve, method=POST, clear=true"
        # Reject URL (POST)
        action_reject = f"action=http, Reject, {PUBLIC_URL}/api/admin/news/{item.id}/reject, method=POST, clear=true"
        
        headers = {
            "Title": "New Draft Headline",
            "Priority": "high",
            "Tags": "newspaper,waiting",
            "Actions": f"{action_approve}; {action_reject}"
        }
        
        requests.post(url, 
            data=f"Review: {item.title_tamil} ({item.category})", 
            headers=headers,
            timeout=5
        )
    except Exception as e:
        print(f"[NTFY] Failed to send notification: {e}")




@app.post("/api/news/{news_id}/show")
async def show_news_on_screen(news_id: int, db: Session = Depends(get_db)):
    db_item = db.query(NewsItem).filter(NewsItem.id == news_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="News item not found")
    
    # Payload for overlay
    payload = {
        "id": db_item.id,
        "title": db_item.title_tamil,
        "category": db_item.category,
        "media_url": db_item.media_url,
        "source": db_item.source,
        "description": db_item.title_english or "" # Use english title as description fallback? Or just Title.
    }
    
    await broadcast_news_update("SHOW_NEWS_MAIN", payload)
    return {"status": "success"}

# --- Filter Management API ---

class FilterConfig(BaseModel):
    filters: List[str]

@app.get("/api/config/filters")
def get_filters(db: Session = Depends(get_db)):
    config = db.query(SystemConfig).filter(SystemConfig.key == "news_filters").first()
    if config and config.value:
        try:
            return json.loads(config.value)
        except:
            return []
    return []

@app.post("/api/config/filters")
def set_filters(data: FilterConfig, db: Session = Depends(get_db)):
    # Store as JSON string
    json_val = json.dumps(data.filters)
    
    config = db.query(SystemConfig).filter(SystemConfig.key == "news_filters").first()
    if config:
        config.value = json_val
    else:
        config = SystemConfig(key="news_filters", value=json_val)
        db.add(config)
    
    db.commit()
    return {"status": "success", "filters": data.filters}

# --- Stream Control API ---
class StreamConfig(BaseModel):
    rtmp_url: Optional[str] = None
    backup_rtmp_url: Optional[str] = None
    stream_key: Optional[str] = None

@app.post("/api/stream/start")
def start_stream(config: StreamConfig):
    # Persist the stream key if provided
    if config.stream_key:
        if os.path.exists(OVERLAY_FILE):
            try:
                with open(OVERLAY_FILE, "r") as f:
                    data = json.load(f)
            except:
                data = {}
        else:
            data = {}
            
        data["stream_key"] = config.stream_key
        
        with open(OVERLAY_FILE, "w") as f:
            json.dump(data, f)
    
    if stream_manager.is_running():
        return {"status": "already_running"}
    
    # Start Manager
    stream_manager.start(
        rtmp_url=config.rtmp_url, 
        backup_rtmp_url=config.backup_rtmp_url,
        stream_key=config.stream_key
    )
    
    return {"status": "started"}

@app.post("/api/stream/stop")
def stop_stream():
    stream_manager.stop()
    return {"status": "stopped"}

@app.get("/api/stream/status")
def get_status():
    return {"running": stream_manager.is_running()}
