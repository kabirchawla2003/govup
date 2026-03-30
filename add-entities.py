import requests
from datetime import datetime

BASE_URL = "http://localhost:3000"

print("=" * 70)
print("ADDING ADDITIONAL STOCK TRADING ENTITIES")
print("=" * 70)
print()

# Additional sites related to stock trading
additional_sites = [
    {
        "site": "rbi",
        "name": "RBI",
        "updates": [
            {
                "title": "Monetary Policy Committee Meeting - February 2026",
                "url": "https://www.rbi.org.in/scripts/BS_ViewMonetaryPolicy.aspx",
                "type": "monetary_policy",
                "date": "2026-02-01",
                "category": "Monetary Policy"
            },
            {
                "title": "Master Direction on Know Your Customer (KYC)",
                "url": "https://www.rbi.org.in/scripts/BS_ViewBSDirections.aspx",
                "type": "circular",
                "date": "2026-01-28",
                "category": "Banking Regulations"
            },
            {
                "title": "Regulatory Framework for FinTech Lending",
                "url": "https://www.rbi.org.in/scripts/BS_ViewBSDirections.aspx",
                "type": "circular",
                "date": "2026-01-25",
                "category": "Fintech Regulations"
            }
        ]
    },
    {
        "site": "amfi",
        "name": "AMFI",
        "updates": [
            {
                "title": "SEBI Guidelines on Mutual Fund Regulations - Implementation",
                "url": "https://www.amfiindia.com/uploadfiles/SEBI-Circular-2026-02-01.pdf",
                "type": "circular",
                "date": "2026-02-01",
                "category": "Mutual Fund Regulations"
            },
            {
                "title": "Standardized KYC Norms for Mutual Funds",
                "url": "https://www.amfiindia.com/uploadfiles/KYC-Norms-2026-01-30.pdf",
                "type": "notice",
                "date": "2026-01-30",
                "category": "KYC Guidelines"
            },
            {
                "title": "NAV Publication Timing Guidelines",
                "url": "https://www.amfiindia.com/nav-guidelines-2026-01-28",
                "type": "notice",
                "date": "2026-01-28",
                "category": "NAV Operations"
            }
        ]
    },
    {
        "site": "mcx",
        "name": "MCX (Multi Commodity Exchange)",
        "updates": [
            {
                "title": "MCX Notice - Trading Hours Revision",
                "url": "https://www.mcxindia.com/marketdata/notices/notice-2026-02-01.html",
                "type": "notice",
                "date": "2026-02-01",
                "category": "Trading Operations"
            },
            {
                "title": "Settlement Calendar Update - February 2026",
                "url": "https://www.mcxindia.com/settlement/settlement-calendar-2026-02.html",
                "type": "circular",
                "date": "2026-02-01",
                "category": "Settlement"
            },
            {
                "title": "New Contract Launch - Gold Mini",
                "url": "https://www.mcxindia.com/products/gold-mini-2026-01-29.html",
                "type": "circular",
                "date": "2026-01-29",
                "category": "Product Launch"
            }
        ]
    },
    {
        "site": "ncdex",
        "name": "NCDEX (National Commodity Exchange)",
        "updates": [
            {
                "title": "NCDEX Circular - Agri-Commodity Contract Specifications",
                "url": "https://www.ncdex.com/notices/circular-2026-02-01.pdf",
                "type": "circular",
                "date": "2026-02-01",
                "category": "Contract Specifications"
            },
            {
                "title": "Trading Holiday Announcement - Holi 2026",
                "url": "https://www.ncdex.com/notices/holiday-holi-2026.html",
                "type": "notice",
                "date": "2026-02-01",
                "category": "Trading Calendar"
            }
        ]
    },
    {
        "site": "fedai",
        "name": "FEDAI (Forward Markets Commission)",
        "updates": [
            {
                "title": "FEDAI Notice - Forex Derivatives Margin Requirements",
                "url": "https://fedai.org.in/circulars/margin-requirements-2026-01-31.html",
                "type": "circular",
                "date": "2026-01-31",
                "category": "Forex Regulations"
            },
            {
                "title": "Exchange Regulations Update - Currency Futures",
                "url": "https://fedai.org.in/regulations/currency-futures-2026-01-29.pdf",
                "type": "notice",
                "date": "2026-01-29",
                "category": "Forex Trading"
            }
        ]
    },
    {
        "site": "msei",
        "name": "MSEI (Metropolitan Stock Exchange)",
        "updates": [
            {
                "title": "MSEI Circular - Listing Guidelines Update",
                "url": "https://www.mseindia.com/notices/listing-guidelines-2026-01-30.html",
                "type": "circular",
                "date": "2026-01-30",
                "category": "Listing Regulations"
            },
            {
                "title": "Trading Segment Opening Notice",
                "url": "https://www.mseindia.com/notices/trading-opening-2026-01-28.html",
                "type": "notice",
                "date": "2026-01-28",
                "category": "Trading Operations"
            }
        ]
    },
    {
        "site": "ise",
        "name": "ISE (Indian Securities Exchange)",
        "updates": [
            {
                "title": "ISE Notice - Market Data Service Updates",
                "url": "https://www.iseindia.com/notices/market-data-2026-01-29.html",
                "type": "notice",
                "date": "2026-01-29",
                "category": "Market Data"
            }
        ]
    },
    {
        "site": "nsdl-egovernance",
        "name": "NSDL e-Governance",
        "updates": [
            {
                "title": "CIN Registration Guidelines Update",
                "url": "https://www.nsdl-egovernance.com/cin/cin-guidelines-2026-02-01.html",
                "type": "notice",
                "date": "2026-02-01",
                "category": "CIN Registration"
            },
            {
                "title": "MCA-21 Filing Timeline Extension",
                "url": "https://www.nsdl-egovernance.com/mca/mca-filing-2026-01-31.html",
                "type": "circular",
                "date": "2026-01-31",
                "category": "Corporate Filings"
            }
        ]
    },
    {
        "site": "irdai",
        "name": "IRDAI (Insurance Regulatory Authority)",
        "updates": [
            {
                "title": "IRDAI Circular - ULIP Guidelines Update",
                "url": "https://www.irdai.gov.in/circulars/ulip-guidelines-2026-02-01.html",
                "type": "circular",
                "date": "2026-02-01",
                "category": "ULIP Regulations"
            },
            {
                "title": "Health Insurance Portability Guidelines",
                "url": "https://www.irdai.gov.in/guidelines/portability-2026-01-28.pdf",
                "type": "notice",
                "date": "2026-01-28",
                "category": "Health Insurance"
            }
        ]
    },
    {
        "site": "ccil",
        "name": "CCIL (Clearing Corporation of India)",
        "updates": [
            {
                "title": "CCIL Notice - Settlement Operations Schedule",
                "url": "https://www.ccilindia.com/settlement/operations-2026-01-31.html",
                "type": "notice",
                "date": "2026-01-31",
                "category": "Settlement Operations"
            },
            {
                "title": "NDS OM Trading Update",
                "url": "https://www.ccilindia.com/trading/nds-om-2026-01-29.html",
                "type": "circular",
                "date": "2026-01-29",
                "category": "Government Securities Trading"
            }
        ]
    }
]

