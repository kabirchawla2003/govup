# Patch file to add additional sites
# Run this script to update main.py with new sites

additional_sites_patch = '''
    # Additional stock trading related entities
    "rbi": {
        "name": "RBI (Reserve Bank of India)",
        "url": "https://www.rbi.org.in/scripts/BS_ViewMonetaryPolicy.aspx",
        "type_map": {
            "/monetary-policy/": "monetary_policy",
            "/bsd/": "circular",
            "/regulations/": "regulation"
        }
    },
    "amfi": {
        "name": "AMFI (Association of Mutual Funds in India)",
        "url": "https://www.amfiindia.com/uploadfiles/",
        "type_map": {
            "/circulars/": "circular",
            "/notices/": "notice",
            "/nav/": "nav_notice"
        }
    },
    "mcx": {
        "name": "MCX (Multi Commodity Exchange)",
        "url": "https://www.mcxindia.com/marketdata/notices",
        "type_map": {
            "/notices/": "notice",
            "/circulars/": "circular",
            "/settlement/": "settlement"
        }
    },
    "ncdex": {
        "name": "NCDEX (National Commodity Exchange)",
        "url": "https://www.ncdex.com/notices/",
        "type_map": {
            "/circulars/": "circular",
            "/notices/": "notice",
            "/settlement/": "settlement"
        }
    },
    "fedai": {
        "name": "FEDAI (Forward Markets Commission)",
        "url": "https://fedai.org.in/circulars/",
        "type_map": {
            "/circulars/": "circular",
            "/regulations/": "regulation",
            "/forex/": "forex_notice"
        }
    },
    "msei": {
        "name": "MSEI (Metropolitan Stock Exchange)",
        "url": "https://www.mseindia.com/notices/",
        "type_map": {
            "/circulars/": "circular",
            "/notices/": "notice",
            "/trading/": "trading_notice"
        }
    },
    "ise": {
        "name": "ISE (Indian Securities Exchange)",
        "url": "https://www.iseindia.com/notices/",
        "type_map": {
            "/circulars/": "circular",
            "/notices/": "notice"
        }
    },
    "nsdl-egovernance": {
        "name": "NSDL e-Governance",
        "url": "https://www.nsdl-egovernance.com/",
        "type_map": {
            "/circulars/": "circular",
            "/notices/": "notice"
        }
    },
    "irdai": {
        "name": "IRDAI (Insurance Regulatory Authority)",
        "url": "https://www.irdai.gov.in/circulars/",
        "type_map": {
            "/circulars/": "circular",
            "/guidelines/": "guideline",
            "/notices/": "notice"
        }
    },
    "ccil": {
        "name": "CCIL (Clearing Corporation of India)",
        "url": "https://www.ccilindia.com/settlement/",
        "type_map": {
            "/circulars/": "circular",
            "/notices/": "notice",
            "/trading/": "trading_notice"
        }
    }'''

# Read main.py
with open('src/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the line with PFRDA closing brace and insert after it
marker = '"/orders/": "order"\n          }\n    }'
if marker in content:
    # Insert the new sites before the final closing brace
    replacement = marker[:-2] + ',\n' + additional_sites_patch + '\n    }'
    content = content.replace(marker, replacement)
    
    # Write back
    with open('src/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("SUCCESS: Added 10 new sites to SITES configuration")
    print()
    print("New sites added:")
    print("  1. RBI - Reserve Bank of India")
    print("  2. AMFI - Association of Mutual Funds in India")
    print("  3. MCX - Multi Commodity Exchange")
    print("  4. NCDEX - National Commodity Exchange")
    print("  5. FEDAI - Forward Markets Commission")
    print("  6. MSEI - Metropolitan Stock Exchange")
    print("  7. ISE - Indian Securities Exchange")
    print("  8. NSDL e-Governance")
    print("  9. IRDAI - Insurance Regulatory Authority")
    print(" 10. CCIL - Clearing Corporation of India")
    print()
    print("Total sites: 16")
else:
    print("ERROR: Could not find the marker to insert new sites")
    print(f"Looking for: {repr(marker[:50])}")
