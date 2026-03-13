import os
import time
import requests
import datetime
import threading
import json
import re
from sqlalchemy.orm import Session
from database import SessionLocal, Voter, VoteCount, SystemConfig, ApiLog

# Party Configuration
PARTIES = {
    "DMK_PLUS": {
        "tamil": "திமுக கூட்டணி",
        "keywords": ["DMK", "VOTE DMK", "dmk", "vote dmk", "திமுக", "உதயசூரியன்", "DMK+", "DMK PLUS", "dmk+", "dmk plus", " உதயசூரியன்", "ஸ்டாலின்", "STALIN", "stalin", "☀️"]
    },
    "ADMK_PLUS": {
        "tamil": "அதிமுக கூட்டணி",
        "keywords": ["ADMK", "AIADMK", "admk", "aiadmk", "அதிமுக", "இரட்டை இலை", "ADMK+", "ADMK PLUS", "admk+", "admk plus", "இரட்டை இலை", "எடப்பாடி", "EPS", "eps", "🍃", "🌿"]
    },
    "NTK": {
        "tamil": "நாம் தமிழர்",
        "keywords": ["NTK", "NAM TAMILAR", "ntk", "nam tamilar", "நாம் தமிழர்", "சீமான்", "seeman","vivasayi","VIVASAYI","vivasayi katchi", "விவசாயி", "SEEMAN", "🌾"]
    },
    "TVK": {
        "tamil": "தவெக",
        "keywords": ["TVK", "TAVK", "tvk", "tavk", "தவெக", "விஜய்", "vijay", "thalapathy", "THALAPATHY", "தளபதி", "VIJAY", "🚩"]
    }
}

