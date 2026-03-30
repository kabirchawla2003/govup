import sqlite3
import time
import json
import importlib.util
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / 'data' / 'govupdate.db'
MODULE_PATH = Path(__file__).resolve().parents[1] / 'src' / 'main-v7-final-working.py'

if not DB.exists():
    print('Database not found at', DB)
    raise SystemExit(1)

print('Using DB:', DB)
conn = sqlite3.connect(str(DB))
cur = conn.cursor()

print('\nCreating indexes (if not exist)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_updates_published_at ON updates(published_at)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_updates_site ON updates(site)')
conn.commit()

print('\nIndexes now:')
for row in cur.execute("PRAGMA index_list('updates')"):
    print(dict(enumerate(row)))

# Load module and run process_all_sites()
print('\nLoading scraper module...')
spec = importlib.util.spec_from_file_location('govupdate_main', str(MODULE_PATH))
module = importlib.util.module_from_spec(spec)
sys.modules['govupdate_main'] = module
spec.loader.exec_module(module)

process_all_sites = module.process_all_sites

print('\nRunning benchmark: one full run of process_all_sites()')
start = time.time()
try:
    import asyncio
    asyncio.run(process_all_sites())
except Exception as e:
    print('Error running process_all_sites():', e)
end = time.time()

print(f'Benchmark duration: {end - start:.2f} seconds')

# Read latest scraping log summary
for row in cur.execute('SELECT COUNT(*) as cnt FROM scraping_logs'):
    total_logs = row[0]
print('Total scraping log entries:', total_logs)
print('\nMost recent scraping log:')
for r in cur.execute('SELECT site, status, items_found, items_added, started_at FROM scraping_logs ORDER BY started_at DESC LIMIT 1'):
    print(json.dumps(dict(r), default=str, ensure_ascii=False))

conn.close()
