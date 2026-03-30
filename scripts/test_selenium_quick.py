import time
import importlib.util

# Load main module
spec = importlib.util.spec_from_file_location('m', 'src/main-v7-final-working.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Test just a few key sites
test_sites = ['sebi', 'nse', 'mca', 'irdai', 'rbi']

print("\n" + "="*80)
print("TESTING SELENIUM FOR KEY SITES (QUICK TEST)")
print("="*80 + "\n")

results = {"working": [], "failed": []}

for site_key in test_sites:
    if site_key not in m.SITES:
        continue
    
    site_config = m.SITES[site_key]
    url = site_config["urls"][0]
    print(f"Testing {site_key:15} ({site_config['name']:25}) at {url[:40]:<40} ... ", 
          end="", flush=True)
    
    start = time.time()
    html = m.scrape_with_selenium(url, site_key, timeout=15)
    duration = time.time() - start
    
    if html and len(html) > 500:
        results["working"].append((site_key, site_config['name'], duration, len(html)))
        print(f"OK ({duration:.1f}s, {len(html):,} chars)")
    else:
        html_size = len(html) if html else 0
        results["failed"].append((site_key, site_config['name'], duration, html_size))
        print(f"FAILED ({duration:.1f}s, {html_size:,} chars)")

print("\n" + "="*80)
print("RESULTS")
print("="*80)
print(f"\nWorking: {len(results['working'])} / {len(test_sites)}")
if results['working']:
    for site, name, duration, size in results['working']:
        print(f"  [OK] {site:15} {name:30} {duration:6.1f}s  ({size:,} chars)")

if results['failed']:
    print(f"\nFailed: {len(results['failed'])} / {len(test_sites)}")
    for site, name, duration, size in results['failed']:
        print(f"  [X]  {site:15} {name:30} {duration:6.1f}s  ({size:,} chars)")
