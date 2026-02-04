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
    BREAKING = "BREAKING" # Full screen / Top bar red
    TICKER = "TICKER"     # Bottom scroll
    HEADLINE = "HEADLINE" # Main story
    FLASH = "FLASH"       # Yellow interrupt

class NewsCategory(str, enum.Enum):
    POLITICS = "POLITICS"
    ELECTION = "ELECTION"
    DISTRICT = "DISTRICT"
    SPORTS = "SPORTS"
    GENERAL = "GENERAL"

# Models
class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, default=NewsType.TICKER) # Stored as string for simplicity
    category = Column(String, default=NewsCategory.GENERAL)
    
    title_tamil = Column(String, nullable=False) # Main content
    title_english = Column(String, nullable=True) # Optional
    
    location = Column(String, nullable=True) # e.g. "Chennai"
    media_url = Column(String, nullable=True) # Image/Video path
    
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0) # Higher = Show first
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

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
