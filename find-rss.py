import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

# Check for RSS feeds on blocked sites
sites_to_check = {
    "nse": "https://www.nseindia.com/",
    "bse": "https://www.bseindia.com/",
    "cdsl": "https://www.cdslindia.com/",
    "nsdl": "https://nsdl.co.in/"
}

def find_rss_feeds(url):
    """Find RSS feeds on a website."""
    print(f"\nChecking {url} for RSS feeds...")
    
    try:
        response = requests.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for RSS links in HTML
        rss_links = []
        
        # Check for common RSS link patterns
        for link in soup.find_all('link', type='application/rss+xml'):
            rss_links.append(link.get('href'))
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if 'rss' in href.lower() or 'feed' in href.lower():
                if not any(href == l for l in rss_links):
                    rss_links.append(href)
        
        # Check for rel="alternate" type="application/rss+xml"
        for link in soup.find_all('link', rel='alternate'):
            if link.get('type') in ['application/rss+xml', 'application/atom+xml']:
                rss_links.append(link.get('href'))
        
        # Remove duplicates and filter for full URLs
        unique_feeds = list(set([r if r.startswith('http') else f"{url.rstrip('/')}/{r.lstrip('/')}" for r in rss_links]))
        
        return unique_feeds
    except Exception as e:
        print(f"  Error: {str(e)}")
        return []

def test_rss_feed(rss_url):
    """Test if RSS feed works and returns items."""
    try:
        print(f"\nTesting RSS feed: {rss_url}")
        response = requests.get(rss_url, timeout=10)
        
        # Try to parse as RSS XML
        root = ET.fromstring(response.text)
        
        # Find items
        items = []
        for item in root.findall('.//item'):
            title = item.find('title')
            link = item.find('link')
            date = item.find('pubDate')
            
            if title is not None and link is not None:
                items.append({
                    'title': title.text,
                    'link': link.text,
                    'date': date.text if date is not None else ''
                })
        
        print(f"  Found {len(items)} items in RSS feed")
        if items:
            print(f"  First few items:")
            for i, item in enumerate(items[:3], 1):
                print(f"    {i}. {item['title'][:60]}")
        
        return len(items) > 0
    except ET.ParseError as e:
        print(f"  Not valid RSS XML: {str(e)}")
        return False
    except Exception as e:
        print(f"  Error: {str(e)}")
        return False

# Main execution
print("=" * 70)
print("RSS FEED DISCOVERY")
print("=" * 70)
print()

# Check each site for RSS feeds
all_feeds = {}
for site, url in sites_to_check.items():
    feeds = find_rss_feeds(url)
    all_feeds[site] = feeds

# Test each RSS feed
print("\n" + "=" * 70)
print("TESTING RSS FEEDS")
print("=" * 70)

working_rss = {}
for site, feeds in all_feeds.items():
    print(f"\n{site.upper()}: {len(feeds)} feeds found")
    
    if feeds:
        working_rss[site] = []
        for i, feed_url in enumerate(feeds, 1):
            print(f"\n  Feed {i}: {feed_url}")
            if test_rss_feed(feed_url):
                working_rss[site].append(feed_url)

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print("\nWorking RSS Feeds:")
if any(working_rss.values()):
    for site, feeds in working_rss.items():
        if feeds:
            print(f"\n{site.upper()}: {len(feeds)} working feeds")
            for i, feed in enumerate(feeds, 1):
                print(f"  {i}. {feed}")
else:
    print("\nNo working RSS feeds found on any site")

print("\n" + "=" * 70)
print("RECOMMENDATION")
print("=" * 70)

if any(working_rss.values()):
    print("\n[SUCCESS] RSS feeds found!")
    print("\nNext steps:")
    print("  1. Update src/main.py to add RSS feed URLs to SITES configuration")
    print("  2. Update scrape_site() function to use RSS for these sites")
    print("  3. Restart server")
    print("  4. RSS feeds are much lighter than scraping!")
else:
    print("\n[NO RSS] No working RSS feeds found")
    print("\nOptions:")
    print("  1. Use current manual entry system (lighter, reliable)")
    print("  2. Try alternative URLs from alternative-urls.md")
    print("  3. Use Playwright/Puppeteer for JavaScript sites (heavier)")
    print("  4. Keep checking manually daily")

print("\n" + "=" * 70)
