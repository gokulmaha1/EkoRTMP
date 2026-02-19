import feedparser
import requests
from bs4 import BeautifulSoup
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

# --- Scrapy Implementation ---
try:
    import scrapy
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings
    import multiprocessing
except ImportError:
    scrapy = None
    print("WARNING: Scrapy not installed.")

class NewsSpider(scrapy.Spider):
    name = "news_spider"
    
    def __init__(self, url=None, *args, **kwargs):
        super(NewsSpider, self).__init__(*args, **kwargs)
        self.start_urls = [url] if url else []
        self.items = []

    def parse(self, response):
        # Heuristic: Find all links
        # Filter for substantial text
        seen_links = set()
        
        for a in response.css('a'):
            href = a.attrib.get('href')
            text = a.css('::text').get()
            
            if not href or not text:
                continue
                
            text = text.strip()
            href = response.urljoin(href)
            
            # Basic Filters
            if len(text) < 20: continue 
            if href in seen_links: continue
            if "javascript:" in href or "mailto:" in href: continue
            
            # Skip common non-news links
            if any(x in href.lower() for x in ['privacy', 'terms', 'contact', 'login', 'signup', 'about']):
                continue

            seen_links.add(href)
            
            # Image extraction (heuristic)
            image = None
            img = a.css('img::attr(src)').get()
            if img:
                image = response.urljoin(img)
            
            self.items.append({
                "title": text,
                "summary": "",
                "link": href,
                "id": href,
                "published": "",
                "image": image,
                "source": "SCRAPER"
            })
            
            if len(self.items) >= 15:
                break

def run_spider(url, queue):
    """
    Worker function to run Scrapy in a separate process.
    """
    try:
        # Create a spider class on the fly or use the one defined
        class ResultsSpider(NewsSpider):
            def closed(self, reason):
                queue.put(self.items)

        process = CrawlerProcess(settings={
            'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'LOG_LEVEL': 'ERROR',
            'REQUEST_FINGERPRINTER_IMPLEMENTATION': '2.7',
        })
        
        process.crawl(ResultsSpider, url=url)
        process.start() # Blocks until finished
    except Exception as e:
        queue.put({"error": str(e)})

def scrape_news_feed(url: str, limit: int = 15) -> List[Dict]:
    """
    Scrapes a news feed using Scrapy in a separate process.
    """
    if scrapy is None:
        print("Scrapy not installed. Returning empty list.")
        return []

    queue = multiprocessing.Queue()
    p = multiprocessing.Process(target=run_spider, args=(url, queue))
    
    try:
        p.start()
        # Wait with timeout (e.g. 30 seconds)
        p.join(timeout=30)
        
        if p.is_alive():
            print("Scrapy process timed out. Terminating...")
            p.terminate()
            p.join()
            return []
            
        if not queue.empty():
            result = queue.get()
            if isinstance(result, dict) and "error" in result:
                print(f"Scrapy Error: {result['error']}")
                return []
            return result
            
        return []
    except Exception as e:
        print(f"Multiprocessing Error: {e}")
        return []
