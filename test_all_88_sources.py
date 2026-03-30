"""
Comprehensive test of all 88 sources in v9 API
Tests each source and categorizes results
"""
import sys
import asyncio
import time
sys.path.insert(0, 'src')

from importlib import util
import os

# Import v9
spec = util.spec_from_file_location('main_v9', 'src/main-v9-broker-enhanced.py')
main_v9 = util.module_from_spec(spec)
spec.loader.exec_module(main_v9)

async def test_all_sources():
    print("="*80)
    print("COMPREHENSIVE SCRAPER TEST - ALL 88 SOURCES")
    print("="*80)
    print(f"\nTotal sources configured: {len(main_v9.SITES)}\n")

    results = {
        'working': [],
        'blocked': [],
        'needs_selectors': [],
        'errors': [],
        'dns_errors': []
    }

    all_sites = list(main_v9.SITES.keys())

    for idx, site_key in enumerate(all_sites, 1):
        site = main_v9.SITES[site_key]
        print(f"\n[{idx}/{len(all_sites)}] Testing {site_key} ({site['name']})...")

        try:
            start_time = time.time()
            items, stats = await main_v9.scrape_site(site_key, site)
            duration = time.time() - start_time
            count = stats.get('items_found', 0)

            if count > 0:
                results['working'].append({
                    'site': site_key,
                    'name': site['name'],
                    'count': count,
                    'duration': f"{duration:.2f}s"
                })
                print(f"  [OK] Found {count} items in {duration:.2f}s")
                if items:
                    print(f"  Sample: {items[0]['title'][:70]}...")
            else:
                results['needs_selectors'].append({
                    'site': site_key,
                    'name': site['name'],
                    'duration': f"{duration:.2f}s"
                })
                print(f"  [WARN] Connected but 0 items (needs site-specific selectors)")

        except Exception as e:
            error_msg = str(e)

            if '403' in error_msg or 'Forbidden' in error_msg:
                results['blocked'].append({
                    'site': site_key,
                    'name': site['name'],
                    'error': '403 Forbidden (anti-bot)'
                })
                print(f"  [BLOCKED] 403 Forbidden - anti-bot protection active")

            elif 'getaddrinfo failed' in error_msg or 'ERR_NAME_NOT_RESOLVED' in error_msg:
                results['dns_errors'].append({
                    'site': site_key,
                    'name': site['name'],
                    'error': 'DNS resolution failed'
                })
                print(f"  [DNS ERROR] Site may be down or URL incorrect")

            else:
                results['errors'].append({
                    'site': site_key,
                    'name': site['name'],
                    'error': error_msg[:100]
                })
                print(f"  [ERROR] {error_msg[:100]}")

    # Print comprehensive summary
    print("\n" + "="*80)
    print("FINAL RESULTS - ALL 88 SOURCES TESTED")
    print("="*80)

    total_working = len(results['working'])
    total_circulars = sum(r['count'] for r in results['working'])
    success_rate = (total_working / len(all_sites)) * 100

    print(f"\n[SUMMARY]")
    print(f"  Working sources: {total_working}/88 ({success_rate:.1f}%)")
    print(f"  Total circulars found: {total_circulars:,}")
    print(f"  Blocked (403): {len(results['blocked'])}")
    print(f"  Need selectors: {len(results['needs_selectors'])}")
    print(f"  DNS errors: {len(results['dns_errors'])}")
    print(f"  Other errors: {len(results['errors'])}")

    # Top performers
    if results['working']:
        print(f"\n[TOP 10 SOURCES BY CIRCULAR COUNT]")
        top_10 = sorted(results['working'], key=lambda x: x['count'], reverse=True)[:10]
        for i, r in enumerate(top_10, 1):
            print(f"  {i}. {r['name']}: {r['count']:,} circulars ({r['duration']})")

    # Working sources
    if results['working']:
        print(f"\n[ALL WORKING SOURCES] ({len(results['working'])})")
        for r in sorted(results['working'], key=lambda x: x['count'], reverse=True):
            print(f"  [OK] {r['name']}: {r['count']} items")

    # Sources needing work
    if results['blocked']:
        print(f"\n[BLOCKED SOURCES] ({len(results['blocked'])})")
        for r in results['blocked']:
            print(f"  [BLOCKED] {r['name']}: {r['error']}")

    if results['needs_selectors']:
        print(f"\n[SOURCES NEEDING SELECTORS] ({len(results['needs_selectors'])})")
        for r in results['needs_selectors'][:10]:  # Show first 10
            print(f"  [WARN] {r['name']}")
        if len(results['needs_selectors']) > 10:
            print(f"  ... and {len(results['needs_selectors']) - 10} more")

    if results['dns_errors']:
        print(f"\n[DNS/CONNECTIVITY ERRORS] ({len(results['dns_errors'])})")
        for r in results['dns_errors']:
            print(f"  [DNS] {r['name']}: {r['error']}")

    if results['errors']:
        print(f"\n[OTHER ERRORS] ({len(results['errors'])})")
        for r in results['errors'][:5]:  # Show first 5
            print(f"  [ERROR] {r['name']}: {r['error']}")

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)

    return results

if __name__ == "__main__":
    asyncio.run(test_all_sources())
