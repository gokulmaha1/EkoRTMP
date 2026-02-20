import sys
import json
import logging

try:
    import scrapy
    from scrapy.crawler import CrawlerProcess
except ImportError:
    print(json.dumps({"error": "Scrapy not installed"}))
    sys.exit(1)

# Suppress Scrapy Logs
logging.getLogger('scrapy').setLevel(logging.ERROR)

class SinglePageSpider(scrapy.Spider):
    name = "single_page"
    
    def __init__(self, url=None, *args, **kwargs):
        super(SinglePageSpider, self).__init__(*args, **kwargs)
        self.start_urls = [url] if url else []
        self.found_items = []

    def parse(self, response):
        seen_links = set()
        for a in response.css('a'):
            href = a.attrib.get('href')
            text = a.css('::text').get()
            
            if not href or not text:
                continue
                
            text = text.strip()
            href = response.urljoin(href)
            
            # Filters
            if len(text) < 20: continue 
            if href in seen_links: continue
            if "javascript:" in href or "mailto:" in href: continue
            if any(x in href.lower() for x in ['privacy', 'terms', 'contact', 'login', 'signup', 'about']):
                continue

            seen_links.add(href)
            
            image = None
            img = a.css('img::attr(src)').get()
            if img:
                image = response.urljoin(img)
            
            self.found_items.append({
                "title": text,
                "summary": "",
                "link": href,
                "id": href,
                "published": "",
                "image": image,
                "source": "SCRAPER"
            })
            
            if len(self.found_items) >= 15:
                break

    def closed(self, reason):
        # On close, print items as JSON
        print(json.dumps(self.found_items))

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}))
        sys.exit(1)
        
    url = sys.argv[1]
    
    process = CrawlerProcess(settings={
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'LOG_LEVEL': 'ERROR',
        'REQUEST_FINGERPRINTER_IMPLEMENTATION': '2.7',
        'TELNETCONSOLE_ENABLED': False,
    })
    
    process.crawl(SinglePageSpider, url=url)
    process.start()

if __name__ == "__main__":
    main()
