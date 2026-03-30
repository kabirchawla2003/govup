import asyncio
import json
import importlib.util
from pathlib import Path
import sys

MODULE_PATH = Path(__file__).resolve().parents[1] / 'src' / 'main-v7-final-working.py'

spec = importlib.util.spec_from_file_location('govupdate_main', str(MODULE_PATH))
module = importlib.util.module_from_spec(spec)
sys.modules['govupdate_main'] = module
spec.loader.exec_module(module)

scrape_site = module.scrape_site
SITES = module.SITES

async def run(site_key):
    site = SITES.get(site_key)
    if not site:
        print('Site key not found:', site_key)
        return
    items, stats = await scrape_site(site_key, site)
    print('Site:', site_key)
    print('Stats:', stats)
    print('Items found:', len(items))
    for i, item in enumerate(items[:10]):
        print(json.dumps(item, ensure_ascii=False))

if __name__ == '__main__':
    key = sys.argv[1] if len(sys.argv) > 1 else 'rbi'
    asyncio.run(run(key))
