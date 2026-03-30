# Additional broker-relevant sources to add to SITES dictionary

ADDITIONAL_BROKER_SOURCES = {
    # ===== STOCK MARKET INTERMEDIARIES (8) =====
    "nse_clearing": {
        "name": "NSE Clearing",
        "description": "NSE Clearing Limited",
        "category": "clearing",
        "urls": ["https://www.nsccl.co.in/"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "notice"],
        "new_source": True
    },
    "iccl": {
        "name": "ICCL",
        "description": "Indian Clearing Corporation Limited (BSE Clearing)",
        "category": "clearing",
        "urls": ["https://www.icclindia.com/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True
    },
    "mcx_ccl": {
        "name": "MCX-SX Clearing",
        "description": "MCX Stock Exchange Clearing Corporation",
        "category": "clearing",
        "urls": ["https://www.mcxccl.com/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True
    },

    # ===== BROKER ASSOCIATIONS & SROs (5) =====
    "anmi": {
        "name": "ANMI",
        "description": "Association of National Exchanges Members of India",
        "category": "broker-association",
        "urls": ["http://www.anmi.in/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice", "update"],
        "new_source": True
    },
    "brokers_forum": {
        "name": "BSE Brokers Forum",
        "description": "BSE Brokers' Forum",
        "category": "broker-association",
        "urls": ["https://www.bsebrokersforum.co.in/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True
    },
    "asba": {
        "name": "ASBA",
        "description": "Association of Stock Broking Agencies",
        "category": "broker-association",
        "urls": ["http://www.asba.co.in/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True
    },

    # ===== MARKET DATA & INDICES (3) =====
    "nse_indices": {
        "name": "NSE Indices",
        "description": "NSE Indices Limited",
        "category": "market-data",
        "urls": ["https://www.niftyindices.com/"],
        "rate_limit_delay": 2,
        "update_types": ["notice", "circular", "methodology"],
        "new_source": True
    },
    "bse_indices": {
        "name": "BSE Indices",
        "description": "Asia Index Private Limited (BSE Indices)",
        "category": "market-data",
        "urls": ["https://www.bseindia.com/indices/"],
        "rate_limit_delay": 2,
        "update_types": ["notice", "circular"],
        "new_source": True
    },

    # ===== TRADING PLATFORMS & TECH (4) =====
    "cdslindia": {
        "name": "CDSL Ventures",
        "description": "CDSL Ventures Limited (CVL)",
        "category": "market-infrastructure",
        "urls": ["https://www.cdslindia.com/ventures/"],
        "rate_limit_delay": 2,
        "update_types": ["notice", "circular"],
        "new_source": True
    },
    "nsdl_eservices": {
        "name": "NSDL e-Governance",
        "description": "NSDL e-Governance Infrastructure Limited",
        "category": "market-infrastructure",
        "urls": ["https://www.nsdl.co.in/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True
    },

    # ===== COMMODITY TRADING (2) =====
    "nmce": {
        "name": "NMCE",
        "description": "National Multi-Commodity Exchange",
        "category": "commodity-exchange",
        "urls": ["http://www.nmce.com/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True
    },
    "ace": {
        "name": "ACE",
        "description": "ACE Derivatives Exchange",
        "category": "commodity-exchange",
        "urls": ["https://www.ace.agri/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True
    },

    # ===== DERIVATIVES & OPTIONS (2) =====
    "nse_fo": {
        "name": "NSE F&O",
        "description": "NSE Futures & Options Segment",
        "category": "derivatives",
        "urls": ["https://www.nseindia.com/products-services/equity-derivatives"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "notice"],
        "new_source": True,
        "requires_browser": True
    },
    "bse_fo": {
        "name": "BSE F&O",
        "description": "BSE Futures & Options",
        "category": "derivatives",
        "urls": ["https://www.bseindia.com/markets/derivatives/"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "notice"],
        "new_source": True,
        "requires_browser": True
    },

    # ===== INVESTOR PROTECTION (4) =====
    "iepf": {
        "name": "IEPF",
        "description": "Investor Education and Protection Fund Authority",
        "category": "investor-protection",
        "urls": ["http://www.iepf.gov.in/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notification"],
        "new_source": True
    },
    "scores": {
        "name": "SCORES",
        "description": "SEBI Complaints Redress System",
        "category": "investor-protection",
        "urls": ["https://scores.gov.in/"],
        "rate_limit_delay": 2,
        "update_types": ["notice", "update"],
        "new_source": True
    },
    "investor_grievance": {
        "name": "IGR Cell",
        "description": "Investor Grievance Redressal Cell",
        "category": "investor-protection",
        "urls": ["https://igrs.sebi.gov.in/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True
    },

    # ===== LISTING & COMPLIANCE (2) =====
    "bse_listing": {
        "name": "BSE Listing",
        "description": "BSE Listing Compliance",
        "category": "compliance",
        "urls": ["https://listing.bseindia.com/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True
    },
    "nse_listing": {
        "name": "NSE Listing",
        "description": "NSE Listing Compliance",
        "category": "compliance",
        "urls": ["https://www.nseindia.com/regulations/listing-compliance"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "notice"],
        "new_source": True,
        "requires_browser": True
    },

    # ===== TREASURY & DEBT MARKET (3) =====
    "rbi_fmrd": {
        "name": "RBI FMRD",
        "description": "RBI Financial Markets Regulation Department",
        "category": "banking-regulator",
        "urls": ["https://www.rbi.org.in/Scripts/FMRD.aspx"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "notification"],
        "new_source": True
    },
    "rbi_dbod": {
        "name": "RBI DBOD",
        "description": "RBI Department of Banking Operations and Development",
        "category": "banking-regulator",
        "urls": ["https://www.rbi.org.in/Scripts/BS_ViewBulletin.aspx"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "master-circular"],
        "new_source": True
    },

    # ===== FDI & FOREIGN EXCHANGE (2) =====
    "fema": {
        "name": "FEMA",
        "description": "Foreign Exchange Management Act",
        "category": "forex",
        "urls": ["https://www.rbi.org.in/Scripts/Fema.aspx"],
        "rate_limit_delay": 3,
        "update_types": ["notification", "circular"],
        "new_source": True
    },
    "dipp": {
        "name": "DPIIT",
        "description": "Department for Promotion of Industry and Internal Trade",
        "category": "government",
        "urls": ["https://www.dpiit.gov.in/"],
        "rate_limit_delay": 2,
        "update_types": ["press-release", "circular", "notification"],
        "new_source": True
    },

    # ===== SEBI SPECIALIZED DIVISIONS (5) =====
    "sebi_enforcement": {
        "name": "SEBI Enforcement",
        "description": "SEBI Enforcement and Investigation Department",
        "category": "regulator",
        "urls": ["https://www.sebi.gov.in/enforcement.html"],
        "rate_limit_delay": 3,
        "update_types": ["order", "notice"],
        "new_source": True
    },
    "sebi_intermediaries": {
        "name": "SEBI Intermediaries",
        "description": "SEBI Division of Intermediaries",
        "category": "regulator",
        "urls": ["https://www.sebi.gov.in/intermediaries.html"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "guidelines"],
        "new_source": True
    },
    "sebi_mr": {
        "name": "SEBI MR",
        "description": "SEBI Market Regulation Department",
        "category": "regulator",
        "urls": ["https://www.sebi.gov.in/"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "order"],
        "new_source": True
    },
    "sebi_cir": {
        "name": "SEBI CIR",
        "description": "SEBI Corporation Finance Department",
        "category": "regulator",
        "urls": ["https://www.sebi.gov.in/"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "guidelines"],
        "new_source": True
    },
    "sebi_broker_regulations": {
        "name": "SEBI Broker Regulations",
        "description": "SEBI broker-relevant regulations",
        "category": "regulator",
        "urls": ["https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingLegal=yes&sid=1&smid=0&ssid=3"],
        "rate_limit_delay": 3,
        "update_types": ["regulation", "amendment"],
        "new_source": True
    },
    "sebi_broker_master_circulars": {
        "name": "SEBI Broker Master Circulars",
        "description": "SEBI broker-related master circulars",
        "category": "regulator",
        "urls": ["https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6&smid=0"],
        "rate_limit_delay": 3,
        "update_types": ["master-circular"],
        "new_source": True
    },

    # ===== ARBITRATION & DISPUTES (2) =====
    "sebi_saa": {
        "name": "SEBI SAT",
        "description": "Securities Appellate Tribunal",
        "category": "legal",
        "urls": ["http://www.sat.gov.in/"],
        "rate_limit_delay": 2,
        "update_types": ["order", "judgment"],
        "new_source": True
    },
    "stock_exchange_arbitration": {
        "name": "Exchange Arbitration",
        "description": "Stock Exchange Arbitration Mechanism",
        "category": "legal",
        "urls": ["https://www.nseindia.com/invest/arbitration"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True,
        "requires_browser": True
    },

    # ===== KYC & AML (3) =====
    "cersai": {
        "name": "CERSAI",
        "description": "Central Registry of Securitisation Asset Reconstruction",
        "category": "market-infrastructure",
        "urls": ["https://www.cersai.org.in/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notification"],
        "new_source": True
    },
    "ckycr": {
        "name": "CKYCR",
        "description": "Central KYC Registry",
        "category": "kyc",
        "urls": ["https://www.ckycindia.in/"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "notice"],
        "new_source": True
    },
    "fiu_ind_guidance": {
        "name": "FIU-IND Guidance",
        "description": "FIU-IND guidance and reporting-entity circulars",
        "category": "kyc",
        "urls": ["https://fiuindia.gov.in/files/downloads/downloads.html"],
        "rate_limit_delay": 2,
        "update_types": ["guidelines", "circular", "notification"],
        "new_source": True
    },
    "uidai_authentication_docs": {
        "name": "UIDAI Authentication Documents",
        "description": "UIDAI authentication circulars and onboarding documents",
        "category": "government",
        "urls": ["https://uidai.gov.in/en/ecosystem/authentication-devices-documents/authentication-document.html"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "guidelines", "checklist"],
        "new_source": True
    },

    # ===== WEALTH & ADVISORY (2) =====
    "sebi_ria": {
        "name": "SEBI RIA",
        "description": "SEBI Registered Investment Advisers",
        "category": "advisory",
        "urls": ["https://www.sebi.gov.in/"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "guidelines"],
        "new_source": True
    },
    "sebi_ra": {
        "name": "SEBI RA",
        "description": "SEBI Research Analysts",
        "category": "advisory",
        "urls": ["https://www.sebi.gov.in/"],
        "rate_limit_delay": 3,
        "update_types": ["circular", "guidelines"],
        "new_source": True
    },

    # ===== ADDITIONAL GOVERNMENT CIRCULAR SOURCES (5) =====
    "doe": {
        "name": "Department of Expenditure",
        "description": "Ministry of Finance - Department of Expenditure Circulars",
        "category": "government",
        "urls": ["https://doe.gov.in/circulars"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "office-memorandum", "notification"],
        "new_source": True
    },
    "nfra": {
        "name": "NFRA",
        "description": "National Financial Reporting Authority Circulars",
        "category": "regulator",
        "urls": ["https://nfra.gov.in/document-category/circulars/"],
        "rate_limit_delay": 2,
        "update_types": ["circular"],
        "new_source": True
    },
    "ibbi": {
        "name": "IBBI",
        "description": "Insolvency and Bankruptcy Board of India Circulars",
        "category": "regulator",
        "urls": ["https://ibbi.gov.in/legal-framework/circulars"],
        "rate_limit_delay": 2,
        "update_types": ["circular"],
        "new_source": True
    },
    "pfrda_circulars": {
        "name": "PFRDA Circulars",
        "description": "PFRDA Active Circulars",
        "category": "pension",
        "urls": ["https://www.pfrda.org.in/web/pfrda/regulatory-framework/circulars/active-circulars"],
        "rate_limit_delay": 2,
        "update_types": ["circular", "guidelines", "notification"],
        "new_source": True
    },
    "pfrda_master_circulars": {
        "name": "PFRDA Master Circulars",
        "description": "PFRDA Active Master Circulars",
        "category": "pension",
        "urls": ["https://www.pfrda.org.in/web/pfrda/regulatory-framework/master-circulars/active-master-circulars"],
        "rate_limit_delay": 2,
        "update_types": ["master-circular", "circular", "guidelines"],
        "new_source": True
    },
}

def print_summary() -> None:
    """Print a simple summary when the module is run directly."""
    print(f"Total additional sources: {len(ADDITIONAL_BROKER_SOURCES)}")
    print("\nCategories:")
    categories = {}
    for site in ADDITIONAL_BROKER_SOURCES.values():
        cat = site["category"]
        categories[cat] = categories.get(cat, 0) + 1

    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    print_summary()
