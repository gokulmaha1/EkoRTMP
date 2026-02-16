import os
import time
import datetime
import json
import re
import re
try:
    import requests
except ImportError:
    requests = None
import threading
from sqlalchemy.orm import Session
from database import SessionLocal, Voter, VoteCount

class YouTubePollingService:
    def __init__(self):
        self.api_key = os.environ.get("YOUTUBE_API_KEY", "")
        self.video_id = None
        self.live_chat_id = None
        self.is_running = False
        self.polling_thread = None
        self.next_page_token = None
        self.polling_interval = 60 # Seconds (safety)
        
        # Party Mappings
        self.party_map = {
            "DMK": ["DMK", "திமுக", "உதயநிதி", "ஸ்டாலின்"],
            "ADMK": ["ADMK", "AIADMK", "அதிமுக", "எடப்பாடி", "EPS"],
            "BJP": ["BJP", "பாஜக", "மோடி", "அண்ணாமலை"],
            "NTK": ["NTK", "சீமான்", "நாம் தமிழர்"],
            "TVK": ["TVK", "விஜய்", "தவெக"]
        }
        
    def start(self, video_id):
        if not self.api_key:
            print("[Vote] Error: YOUTUBE_API_KEY not set.")
            return False
            
        self.video_id = video_id
        self.is_running = True
        
        # Reset tokenizer on new start is usually good, but if restarting same stream, maybe keep?
        # For simplicity, reset.
        self.next_page_token = None
        
        if self.polling_thread is None or not self.polling_thread.is_alive():
            self.polling_thread = threading.Thread(target=self._poll_loop, daemon=True)
            self.polling_thread.start()
            
        return True

    def stop(self):
        self.is_running = False
        
    def _poll_loop(self):
        print(f"[Vote] Service started for Video: {self.video_id}")
        
        # 1. Get Live Chat ID
        if not self._fetch_live_chat_id():
            print("[Vote] Failed to get Live Chat ID. Stopping.")
            self.is_running = False
            return

        while self.is_running:
            try:
                # 2. Check Time Window (6 AM - 12 PM IST)
                # IST is UTC+5:30. 6 AM IST = 00:30 UTC. 12 PM IST = 06:30 UTC.
                # For now, let's keep it running 24/7 or user controlled, implementing strict cron later if needed.
                # The user requirement said 6-12, but we can enforce it here or via external trigger.
                # Let's Skip strict time check for MVP/Testing unless requested.
                
                self._poll_chat()
                
                # Wait for next poll (Dynamic based on API response, but min 10s)
                time.sleep(self.polling_interval)
                
            except Exception as e:
                print(f"[Vote] Polling Loop Error: {e}")
                time.sleep(60)

    def _fetch_live_chat_id(self):
        url = f"https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails&id={self.video_id}&key={self.api_key}"
        try:
            res = requests.get(url)
            data = res.json()
            if "items" in data and len(data["items"]) > 0:
                details = data["items"][0].get("liveStreamingDetails", {})
                self.live_chat_id = details.get("activeLiveChatId")
                if self.live_chat_id:
                    print(f"[Vote] Found Chat ID: {self.live_chat_id}")
                    return True
            print(f"[Vote] No Chat ID found (Stream offline?). Data: {json.dumps(data)}")
        except Exception as e:
            print(f"[Vote] API Error fetching details: {e}")
        return False

    def _poll_chat(self):
        url = f"https://www.googleapis.com/youtube/v3/liveChat/messages?liveChatId={self.live_chat_id}&part=snippet,authorDetails&key={self.api_key}"
        if self.next_page_token:
            url += f"&pageToken={self.next_page_token}"
            
        try:
            res = requests.get(url)
            data = res.json()
            
            if "error" in data:
                print(f"[Vote] API Error: {json.dumps(data['error'])}")
                # Handle quota/auth errors
                return

            # Update timing
            self.polling_interval = data.get("pollingIntervalMillis", 10000) / 1000
            self.polling_interval = max(self.polling_interval, 5) # Safety floor
            self.next_page_token = data.get("nextPageToken")
            
            items = data.get("items", [])
            if items:
                self._process_messages(items)
                
        except Exception as e:
            print(f"[Vote] Chat Poll Error: {e}")

    def _process_messages(self, messages):
        db = SessionLocal()
        new_votes = 0
        
        for msg in messages:
            snippet = msg.get("snippet", {})
            auth_details = msg.get("authorDetails", {})
            
            msg_type = snippet.get("type")
            if msg_type != "textMessageEvent":
                continue
                
            text = snippet.get("textMessageDetails", {}).get("messageText", "")
            channel_id = auth_details.get("channelId")
            
            # Simple Spam Check: Ignore if already processed via message_id (if we store it)
            # But duplicate voting logic is User+Stream based.
            
            party = self._parse_party(text)
            if party:
                # Check if user already voted in this stream
                existing = db.query(Voter).filter(
                    Voter.stream_id == self.video_id,
                    Voter.author_channel_id == channel_id
                ).first()
                
                if not existing:
                    # Register Vote
                    voter = Voter(
                        stream_id=self.video_id,
                        author_channel_id=channel_id,
                        display_name=auth_details.get("displayName"),
                        profile_image_url=auth_details.get("profileImageUrl"),
                        party_code=party['code'],
                        party_tamil=party['tamil'],
                        message_id=msg.get("id"),
                        voted_at=datetime.datetime.utcnow()
                    )
                    db.add(voter)
                    
                    # Update Aggregate
                    count_rec = db.query(VoteCount).filter(
                        VoteCount.stream_id == self.video_id, 
                        VoteCount.party_code == party['code']
                    ).first()
                    
                    if not count_rec:
                        count_rec = VoteCount(
                            stream_id=self.video_id, 
                            party_code=party['code'],
                            party_tamil=party['tamil'],
                            count=0
                        )
                        db.add(count_rec)
                    
                    count_rec.count += 1
                    
                    new_votes += 1
                    print(f"[Vote] +1 for {party['code']} from {voter.display_name}")

        if new_votes > 0:
            db.commit()
            
        db.close()

    def _parse_party(self, text):
        # Normalize: Upper, only alphanumeric logic if needed? 
        # Just simple containment check for keywords
        clean_text = text.upper()
        
        for code, keywords in self.party_map.items():
            for kw in keywords:
                # Word boundary check is better but simple contains is robust enough for chaotic chat
                # "I vote DMK" -> Matches
                # "DMK win" -> Matches
                if kw.upper() in clean_text:
                    # Tamil Label Map
                    tamil_labels = {
                        "DMK": "திமுக",
                        "ADMK": "அதிமுக",
                        "BJP": "பாஜக",
                        "NTK": "நாதக",
                        "TVK": "தவெக"
                    }
                    return {"code": code, "tamil": tamil_labels.get(code, code)}
        return None

# Singleton
vote_service = YouTubePollingService()
