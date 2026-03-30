#!/usr/bin/env python3
"""
Test Selenium against the 8 failing Playwright sites.
"""
import asyncio
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

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

def scrape_with_selenium(url, site_key, timeout=15):
    """Scrape a single URL with Selenium."""
    try:
        options = Options()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        options.add_argument('--disable-web-resources')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-cache')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(timeout)
        driver.set_script_timeout(timeout)
        
        start = time.time()
        driver.get(url)
        elapsed = time.time() - start
        
        html = driver.page_source
        byte_len = len(html.encode('utf-8'))
        
        driver.quit()
        return html, byte_len, elapsed
    except Exception as e:
        if 'driver' in locals():
            try:
                driver.quit()
            except:
                pass
        return None, 0, time.time() - start if 'start' in locals() else 0

def main():
    print("="*80)
    print("Testing 8 Playwright-failing sites with Selenium")
    print("="*80)
    
    results = []
    working = []
    failed = []
    
    for i, (site_key, url) in enumerate(FAILING_SITES.items(), 1):
        site_name = site_key.upper()
        print(f"\n[{i}/8] {site_key:<15} {url}")
        
        html, byte_len, elapsed = scrape_with_selenium(url, site_key, timeout=15)
        
        if html:
            results.append((site_key, "OK", byte_len, elapsed))
            working.append(site_key)
            print(f"      OK     {elapsed:.1f}s  {byte_len:,}b")
        else:
            results.append((site_key, "FAIL", 0, elapsed))
            failed.append(site_key)
            print(f"      FAIL   {elapsed:.1f}s")
    
    print("\n" + "="*80)
    print(f"SUMMARY: {len(working)}/8 working ({100*len(working)//8}%)")
    print("="*80)
    
    print(f"\nWORKING ({len(working)} sites):")
    for site in working:
        print(f"  {site}")
    
    if failed:
        print(f"\nFAILED ({len(failed)} sites):")
        for site in failed:
            print(f"  {site}")

if __name__ == "__main__":
    main()
