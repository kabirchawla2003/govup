#!/usr/bin/env python3
import asyncio
import time
import importlib.util

spec = importlib.util.spec_from_file_location('m', 'src/main-v7-final-working.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

async def test_all_sites():
    working = []
    failed = []
    
    sites_list = sorted(m.SITES.items())
    total = len(sites_list)
    
    print(f"\nTesting {total} sites with Playwright (8s timeout each)...\n")
    
    for idx, (site_key, site_config) in enumerate(sites_list, 1):
        url = site_config['urls'][0]
        name = site_config['name']
        
        # Print progress without newline
        print(f"[{idx:2d}/{total}] {site_key:15} {name:30} ", end='', flush=True)
        
        start = time.time()
        try:
            html = await m.scrape_with_playwright(url, site_key, timeout=8)
            dur = time.time() - start
            
            if html and len(html) > 100:
                working.append((site_key, name, dur, len(html)))
                print(f"OK {dur:5.1f}s {len(html):8,}b")
            else:
                failed.append((site_key, name, dur, "No content"))
                print(f"FAIL {dur:5.1f}s")
        except Exception as e:
            dur = time.time() - start
            failed.append((site_key, name, dur, str(e)[:30]))
            print(f"ERR  {dur:5.1f}s")
    
    # Print summary
    print("\n" + "="*80)
    print(f"SUMMARY: {len(working)}/{total} working ({100*len(working)/total:.0f}%)")
    print("="*80)
    
    if working:
        print(f"\nWORKING ({len(working)} sites):")
        for sk, n, dur, sz in sorted(working, key=lambda x: x[2])[:10]:
            print(f"  {sk:15} {dur:5.1f}s {sz:,} bytes")
        if len(working) > 10:
            print(f"  ... and {len(working)-10} more")
    
    if failed:
        print(f"\nFAILED ({len(failed)} sites):")
        for sk, n, dur, err in sorted(failed, key=lambda x: x[2], reverse=True)[:10]:
            print(f"  {sk:15} {dur:5.1f}s")
        if len(failed) > 10:
            print(f"  ... and {len(failed)-10} more")
    
    return working, failed

if __name__ == "__main__":
    w, f = asyncio.run(test_all_sites())
