"""
Compare all 3 versions by running them and hitting endpoints
"""
import subprocess
import time
import requests
import json
from pathlib import Path

versions = [
    ("A: httpx-only", "main-v7-a-httpx-only:app"),
    ("B: proxy-rotation", "main-v7-b-proxy-rotation:app"),
    ("C: docker-ready", "main-v7-c-docker:app"),
]

test_sites = ['sebi', 'rbi', 'irdai', 'nse']  # Quick test
API_URL = "http://localhost:8000"
timeout = 10  # Per request

def test_version(version_name, app_module):
    """Start API, test it, then stop"""
    print(f"\n{'='*80}")
    print(f"Testing {version_name}: {app_module}")
    print(f"{'='*80}\n")
    
    # Start uvicorn in background
    proc = subprocess.Popen(
        ['.venv\\Scripts\\python.exe', '-m', 'uvicorn', f'src.{app_module}', '--port', '8000'],
        cwd='d:\\circular_api',
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    time.sleep(5)  # Wait for startup
    
    results = {"working": [], "failed": []}
    start = time.time()
    
    try:
        # Wait for API to be ready
        for _ in range(10):
            try:
                resp = requests.get(f"{API_URL}/api/status", headers={"X-API-Key": "test"}, timeout=2)
                if resp.status_code == 200:
                    break
            except:
                time.sleep(1)
        
        # Test a few sites
        for site in test_sites:
            try:
                print(f"  {site:15} ... ", end="", flush=True)
                resp = requests.get(
                    f"{API_URL}/api/updates?site={site}&limit=5",
                    headers={"X-API-Key": "test"},
                    timeout=30
                )
                if resp.status_code == 200:
                    data = resp.json()
                    count = data.get('count', 0)
                    if count > 0:
                        print(f"OK ({count} items)")
                        results["working"].append((site, count))
                    else:
                        print(f"FAILED (0 items)")
                        results["failed"].append(site)
                else:
                    print(f"ERROR ({resp.status_code})")
                    results["failed"].append(site)
            except Exception as e:
                print(f"ERROR ({str(e)[:30]})")
                results["failed"].append(site)
    
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        time.sleep(1)
    
    duration = time.time() - start
    return {"working": results["working"], "failed": results["failed"], "duration": duration}

# Run tests
print("TESTING ALL 3 VERSIONS")
print("This will start each API, test it, then stop\n")

all_results = {}
for version_name, app_module in versions:
    try:
        result = test_version(version_name, app_module)
        all_results[version_name] = result
    except Exception as e:
        print(f"\nERROR testing {version_name}: {str(e)}")
        all_results[version_name] = {"working": [], "failed": test_sites, "duration": 0}

# Summary
print(f"\n{'='*80}")
print("FINAL COMPARISON")
print(f"{'='*80}\n")

for version_name, result in all_results.items():
    working = len(result.get("working", []))
    failed = len(result.get("failed", []))
    print(f"{version_name:25} | Working: {working}/4 | Failed: {failed}/4 | Time: {result.get('duration', 0):.1f}s")
    for site, count in result.get("working", []):
        print(f"    [OK] {site:15} {count:5} items")
