import asyncio
import time
import importlib.util
from pathlib import Path

# Load main module
spec = importlib.util.spec_from_file_location('m', 'src/main-v7-final-working.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

async def test_all_sites_playwright():
    """Test Playwright scraping on all sites"""
    results = {
        "working": [],
        "failed": [],
        "errors": {}
    }
    
    print("\n" + "="*80)
    print("TESTING PLAYWRIGHT FOR ALL 34 SITES")
    print("="*80 + "\n")
    
    for site_key, site_config in m.SITES.items():
        url = site_config["urls"][0]
        print(f"Testing {site_key:15} ({site_config['name']:25}) ... ", end="", flush=True)
        
        start = time.time()
        try:
            html = await m.scrape_with_playwright(url, site_key, timeout=20)
        except Exception as e:
            html = None
            error = str(e)
        duration = time.time() - start
        
        if html and len(html) > 100:  # assume valid HTML
            results["working"].append({
                "site": site_key,
                "name": site_config['name'],
                "duration": duration,
                "html_size": len(html)
            })
            print(f"OK ({duration:.1f}s, {len(html):,} chars)")
        else:
            results["failed"].append({
                "site": site_key,
                "name": site_config['name'],
                "duration": duration
            })
            print(f"FAILED ({duration:.1f}s)")
            results["errors"][site_key] = html if html else error if 'error' in locals() else "No HTML"
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"\nTotal sites tested: {len(m.SITES)}")
    print(f"Working:           {len(results['working'])} sites")
    print(f"Failed:            {len(results['failed'])} sites")
    
    if results['working']:
        print("\nWORKING SITES:")
        for r in sorted(results['working'], key=lambda x: x['duration']):
            print(f"  {r['site']:15} {r['name']:30} {r['duration']:6.1f}s")
    
    if results['failed']:
        print("\nFAILED SITES:")
        for r in sorted(results['failed'], key=lambda x: x['duration'], reverse=True):
            print(f"  {r['site']:15} {r['name']:30} {r['duration']:6.1f}s")
    
    return results

if __name__ == "__main__":
    # ensure asyncio event loop is not already running
    results = asyncio.run(test_all_sites_playwright())
