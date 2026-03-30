#!/usr/bin/env python3
"""
Test Playwright with increased 60s timeout for slow sites.
"""
import asyncio
import logging
from playwright.async_api import async_playwright
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

SLOW_SITES = {"nse", "bse", "icici_pru", "irdai", "cbdt", "nsdl"}

FAILING_SITES = {
    "nse": "http://nseindia.com/",
    "bse": "http://www.bseindia.com/",
    "icra": "https://www.icra.in/",
    "icici_pru": "https://www.icicipruamc.com/",
    "irdai": "http://www.irdai.gov.in/",
    "nsdl": "http://www.nsdlindia.com/",
    "pfrda": "http://pfrda.gov.in/",
    "mse": "http://www.mseindia.com/",
}

async def scrape_with_playwright(url: str, site_key: str, timeout: int = 30) -> tuple:
    """Scrape a single URL with Playwright."""
    try:
        # Increase timeout for slow sites (60s)
        if site_key in SLOW_SITES:
            timeout = 60
        
        start = time.time()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=timeout * 1000)
            html = await page.content()
            await browser.close()
        elapsed = time.time() - start
        byte_len = len(html.encode('utf-8'))
        return html, byte_len, elapsed
    except Exception as e:
        elapsed = time.time() - start if 'start' in locals() else 0
        logger.error(f"[Playwright] Error {site_key}: {str(e)[:60]}")
        return None, 0, elapsed

async def main():
    print("=" * 80)
    print("Testing 8 Playwright-failing sites with 60s timeout for slow sites")
    print("=" * 80)
    
    results = []
    working = []
    failed = []
    
    for i, (site_key, url) in enumerate(FAILING_SITES.items(), 1):
        print(f"\n[{i}/8] {site_key:<15} {url}")
        
        html, byte_len, elapsed = await scrape_with_playwright(url, site_key, timeout=30)
        
        if html:
            results.append((site_key, "OK", byte_len, elapsed))
            working.append(site_key)
            print(f"      OK     {elapsed:.1f}s  {byte_len:,}b")
        else:
            results.append((site_key, "FAIL", 0, elapsed))
            failed.append(site_key)
            print(f"      FAIL   {elapsed:.1f}s")
    
    print("\n" + "=" * 80)
    print(f"SUMMARY: {len(working)}/8 working ({100*len(working)//8}%)")
    print("=" * 80)
    
    print(f"\nWORKING ({len(working)} sites):")
    for site in working:
        print(f"  {site}")
    
    if failed:
        print(f"\nFAILED ({len(failed)} sites):")
        for site in failed:
            print(f"  {site}")

if __name__ == "__main__":
    asyncio.run(main())
