# GovUpdate API v3.0 - API Key Authentication
# Compatible with working pydantic 2.5.0

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse
from functools import wraps

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import sqlite3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PORT = int(os.getenv("PORT", 3000))
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "../data/govupdate.db"))
CRON_SCHEDULE = os.getenv("CRON_SCHEDULE", "0 10 * * *")

# Site configurations
SITES = {
    "sebi": {
        "name": "SEBI",
        "url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes",
        "uses_playwright": False
    },
    "nse": {
        "name": "NSE",
        "url": "https://www.nseindia.com/market-data/content/notices",
        "uses_playwright": False  # Manual entry only
    },
    "bse": {
        "name": "BSE",
        "url": "https://www.bseindia.com/corporates/announcements.html",
        "uses_playwright": False  # Manual entry only
    },
    "cdsl": {
        "name": "CDSL",
        "url": "https://www.cdslindia.com/investorservices/noticesandannouncements",
        "uses_playwright": False  # Manual entry only
    },
    "nsdl": {
        "name": "NSDL",
        "url": "https://nsdl.co.in/investorservices/noticesandannouncements",
        "uses_playwright": False  # Manual entry only
    },
    "pfrda": {
        "name": "PFRDA",
        "url": "https://www.pfrda.org.in/",
        "uses_playwright": False
    }
}


# Database setup
def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS updates (
                id TEXT PRIMARY KEY,
                site TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT,
                summary TEXT,
                content TEXT,
                url TEXT NOT NULL,
                category TEXT,
                published_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL DEFAULT 'scraped'
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_id TEXT NOT NULL,
                url TEXT NOT NULL,
                filename TEXT,
                type TEXT,
                FOREIGN KEY (update_id) REFERENCES updates(id) ON DELETE CASCADE
            )
        """)
        
        # API Keys table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                name TEXT,
                description TEXT,
                requests_count INTEGER DEFAULT 0,
                last_used TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Create indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_updates_date ON updates(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_updates_type ON updates(type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_updates_site ON updates(site)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_updates_source ON updates(source)")
        conn.commit()


# API Key Management
def validate_api_key(api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """Validate API key from header."""
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="API key is required. Include X-API-Key header."
        )
    
    with get_db() as conn:
        key_data = conn.execute(
            "SELECT * FROM api_keys WHERE key = ? AND is_active = 1",
            (api_key,)
        ).fetchone()
        
        if not key_data:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        
        # Update last_used timestamp
        conn.execute(
            "UPDATE api_keys SET last_used = ?, requests_count = requests_count + 1 WHERE key = ?",
            (datetime.utcnow().isoformat(), api_key)
        )
        conn.commit()
        
        return api_key


def generate_api_key() -> str:
    """Generate a new API key."""
    import secrets
    return f"govup_{secrets.token_urlsafe(32)}"


def create_admin_key():
    """Create admin API key for setup."""
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM api_keys WHERE name = 'admin'"
        ).fetchone()
        
        if not existing:
            admin_key = generate_api_key()
            conn.execute(
                "INSERT INTO api_keys (key, name, description, is_active) VALUES (?, ?, ?, ?)",
                (admin_key, "admin", "Admin key for initial setup", 1)
            )
            conn.commit()
            logger.info(f"Admin API key created: {admin_key}")
            return admin_key
        else:
            logger.info(f"Admin key already exists")
            return existing['key']


# Scraping functions
async def scrape_site(site_key: str, site: Dict) -> List[Dict[str, Any]]:
    """Scrape updates from a site."""
    
    try:
        logger.info(f"[{datetime.utcnow().isoformat()}] Scraping {site['name']}...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(site["url"])
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
                
                full_url = href if href.startswith('http') else urljoin(site["url"], href)
                
                items.append({
                    'title': title,
                    'link': full_url,
                    'pub_date': datetime.utcnow().strftime('%Y-%m-%d'),
                    'isoDate': datetime.utcnow().isoformat(),
                    'content_snippet': title,
                    'category': site['name'],
                    'type': 'notice',
                    'site': site_key,
                    'source': 'scraped'
                })
            
            seen = set()
            unique_items = [item for item in items if not (item['link'] in seen or seen.add(item['link']))]
            
            logger.info(f"[{datetime.utcnow().isoformat()}] {site['name']}: Found {len(unique_items)} items")
            
            return unique_items
            
    except Exception as e:
        logger.error(f"[{datetime.utcnow().isoformat()}] {site['name']} Error: {str(e)}")
        return []


def generate_id() -> str:
    """Generate unique ID."""
    return f"{int(datetime.utcnow().timestamp() * 1000)}-{os.urandom(4).hex()}"


def save_update(conn: sqlite3.Connection, item: Dict[str, Any]) -> Optional[str]:
    """Save update to database."""
    try:
        update_id = generate_id()
        pub_date = item['pub_date']
        date_part = pub_date.split('T')[0] if 'T' in pub_date else pub_date
        time_part = pub_date.split('T')[1].split('.')[0] if 'T' in pub_date else ''
        
        conn.execute("""
            INSERT INTO updates (id, site, type, title, date, time, summary, content, url, category, published_at, fetched_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            update_id,
            item.get('site', 'sebi'),
            item.get('type', 'notice'),
            item.get('title'),
            date_part,
            time_part,
            item.get('content_snippet', ''),
            '',
            item.get('link'),
            item.get('category', ''),
            pub_date,
            datetime.utcnow().isoformat(),
            item.get('source', 'scraped')
        ))
        
        conn.commit()
        return update_id
    except Exception as e:
        logger.error(f"Error saving update: {e}")
        return None