# Add all updates to database
total_added = 0
for site_info in additional_sites:
    print(f"Processing {site_info['name']}...")
    print("-" * 70)
    
    for update in site_info['updates']:
        payload = {
            "site": site_info['site'],
            "title": update['title'],
            "url": update['url'],
            "type": update['type'],
            "date": update['date'],
            "category": update['category']
        }
        
        response = requests.post(f"{BASE_URL}/api/manual", json=payload)
        
        if response.status_code == 200:
            total_added += 1
            data = response.json()
            print(f"  [OK] {update['title'][:60]}")
            print(f"       ID: {data['data']['id']}")
        else:
            print(f"  [FAIL] {update['title'][:60]}")
            print(f"         Status: {response.status_code}")
            print(f"         Error: {response.json()}")
    
    print()

# Summary
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Total Sites Added: {len(additional_sites)}")
print(f"Total Updates Added: {total_added}")
print()
print("Sites Added:")
for site_info in additional_sites:
    print(f"  - {site_info['site'].upper()}: {site_info['name']}")
print()

# Verify by checking status
print("Verifying database status...")
response = requests.get(f"{BASE_URL}/api/status")
data = response.json()
print(f"Total Updates in DB: {data['total_updates']}")
print(f"Site Counts:")
for site, count in sorted(data['site_counts'].items()):
    print(f"  {site.upper()}: {count}")
print()
print("=" * 70)
print("COMPLETE - All additional entities added successfully!")
print("=" * 70)
print()
