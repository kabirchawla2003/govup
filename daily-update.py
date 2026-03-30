# Daily update script - Run this via Windows Task Scheduler or cron
import httpx
from bs4 import BeautifulSoup
import sqlite3
import asyncio
from datetime import datetime, timedelta
import os

# Configuration
DB_PATH = os.path.join(os.path.dirname(__file__), "data/govupdate.db")
SITES = {
    "sebi": {
        "name": "SEBI",
        "url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes"
    },
    "nse": {
        "name": "NSE",
        "url": "https://www.nseindia.com/market-data/content/notices"
    },
    "bse": {
        "name": "BSE",
        "url": "https://www.bseindia.com/corporates/announcements.html"
    },
    "cdsl": {
        "name": "CDSL",
        "url": "https://www.cdslindia.com/investorservices/noticesandannouncements"
    },
    "nsdl": {
        "name": "NSDL",
        "url": "https://nsdl.co.in/investorservices/noticesandannouncements"
    },
    "pfrda": {
        "name": "PFRDA",
        "url": "https://www.pfrda.org.in/"
    }
}


def scrape_site(site_key: str, site: dict) -> list:
    """Scrape updates from a site."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scraping {site['name']}...")
    
    try:
        response = httpx.get(site["url"], timeout=30.0)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        items = []
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            title = link.get_text(strip=True)
            
            if not title or not href:
                continue
            if href.startswith('#') or 'javascript:' in href or 'mailto:' in href:
                continue
            if not href.endswith('.html'):
                continue
            if title in ['View All', 'Read More']:
                continue
            
            full_url = href if href.startswith('http') else href
            items.append({
                'title': title,
                'link': full_url,
                'pub_date': datetime.now().strftime('%Y-%m-%d'),
                'site': site_key
            })
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {site['name']}: Found {len(items)} items")
        return items
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {site['name']} Error: {str(e)}")
        return []


def generate_id() -> str:
    """Generate unique ID."""
    return f"{int(datetime.now().timestamp() * 1000)}-{os.urandom(4).hex()}"


def save_updates(items: list) -> int:
    """Save updates to database and trigger webhooks/emails."""
    if not items:
        return 0
    
    new_count = 0
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        for item in items:
            # Check if already exists
            existing = conn.execute(
                "SELECT id FROM updates WHERE url = ?", (item['link'],)
            ).fetchone()
            
            if not existing:
                update_id = generate_id()
                pub_date = item['pub_date']
                date_part = pub_date.split('T')[0] if 'T' in pub_date else pub_date
                time_part = pub_date.split('T')[1].split('.')[0] if 'T' in pub_date else ''
                
                conn.execute("""
                    INSERT INTO updates (id, site, type, title, date, time, summary, content, url, category, published_at, fetched_at, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    update_id,
                    item['site'],
                    'notice',
                    item['title'],
                    date_part,
                    time_part,
                    item.get('title', ''),
                    '',
                    item['link'],
                    '',
                    pub_date,
                    datetime.now().isoformat(),
                    'manual'
                ))
                
                new_count += 1
                print(f"[{datetime.now().strftime('%H:%M:%S')}] New update: {item['title'][:60]}... ({item['site']})")
        
        conn.commit()
        conn.close()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {new_count} new updates")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Triggering webhooks...")
        
        # TODO: Trigger webhooks (implement in main API)
        # TODO: Send email alerts (implement in main API)
        
        return new_count
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error saving updates: {str(e)}")
        return 0


async def main():
    """Main function to run daily update."""
    print("=" * 70)
    print("GOVUPDATE API - DAILY UPDATE SCRIPT")
    print("=" * 70)
    print()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting daily update...")
    print()
    
    all_items = []
    for site_key in SITES.keys():
        items = scrape_site(site_key, SITES[site_key])
        all_items.extend(items)
    
    print()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Total items scraped: {len(all_items)}")
    print()
    
    new_count = save_updates(all_items)
    
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total Items Scraped: {len(all_items)}")
    print(f"New Updates Saved: {new_count}")
    print(f"Database: {DB_PATH}")
    print("=" * 70)
    print()
    print("NEXT STEPS:")
    print("1. Run this script daily via Windows Task Scheduler")
    print("2. Use API to fetch updates: curl http://localhost:3000/api/updates")
    print("3. Use API keys to authenticate: curl -H \"X-API-Key: YOUR_KEY\" ...")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