async def process_all_sites():
    """Fetch and process updates from all sites."""
    logger.info(f"[{datetime.utcnow().isoformat()}] Starting scheduled check for all sites...")
    
    with get_db() as conn:
        for site_key in SITES.keys():
            try:
                logger.info(f"[{datetime.utcnow().isoformat()}] Processing {site_key}...")
                items = await scrape_site(site_key, SITES[site_key])
                
                for item in items:
                    existing = conn.execute(
                        "SELECT id FROM updates WHERE url = ?", (item['link'],)
                    ).fetchone()
                    
                    if not existing:
                        logger.info(f"[{datetime.utcnow().isoformat()}] [{site_key.upper()}] New item: {item['title'][:60]}...")
                        save_update(conn, {
                            ...item,
                            site: site_key,
                            source: 'scraped'
                        })
                        
            except Exception as e:
                logger.error(f"[{datetime.utcnow().isoformat()}] {site_key.upper()}] Error: {str(e)}")
        
        six_months_ago = (datetime.utcnow() - timedelta(days=180)).isoformat()
        delete_count = conn.execute(
            "DELETE FROM updates WHERE published_at < ?", (six_months_ago,)
        ).rowcount
        conn.commit()
        
        if delete_count > 0:
            logger.info(f"[{datetime.utcnow().isoformat()}] Cleaned up {delete_count} old items")


# FastAPI app
app = FastAPI(title="GovUpdate API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class ManualUpdateRequest(BaseModel):
    site: str
    title: str
    url: str
    type: Optional[str] = "notice"
    date: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None


class CreateAPIKeyRequest(BaseModel):
    name: str
    description: Optional[str] = None


# API Endpoints
@app.get("/")
async def root():
    """Root endpoint - list available sites."""
    return {
        "name": "GovUpdate API",
        "version": "3.0.0",
        "status": "running",
        "features": [
            "Multi-site monitoring (6 sites)",
            "API key authentication",
            "Manual entry fallback for all sites",
            "Daily cron job",
            "Clean JSON output",
            "Site and type filtering"
        ],
        "sites": list(SITES.keys()),
        "endpoints": {
            "updates": "/api/updates",
            "manual": "/api/manual",
            "status": "/api/status",
            "api_keys": "/api/keys",
            "docs": "/api/docs"
        }
    }


@app.get("/api/updates")
async def get_updates(
    site: Optional[str] = None,
    since: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 50,
    api_key: str = Depends(validate_api_key)
):
    """Get all updates with optional filters."""
    try:
        with get_db() as conn:
            query = "SELECT * FROM updates WHERE 1=1"
            params = []
            
            if site and site in SITES:
                query += " AND site = ?"
                params.append(site)
            
            if since:
                query += " AND date >= ?"
                params.append(since)
            
            if type:
                query += " AND type = ?"
                params.append(type)
            
            query += " ORDER BY published_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            
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
                "data": updates
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GET /api/updates error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/updates/{update_id}")
async def get_update(
    update_id: str,
    api_key: str = Depends(validate_api_key)
):
    """Get single update by ID."""
    try:
        with get_db() as conn:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GET /api/updates/{update_id} error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/manual")
async def manual_update(
    request: ManualUpdateRequest,
    api_key: str = Depends(validate_api_key)
):
    """Add manual update for sites."""
    try:
        if request.site not in SITES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid site: {request.site}. Must be one of: {list(SITES.keys())}"
            )
        
        pub_date = request.date if request.date else datetime.utcnow().isoformat()
        date_part = pub_date.split('T')[0] if 'T' in pub_date else pub_date
        time_part = pub_date.split('T')[1].split('.')[0] if 'T' in pub_date else ''
        
        item = {
            'site': request.site,
            'title': request.title,
            'link': request.url,
            'type': request.type,
            'date': date_part,
            'pub_date': pub_date,
            'content_snippet': request.title,
            'content': request.content or '',
            'category': request.category or '',
            'source': 'manual'
        }
        
        with get_db() as conn:
            update_id = save_update(conn, item)
            
        logger.info(f"[{datetime.utcnow().isoformat()}] Manual entry: {request.title[:60]}... ({request.site})")
        
        return {
            "success": True,
            "message": "Update added successfully",
            "data": {**item, 'id': update_id}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"POST /api/manual error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/keys")
