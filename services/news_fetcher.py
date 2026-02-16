try:
    import feedparser
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    feedparser = None
    requests = None
    BeautifulSoup = None
from typing import List, Dict, Optional
import re
import ssl

# Fix legacy SSL issues if any
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

def fetch_rss_feed(url: str, limit: int = 10) -> List[Dict]:
    """
    Fetches an RSS feed and returns normalized items.
    """
    if not feedparser or not BeautifulSoup:
        print("RSS Svc: Missing dependencies (feedparser/bs4)")
        return []
    try:
        feed = feedparser.parse(url)
        items = []
        
        for entry in feed.entries[:limit]:
            # Try to find a summary or description
            summary = ""
            if hasattr(entry, 'summary'):
                summary = entry.summary
            elif hasattr(entry, 'description'):
                summary = entry.description
                
            # Clean summary (remove HTML tags for simple ticker)
            clean_summary = BeautifulSoup(summary, "html.parser").get_text()
            
            # Image extraction (basic)
            image_url = None
            if hasattr(entry, 'media_content'):
                image_url = entry.media_content[0]['url']
            elif hasattr(entry, 'enclosures'):
                for enc in entry.enclosures:
                    if enc.type.startswith('image/'):
                        image_url = enc.href
                        break
            
            # Clean Title (Remove " - SourceName" suffix common in Google News)
            # Regex removes the last " - Something" from the end of the string
            clean_title = re.sub(r' - [^-]+$', '', entry.title)

            # Skip if title is too short (<= 3 words)
            if len(clean_title.split()) <= 3:
                continue

            items.append({
                "title": clean_title,
                "summary": clean_summary[:200] + "..." if len(clean_summary) > 200 else clean_summary,
                "link": entry.link,
                "id": entry.get('id', entry.link),
                "published": entry.get('published', ''),
                "image": image_url,
                "source": "RSS"
            })
            
        return items
    except Exception as e:
        print(f"RSS Fetch Error: {e}")
        return []

def scrape_url(url: str) -> Dict:
    """
    Scrapes a web page to extract the main headline and metadata.
    Simulates 'AI Summarizer' by extracting meta tags.
    """
    if not requests or not BeautifulSoup:
        return {"error": "Missing dependencies (requests/bs4)"}
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 1. Title
        title = soup.title.string if soup.title else ""
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title["content"]
            
        # 2. Description / Summary
        description = ""
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            description = og_desc["content"]
        else:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                description = meta_desc["content"]
                
        # 3. Image
        image = None
        og_image = soup.find("meta", property="og:image")
        if og_image:
            image = og_image["content"]
            
        return {
            "title": title.strip(),
            "summary": description.strip(),
            "link": url,
            "image": image,
            "source": "SCRAPER"
        }
    except Exception as e:
        print(f"Scrape Error: {e}")
        return {"error": str(e)}
