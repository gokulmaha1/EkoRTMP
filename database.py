from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import enum

# Database Setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./news_system.db"
# check_same_thread=False is needed for SQLite with FastAPI/threading
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Enums
class NewsType(str, enum.Enum):
    BREAKING = "BREAKING"
    TICKER = "TICKER"
    HEADLINE = "HEADLINE"
    FLASH = "FLASH"

class NewsCategory(str, enum.Enum):
    POLITICS = "POLITICS"
    ELECTION = "ELECTION"
    DISTRICT = "DISTRICT"
    SPORTS = "SPORTS"
    GENERAL = "GENERAL"

class NewsSource(str, enum.Enum):
    MANUAL = "MANUAL"
    RSS = "RSS"
    API = "API"
    SCRAPER = "SCRAPER"

# Models
class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, default=NewsType.TICKER)
    category = Column(String, default=NewsCategory.GENERAL)
    
    title_tamil = Column(String, nullable=False)
    title_english = Column(String, nullable=True)
    
    # Source Tracking
    source = Column(String, default=NewsSource.MANUAL)
    source_url = Column(String, nullable=True)
    external_id = Column(String, nullable=True) # For deduping RSS items
    
    location = Column(String, nullable=True)
    media_url = Column(String, nullable=True)
    
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0) # Higher = Show first
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# --- Ad Management Models ---
class AdType(str, enum.Enum):
    TICKER = "TICKER"
    L_BAR = "L_BAR"
    FULLSCREEN = "FULLSCREEN"
    POPUP = "POPUP"

class AdCampaign(Base):
    __tablename__ = "ad_campaigns"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    client = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    start_date = Column(DateTime, default=datetime.datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    priority = Column(Integer, default=1)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AdItem(Base):
    __tablename__ = "ad_items"
    
    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, nullable=False) # ForeignKey logic handled manually or via simple ID for simplicity in SQLite
    type = Column(String, default=AdType.TICKER)
    
    content = Column(String, nullable=False) # Text for Ticker, Media URL for others
    duration = Column(Integer, default=10) # Seconds (for L-Bar/Fullscreen)
    interval = Column(Integer, default=5) # Minutes (Frequency)
    
    last_played_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class NewsFeed(Base):
    __tablename__ = "news_feeds"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False) # e.g. "Polimer News"
    url = Column(String, nullable=False)
    source_type = Column(String, default=NewsSource.RSS) # RSS, SCRAPER
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class BlockedNews(Base):
    __tablename__ = "blocked_news"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True) # The ID/URL to block
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Program(Base):
    __tablename__ = "programs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    video_path = Column(String, nullable=False) # Local path or URL
    
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String, primary_key=True, index=True)
    value = Column(Text) # JSON string or raw text

# --- YouTube Voting Models ---
class Voter(Base):
    __tablename__ = "voters"

    id = Column(Integer, primary_key=True, index=True)
    stream_id = Column(String, index=True) # YouTube Video ID
    author_channel_id = Column(String, index=True)
    display_name = Column(String, nullable=True)
    profile_image_url = Column(String, nullable=True)
    
    party_code = Column(String, index=True) # DMK, ADMK, etc.
    party_tamil = Column(String, nullable=True)
    message_id = Column(String, unique=True, index=True)
    
    voted_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Unique constraint to prevent duplicate votes per stream per user
    # Handled via code check or unique index. sqlalchemy UniqueConstraint can be used.
    # __table_args__ = (UniqueConstraint('stream_id', 'author_channel_id', name='_user_stream_uc'),)

class VoteCount(Base):
    __tablename__ = "vote_counts"
    
    id = Column(Integer, primary_key=True, index=True)
    stream_id = Column(String, index=True)
    party_code = Column(String)
    party_tamil = Column(String)
    count = Column(Integer, default=0)
    
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Init DB
def init_db():
    Base.metadata.create_all(bind=engine)