async def create_api_key(
    request: CreateAPIKeyRequest,
    api_key: str = Depends(validate_api_key)
):
    """Create a new API key (requires admin key)."""
    try:
        # Verify requesting key is admin
        with get_db() as conn:
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
            
            conn.execute(
                "INSERT INTO api_keys (key, name, description, created_at) VALUES (?, ?, ?, ?)",
                (new_key, request.name, request.description or '')
            )
            conn.commit()
            
            logger.info(f"[{datetime.utcnow().isoformat()}] New API key created: {request.name}")
            
            return {
                "success": True,
                "message": "API key created successfully",
                "data": {
                    "key": new_key,
                    "name": request.name,
                    "description": request.description
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"POST /api/keys error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/keys")
async def list_api_keys(
    api_key: str = Depends(validate_api_key)
):
    """List all API keys (requires admin key)."""
    try:
        # Verify admin key
        with get_db() as conn:
            key_data = conn.execute(
                "SELECT * FROM api_keys WHERE key = ? AND name = 'admin'",
                (api_key,)
            ).fetchone()
            
            if not key_data:
                raise HTTPException(
                    status_code=403,
                    detail="Only admin key can list API keys"
                )
            
            keys = conn.execute(
                "SELECT id, name, description, requests_count, last_used, created_at, is_active FROM api_keys ORDER BY created_at DESC"
            ).fetchall()
            
            return {
                "success": True,
                "count": len(keys),
                "data": [dict(k) for k in keys]
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GET /api/keys error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.delete("/api/keys/{key_id}")
async def delete_api_key(
    key_id: int,
    api_key: str = Depends(validate_api_key)
):
    """Delete an API key (requires admin key)."""
    try:
        # Verify admin key
        with get_db() as conn:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"DELETE /api/keys/{key_id} error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/status")
async def get_status(api_key: str = Depends(validate_api_key)):
    """Get API status and stats."""
    try:
        with get_db() as conn:
            last_update = conn.execute(
                "SELECT published_at FROM updates ORDER BY published_at DESC LIMIT 1"
            ).fetchone()
            
            total_updates = conn.execute(
                "SELECT COUNT(*) as count FROM updates"
            ).fetchone()
            
            site_counts = {}
            for site_key in SITES.keys():
                count = conn.execute(
                    "SELECT COUNT(*) as count FROM updates WHERE site = ?", (site_key,)
                ).fetchone()
                site_counts[site_key] = count['count'] if count else 0
            
            key_count = conn.execute(
                "SELECT COUNT(*) as count FROM api_keys WHERE is_active = 1"
            ).fetchone()
            
            return {
                "success": True,
                "last_check": datetime.utcnow().isoformat(),
                "last_update": last_update['published_at'] if last_update else None,
                "total_updates": total_updates['count'] if total_updates else 0,
                "sites": SITES,
                "site_counts": site_counts,
                "api_keys_count": key_count['count'] if key_count else 0
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GET /api/status error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Scheduler
scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    logger.info("Initializing GovUpdate API v3.0...")
    init_db()
    
    # Create admin key
    admin_key = create_admin_key()
    print("\n" + "=" * 70)
    print("IMPORTANT: ADMIN API KEY CREATED")
    print("=" * 70)
    print(f"Admin Key: {admin_key}")
    print("Use this key to create additional API keys via POST /api/keys")
    print("Include X-API-Key header in all requests")
    print("=" * 70 + "\n")
    
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
    logger.info(f"Starting server on port {PORT}")
    logger.info(f"API available at: http://localhost:{PORT}/api/updates")
    logger.info(f"Supported sites: {', '.join(SITES.keys())}")
    logger.info(f"Features: API key authentication, Manual entry")
    
    uvicorn.run(app, host="0.0.0.0", port=PORT)
