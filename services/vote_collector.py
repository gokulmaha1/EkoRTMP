import os
import time
import requests
import datetime
import threading
import json
from sqlalchemy.orm import Session
from database import SessionLocal, Voter, VoteCount, SystemConfig

# Party Configuration
PARTIES = {
    "DMK_PLUS": {
        "tamil": "திமுக கூட்டணி",
        "keywords": ["DMK", "VOTE DMK", "திமுக", "உதயசூரியன்", "DMK+", "DMK PLUS"]
    },
    "ADMK_PLUS": {
        "tamil": "அதிமுக கூட்டணி",
        "keywords": ["ADMK", "AIADMK", "அதிமுக", "இரட்டை இலை", "ADMK+", "ADMK PLUS"]
    },
    "NTK": {
        "tamil": "நாம் தமிழர்",
        "keywords": ["NTK", "NAM TAMILAR", "நாம் தமிழர்", "சீமான்"]
    },
    "TVK": {
        "tamil": "தவெக",
        "keywords": ["TVK", "VIJAY", "தவெக", "விஜய்", "வெற்றி கழகம்"]
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
        self.polling_interval = 5 # seconds
        self.last_chat_id = None
        self.on_new_vote = None

    def load_config(self, db: Session):
        def get_cfg(key, default=None):
            cfg = db.query(SystemConfig).filter(SystemConfig.key == key).first()
            return cfg.value if cfg else default

        self.api_key = get_cfg("youtube_api_key")
        self.main_video_id = get_cfg("main_video_id")
        self.vote_video_id = get_cfg("vote_video_id")
        self.stream_mode = get_cfg("stream_mode", "single")
        
    def get_live_chat_id(self, video_id):
        if not self.api_key or not video_id:
            return None
            
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "liveStreamingDetails",
            "id": video_id,
            "key": self.api_key
        }
        try:
            r = requests.get(url, params=params)
            data = r.json()
            if "items" in data and len(data["items"]) > 0:
                return data["items"][0].get("liveStreamingDetails", {}).get("activeLiveChatId")
        except Exception as e:
            print(f"[VoteCollector] Error fetching chat ID: {e}")
        return None

    def normalize_text(self, text):
        if not text: return ""
        # Basic normalization: uppercase, trim, remove some punctuation
        text = text.upper().strip()
        # Remove common punctuation but keep Tamil characters
        import re
        text = re.sub(r'[^\w\s\u0B80-\u0BFF]', '', text)
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
        for msg in messages:
            snippet = msg.get("snippet", {})
            if snippet.get("type") != "textMessageEvent":
                continue
                
            author = msg.get("authorDetails", {})
            channel_id = author.get("channelId")
            display_name = author.get("displayName")
            profile_url = author.get("profileImageUrl")
            text = snippet.get("textMessageDetails", {}).get("messageText")
            msg_id = msg.get("id")
            
            party_code, party_tamil = self.detect_party(text)
            if party_code:
                # Check for duplicate
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
                    
                    # Update count
                    count = db.query(VoteCount).filter(
                        VoteCount.stream_id == stream_id,
                        VoteCount.party_code == party_code
                    ).first()
                    
                    if not count:
                        count = VoteCount(stream_id=stream_id, party_code=party_code, party_tamil=party_tamil, total=0)
                        db.add(count)
                    
                    count.total += 1
                    new_votes.append({
                        "id": voter.id,
                        "name": display_name,
                        "party": party_tamil,
                        "image": profile_url
                    })
        
        if new_votes:
            db.commit()
            return new_votes
        return []

    def run_loop(self):
        print("[VoteCollector] Service started.")
        while self.is_running:
            # Check window: 06:00 - 12:00 IST (UTC+5:30)
            # IST 06:00 = 00:30 UTC
            # IST 12:00 = 06:30 UTC
            # But the user might want current server time or actual IST. 
            # Let's assume server is in a known TZ or we use offset.
            # Local time check for 06:00 - 12:00
            now = datetime.datetime.now()
            if not (6 <= now.hour < 12):
                # Outside window, sleep longer
                time.sleep(60)
                continue

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

                url = "https://www.googleapis.com/youtube/v3/liveChatMessages"
                params = {
                    "part": "snippet,authorDetails",
                    "liveChatId": chat_id,
                    "maxResults": 200,
                    "key": self.api_key
                }
                if self.next_page_token:
                    params["pageToken"] = self.next_page_token
                
                r = requests.get(url, params=params)
                data = r.json()
                
                if "error" in data:
                    print(f"[VoteCollector] API Error: {data['error'].get('message')}")
                    time.sleep(60)
                    continue
                
                messages = data.get("items", [])
                self.next_page_token = data.get("nextPageToken")
                self.polling_interval = data.get("pollingIntervalMillis", 5000) / 1000.0
                
                new_votes = self.process_messages(messages, target_video_id, db)
                
                # Broadcast new votes if any
                if new_votes and self.on_new_vote:
                    self.on_new_vote(new_votes)

            except Exception as e:
                print(f"[VoteCollector] Loop Error: {e}")
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
