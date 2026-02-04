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

class NewsFeed(Base):
    __tablename__ = "news_feeds"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False) # e.g. "Polimer News"
    url = Column(String, nullable=False)
    source_type = Column(String, default=NewsSource.RSS) # RSS, SCRAPER
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String, primary_key=True, index=True)
    value = Column(Text) # JSON string or raw text

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
