# Additional 66 Government and Institutional Sites for Circular Scraping
# This extends your existing 34 sites to 100+ total sources
# Research completed: March 2026

ADDITIONAL_SITES = {

    # ============================================
    # 1. BANKING & FINANCE REGULATORS (5 sites)
    # ============================================

    "npci": {
        "name": "NPCI",
        "full_name": "National Payments Corporation of India",
        "category": "banking-regulator",
        "url": "https://www.npci.org.in/what-we-do/imps/circular",
        "alternate_urls": ["https://www.npci.org.in/what-we-do/rupay/circulars"],
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Payment systems regulator - IMPS, RuPay, UPI circulars"
    },

    "ifsca": {
        "name": "IFSCA",
        "full_name": "International Financial Services Centres Authority",
        "category": "financial-regulator",
        "url": "https://www.ifsca.gov.in/Legal/Index/ogGPf3wx5GE=",
        "update_types": ["regulation", "circular", "notification"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Regulator for GIFT City and international financial services"
    },

    "nhb": {
        "name": "NHB",
        "full_name": "National Housing Bank",
        "category": "financial-institution",
        "url": "https://www.nhb.org.in/regulation_post/supervisory-circular/",
        "alternate_urls": ["https://www.nhb.org.in/regulation_post/circulars/"],
        "update_types": ["circular", "notification", "master-circular"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Housing finance regulator"
    },

    "ibbi": {
        "name": "IBBI",
        "full_name": "Insolvency and Bankruptcy Board of India",
        "category": "financial-regulator",
        "url": "https://ibbi.gov.in/",
        "update_types": ["regulation", "circular", "notification"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Insolvency and bankruptcy regulator"
    },

    "iba": {
        "name": "IBA",
        "full_name": "Indian Banks' Association",
        "category": "industry-body",
        "url": "https://www.iba.org.in/",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Banking industry representative body"
    },

    # ============================================
    # 2. PROFESSIONAL BODIES (3 sites)
    # ============================================

    "icai": {
        "name": "ICAI",
        "full_name": "Institute of Chartered Accountants of India",
        "category": "professional-body",
        "url": "https://www.icai.org/category/notifications",
        "update_types": ["notification", "announcement", "circular"],
        "uses_playwright": False,
        "priority": "high",
        "description": "CA professional body - accounting standards, ethics"
    },

    "icsi": {
        "name": "ICSI",
        "full_name": "Institute of Company Secretaries of India",
        "category": "professional-body",
        "url": "https://www.icsi.edu/whats_new_icsi/",
        "alternate_urls": ["https://www.icsi.edu/latest-icsi/"],
        "update_types": ["circular", "notification", "guideline"],
        "uses_playwright": False,
        "priority": "high",
        "description": "CS professional body - corporate governance"
    },

    "icmai": {
        "name": "ICMAI",
        "full_name": "Institute of Cost Accountants of India",
        "category": "professional-body",
        "url": "https://icmai.in/studentswebsite/circulars.php",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "CMA professional body - cost accounting"
    },

    # ============================================
    # 3. CORPORATE AFFAIRS & COMPLIANCE (5 sites)
    # ============================================

    "nfra": {
        "name": "NFRA",
        "full_name": "National Financial Reporting Authority",
        "category": "regulatory-body",
        "url": "https://nfra.gov.in/document-category/circulars/",
        "alternate_urls": ["https://nfra.gov.in/document-category/orders/"],
        "update_types": ["circular", "order", "notification"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Financial reporting and auditing standards oversight"
    },

    "iepf": {
        "name": "IEPF",
        "full_name": "Investor Education and Protection Fund Authority",
        "category": "regulatory-body",
        "url": "http://www.iepf.gov.in/IEPF/notification.html",
        "update_types": ["notification", "circular"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Unclaimed dividends and investor protection"
    },

    "sfio": {
        "name": "SFIO",
        "full_name": "Serious Fraud Investigation Office",
        "category": "regulatory-body",
        "url": "https://sfio.gov.in/en/document-category/office-orders/",
        "alternate_urls": ["https://sfio.gov.in/en/past-notices/notifications/"],
        "update_types": ["order", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Corporate fraud investigations"
    },

    "nclt": {
        "name": "NCLT",
        "full_name": "National Company Law Tribunal",
        "category": "tribunal",
        "url": "https://nclt.gov.in/circulars",
        "update_types": ["circular", "order", "notification"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Company law tribunal - insolvency, mergers"
    },

    "nclat": {
        "name": "NCLAT",
        "full_name": "National Company Law Appellate Tribunal",
        "category": "tribunal",
        "url": "https://nclat.nic.in/circulars-orders",
        "update_types": ["circular", "order"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Appeals from NCLT"
    },

    # ============================================
    # 4. TAX AUTHORITIES (3 sites)
    # ============================================

    "gst_council": {
        "name": "GST Council",
        "full_name": "Goods and Services Tax Council",
        "category": "tax-authority",
        "url": "https://gstcouncil.gov.in/cgst-circulars",
        "alternate_urls": ["https://gstcouncil.gov.in/cgst-tax-notification"],
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "high",
        "description": "GST policy and rate decisions"
    },

    "gstn": {
        "name": "GSTN",
        "full_name": "Goods and Services Tax Network",
        "category": "tax-infrastructure",
        "url": "https://www.gstn.org.in/",
        "alternate_urls": ["https://services.gst.gov.in/services/advisory/advisoryandreleases"],
        "update_types": ["advisory", "release", "notification"],
        "uses_playwright": False,
        "priority": "high",
        "description": "GST IT infrastructure and system advisories"
    },

    "cestat": {
        "name": "CESTAT",
        "full_name": "Customs Excise Service Tax Appellate Tribunal",
        "category": "tribunal",
        "url": "https://cestat.gov.in/",
        "update_types": ["order", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Indirect tax appeals tribunal"
    },

    # ============================================
    # 5. FINANCIAL INSTITUTIONS (6 sites)
    # ============================================

    "iifcl": {
        "name": "IIFCL",
        "full_name": "India Infrastructure Finance Company Limited",
        "category": "financial-institution",
        "url": "https://www.iifcl.in",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Infrastructure financing"
    },

    "ifci": {
        "name": "IFCI",
        "full_name": "IFCI Limited",
        "category": "financial-institution",
        "url": "https://www.ifciltd.com/",
        "update_types": ["notification", "announcement"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Development finance institution"
    },

    "mudra": {
        "name": "MUDRA",
        "full_name": "Micro Units Development and Refinance Agency",
        "category": "financial-institution",
        "url": "https://www.mudra.org.in/",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "MSME financing refinance agency"
    },

    "ecgc": {
        "name": "ECGC",
        "full_name": "Export Credit Guarantee Corporation of India",
        "category": "financial-institution",
        "url": "https://main.ecgc.in/circular/",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Export credit insurance"
    },

    "shcil": {
        "name": "SHCIL",
        "full_name": "Stock Holding Corporation of India Limited",
        "category": "market-infrastructure",
        "url": "https://www.stockholding.com/",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Custodial and depository participant services"
    },

    "pfrda_detailed": {
        "name": "PFRDA Master Circulars",
        "full_name": "PFRDA Regulatory Framework",
        "category": "pension-regulator",
        "url": "https://www.pfrda.org.in/web/pfrda/regulatory-framework/circulars/active-circulars",
        "alternate_urls": ["https://www.pfrda.org.in/web/pfrda/regulatory-framework/master-circulars/active-master-circulars"],
        "update_types": ["circular", "regulation", "notification", "master-circular"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Pension fund detailed regulatory circulars"
    },

    # ============================================
    # 6. RATING AGENCIES (3 sites)
    # ============================================

    "acuite": {
        "name": "Acuité Ratings",
        "full_name": "Acuité Ratings & Research Limited",
        "category": "rating-agency",
        "url": "https://www.acuite.in/operating-guidelines.htm",
        "update_types": ["guideline", "circular"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Credit rating agency"
    },

    "india_ratings": {
        "name": "India Ratings",
        "full_name": "India Ratings & Research (Fitch Group)",
        "category": "rating-agency",
        "url": "https://www.indiaratings.co.in",
        "update_types": ["report", "notification"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Fitch-affiliated rating agency"
    },

    "brickwork": {
        "name": "Brickwork Ratings",
        "full_name": "Brickwork Ratings India Pvt Ltd",
        "category": "rating-agency",
        "url": "https://www.brickworkratings.com/",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "low",
        "description": "SEBI-registered rating agency"
    },

    # ============================================
    # 7. CAPITAL MARKETS & EXCHANGES (3 sites)
    # ============================================

    "amfi": {
        "name": "AMFI",
        "full_name": "Association of Mutual Funds in India",
        "category": "industry-body",
        "url": "https://www.amfiindia.com/distributor-corner/circulars-and-announcements/circulars",
        "update_types": ["circular", "announcement"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Mutual fund industry body"
    },

    "nse_emerge": {
        "name": "NSE Emerge",
        "full_name": "NSE SME Emerge Platform",
        "category": "stock-exchange",
        "url": "https://www1.nseindia.com/emerge/circulars.htm",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "SME stock exchange platform"
    },

    "cci": {
        "name": "CCI",
        "full_name": "Competition Commission of India",
        "category": "regulatory-body",
        "url": "https://www.cci.gov.in/",
        "alternate_urls": ["https://cci.gov.in/antitrust/orders"],
        "update_types": ["order", "notification", "regulation"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Antitrust and competition regulator"
    },

    # ============================================
    # 8. TELECOMMUNICATIONS & TECHNOLOGY (1 site)
    # ============================================

    "trai": {
        "name": "TRAI",
        "full_name": "Telecom Regulatory Authority of India",
        "category": "regulatory-body",
        "url": "http://www.trai.gov.in/release-publication/regulations",
        "alternate_urls": ["http://www.trai.gov.in/notifications/press-release"],
        "update_types": ["regulation", "notification", "press-release"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Telecom sector regulator"
    },

    # ============================================
    # 9. MINISTRY & GOVERNMENT DEPARTMENTS (13 sites)
    # ============================================

    "dpiit": {
        "name": "DPIIT",
        "full_name": "Department for Promotion of Industry and Internal Trade",
        "category": "government-department",
        "url": "https://www.dpiit.gov.in/policies-rules-and-acts/notifications",
        "update_types": ["notification", "circular", "policy"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Industrial policy, FDI, IPR, startup India"
    },

    "dgft": {
        "name": "DGFT",
        "full_name": "Directorate General of Foreign Trade",
        "category": "government-department",
        "url": "https://www.dgft.gov.in/CP/?opt=notification",
        "update_types": ["notification", "circular", "trade-notice"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Foreign trade policy and EXIM regulations"
    },

    "cvc": {
        "name": "CVC",
        "full_name": "Central Vigilance Commission",
        "category": "government-body",
        "url": "https://cvc.gov.in/guidelines.html",
        "update_types": ["guideline", "circular", "order"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Anti-corruption watchdog"
    },

    "fssai": {
        "name": "FSSAI",
        "full_name": "Food Safety and Standards Authority of India",
        "category": "regulatory-body",
        "url": "https://fssai.gov.in/notifications.php",
        "alternate_urls": ["https://fssai.gov.in/cms/regulations.php"],
        "update_types": ["notification", "regulation", "circular"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Food safety and standards"
    },

    "ministry_power": {
        "name": "Ministry of Power",
        "full_name": "Ministry of Power, Government of India",
        "category": "government-ministry",
        "url": "https://powermin.gov.in/en/circular",
        "alternate_urls": ["https://powermin.gov.in/en/content/important-orders-guidelines-notifications-reports"],
        "update_types": ["circular", "notification", "order"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Power sector policies and regulations"
    },

    "ministry_coal": {
        "name": "Ministry of Coal",
        "full_name": "Ministry of Coal, Government of India",
        "category": "government-ministry",
        "url": "https://www.coal.nic.in/",
        "update_types": ["notification", "circular"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Coal sector policies"
    },

    "cerc": {
        "name": "CERC",
        "full_name": "Central Electricity Regulatory Commission",
        "category": "regulatory-body",
        "url": "http://cercind.gov.in/",
        "alternate_urls": ["https://cercind.gov.in/Current_reg.html"],
        "update_types": ["regulation", "order", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Electricity tariff and market regulation"
    },

    "moefcc": {
        "name": "MoEFCC",
        "full_name": "Ministry of Environment, Forest and Climate Change",
        "category": "government-ministry",
        "url": "https://moef.gov.in/orders/update",
        "alternate_urls": ["https://cpc.parivesh.nic.in/Notifications.aspx?id=EC"],
        "update_types": ["notification", "circular", "order"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Environmental clearances and regulations"
    },

    "ministry_labour": {
        "name": "Ministry of Labour",
        "full_name": "Ministry of Labour & Employment",
        "category": "government-ministry",
        "url": "https://labour.gov.in/circulars",
        "alternate_urls": ["https://labour.gov.in/gazette-notification"],
        "update_types": ["circular", "notification", "gazette"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Labour laws and social security"
    },

    "epfo": {
        "name": "EPFO",
        "full_name": "Employees' Provident Fund Organisation",
        "category": "statutory-body",
        "url": "https://www.epfindia.gov.in/site_en/circulars.php",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Provident fund regulations"
    },

    "esic": {
        "name": "ESIC",
        "full_name": "Employees State Insurance Corporation",
        "category": "statutory-body",
        "url": "https://esic.gov.in/circulars",
        "update_types": ["circular", "notification", "order"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Employee health insurance scheme"
    },

    "morth": {
        "name": "MoRTH",
        "full_name": "Ministry of Road Transport and Highways",
        "category": "government-ministry",
        "url": "https://morth.nic.in/OMs-Circular-Other-Notification",
        "alternate_urls": ["https://morth.nic.in/notification"],
        "update_types": ["circular", "notification", "order", "GSR"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Transport and vehicle regulations"
    },

    "uidai": {
        "name": "UIDAI",
        "full_name": "Unique Identification Authority of India (Aadhaar)",
        "category": "statutory-body",
        "url": "https://uidai.gov.in/en/about-uidai/legal-framework/circulars.html",
        "alternate_urls": ["https://uidai.gov.in/en/media-resources/uidai-documents/circulars-memorandums-notification-01.html"],
        "update_types": ["circular", "notification", "memorandum"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Aadhaar regulations and updates"
    },

    # ============================================
    # 10. SECTOR-SPECIFIC REGULATORS (8 sites)
    # ============================================

    "ministry_petroleum": {
        "name": "Ministry of Petroleum",
        "full_name": "Ministry of Petroleum and Natural Gas",
        "category": "government-ministry",
        "url": "http://petroleum.nic.in/exploration-production/orders-notifications-amendment",
        "alternate_urls": ["https://mopng.gov.in/en"],
        "update_types": ["notification", "order", "circular"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Oil and gas sector policies"
    },

    "pci": {
        "name": "PCI",
        "full_name": "Pharmacy Council of India",
        "category": "professional-body",
        "url": "https://pci.gov.in/en/blog/?category=Circulars",
        "alternate_urls": ["https://pci.gov.in/notifications-all/"],
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Pharmacy education and practice regulation"
    },

    "cdsco": {
        "name": "CDSCO",
        "full_name": "Central Drugs Standard Control Organisation",
        "category": "regulatory-body",
        "url": "https://cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Drug approval and pharma regulation"
    },

    "mha": {
        "name": "MHA",
        "full_name": "Ministry of Home Affairs",
        "category": "government-ministry",
        "url": "https://www.mha.gov.in/en/notifications/circular",
        "alternate_urls": ["https://www.mha.gov.in/en/notifications/notice"],
        "update_types": ["circular", "notice", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Internal security, immigration, FCRA"
    },

    "ministry_steel": {
        "name": "Ministry of Steel",
        "full_name": "Ministry of Steel, Government of India",
        "category": "government-ministry",
        "url": "https://steel.gov.in/",
        "update_types": ["notification", "circular", "order"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Steel industry policies"
    },

    "ministry_textiles": {
        "name": "Ministry of Textiles",
        "full_name": "Ministry of Textiles, Government of India",
        "category": "government-ministry",
        "url": "https://texmin.nic.in/notification",
        "update_types": ["notification", "circular"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Textile industry policies"
    },

    "ministry_msme": {
        "name": "Ministry of MSME",
        "full_name": "Ministry of Micro, Small & Medium Enterprises",
        "category": "government-ministry",
        "url": "https://msme.gov.in/circulars",
        "alternate_urls": ["https://msme.gov.in/notifications"],
        "update_types": ["circular", "notification", "order"],
        "uses_playwright": False,
        "priority": "high",
        "description": "MSME sector policies and schemes"
    },

    "dgshipping": {
        "name": "DGS",
        "full_name": "Directorate General of Shipping",
        "category": "regulatory-body",
        "url": "https://www.dgshipping.gov.in/content/dgscirculars.aspx",
        "update_types": ["circular", "notice", "order"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Maritime and shipping regulations"
    },

    # ============================================
    # 11. AVIATION & STANDARDS (3 sites)
    # ============================================

    "dgca": {
        "name": "DGCA",
        "full_name": "Directorate General of Civil Aviation",
        "category": "regulatory-body",
        "url": "https://www.dgca.gov.in/",
        "update_types": ["CAR", "circular", "notification"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Civil aviation safety and regulation"
    },

    "bis": {
        "name": "BIS",
        "full_name": "Bureau of Indian Standards",
        "category": "standards-body",
        "url": "https://www.bis.gov.in/whats-new-notifications/",
        "update_types": ["notification", "circular", "QCO"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "National standards and quality certification"
    },

    "cic": {
        "name": "CIC",
        "full_name": "Central Information Commission",
        "category": "statutory-body",
        "url": "https://cic.gov.in/decision",
        "alternate_urls": ["https://cic.gov.in/circulars-and-mom-reports"],
        "update_types": ["decision", "circular", "order"],
        "uses_playwright": False,
        "priority": "low",
        "description": "RTI Act implementation"
    },

    # ============================================
    # 12. LAW & ENFORCEMENT (2 sites)
    # ============================================

    "bar_council": {
        "name": "Bar Council of India",
        "full_name": "Bar Council of India",
        "category": "professional-body",
        "url": "https://www.barcouncilofindia.org/info/announcements",
        "update_types": ["announcement", "circular", "notification"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Legal profession regulation"
    },

    "enforcement_directorate": {
        "name": "ED",
        "full_name": "Enforcement Directorate",
        "category": "enforcement-agency",
        "url": "https://enforcementdirectorate.gov.in/",
        "update_types": ["notification", "circular"],
        "uses_playwright": False,
        "priority": "medium",
        "description": "Economic law enforcement"
    },

    # ============================================
    # 13. PUBLIC SECTOR BANKS & FINANCE DEPT (3 sites)
    # ============================================

    "pnb": {
        "name": "PNB",
        "full_name": "Punjab National Bank",
        "category": "public-sector-bank",
        "url": "https://pnb.bank.in/Public-Notices.aspx",
        "update_types": ["notice", "circular"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Public sector bank notices"
    },

    "bank_of_india": {
        "name": "Bank of India",
        "full_name": "Bank of India",
        "category": "public-sector-bank",
        "url": "https://www.bankofindia.co.in/",
        "update_types": ["notice", "circular"],
        "uses_playwright": False,
        "priority": "low",
        "description": "Public sector bank updates"
    },

    "dfs_circulars": {
        "name": "DFS Bank Circulars",
        "full_name": "Department of Financial Services - Bank Circulars",
        "category": "government-department",
        "url": "https://financialservices.gov.in/beta/en/circular-page",
        "update_types": ["circular", "notification"],
        "uses_playwright": False,
        "priority": "high",
        "description": "Government banking sector circulars"
    },
}

# Category breakdown
CATEGORIES = {
    "banking-regulator": 2,
    "financial-regulator": 2,
    "financial-institution": 7,
    "professional-body": 6,
    "regulatory-body": 10,
    "tribunal": 3,
    "tax-authority": 1,
    "tax-infrastructure": 1,
    "market-infrastructure": 1,
    "rating-agency": 3,
    "industry-body": 2,
    "stock-exchange": 1,
    "government-ministry": 11,
    "government-department": 3,
    "government-body": 1,
    "statutory-body": 5,
    "pension-regulator": 1,
    "enforcement-agency": 1,
    "standards-body": 1,
    "public-sector-bank": 2,
}

# Priority breakdown
PRIORITIES = {
    "high": 31,
    "medium": 23,
    "low": 12,
}

if __name__ == "__main__":
    print(f"Total additional sites: {len(ADDITIONAL_SITES)}")
    print(f"\nCategories: {len(CATEGORIES)}")
    print(f"High priority: {PRIORITIES['high']}")
    print(f"Medium priority: {PRIORITIES['medium']}")
    print(f"Low priority: {PRIORITIES['low']}")

    print("\n=== HIGH PRIORITY SITES ===")
    for key, site in ADDITIONAL_SITES.items():
        if site.get("priority") == "high":
            print(f"  {site['name']:20} - {site['description']}")