class VoteCollector:
    def __init__(self):
        self.api_key = None
        self.main_video_id = None
        self.vote_video_id = None
        self.stream_mode = "single" # single or dual
        self.is_running = False
        self.thread = None
        self.next_page_token = None
        self.polling_interval = 30 # Hardcoded default
        self.last_chat_id = None
        self.cached_chat_id = None # Cache for Chat ID
        self.cached_video_id = None # For cache invalidation
        self.on_new_vote = None
        self.status = {
            "is_running": False,
            "last_poll_at": None,
            "messages_found": 0,
            "total_votes_this_session": 0,
            "current_video_id": None,
            "api_error": None,
            "raw_response_snippet": None,
            "last_error_type": None
        }

    def extract_video_id(self, input_str):
        if not input_str: return None
        input_str = input_str.strip()
        if len(input_str) == 11: return input_str
        
        patterns = [
            r"v=([0-9A-Za-z_-]{11})",
            r"be/([0-9A-Za-z_-]{11})",
            r"live/([0-9A-Za-z_-]{11})",
            r"shorts/([0-9A-Za-z_-]{11})",
            r"embed/([0-9A-Za-z_-]{11})"
        ]
        for p in patterns:
            match = re.search(p, input_str)
            if match: return match.group(1)
            
        return input_str

    def load_config(self, db: Session):
        cfg = db.query(SystemConfig).filter(SystemConfig.key == "voting_config").first()
        if not cfg:
            return

        try:
            data = json.loads(cfg.value)
            new_api_key = data.get("youtube_api_key")
            new_main_id = data.get("main_video_id")
            new_vote_id = data.get("vote_video_id")
            new_mode = data.get("stream_mode", "single")
            # poll_interval is ignored, now hardcoded to 30s

            # Detect change in video/key to reset polling state
            target_id = new_vote_id if new_mode == "dual" else new_main_id
            current_target = self.vote_video_id if self.stream_mode == "dual" else self.main_video_id
            
            if target_id != current_target or new_api_key != self.api_key:
                print(f"[VoteCollector] Config changed. Resetting state. Target: {target_id}")
                self.next_page_token = None
                self.last_chat_id = None
                self.cached_chat_id = None # Reset cache

            self.api_key = new_api_key
            self.main_video_id = new_main_id
            self.vote_video_id = new_vote_id
            self.stream_mode = new_mode
        except Exception as e:
            print(f"[VoteCollector] Error loading config: {e}")

    def log_api_call(self, db: Session, endpoint: str, params: dict, response: requests.Response):
        try:
            log = ApiLog(
                service_name="VoteCollector",
                endpoint=endpoint,
                method="GET",
                request_params=json.dumps(params),
                response_code=response.status_code,
                response_body=response.text[:2000],
                is_error=(response.status_code != 200)
            )
            db.add(log)
            db.commit()
        except Exception as e:
            print(f"[VoteCollector] Log error: {e}")
        
    def get_live_chat_id(self, video_id):
        video_id = self.extract_video_id(video_id)

        # Use Cache if available
        if self.cached_chat_id and self.cached_video_id == video_id and not self.status.get("api_error"):
            return self.cached_chat_id

        if not self.api_key or not video_id:
            print(f"[VoteCollector] Missing API Key or Video ID for chat fetch.")
            return None
            
        print(f"[VoteCollector] Requesting live chat ID for video: {video_id}")
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "liveStreamingDetails",
            "id": video_id,
            "key": self.api_key
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            self.log_api_call(SessionLocal(), url, params, r)
            self.status["raw_response_snippet"] = r.text[:500]
            
            if r.status_code != 200:
                error_data = r.json().get("error", {})
                reason = error_data.get("errors", [{}])[0].get("reason", "unknown")
                msg = error_data.get("message", "Request Failed")
                
                print(f"[VoteCollector] API Error (ChatID): {reason} - {msg}")
                self.status["last_error_type"] = reason
                self.status["api_error"] = f"YouTube API Error ({reason}): {msg}"
                return None
            
            data = r.json()
            if "items" in data and len(data["items"]) > 0:
                details = data["items"][0].get("liveStreamingDetails", {})
                chat_id = details.get("activeLiveChatId")
                
                if not chat_id:
                    print(f"[VoteCollector] Video exists but no activeLiveChatId. Is it live?")
                    self.status["last_error_type"] = "not_live"
                    self.status["api_error"] = "Video is not currently live or streaming."
                    return None
                    
                print(f"[VoteCollector] Cached chat ID: {chat_id}")
                self.cached_chat_id = chat_id
                self.cached_video_id = video_id
                return chat_id
            else:
                print(f"[VoteCollector] Video ID not found or invalid: {video_id}")
                self.status["last_error_type"] = "video_not_found"
                self.status["api_error"] = f"Video ID '{video_id}' not found."
        except Exception as e:
            print(f"[VoteCollector] Exception fetching chat ID: {e}")
            self.status["api_error"] = str(e)
        return None

    def normalize_text(self, text):
        if not text: return ""
        # Basic normalization: uppercase, trim
        text = text.upper().strip()
        # Keep Tamil characters, alphanumeric, and spaces. Remove other punctuation but keep common emojis if they are in keywords?
        # Actually, let's just keep everything and do a 'contains' check.
        return text

    def detect_party(self, message):
        norm_message = self.normalize_text(message)
        for code, info in PARTIES.items():
            for kw in info["keywords"]:
                if kw.upper() in norm_message:
                    return code, info["tamil"]
        return None, None

    def process_messages(self, messages, stream_id, db: Session):
        new_votes = []
        counts_cache = {} # (stream_id, party_code) -> VoteCount object
        batch_channel_ids = set() # track users already counted in this specific batch

        for msg in messages:
            snippet = msg.get("snippet", {})
            if snippet.get("type") != "textMessageEvent":
                continue
                
            author = msg.get("authorDetails", {})
            channel_id = author.get("channelId")
            
            # 1. Batch-level deduplication (Fast in-memory check)
            if channel_id in batch_channel_ids:
                continue

            display_name = author.get("displayName")
            profile_url = author.get("profileImageUrl")
            text = snippet.get("textMessageDetails", {}).get("messageText")
            msg_id = msg.get("id")
            
            party_code, party_tamil = self.detect_party(text)
            if party_code:
                # 2. DB-level check for duplicate (Existing voters from previous runs)
                exists = db.query(Voter).filter(
                    Voter.stream_id == stream_id,
                    Voter.author_channel_id == channel_id
                ).first()
                
                if not exists:
                    voter = Voter(
                        stream_id=stream_id,
                        author_channel_id=channel_id,
                        display_name=display_name,
                        profile_image_url=profile_url,
                        party_code=party_code,
                        party_tamil=party_tamil,
                        message_id=msg_id
                    )
                    db.add(voter)
                    batch_channel_ids.add(channel_id)
                    
                    # Track counts in memory during the batch to avoid IntegrityError
                    count_key = (stream_id, party_code)
                    if count_key in counts_cache:
                        count = counts_cache[count_key]
                    else:
                        count = db.query(VoteCount).filter(
                            VoteCount.stream_id == stream_id,
                            VoteCount.party_code == party_code
                        ).first()
                        
                        if not count:
                            count = VoteCount(stream_id=stream_id, party_code=party_code, party_tamil=party_tamil, total=0)
                            db.add(count)
                        
                        counts_cache[count_key] = count
                    
                    count.total += 1
                    
                    # We flush to get the ID for the overlay feed, but don't commit until the end
                    try:
                        db.flush()
                        new_votes.append({
                            "id": voter.id,
                            "name": display_name,
                            "party": party_tamil,
                            "image": profile_url
                        })
                    except Exception as e:
                        print(f"[VoteCollector] Flush error: {e}")
                        db.rollback()
                        continue
        
        if new_votes:
            try:
                db.commit()
                return new_votes
            except Exception as e:
                print(f"[VoteCollector] Commit error: {e}")
                db.rollback()
        return []

    def run_loop(self):
        print("[VoteCollector] Service started.")
        while self.is_running:
            # IST 12:00 = 06:30 UTC
            # But the user might want current server time or actual IST. 
            # Let's assume server is in a known TZ or we use offset.
            
            db = SessionLocal()
            try:
                self.load_config(db)
                target_video_id = self.vote_video_id if self.stream_mode == "dual" else self.main_video_id
                
                if not target_video_id or not self.api_key:
                    time.sleep(10)
                    continue
                
                chat_id = self.get_live_chat_id(target_video_id)
                if not chat_id:
                    time.sleep(30)
                    continue
                url = "https://youtube.googleapis.com/youtube/v3/liveChat/messages"
                # url = "https://www.googleapis.com/youtube/v3/liveChatMessages"
                params = {
                    "part": "snippet,authorDetails",
                    "liveChatId": chat_id,
                    "maxResults": 200,
                    "key": self.api_key
                }
                if self.next_page_token:
                    params["pageToken"] = self.next_page_token
                
                print(f"[VoteCollector] Polling chat messages (liveChatId: {chat_id})...")
                r = requests.get(url, params=params, timeout=10)
                # Detailed log mapping for debugging
                self.log_api_call(db, url, params, r)
                self.status["raw_response_snippet"] = r.text[:500]
                
                if r.status_code != 200:
                    self.status["api_error"] = f"HTTP {r.status_code}: {r.text[:100]}"
                    time.sleep(30)
                    continue

                try:
                    data = r.json()
                except Exception as je:
                    self.status["api_error"] = f"JSON Parse Error: {str(je)}"
                    self.status["raw_response_snippet"] = r.text[:500]
                    time.sleep(30)
                    continue
                
                if "error" in data:
                    err_msg = data['error'].get('message', 'Unknown Error')
                    self.status["api_error"] = f"YouTube API: {err_msg}"
                    print(f"[VoteCollector] API Error: {err_msg}")
                    time.sleep(60)
                    continue
                
                messages = data.get("items", [])
                self.next_page_token = data.get("nextPageToken")
                
                # We enforce minimum 30s polling, but if YouTube asks for MORE, we respect that.
                yt_suggested = data.get("pollingIntervalMillis", 5000) / 1000.0
                self.polling_interval = max(30.0, yt_suggested)
                
                new_votes = self.process_messages(messages, target_video_id, db)
                
                # Update Status
                self.status.update({
                    "is_running": True,
                    "last_poll_at": datetime.datetime.now().strftime("%H:%M:%S"),
                    "messages_found": len(messages),
                    "total_votes_this_session": self.status.get("total_votes_this_session", 0) + len(new_votes),
                    "current_video_id": target_video_id,
                    "api_error": None,
                    "raw_response_snippet": r.text[:500]
                })

                if len(messages) > 0:
                    print(f"[VoteCollector] Poll complete. Found {len(messages)} messages, {len(new_votes)} new votes. Next poll in {self.polling_interval}s.")
                else:
                    print(f"[VoteCollector] Poll complete. No new messages. Next poll in {self.polling_interval}s.")

                # Broadcast new votes if any
                if new_votes and self.on_new_vote:
                    self.on_new_vote(new_votes)

            except Exception as e:
                print(f"[VoteCollector] Loop Error: {e}")
                self.status["api_error"] = str(e)
            finally:
                db.close()
            
            time.sleep(self.polling_interval)

    def start(self):
        if self.is_running: return
        self.is_running = True
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False

vote_collector = VoteCollector()
