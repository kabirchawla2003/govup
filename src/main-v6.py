# GovUpdate API v6.0 - Enhanced with Rate Limiting, More Entities, & Better Error Handling
# Compatible with pydantic 2.5.0

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse
from functools import wraps
import time
import json

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query, Header, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import sqlite3
from collections import defaultdict
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
PORT = int(os.getenv("PORT", 3000))
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "../data/govupdate.db"))
CRON_SCHEDULE = os.getenv("CRON_SCHEDULE", "0 10 * * *")
MAX_REQUESTS_PER_MINUTE = int(os.getenv("MAX_REQUESTS_PER_MINUTE", 60))
MAX_REQUESTS_PER_HOUR = int(os.getenv("MAX_REQUESTS_PER_HOUR", 1000))
SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", 30))
SCRAPER_MAX_RETRIES = int(os.getenv("SCRAPER_MAX_RETRIES", 3))
SCRAPER_RETRY_DELAY = int(os.getenv("SCRAPER_RETRY_DELAY", 2))

# Enhanced site configurations with more circulars
SITES = {
    "sebi": {
        "name": "SEBI",
        "description": "Securities and Exchange Board of India",
        "urls": [
            "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes",
            "https://www.sebi.gov.in/sebiweb/common/sebiCommonListAction.do?doList=true&moduleList=Circulars",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["circular", "notice", "press-release", "order", "regulation"]
    },
    "rbi": {
        "name": "RBI",
        "description": "Reserve Bank of India",
        "urls": [
            "https://www.rbi.org.in/scripts/BS_ViewBS.aspx?Id=1015",
            "https://www.rbi.org.in/scripts/NotificationUser.aspx",
            "https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["circular", "notification", "press-release", "master-direction"]
    },
    "irdai": {
        "name": "IRDAI",
        "description": "Insurance Regulatory and Development Authority",
        "urls": [
            "https://www.irdai.gov.in/",
            "https://www.irdai.gov.in/notifications/circulars",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["circular", "notification", "order", "guideline"]
    },
    "nse": {
        "name": "NSE",
        "description": "National Stock Exchange",
        "urls": [
            "https://www.nseindia.com/market-data/content/notices",
            "https://www.nseindia.com/products/content/circulars.htm",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 3,
        "categories": ["notice", "circular", "settlement-circular"]
    },
    "bse": {
        "name": "BSE",
        "description": "Bombay Stock Exchange",
        "urls": [
            "https://www.bseindia.com/corporates/announcements.html",
            "https://www.bseindia.com/static/circulars/index.html",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 3,
        "categories": ["announcement", "circular", "notice"]
    },
    "cdsl": {
        "name": "CDSL",
        "description": "Central Depository Services (India) Limited",
        "urls": [
            "https://www.cdslindia.com/investorservices/noticesandannouncements",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["notice", "announcement"]
    },
    "nsdl": {
        "name": "NSDL",
        "description": "National Securities Depository Limited",
        "urls": [
            "https://nsdl.co.in/investorservices/noticesandannouncements",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["notice", "announcement"]
    },
    "pfrda": {
        "name": "PFRDA",
        "description": "Pension Fund Regulatory and Development Authority",
        "urls": [
            "https://www.pfrda.org.in/",
            "https://pfrda.org.in/WRMS/StaticPages.aspx?pageid=circulars",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["circular", "notice", "order"]
    },
    "cbdt": {
        "name": "CBDT",
        "description": "Central Board of Direct Taxes",
        "urls": [
            "https://incometaxindia.gov.in/Pages/acts-and-rules/circulars.aspx",
            "https://incometaxindia.gov.in/Pages/notifications/notifications.aspx",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["circular", "notification", "clarification"]
    },
    "cbic": {
        "name": "CBIC",
        "description": "Central Board of Indirect Taxes and Customs",
        "urls": [
            "https://cbic-gst.gov.in/gst-circulars",
            "https://www.cbic.gov.in/",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["circular", "notification", "instruction"]
    },
    "mca": {
        "name": "MCA",
        "description": "Ministry of Corporate Affairs",
        "urls": [
            "https://www.mca.gov.in/content/mca/global/en/notifications/general-circulars.html",
            "https://www.mca.gov.in/content/mca/global/en/home/circulars.html",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["circular", "notification", "general-circular"]
    },
    "mf": {
        "name": "Ministry of Finance",
        "description": "Ministry of Finance, Government of India",
        "urls": [
            "https://finmin.gov.in/",
            "https://finmin.gov.in/notifications/circulars",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["circular", "press-release", "notification"]
    },
    "sebi_sme": {
        "name": "SEBI SME",
        "description": "SEBI - SME Platform and Startup Platform",
        "urls": [
            "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&method=smeListing",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["circular", "notice", "order"]
    },
    "pmla": {
        "name": "FIU-IND",
        "description": "Financial Intelligence Unit - India (PMLA)",
        "urls": [
            "https://fiu-ind.gov.in/",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["circular", "notification", "advisory"]
    },
    "sat": {
        "name": "SAT",
        "description": "Securities Appellate Tribunal",
        "urls": [
            "https://sat.gov.in/",
        ],
        "uses_playwright": False,
        "rate_limit_delay": 2,
        "categories": ["order", "notice", "circular"]
    }
}


# Rate limiting in-memory storage
class RateLimiter:
    """Thread-safe rate limiter using in-memory storage."""
    
    def __init__(self):
        self.requests = defaultdict(lambda: {"count": 0, "reset_time": time.time()})
        self.hourly_requests = defaultdict(lambda: {"count": 0, "reset_time": time.time()})
    
    def is_allowed(self, identifier: str, max_per_minute: int, max_per_hour: int) -> Tuple[bool, Optional[str]]:
        """Check if request is allowed within rate limits."""
        current_time = time.time()
        
        # Check per-minute limit
        minute_data = self.requests[identifier]
        if current_time - minute_data["reset_time"] >= 60:
            minute_data["count"] = 0
            minute_data["reset_time"] = current_time
        
        if minute_data["count"] >= max_per_minute:
            return False, f"Rate limit exceeded: {max_per_minute} requests per minute"
        
        # Check per-hour limit
        hour_data = self.hourly_requests[identifier]
        if current_time - hour_data["reset_time"] >= 3600:
            hour_data["count"] = 0
            hour_data["reset_time"] = current_time
        
        if hour_data["count"] >= max_per_hour:
            return False, f"Rate limit exceeded: {max_per_hour} requests per hour"
        
        # Increment counters
        minute_data["count"] += 1
        hour_data["count"] += 1
        
        return True, None
    
    def get_remaining(self, identifier: str, max_per_minute: int, max_per_hour: int) -> Dict[str, int]:
        """Get remaining request counts."""
        current_time = time.time()
        
        minute_remaining = max_per_minute - self.requests[identifier]["count"]
        if current_time - self.requests[identifier]["reset_time"] >= 60:
            minute_remaining = max_per_minute
        
        hour_remaining = max_per_hour - self.hourly_requests[identifier]["count"]
        if current_time - self.hourly_requests[identifier]["reset_time"] >= 3600:
            hour_remaining = max_per_hour
        
        return {
            "per_minute": minute_remaining,
            "per_hour": hour_remaining
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


# Database setup
def get_db():
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@asynccontextmanager
async def get_db_async():
    """Async context manager for database connections."""
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database tables with enhanced schema."""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        with get_db() as conn:
            # Updates table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS updates (
                    id TEXT PRIMARY KEY,
                    site TEXT NOT NULL,
                    type TEXT NOT NULL,
                    category TEXT,
                    title TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT,
                    summary TEXT,
                    content TEXT,
                    url TEXT NOT NULL UNIQUE,
                    reference_number TEXT,
                    effective_date TEXT,
                    expiry_date TEXT,
                    tags TEXT,
                    priority TEXT DEFAULT 'normal',
                    source TEXT NOT NULL DEFAULT 'scraped',
                    published_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Attachments table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    update_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    filename TEXT,
                    file_type TEXT,
                    file_size INTEGER,
                    FOREIGN KEY (update_id) REFERENCES updates(id) ON DELETE CASCADE
                )
            """)
            
            # API Keys table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT,
                    rate_limit_per_minute INTEGER DEFAULT 60,
                    rate_limit_per_hour INTEGER DEFAULT 1000,
                    requests_count INTEGER DEFAULT 0,
                    last_used TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    expires_at TEXT
                )
            """)
            
            # Webhooks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    site_filter TEXT,
                    type_filter TEXT,
                    category_filter TEXT,
                    api_key TEXT NOT NULL,
                    events TEXT DEFAULT 'new',
                    retry_count INTEGER DEFAULT 3,
                    is_active INTEGER DEFAULT 1,
                    last_triggered TEXT,
                    last_success TEXT,
                    last_failure TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Email subscriptions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS email_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    name TEXT,
                    site_filter TEXT,
                    type_filter TEXT,
                    category_filter TEXT,
                    api_key TEXT NOT NULL,
                    frequency TEXT DEFAULT 'daily',
                    is_active INTEGER DEFAULT 1,
                    last_sent TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Scraping log table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scraping_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site TEXT NOT NULL,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    items_found INTEGER DEFAULT 0,
                    items_added INTEGER DEFAULT 0,
                    error_message TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_seconds REAL
                )
            """)
            
            # Create indexes for performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_updates_date ON updates(date)",
                "CREATE INDEX IF NOT EXISTS idx_updates_type ON updates(type)",
                "CREATE INDEX IF NOT EXISTS idx_updates_site ON updates(site)",
                "CREATE INDEX IF NOT EXISTS idx_updates_category ON updates(category)",
                "CREATE INDEX IF NOT EXISTS idx_updates_source ON updates(source)",
                "CREATE INDEX IF NOT EXISTS idx_updates_published_at ON updates(published_at)",
                "CREATE INDEX IF NOT EXISTS idx_updates_priority ON updates(priority)",
                "CREATE INDEX IF NOT EXISTS idx_updates_url ON updates(url)",
                "CREATE INDEX IF NOT EXISTS idx_attachments_update_id ON attachments(update_id)",
                "CREATE INDEX IF NOT EXISTS idx_webhooks_site ON webhooks(site_filter)",
                "CREATE INDEX IF NOT EXISTS idx_webhooks_type ON webhooks(type_filter)",
                "CREATE INDEX IF NOT EXISTS idx_webhooks_category ON webhooks(category_filter)",
                "CREATE INDEX IF NOT EXISTS idx_email_subscriptions_email ON email_subscriptions(email)",
                "CREATE INDEX IF NOT EXISTS idx_scraping_logs_site ON scraping_logs(site)",
                "CREATE INDEX IF NOT EXISTS idx_scraping_logs_status ON scraping_logs(status)"
            ]
            
            for index in indexes:
                conn.execute(index)
            
            conn.commit()
            logger.info("Database initialized successfully")
            
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


# API Key Management
def generate_api_key() -> str:
    """Generate a new API key."""
    import secrets
    return f"govup_{secrets.token_urlsafe(32)}"


async def validate_api_key(
    request: Request,
    api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """Validate API key from header with rate limiting."""
    
    # Get client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"
    
    # Check rate limit by IP first
    allowed, error_msg = rate_limiter.is_allowed(
        client_ip, 
        MAX_REQUESTS_PER_MINUTE, 
        MAX_REQUESTS_PER_HOUR
    )
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=error_msg,
            headers={
                "X-RateLimit-Limit-Minute": str(MAX_REQUESTS_PER_MINUTE),
                "X-RateLimit-Limit-Hour": str(MAX_REQUESTS_PER_HOUR),
                "Retry-After": "60"
            }
        )
    
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="API key is required. Include X-API-Key header."
        )
    
    async with get_db_async() as conn:
        key_data = conn.execute(
            "SELECT * FROM api_keys WHERE key = ? AND is_active = 1",
            (api_key,)
        ).fetchone()
        
        if not key_data:
            raise HTTPException(
                status_code=403,
                detail="Invalid API key"
            )
        
        # Check if API key is expired
        if key_data['expires_at']:
            expiry = datetime.fromisoformat(key_data['expires_at'])
            if datetime.utcnow() > expiry:
                raise HTTPException(
                    status_code=403,
                    detail="API key has expired"
                )
        
        # Check rate limit for specific API key
        allowed, error_msg = rate_limiter.is_allowed(
            api_key,
            key_data['rate_limit_per_minute'],
            key_data['rate_limit_per_hour']
        )
        
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=error_msg,
                headers={
                    "X-RateLimit-Limit-Minute": str(key_data['rate_limit_per_minute']),
                    "X-RateLimit-Limit-Hour": str(key_data['rate_limit_per_hour']),
                    "Retry-After": "60"
                }
            )
        
        # Update last_used timestamp and request count
        conn.execute(
            "UPDATE api_keys SET last_used = ?, requests_count = requests_count + 1 WHERE key = ?",
            (datetime.utcnow().isoformat(), api_key)
        )
        conn.commit()
        
        return api_key


def create_admin_key():
    """Create admin API key for setup."""
    try:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT * FROM api_keys WHERE name = 'admin'"
            ).fetchone()
            
            if not existing:
                admin_key = generate_api_key()
                conn.execute(
                    "INSERT INTO api_keys (key, name, description, rate_limit_per_minute, rate_limit_per_hour, is_active) VALUES (?, ?, ?, ?, ?, ?)",
                    (admin_key, "admin", "Admin key for initial setup", 120, 5000, 1)
                )
                conn.commit()
                logger.info(f"Admin API key created: {admin_key}")
                return admin_key
            else:
                logger.info(f"Admin key already exists")
                return existing['key']
    except Exception as e:
        logger.error(f"Error creating admin key: {e}")
        raise


# Error handling utilities
class APIError(Exception):
    """Custom API error with status code and details."""
    def __init__(self, status_code: int, message: str, details: Optional[Dict] = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


def handle_api_errors(func):
    """Decorator for consistent error handling."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except APIError as e:
            raise HTTPException(status_code=e.status_code, detail={
                "message": e.message,
                "details": e.details
            })
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except sqlite3.IntegrityError as e:
            raise HTTPException(status_code=409, detail=f"Duplicate entry: {str(e)}")
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Request timeout")
        except httpx.RequestError as e:
            logger.error(f"HTTP request error: {e}")
            raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    
    return wrapper


# Enhanced scraping with retry logic and error handling
async def fetch_with_retry(url: str, client: httpx.AsyncClient, max_retries: int = 3) -> Optional[httpx.Response]:
    """Fetch URL with retry logic."""
    for attempt in range(max_retries):
        try:
            response = await client.get(url, timeout=SCRAPER_TIMEOUT)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP {e.response.status_code} for {url} (attempt {attempt + 1}/{max_retries})")
            if attempt == max_retries - 1:
                raise
        except httpx.TimeoutException:
            logger.warning(f"Timeout for {url} (attempt {attempt + 1}/{max_retries})")
            if attempt == max_retries - 1:
                raise
        except Exception as e:
            logger.error(f"Error fetching {url}: {e} (attempt {attempt + 1}/{max_retries})")
            if attempt == max_retries - 1:
                raise
        
        # Exponential backoff
        await asyncio.sleep(SCRAPER_RETRY_DELAY * (2 ** attempt))
    
    return None


async def scrape_site(site_key: str, site: Dict) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Enhanced scraping with error handling and logging."""
    
    start_time = time.time()
    stats = {
        "status": "success",
        "items_found": 0,
        "items_added": 0,
        "errors": []
    }
    
    try:
        logger.info(f"[{datetime.utcnow().isoformat()}] Scraping {site['name']}...")
        
        all_items = []
        
        async with httpx.AsyncClient(timeout=SCRAPER_TIMEOUT) as client:
            for url in site["urls"]:
                try:
                    # Rate limiting per site
                    if site.get("rate_limit_delay", 0) > 0:
                        await asyncio.sleep(site["rate_limit_delay"])
                    
                    response = await fetch_with_retry(url, client, SCRAPER_MAX_RETRIES)
                    
                    if response:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        items = extract_items_from_soup(soup, url, site_key, site)
                        all_items.extend(items)
                        
                except Exception as e:
                    error_msg = f"Error fetching {url}: {str(e)}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)
        
        # Remove duplicates
        seen = set()
        unique_items = []
        for item in all_items:
            if item['url'] not in seen:
                seen.add(item['url'])
                unique_items.append(item)
        
        stats["items_found"] = len(unique_items)
        
        duration = time.time() - start_time
        
        # Log scraping result
        async with get_db_async() as conn:
            conn.execute("""
                INSERT INTO scraping_logs 
                (site, url, status, items_found, error_message, started_at, completed_at, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                site_key,
                site["urls"][0],
                stats["status"],
                stats["items_found"],
                json.dumps(stats["errors"]) if stats["errors"] else None,
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat(),
                duration
            ))
            conn.commit()
        
        logger.info(f"[{datetime.utcnow().isoformat()}] {site['name']}: Found {len(unique_items)} items in {duration:.2f}s")
        
        return unique_items, stats
        
    except Exception as e:
        stats["status"] = "failed"
        stats["errors"].append(str(e))
        logger.error(f"[{datetime.utcnow().isoformat()}] {site['name']} Error: {str(e)}", exc_info=True)
        
        # Log failure
        try:
            async with get_db_async() as conn:
                conn.execute("""
                    INSERT INTO scraping_logs 
                    (site, url, status, items_found, error_message, started_at, completed_at, duration_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    site_key,
                    site["urls"][0],
                    "failed",
                    0,
                    str(e),
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                    time.time() - start_time
                ))
                conn.commit()
        except Exception as log_error:
            logger.error(f"Failed to log scraping error: {log_error}")
        
        return [], stats


def extract_items_from_soup(soup: BeautifulSoup, base_url: str, site_key: str, site: Dict) -> List[Dict[str, Any]]:
    """Extract items from BeautifulSoup object based on site configuration."""
    items = []
    
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        title = link.get_text(strip=True)
        
        # Skip invalid links
        if not title or not href:
            continue
        if href.startswith('#') or 'javascript:' in href or 'mailto:' in href:
            continue
        if title in ['View All', 'Read More', 'More', 'Click here']:
            continue
        if len(title) < 10:  # Skip very short titles
            continue
        
        # Determine URL
        full_url = href if href.startswith('http') else urljoin(base_url, href)
        
        # Determine category based on URL patterns
        category = 'notice'
        for cat in site.get("categories", []):
            if cat.lower() in full_url.lower() or cat.lower() in title.lower():
                category = cat
                break
        
        # Try to extract date from nearby elements or title
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        date_pattern = r'\d{2}[-/]\d{2}[-/]\d{4}|\d{4}[-/]\d{2}[-/]\d{2}'
        date_match = None
        
        # Check parent element for date
        parent = link.parent
        if parent:
            parent_text = parent.get_text()
            date_match = next(iter([m for m in [None] if m is None]), None)
        
        # Check title for date
        if not date_match:
            import re
            date_match = re.search(date_pattern, title)
            if date_match:
                date_str = date_match.group(0)
        
        items.append({
            'title': title,
            'link': full_url,
            'pub_date': date_str,
            'isoDate': datetime.utcnow().isoformat(),
            'content_snippet': title[:200],
            'category': category,
            'type': category,
            'site': site_key,
            'source': 'scraped'
        })
    
    return items


def generate_id() -> str:
    """Generate unique ID."""
    return f"{int(datetime.utcnow().timestamp() * 1000)}-{os.urandom(4).hex()}"


async def save_update(conn: sqlite3.Connection, item: Dict[str, Any]) -> Optional[str]:
    """Save update to database with enhanced fields."""
    try:
        update_id = generate_id()
        pub_date = item['pub_date']
        date_part = pub_date.split('T')[0] if 'T' in pub_date else pub_date
        time_part = pub_date.split('T')[1].split('.')[0] if 'T' in pub_date else ''
        
        # Insert update
        conn.execute("""
            INSERT INTO updates (id, site, type, category, title, date, time, summary, content, url, 
                               published_at, fetched_at, source, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            update_id,
            item.get('site', 'sebi'),
            item.get('type', 'notice'),
            item.get('category', 'notice'),
            item.get('title'),
            date_part,
            time_part,
            item.get('content_snippet', ''),
            '',
            item.get('link'),
            pub_date,
            datetime.utcnow().isoformat(),
            item.get('source', 'scraped'),
            'normal'
        ))
        
        conn.commit()
        
        # Trigger webhooks and emails
        update_with_id = {**item, 'id': update_id, 'attachments': []}
        asyncio.create_task(trigger_webhook(update_with_id))
        asyncio.create_task(send_email_alert(update_with_id))
        
        return update_id
    except sqlite3.IntegrityError:
        # URL already exists, skip
        return None
    except Exception as e:
        logger.error(f"Error saving update: {e}")
        return None


async def process_all_sites():
    """Fetch and process updates from all sites with enhanced logging."""
    logger.info(f"[{datetime.utcnow().isoformat()}] Starting scheduled check for all sites...")
    
    total_stats = {
        "sites_processed": 0,
        "sites_failed": 0,
        "items_found": 0,
        "items_added": 0
    }
    
    async with get_db_async() as conn:
        for site_key in SITES.keys():
            try:
                items, stats = await scrape_site(site_key, SITES[site_key])
                
                total_stats["sites_processed"] += 1
                total_stats["items_found"] += stats["items_found"]
                
                for item in items:
                    existing = conn.execute(
                        "SELECT id FROM updates WHERE url = ?", (item['link'],)
                    ).fetchone()
                    
                    if not existing:
                        update_id = await save_update(conn, item)
                        if update_id:
                            total_stats["items_added"] += 1
                            logger.info(f"[{datetime.utcnow().isoformat()}] [{site_key.upper()}] New: {item['title'][:60]}...")
                
                if stats["status"] == "failed":
                    total_stats["sites_failed"] += 1
                        
            except Exception as e:
                logger.error(f"[{datetime.utcnow().isoformat()}] {site_key.upper()} Error: {str(e)}", exc_info=True)
                total_stats["sites_failed"] += 1
        
        # Cleanup old items (keep last 6 months)
        six_months_ago = (datetime.utcnow() - timedelta(days=180)).isoformat()
        delete_count = conn.execute(
            "DELETE FROM updates WHERE published_at < ?", (six_months_ago,)
        ).rowcount
        conn.commit()
        
        if delete_count > 0:
            logger.info(f"[{datetime.utcnow().isoformat()}] Cleaned up {delete_count} old items")
        
        logger.info(f"[{datetime.utcnow().isoformat()}] Processing complete. Stats: {json.dumps(total_stats)}")


# Webhook Functions
async def trigger_webhook(update: dict):
    """Trigger webhooks for a new update."""
    try:
        async with get_db_async() as conn:
            webhooks = conn.execute("""
                SELECT * FROM webhooks 
                WHERE is_active = 1 
                AND (site_filter = ? OR site_filter = '' OR site_filter IS NULL)
                AND (type_filter = ? OR type_filter = '' OR type_filter IS NULL)
                AND (category_filter = ? OR category_filter = '' OR category_filter IS NULL)
            """, (update['site'], update['type'], update.get('category', ''))).fetchall()
            
            if not webhooks:
                return
            
            for webhook in webhooks:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.post(
                            webhook['url'],
                            json={
                                'event': 'new_update',
                                'data': update,
                                'timestamp': datetime.utcnow().isoformat()
                            },
                            headers={
                                'Content-Type': 'application/json',
                                'X-GovUpdate-Event': 'new_update'
                            }
                        )
                        
                        # Update webhook statistics
                        if response.status_code < 400:
                            conn.execute("""
                                UPDATE webhooks 
                                SET last_triggered = ?, 
                                    last_success = ?,
                                    success_count = success_count + 1 
                                WHERE id = ?
                            """, (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), webhook['id']))
                        else:
                            conn.execute("""
                                UPDATE webhooks 
                                SET last_triggered = ?, 
                                    last_failure = ?,
                                    failure_count = failure_count + 1 
                                WHERE id = ?
                            """, (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), webhook['id']))
                        
                        conn.commit()
                        
                        logger.info(f"Webhook triggered: {webhook['name']} - {webhook['url']} - {response.status_code}")
                        
                except Exception as e:
                    logger.error(f"Webhook failed: {webhook['name']} - {str(e)}")
                    
    except Exception as e:
        logger.error(f"Error triggering webhooks: {str(e)}")


# Email Functions
async def send_email_alert(update: dict):
    """Send email alert for a new update."""
    try:
        async with get_db_async() as conn:
            subscriptions = conn.execute("""
                SELECT * FROM email_subscriptions 
                WHERE is_active = 1 
                AND (site_filter = ? OR site_filter = '' OR site_filter IS NULL)
                AND (type_filter = ? OR type_filter = '' OR type_filter IS NULL)
                AND (category_filter = ? OR category_filter = '' OR category_filter IS NULL)
            """, (update['site'], update['type'], update.get('category', ''))).fetchall()
            
            if not subscriptions:
                return
            
            for sub in subscriptions:
                try:
                    # TODO: Implement actual email sending
                    logger.info(f"Email alert would be sent to: {sub['email']} - {update['title'][:60]}...")
                    
                    conn.execute("""
                        UPDATE email_subscriptions 
                        SET last_sent = ? 
                        WHERE id = ?
                    """, (datetime.utcnow().isoformat(), sub['id']))
                    conn.commit()
                    
                except Exception as e:
                    logger.error(f"Email failed: {sub['email']} - {str(e)}")
                    
    except Exception as e:
        logger.error(f"Error sending email alerts: {str(e)}")


# FastAPI app
app = FastAPI(
    title="GovUpdate API",
    version="6.0.0",
    description="API for monitoring Indian government and regulatory updates with enhanced features"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add rate limit headers to responses
@app.middleware("http")
async def add_rate_limit_headers(request: Request, call_next):
    """Add rate limit headers to all responses."""
    response = await call_next(request)
    
    # Add remaining rate limit info if available
    response.headers["X-RateLimit-Request-Limit-Minute"] = str(MAX_REQUESTS_PER_MINUTE)
    response.headers["X-RateLimit-Request-Limit-Hour"] = str(MAX_REQUESTS_PER_HOUR)
    
    return response


# Pydantic models with validation
class ManualUpdateRequest(BaseModel):
    site: str = Field(..., description="Site identifier")
    title: str = Field(..., min_length=5, max_length=500, description="Update title")
    url: str = Field(..., description="URL of the update")
    type: Optional[str] = Field("notice", description="Type of update")
    category: Optional[str] = Field(None, description="Category of update")
    date: Optional[str] = Field(None, description="Publication date")
    content: Optional[str] = Field(None, description="Content/description")
    priority: Optional[str] = Field("normal", regex="^(low|normal|high|critical)$", description="Priority level")
    
    @validator('site')
    def validate_site(cls, v):
        if v not in SITES:
            raise ValueError(f"Invalid site: {v}. Must be one of: {list(SITES.keys())}")
        return v


class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Name for the API key")
    description: Optional[str] = Field(None, max_length=500, description="Description")
    rate_limit_per_minute: Optional[int] = Field(60, ge=1, le=1000, description="Requests per minute limit")
    rate_limit_per_hour: Optional[int] = Field(1000, ge=1, le=100000, description="Requests per hour limit")
    expires_at: Optional[str] = Field(None, description="Expiry date (ISO format)")


class CreateWebhookRequest(BaseModel):
    url: str = Field(..., description="Webhook URL")
    name: str = Field(..., min_length=1, max_length=200, description="Webhook name")
    site_filter: Optional[str] = Field(None, description="Filter by site")
    type_filter: Optional[str] = Field(None, description="Filter by type")
    category_filter: Optional[str] = Field(None, description="Filter by category")
    events: str = Field("new", regex="^(new|all)$", description="Events to trigger on")
    retry_count: Optional[int] = Field(3, ge=0, le=10, description="Number of retries")


class CreateEmailSubscriptionRequest(BaseModel):
    email: str = Field(..., regex=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', description="Email address")
    name: str = Field(..., min_length=1, max_length=200, description="Subscriber name")
    site_filter: Optional[str] = Field(None, description="Filter by site")
    type_filter: Optional[str] = Field(None, description="Filter by type")
    category_filter: Optional[str] = Field(None, description="Filter by category")
    frequency: str = Field("daily", regex="^(daily|weekly|instant)$", description="Email frequency")


# API Endpoints
@app.get("/", tags=["General"])
async def root():
    """Root endpoint - API information."""
    return {
        "name": "GovUpdate API",
        "version": "6.0.0",
        "status": "running",
        "description": "API for monitoring Indian government and regulatory updates",
        "features": [
            "Multi-site monitoring (15+ sites)",
            "API key authentication",
            "Rate limiting (per IP and per key)",
            "Manual entry fallback",
            "Daily cron job",
            "Webhook support - real-time notifications",
            "Email alerts - digest notifications",
            "Site, type, and category filtering",
            "Request tracking",
            "Webhook management",
            "Email subscription management",
            "Enhanced error handling",
            "Performance optimizations",
            "Scraping logs and statistics"
        ],
        "sites": [
            {
                "key": key,
                "name": value["name"],
                "description": value.get("description", ""),
                "categories": value.get("categories", [])
            }
            for key, value in SITES.items()
        ],
        "endpoints": {
            "updates": "/api/updates",
            "manual": "/api/manual",
            "status": "/api/status",
            "api_keys": "/api/keys",
            "webhooks": "/api/webhooks",
            "email_subscriptions": "/api/email-subscriptions",
            "scraping_logs": "/api/scraping-logs",
            "docs": "/docs"
        },
        "rate_limits": {
            "default_per_minute": MAX_REQUESTS_PER_MINUTE,
            "default_per_hour": MAX_REQUESTS_PER_HOUR
        }
    }


@app.get("/api/updates", tags=["Updates"])
@handle_api_errors
async def get_updates(
    request: Request,
    site: Optional[str] = None,
    type: Optional[str] = None,
    category: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    priority: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    api_key: str = Depends(validate_api_key)
):
    """Get updates with comprehensive filters."""
    
    async with get_db_async() as conn:
        query = "SELECT * FROM updates WHERE 1=1"
        params = []
        
        # Filters
        if site and site in SITES:
            query += " AND site = ?"
            params.append(site)
        
        if type:
            query += " AND type = ?"
            params.append(type)
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        if since:
            query += " AND date >= ?"
            params.append(since)
        
        if until:
            query += " AND date <= ?"
            params.append(until)
        
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        if search:
            query += " AND (title LIKE ? OR summary LIKE ?)"
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])
        
        query += " ORDER BY published_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = conn.execute(query, params).fetchall()
        
        # Get total count for pagination
        count_query = query.replace("SELECT *", "SELECT COUNT(*)").replace(" LIMIT ? OFFSET ?", "")
        total = conn.execute(count_query, params[:-2]).fetchone()[0]
        
        # Get attachments for each update
        updates = []
        for row in rows:
            attachments = conn.execute(
                "SELECT * FROM attachments WHERE update_id = ?", (row['id'],)
            ).fetchall()
            
            update = dict(row)
            update['attachments'] = [dict(a) for a in attachments]
            updates.append(update)
        
        return {
            "success": True,
            "count": len(updates),
            "total": total,
            "limit": limit,
            "offset": offset,
            "data": updates
        }


@app.get("/api/updates/{update_id}", tags=["Updates"])
@handle_api_errors
async def get_update(
    update_id: str,
    api_key: str = Depends(validate_api_key)
):
    """Get single update by ID."""
    
    async with get_db_async() as conn:
        row = conn.execute(
            "SELECT * FROM updates WHERE id = ?", (update_id,)
        ).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Update not found")
        
        attachments = conn.execute(
            "SELECT * FROM attachments WHERE update_id = ?", (update_id,)
        ).fetchall()
        
        update = dict(row)
        update['attachments'] = [dict(a) for a in attachments]
        
        return {
            "success": True,
            "data": update
        }


@app.post("/api/manual", tags=["Updates"])
@handle_api_errors
async def manual_update(
    request: ManualUpdateRequest,
    api_key: str = Depends(validate_api_key)
):
    """Add manual update."""
    
    pub_date = request.date if request.date else datetime.utcnow().isoformat()
    date_part = pub_date.split('T')[0] if 'T' in pub_date else pub_date
    time_part = pub_date.split('T')[1].split('.')[0] if 'T' in pub_date else ''
    
    item = {
        'site': request.site,
        'title': request.title,
        'link': request.url,
        'type': request.type,
        'category': request.category or request.type,
        'date': date_part,
        'pub_date': pub_date,
        'content_snippet': request.content or request.title,
        'content': request.content or '',
        'source': 'manual',
        'priority': request.priority
    }
    
    async with get_db_async() as conn:
        update_id = await save_update(conn, item)
        
        if not update_id:
            raise HTTPException(status_code=409, detail="Update with this URL already exists")
        
        logger.info(f"[{datetime.utcnow().isoformat()}] Manual entry: {request.title[:60]}... ({request.site})")
        
        return {
            "success": True,
            "message": "Update added successfully",
            "data": {**item, 'id': update_id}
        }


@app.post("/api/keys", tags=["API Keys"])
@handle_api_errors
async def create_api_key(
    request: CreateAPIKeyRequest,
    api_key: str = Depends(validate_api_key)
):
    """Create a new API key (requires admin key)."""
    
    async with get_db_async() as conn:
        # Verify requesting key is admin
        key_data = conn.execute(
            "SELECT * FROM api_keys WHERE key = ? AND name = 'admin'",
            (api_key,)
        ).fetchone()
        
        if not key_data:
            raise HTTPException(
                status_code=403,
                detail="Only admin key can create new API keys"
            )
        
        new_key = generate_api_key()
        
        # Validate expiry date
        expires_at = None
        if request.expires_at:
            try:
                expiry_date = datetime.fromisoformat(request.expires_at)
                if expiry_date <= datetime.utcnow():
                    raise ValueError("Expiry date must be in the future")
                expires_at = request.expires_at
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid expiry date: {str(e)}")
        
        conn.execute("""
            INSERT INTO api_keys (key, name, description, rate_limit_per_minute, rate_limit_per_hour, 
                                created_at, is_active, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_key,
            request.name,
            request.description or '',
            request.rate_limit_per_minute,
            request.rate_limit_per_hour,
            datetime.utcnow().isoformat(),
            1,
            expires_at
        ))
        conn.commit()
        
        logger.info(f"[{datetime.utcnow().isoformat()}] New API key created: {request.name}")
        
        return {
            "success": True,
            "message": "API key created successfully",
            "data": {
                "key": new_key,
                "name": request.name,
                "description": request.description,
                "rate_limit_per_minute": request.rate_limit_per_minute,
                "rate_limit_per_hour": request.rate_limit_per_hour,
                "expires_at": expires_at
            }
        }


@app.get("/api/keys", tags=["API Keys"])
@handle_api_errors
async def list_api_keys(
    api_key: str = Depends(validate_api_key)
):
    """List all API keys (requires admin key)."""
    
    async with get_db_async() as conn:
        key_data = conn.execute(
            "SELECT * FROM api_keys WHERE key = ? AND name = 'admin'",
            (api_key,)
        ).fetchone()
        
        if not key_data:
            raise HTTPException(
                status_code=403,
                detail="Only admin key can list API keys"
            )
        
        keys = conn.execute("""
            SELECT id, name, description, rate_limit_per_minute, rate_limit_per_hour, 
                   requests_count, last_used, created_at, is_active, expires_at 
            FROM api_keys 
            ORDER BY created_at DESC
        """).fetchall()
        
        return {
            "success": True,
            "count": len(keys),
            "data": [dict(k) for k in keys]
        }


@app.delete("/api/keys/{key_id}", tags=["API Keys"])
@handle_api_errors
async def delete_api_key(
    key_id: int,
    api_key: str = Depends(validate_api_key)
):
    """Delete an API key (requires admin key)."""
    
    async with get_db_async() as conn:
        key_data = conn.execute(
            "SELECT * FROM api_keys WHERE key = ? AND name = 'admin'",
            (api_key,)
        ).fetchone()
        
        if not key_data:
            raise HTTPException(
                status_code=403,
                detail="Only admin key can delete API keys"
            )
        
        conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        conn.commit()
        
        logger.info(f"[{datetime.utcnow().isoformat()}] API key deleted: {key_id}")
        
        return {
            "success": True,
            "message": "API key deleted successfully"
        }


@app.post("/api/webhooks", tags=["Webhooks"])
@handle_api_errors
async def create_webhook(
    request: CreateWebhookRequest,
    api_key: str = Depends(validate_api_key)
):
    """Create a new webhook subscription."""
    
    if request.site_filter and request.site_filter not in SITES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid site_filter: {request.site_filter}. Must be one of: {list(SITES.keys())}"
        )
    
    async with get_db_async() as conn:
        conn.execute("""
            INSERT INTO webhooks (url, name, site_filter, type_filter, category_filter, 
                                api_key, events, retry_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.url,
            request.name,
            request.site_filter or '',
            request.type_filter or '',
            request.category_filter or '',
            api_key,
            request.events,
            request.retry_count,
            datetime.utcnow().isoformat()
        ))
        conn.commit()
        
        logger.info(f"[{datetime.utcnow().isoformat()}] Webhook created: {request.name}")
        
        return {
            "success": True,
            "message": "Webhook created successfully",
            "data": {
                "name": request.name,
                "url": request.url,
                "site_filter": request.site_filter,
                "type_filter": request.type_filter,
                "category_filter": request.category_filter,
                "events": request.events,
                "retry_count": request.retry_count
            }
        }


@app.get("/api/webhooks", tags=["Webhooks"])
@handle_api_errors
async def list_webhooks(
    api_key: str = Depends(validate_api_key)
):
    """List all webhooks."""
    
    async with get_db_async() as conn:
        hooks = conn.execute("""
            SELECT id, url, name, site_filter, type_filter, category_filter, events, 
                   retry_count, is_active, last_triggered, last_success, last_failure, 
                   success_count, failure_count, created_at 
            FROM webhooks 
            ORDER BY created_at DESC
        """).fetchall()
        
        return {
            "success": True,
            "count": len(hooks),
            "data": [dict(h) for h in hooks]
        }


@app.delete("/api/webhooks/{webhook_id}", tags=["Webhooks"])
@handle_api_errors
async def delete_webhook(
    webhook_id: int,
    api_key: str = Depends(validate_api_key)
):
    """Delete a webhook."""
    
    async with get_db_async() as conn:
        conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
        conn.commit()
        
        logger.info(f"[{datetime.utcnow().isoformat()}] Webhook deleted: {webhook_id}")
        
        return {
            "success": True,
            "message": "Webhook deleted successfully"
        }


@app.post("/api/email-subscriptions", tags=["Email Subscriptions"])
@handle_api_errors
async def create_email_subscription(
    request: CreateEmailSubscriptionRequest,
    api_key: str = Depends(validate_api_key)
):
    """Create an email subscription."""
    
    if request.site_filter and request.site_filter not in SITES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid site_filter: {request.site_filter}. Must be one of: {list(SITES.keys())}"
        )
    
    async with get_db_async() as conn:
        conn.execute("""
            INSERT INTO email_subscriptions (email, name, site_filter, type_filter, 
                                           category_filter, frequency, api_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.email,
            request.name,
            request.site_filter or '',
            request.type_filter or '',
            request.category_filter or '',
            request.frequency,
            api_key,
            datetime.utcnow().isoformat()
        ))
        conn.commit()
        
        logger.info(f"[{datetime.utcnow().isoformat()}] Email subscription created: {request.email}")
        
        return {
            "success": True,
            "message": "Email subscription created successfully",
            "data": {
                "email": request.email,
                "name": request.name,
                "site_filter": request.site_filter,
                "type_filter": request.type_filter,
                "category_filter": request.category_filter,
                "frequency": request.frequency
            }
        }


@app.get("/api/email-subscriptions", tags=["Email Subscriptions"])
@handle_api_errors
async def list_email_subscriptions(
    api_key: str = Depends(validate_api_key)
):
    """List all email subscriptions."""
    
    async with get_db_async() as conn:
        subs = conn.execute("""
            SELECT id, email, name, site_filter, type_filter, category_filter, 
                   frequency, is_active, last_sent, created_at 
            FROM email_subscriptions 
            ORDER BY created_at DESC
        """).fetchall()
        
        return {
            "success": True,
            "count": len(subs),
            "data": [dict(s) for s in subs]
        }


@app.delete("/api/email-subscriptions/{sub_id}", tags=["Email Subscriptions"])
@handle_api_errors
async def delete_email_subscription(
    sub_id: int,
    api_key: str = Depends(validate_api_key)
):
    """Delete an email subscription."""
    
    async with get_db_async() as conn:
        conn.execute("DELETE FROM email_subscriptions WHERE id = ?", (sub_id,))
        conn.commit()
        
        logger.info(f"[{datetime.utcnow().isoformat()}] Email subscription deleted: {sub_id}")
        
        return {
            "success": True,
            "message": "Email subscription deleted successfully"
        }


@app.get("/api/scraping-logs", tags=["Monitoring"])
@handle_api_errors
async def get_scraping_logs(
    site: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    api_key: str = Depends(validate_api_key)
):
    """Get scraping logs with optional site filter."""
    
    async with get_db_async() as conn:
        query = "SELECT * FROM scraping_logs WHERE 1=1"
        params = []
        
        if site and site in SITES:
            query += " AND site = ?"
            params.append(site)
        
        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        logs = conn.execute(query, params).fetchall()
        
        return {
            "success": True,
            "count": len(logs),
            "data": [dict(l) for l in logs]
        }


@app.get("/api/status", tags=["Monitoring"])
@handle_api_errors
async def get_status(
    request: Request,
    api_key: str = Depends(validate_api_key)
):
    """Get comprehensive API status and stats."""
    
    async with get_db_async() as conn:
        # Database stats
        last_update = conn.execute(
            "SELECT published_at FROM updates ORDER BY published_at DESC LIMIT 1"
        ).fetchone()
        
        total_updates = conn.execute(
            "SELECT COUNT(*) as count FROM updates"
        ).fetchone()
        
        # Site-wise counts
        site_counts = {}
        site_type_counts = {}
        for site_key in SITES.keys():
            count = conn.execute(
                "SELECT COUNT(*) as count FROM updates WHERE site = ?", (site_key,)
            ).fetchone()
            site_counts[site_key] = count['count'] if count else 0
            
            # Type breakdown per site
            type_counts = conn.execute(
                "SELECT type, COUNT(*) as count FROM updates WHERE site = ? GROUP BY type",
                (site_key,)
            ).fetchall()
            site_type_counts[site_key] = {tc['type']: tc['count'] for tc in type_counts}
        
        # Overall type counts
        type_counts = conn.execute(
            "SELECT type, COUNT(*) as count FROM updates GROUP BY type"
        ).fetchall()
        
        # API key stats
        key_stats = conn.execute(
            "SELECT COUNT(*) as count, SUM(requests_count) as total_requests FROM api_keys WHERE is_active = 1"
        ).fetchone()
        
        # Webhook stats
        webhook_stats = conn.execute(
            "SELECT COUNT(*) as count, SUM(success_count) as successes, SUM(failure_count) as failures FROM webhooks WHERE is_active = 1"
        ).fetchone()
        
        # Email subscription stats
        email_stats = conn.execute(
            "SELECT COUNT(*) as count FROM email_subscriptions WHERE is_active = 1"
        ).fetchone()
        
        # Recent scraping logs
        recent_logs = conn.execute("""
            SELECT site, status, items_found, items_added, started_at 
            FROM scraping_logs 
            ORDER BY started_at DESC 
            LIMIT 10
        """).fetchall()
        
        # Get rate limit info for current key
        client_ip = request.client.host if request.client else "unknown"
        rate_remaining = rate_limiter.get_remaining(
            client_ip,
            MAX_REQUESTS_PER_MINUTE,
            MAX_REQUESTS_PER_HOUR
        )
        
        key_rate_remaining = rate_limiter.get_remaining(
            api_key,
            100,  # Default limits if key data not available
            1000
        )
        
        return {
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "6.0.0",
            "database": {
                "last_update": last_update['published_at'] if last_update else None,
                "total_updates": total_updates['count'] if total_updates else 0,
                "site_counts": site_counts,
                "site_type_breakdown": site_type_counts,
                "type_counts": {tc['type']: tc['count'] for tc in type_counts} if type_counts else {}
            },
            "api_keys": {
                "active_count": key_stats['count'] if key_stats else 0,
                "total_requests": key_stats['total_requests'] if key_stats else 0
            },
            "webhooks": {
                "active_count": webhook_stats['count'] if webhook_stats else 0,
                "total_successes": webhook_stats['successes'] if webhook_stats else 0,
                "total_failures": webhook_stats['failures'] if webhook_stats else 0
            },
            "email_subscriptions": {
                "active_count": email_stats['count'] if email_stats else 0
            },
            "sites": SITES,
            "rate_limits": {
                "ip_based": {
                    "remaining_per_minute": rate_remaining["per_minute"],
                    "remaining_per_hour": rate_remaining["per_hour"],
                    "limit_per_minute": MAX_REQUESTS_PER_MINUTE,
                    "limit_per_hour": MAX_REQUESTS_PER_HOUR
                },
                "api_key_based": {
                    "remaining_per_minute": key_rate_remaining["per_minute"],
                    "remaining_per_hour": key_rate_remaining["per_hour"]
                }
            },
            "recent_scraping_logs": [dict(l) for l in recent_logs]
        }


# Scheduler
scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    logger.info("Initializing GovUpdate API v6.0...")
    init_db()
    
    # Create admin key
    admin_key = create_admin_key()
    print("\n" + "=" * 80)
    print("IMPORTANT: ADMIN API KEY CREATED")
    print("=" * 80)
    print(f"Admin Key: {admin_key}")
    print("\nFeatures in v6.0:")
    print("  ✓ Rate limiting (per IP and per API key)")
    print("  ✓ 15+ regulatory and government sites monitored")
    print("  ✓ Enhanced error handling and retry logic")
    print("  ✓ Scraping logs and statistics")
    print("  ✓ Webhook and email notifications")
    print("  ✓ Comprehensive filtering options")
    print("  ✓ Performance optimizations")
    print("\nUse this admin key to:")
    print("  - Create additional API keys via POST /api/keys")
    print("  - Create webhook subscriptions via POST /api/webhooks")
    print("  - Create email subscriptions via POST /api/email-subscriptions")
    print("  - Monitor scraping logs via GET /api/scraping-logs")
    print("  - View comprehensive status via GET /api/status")
    print("\nAll protected endpoints require X-API-Key header")
    print("=" * 80 + "\n")
    
    # Initial fetch
    logger.info("Starting initial fetch...")
    await process_all_sites()
    
    # Schedule daily check
    scheduler.add_job(
        process_all_sites,
        CronTrigger.from_crontab(CRON_SCHEDULE),
        id='daily_scrape',
        name='Daily scrape of all government sites',
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Scheduler started with cron: {CRON_SCHEDULE}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down scheduler...")
    scheduler.shutdown()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting GovUpdate API v6.0 on port {PORT}")
    logger.info(f"API available at: http://localhost:{PORT}/api/updates")
    logger.info(f"Monitoring {len(SITES)} sites: {', '.join(SITES.keys())}")
    logger.info(f"Rate limits: {MAX_REQUESTS_PER_MINUTE}/min, {MAX_REQUESTS_PER_HOUR}/hour")
    
    uvicorn.run(app, host="0.0.0.0", port=PORT)
