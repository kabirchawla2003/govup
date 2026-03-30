import asyncio
import time
import subprocess
import sys
from pathlib import Path

async def test_version(version_name, module_path, test_sites=['sebi', 'rbi', 'irdai', 'nse', 'mca']):
    """Test a specific version"""
    print(f"\n{'='*80}")
    print(f"Testing Version {version_name}: {module_path}")
    print(f"{'='*80}\n")
    
    # Import the module
    import importlib.util
    spec = importlib.util.spec_from_file_location(f'test_{version_name}', str(module_path))
    if spec is None or spec.loader is None:
        print(f"ERROR: Could not load {module_path}")
        return {"working": [], "failed": test_sites, "duration": 0}
    
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except Exception as e:
        print(f"ERROR loading module: {str(e)[:100]}")
        return {"working": [], "failed": test_sites, "duration": 0}
    
    results = {"working": [], "failed": [], "errors": {}}
    start = time.time()
    
    for site_key in test_sites:
        if site_key not in m.SITES:
            continue
        
        site_config = m.SITES[site_key]
        url = site_config["urls"][0]
        print(f"  {site_key:15} ... ", end="", flush=True)
        
        try:
            site_start = time.time()
            # Call scrape_site synchronously via asyncio.run
            items, stats = asyncio.run(m.scrape_site(site_key, site_config))
            duration = time.time() - site_start
            
            if stats.get("items_found", 0) > 0:
                results["working"].append((site_key, stats["items_found"], duration))
                print(f"OK ({stats['items_found']} items, {duration:.1f}s)")
            else:
                results["failed"].append((site_key, duration))
                results["errors"][site_key] = stats.get("errors", ["No items found"])
                print(f"FAILED ({duration:.1f}s)")
        except Exception as e:
            results["failed"].append((site_key, 0))
            results["errors"][site_key] = str(e)[:100]
            print(f"ERROR ({str(e)[:30]}...)")
    
    total_duration = time.time() - start
    return {
        "working": results["working"],
        "failed": results["failed"],
        "errors": results["errors"],
        "duration": total_duration
    }

async def main():
    versions = [
        ("A: httpx-only", Path("src/main-v7-a-httpx-only.py")),
        ("B: proxy-rotation", Path("src/main-v7-b-proxy-rotation.py")),
        ("C: docker-ready", Path("src/main-v7-c-docker.py")),
    ]
    
    test_sites = ['sebi', 'rbi', 'irdai', 'nse']  # Quick test set
    all_results = {}
    
    for version_name, module_path in versions:
        try:
            result = await test_version(version_name, module_path, test_sites)
            all_results[version_name] = result
        except Exception as e:
            print(f"\nERROR testing {version_name}: {str(e)}")
            all_results[version_name] = {"working": [], "failed": test_sites, "duration": 0, "error": str(e)}
    
    # Print summary
    print(f"\n{'='*80}")
    print("COMPARISON SUMMARY")
    print(f"{'='*80}\n")
    
    for version_name, result in all_results.items():
        working = len(result.get("working", []))
        failed = len(result.get("failed", []))
        duration = result.get("duration", 0)
        
        print(f"{version_name:20} | Working: {working}/4 | Failed: {failed}/4 | Time: {duration:6.1f}s")
        if result.get("working"):
            for site, items, dur in result["working"]:
                print(f"    [OK] {site:15} {items:5} items {dur:6.1f}s")
    
    # Recommendation
    print(f"\n{'='*80}")
    print("RECOMMENDATION")
    print(f"{'='*80}\n")
    
    best_version = max(all_results.items(), key=lambda x: len(x[1].get("working", [])))
    print(f"Best performing version: {best_version[0]}")
    print(f"  - Working sites: {len(best_version[1].get('working', []))}")
    print(f"  - Total time: {best_version[1].get('duration', 0):.1f}s")

if __name__ == "__main__":
    asyncio.run(main())
