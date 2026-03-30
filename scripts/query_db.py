import sqlite3
import json
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / 'data' / 'govupdate.db'
if not DB.exists():
    print('Database not found at', DB)
    raise SystemExit(1)

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

total = cur.execute('SELECT COUNT(*) as cnt FROM updates').fetchone()['cnt']
print('Total updates:', total)

print('\nLast 5 updates:')
for r in cur.execute('SELECT id, site, title, published_at FROM updates ORDER BY published_at DESC LIMIT 5'):
    print(json.dumps(dict(r), ensure_ascii=False))

print('\nCounts by site (top 10):')
for r in cur.execute('SELECT site, COUNT(*) as cnt FROM updates GROUP BY site ORDER BY cnt DESC LIMIT 10'):
    print(json.dumps(dict(r), ensure_ascii=False))

print('\nRecent scraping logs (last 5):')
for r in cur.execute('SELECT site, status, items_found, items_added, started_at FROM scraping_logs ORDER BY started_at DESC LIMIT 5'):
    print(json.dumps(dict(r), ensure_ascii=False))

conn.close()
