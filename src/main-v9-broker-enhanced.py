# GovUpdate API v9.0 - Broker-Enhanced Edition
# Added 33 more broker-relevant sources (Total: 88 sources)
# Fixed generic scraping to be less restrictive
# This file extends v8 with broker-specific enhancements

# Import all from v8
import sys
import os

# Get the directory of this file
current_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
sys.path.insert(0, current_dir)

from importlib import util
v8_path = os.path.join(current_dir, "main-v8-improved.py")
spec = util.spec_from_file_location("main_v8", v8_path)
main_v8 = util.module_from_spec(spec)
sys.modules['main_v8'] = main_v8
spec.loader.exec_module(main_v8)

# Import everything from v8
from main_v8 import *

# Add additional sources
sources_path = os.path.join(current_dir, "additional_sources.py")
spec_sources = util.spec_from_file_location("additional_sources", sources_path)
additional_sources = util.module_from_spec(spec_sources)
spec_sources.loader.exec_module(additional_sources)
ADDITIONAL_BROKER_SOURCES = additional_sources.ADDITIONAL_BROKER_SOURCES

# Merge the new sources
SITES.update(ADDITIONAL_BROKER_SOURCES)

if 'scores' in SITES:
    SITES['scores']['urls'] = ['https://scores.sebi.gov.in/']
    SITES['scores']['html_strategy'] = 'remote_generic_html'
    SITES['scores']['allowed_domains'] = ['scores.sebi.gov.in', 'sebi.gov.in', 'investor.sebi.gov.in']
    SITES['scores']['required_keywords'] = ['circular', 'grievance', 'redressal', 'complaint']
    SITES['scores']['remote_rss_via_ssh'] = 'ubuntu@151.80.232.163'

if 'bse' in SITES:
    SITES['bse']['urls'] = ['https://www.bseindia.com/markets/MarketInfo/NoticesCirculars.aspx']
    SITES['bse']['html_strategy'] = 'bse_notices'
    SITES['bse']['required_keywords'] = ['noticescirculars', 'circular', 'notice']
    SITES['bse']['minimum_expected_items'] = 1

if 'bse_fo' in SITES:
    SITES['bse_fo']['urls'] = ['https://www.bseindia.com/markets/MarketInfo/NoticesCirculars.aspx']
    SITES['bse_fo']['html_strategy'] = 'bse_notices'
    SITES['bse_fo']['bse_include_terms'] = ['derivative', 'derivatives', 'futures', 'options', 'commodity derivatives']
    SITES['bse_fo']['bse_previous_day_lookback'] = 7
    SITES['bse_fo']['allowed_domains'] = ['bseindia.com']
    SITES['bse_fo']['minimum_expected_items'] = 1
    SITES['bse_fo']['requires_browser'] = False
    SITES['bse_fo']['special_source_only'] = True

if 'nse_fo' in SITES:
    SITES['nse_fo']['urls'] = ['https://www.nseindia.com/resources/exchange-communication-circulars']
    SITES['nse_fo']['api_strategy'] = 'nse_circulars'
    SITES['nse_fo']['nse_circular_department'] = 'FAO'
    SITES['nse_fo']['nse_circular_days'] = 365
    SITES['nse_fo']['allowed_domains'] = ['nseindia.com', 'nsearchives.nseindia.com']
    SITES['nse_fo']['requires_browser'] = False

if 'nse_clearing' in SITES:
    SITES['nse_clearing']['urls'] = ['https://www.nseindia.com/resources/exchange-communication-circulars']
    SITES['nse_clearing']['api_strategy'] = 'nse_circulars'
    SITES['nse_clearing']['nse_circular_company'] = 'NCL'
    SITES['nse_clearing']['nse_circular_days'] = 365
    SITES['nse_clearing']['allowed_domains'] = ['nseindia.com', 'nsearchives.nseindia.com']
    SITES['nse_clearing']['minimum_expected_items'] = 10
    SITES['nse_clearing']['requires_browser'] = False

if 'npci' in SITES:
    current_year = datetime.now().year
    SITES['npci']['urls'] = [
        'https://www.npci.org.in/circulars/upi',
        'https://www.npci.org.in/circulars/imps',
        'https://www.npci.org.in/circulars/nach',
    ]
    SITES['npci']['api_strategy'] = 'npci_circulars'
    SITES['npci']['npci_products'] = ['upi', 'imps', 'nach']
    SITES['npci']['npci_years'] = [current_year, current_year - 1]
    SITES['npci']['required_keywords'] = ['circular', '.pdf']

if 'nse' in SITES:
    SITES['nse']['urls'] = ['https://www.nseindia.com/resources/exchange-communication-circulars']
    SITES['nse']['api_strategy'] = 'nse_circulars'
    SITES['nse']['nse_circular_days'] = 30
    SITES['nse']['nse_circular_companies'] = ['NSE', 'NSEIL']
    SITES['nse']['allowed_domains'] = ['nseindia.com', 'nsearchives.nseindia.com']
    SITES['nse']['required_keywords'] = ['circular', '.pdf']
    SITES['nse']['skip_keywords'] = ['twitter', 'facebook', 'instagram', 'linkedin', 'youtube', 'whatsapp']
    SITES['nse']['minimum_expected_items'] = 10
    SITES['nse']['requires_browser'] = False

if 'bse_listing' in SITES:
    SITES['bse_listing']['urls'] = ['https://www.bseindia.com/corporates/CirularToListedComp.html']
    SITES['bse_listing']['api_strategy'] = 'bse_listing_api'
    SITES['bse_listing']['api_url'] = 'https://api.bseindia.com/BseIndiaAPI/api/GetDataCirToListComp/w'
    SITES['bse_listing']['referer'] = 'https://www.bseindia.com/corporates/CirularToListedComp.html'
    SITES['bse_listing']['allowed_domains'] = ['bseindia.com', 'api.bseindia.com']
    SITES['bse_listing']['minimum_expected_items'] = 5
    SITES['bse_listing']['requires_browser'] = False

if 'nse_listing' in SITES:
    SITES['nse_listing']['urls'] = [
        'https://www.nseindia.com/static/companies-listing/circular-for-listed-companies-equity-market',
        'https://www.nseindia.com/companies-listing/circular-for-listed-companies-debt-market',
        'https://www.nseindia.com/companies-listing/circular-for-listed-companies-sse',
    ]
    SITES['nse_listing']['html_strategy'] = 'nse_listing_pages'
    SITES['nse_listing']['allowed_domains'] = ['nseindia.com', 'nsearchives.nseindia.com']
    SITES['nse_listing']['minimum_expected_items'] = 5
    SITES['nse_listing']['requires_browser'] = False

if 'iccl' in SITES:
    SITES['iccl']['urls'] = ['https://www.icclindia.com/DynamicPages/NoticesCirculars.aspx']
    SITES['iccl']['html_strategy'] = 'iccl_notices'
    SITES['iccl']['allowed_domains'] = ['icclindia.com']
    SITES['iccl']['minimum_expected_items'] = 5
    SITES['iccl']['requires_browser'] = False

if 'ccil' in SITES:
    SITES['ccil']['urls'] = ['https://www.ccilindia.com/ccil-notification-view-all']
    SITES['ccil']['html_strategy'] = 'ccil_notifications'
    SITES['ccil']['allowed_domains'] = ['ccilindia.com']
    SITES['ccil']['skip_url_terms'] = ['-xls', '-xlsx']
    SITES['ccil']['minimum_expected_items'] = 5
    SITES['ccil']['requires_browser'] = False

if 'cbic' in SITES:
    SITES['cbic']['urls'] = [
        'https://courier.cbic.gov.in/circular.jsp',
        'https://courier.cbic.gov.in/notification.jsp',
    ]
    SITES['cbic']['html_strategy'] = 'cbic_tables'
    SITES['cbic']['allowed_domains'] = ['courier.cbic.gov.in', 'cbic.gov.in']
    SITES['cbic']['minimum_expected_items'] = 1
    SITES['cbic']['requires_browser'] = False

if 'gst_council' in SITES:
    SITES['gst_council']['urls'] = ['https://gstcouncil.gov.in/cgst-circulars']
    SITES['gst_council']['html_strategy'] = 'gst_council_circulars'
    SITES['gst_council']['allowed_domains'] = ['gstcouncil.gov.in']
    SITES['gst_council']['minimum_expected_items'] = 3
    SITES['gst_council']['requires_browser'] = False

if 'doe' in SITES:
    SITES['doe']['html_strategy'] = 'doe_circulars'
    SITES['doe']['allowed_domains'] = ['doe.gov.in']
    SITES['doe']['minimum_expected_items'] = 5
    SITES['doe']['requires_browser'] = False

if 'nfra' in SITES:
    SITES['nfra']['html_strategy'] = 'nfra_circulars'
    SITES['nfra']['allowed_domains'] = ['nfra.gov.in', 'cdnbbsr.s3waas.gov.in']
    SITES['nfra']['minimum_expected_items'] = 1
    SITES['nfra']['requires_browser'] = False

if 'ibbi' in SITES:
    SITES['ibbi']['html_strategy'] = 'ibbi_circulars'
    SITES['ibbi']['allowed_domains'] = ['ibbi.gov.in']
    SITES['ibbi']['minimum_expected_items'] = 5
    SITES['ibbi']['requires_browser'] = False

if 'pfrda_circulars' in SITES:
    SITES['pfrda_circulars']['html_strategy'] = 'pfrda_listing'
    SITES['pfrda_circulars']['pfrda_page_key'] = '/web/pfrda/regulatory-framework/circulars/active-circulars'
    SITES['pfrda_circulars']['allowed_domains'] = ['pfrda.org.in']
    SITES['pfrda_circulars']['minimum_expected_items'] = 10
    SITES['pfrda_circulars']['requires_browser'] = False

if 'pfrda_master_circulars' in SITES:
    SITES['pfrda_master_circulars']['html_strategy'] = 'pfrda_listing'
    SITES['pfrda_master_circulars']['pfrda_page_key'] = '/web/pfrda/regulatory-framework/master-circulars/active-master-circulars'
    SITES['pfrda_master_circulars']['allowed_domains'] = ['pfrda.org.in']
    SITES['pfrda_master_circulars']['minimum_expected_items'] = 5
    SITES['pfrda_master_circulars']['requires_browser'] = False

if 'mcx' in SITES:
    SITES['mcx']['urls'] = ['https://www.mcxindia.com/circulars']
    SITES['mcx']['api_strategy'] = 'mcx_rss'
    SITES['mcx']['rss_feeds'] = [
        {'url': 'https://www.mcxindia.com/en/rssfeed/circulars/ctcl', 'category': 'ctcl', 'type': 'ctcl'},
        {'url': 'https://www.mcxindia.com/en/rssfeed/circulars/membership-and-compliance', 'category': 'circular', 'type': 'membership-compliance'},
        {'url': 'https://www.mcxindia.com/en/rssfeed/circulars/ddr', 'category': 'circular', 'type': 'due-date-rate'},
        {'url': 'https://www.mcxindia.com/en/rssfeed/circulars/c-s', 'category': 'circular', 'type': 'clearing-settlement'},
        {'url': 'https://www.mcxindia.com/en/rssfeed/circulars/legal', 'category': 'legal', 'type': 'legal'},
        {'url': 'https://www.mcxindia.com/en/rssfeed/circulars/general', 'category': 'circular', 'type': 'general'},
        {'url': 'https://www.mcxindia.com/en/rssfeed/circulars/tech', 'category': 'technology', 'type': 'technology'},
        {'url': 'https://www.mcxindia.com/en/rssfeed/circulars/t-s', 'category': 'trading-surveillance', 'type': 'trading-surveillance'},
    ]
    SITES['mcx']['required_keywords'] = ['circular', '.pdf']
    SITES['mcx']['minimum_expected_items'] = 4
    SITES['mcx']['requires_browser'] = False

if 'mca' in SITES:
    SITES['mca']['urls'] = ['https://www.mca.gov.in/content/mca/global/en/home.html']
    SITES['mca']['browser_url'] = 'https://www.mca.gov.in/content/mca/global/en/home.html'
    SITES['mca']['browser_strategy'] = 'mca_home'
    SITES['mca']['minimum_expected_items'] = 1
    SITES['mca']['requires_browser'] = True

if 'sebi' in SITES:
    SITES['sebi']['urls'] = ['https://www.sebi.gov.in/sebirss.xml']
    SITES['sebi']['rss_feeds'] = ['https://www.sebi.gov.in/sebirss.xml']
    SITES['sebi']['rss_only'] = True
    SITES['sebi']['rss_browser_fallback'] = True
    SITES['sebi']['rss_browser_page_url'] = 'https://www.sebi.gov.in/rss.html'
    SITES['sebi']['remote_rss_via_ssh'] = 'ubuntu@151.80.232.163'
    SITES['sebi']['retry_on_empty'] = 1
    SITES['sebi']['retry_on_empty_delay_seconds'] = 2
    SITES['sebi']['browser_profile'] = 'openclaw'

if 'sebi_enforcement' in SITES:
    SITES['sebi_enforcement']['urls'] = ['https://www.sebi.gov.in/sebirss.xml']
    SITES['sebi_enforcement']['rss_feeds'] = ['https://www.sebi.gov.in/sebirss.xml']
    SITES['sebi_enforcement']['required_keywords'] = [
        'enforcement', 'order', 'recovery', 'auction notice', 'summons',
        'settlement order', 'adjudication order', 'notice of demand'
    ]
    SITES['sebi_enforcement']['skip_keywords'] = ['youtube', '/department/', 'overview', 'complaint registration']
    SITES['sebi_enforcement']['minimum_expected_items'] = 1
    SITES['sebi_enforcement']['rss_only'] = True
    SITES['sebi_enforcement']['rss_browser_fallback'] = True
    SITES['sebi_enforcement']['rss_browser_page_url'] = 'https://www.sebi.gov.in/rss.html'
    SITES['sebi_enforcement']['remote_rss_via_ssh'] = 'ubuntu@151.80.232.163'
    SITES['sebi_enforcement']['retry_on_empty'] = 1
    SITES['sebi_enforcement']['retry_on_empty_delay_seconds'] = 2
    SITES['sebi_enforcement']['browser_profile'] = 'openclaw'

if 'sebi_intermediaries' in SITES:
    SITES['sebi_intermediaries']['urls'] = ['https://www.sebi.gov.in/sebirss.xml']
    SITES['sebi_intermediaries']['rss_feeds'] = ['https://www.sebi.gov.in/sebirss.xml']
    SITES['sebi_intermediaries']['required_keywords'] = [
        'merchant banker', 'merchant bankers',
        'stock broker', 'stock brokers',
        'clearing member', 'clearing members',
        'investment adviser', 'investment advisers',
        'research analyst', 'research analysts', 'research services',
        'registrar', 'registrars', 'registrars to an issue',
        'share transfer', 'share transfer agent', 'share transfer agents',
        'depository', 'depositories', 'depository participant', 'depository participants', 'depository system',
        'portfolio manager', 'portfolio managers',
        'mutual fund', 'mutual funds',
        'credit rating', 'credit rating agency', 'credit rating agencies',
        'debenture trustee', 'debenture trustees',
        'intermediary', 'intermediaries',
        'social media platforms', 'nism certification module'
    ]
    SITES['sebi_intermediaries']['skip_keywords'] = ['youtube', '/department/', 'overview', 'complaint registration']
    SITES['sebi_intermediaries']['minimum_expected_items'] = 1
    SITES['sebi_intermediaries']['rss_only'] = True
    SITES['sebi_intermediaries']['rss_browser_fallback'] = True
    SITES['sebi_intermediaries']['rss_browser_page_url'] = 'https://www.sebi.gov.in/rss.html'
    SITES['sebi_intermediaries']['remote_rss_via_ssh'] = 'ubuntu@151.80.232.163'
    SITES['sebi_intermediaries']['retry_on_empty'] = 1
    SITES['sebi_intermediaries']['retry_on_empty_delay_seconds'] = 2
    SITES['sebi_intermediaries']['browser_profile'] = 'openclaw'

sebi_topic_listing_sites = {
    'sebi_mr': {
        'urls': [
            'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&search=Market+Infrastructure+Institutions',
            'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&search=Stock+Exchanges+and+Clearing+Corporations',
            'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&search=Depository+System',
        ],
        'required_keywords': [
            'market infrastructure institution', 'market infrastructure institutions', 'mii', 'miis',
            'stock exchange', 'stock exchanges',
            'clearing corporation', 'clearing corporations',
            'depository system', 'depository systems',
            'technical glitch',
        ],
        'skip_keywords': ['youtube', '/department/', 'overview', 'complaint registration', 'complaint status', 'calculator', 'recovery certificate', 'adjudication order', 'settlement order'],
    },
    'sebi_cir': {
        'urls': [
            'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&search=Merchant+Bankers',
            'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&search=Issue+of+Capital+and+Disclosure+Requirements',
            'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&search=Non-convertible+Securities',
        ],
        'required_keywords': [
            'merchant banker', 'merchant bankers',
            'debenture', 'debentures',
            'share based employee',
            'buy-back', 'buyback',
            'takeover',
            'listing obligations',
            'non-convertible securities',
            'issue of capital and disclosure requirements',
            'icdr',
        ],
        'skip_keywords': ['youtube', '/department/', 'overview', 'complaint registration', 'complaint status', 'recovery certificate', 'adjudication order', 'settlement order', 'issued against'],
    },
    'sebi_ria': {
        'urls': ['https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&search=Investment+Advisers'],
        'required_keywords': ['investment adviser', 'investment advisers'],
        'skip_keywords': ['youtube', '/department/', 'overview', 'adjudication order', 'settlement order', 'frequently asked questions'],
    },
    'sebi_ra': {
        'urls': ['https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&search=Research+Analysts'],
        'required_keywords': ['research analyst', 'research analysts', 'research services'],
        'skip_keywords': ['youtube', '/department/', 'overview', 'adjudication order', 'settlement order'],
    },
}

for site_key, filters in sebi_topic_listing_sites.items():
    if site_key in SITES:
        SITES[site_key]['urls'] = filters['urls']
        SITES[site_key]['html_strategy'] = 'sebi_news_listing'
        SITES[site_key]['allowed_domains'] = ['sebi.gov.in']
        SITES[site_key]['required_keywords'] = filters['required_keywords']
        SITES[site_key]['skip_keywords'] = filters['skip_keywords']
        SITES[site_key]['sebi_listing_types'] = ['Circulars', 'Master Circulars']
        SITES[site_key]['minimum_expected_items'] = 1
        SITES[site_key]['requires_browser'] = False
        SITES[site_key]['remote_rss_via_ssh'] = 'ubuntu@151.80.232.163'

if 'ckycr' in SITES:
    SITES['ckycr']['urls'] = [
        'https://www.ckycindia.in/ckyc/index.php?r=notification',
        'https://www.ckycindia.in/ckyc/Communiques.php',
    ]
    SITES['ckycr']['html_strategy'] = 'ckycr_notifications'
    SITES['ckycr']['allowed_domains'] = ['ckycindia.in']
    SITES['ckycr']['required_keywords'] = ['notification', 'communique']
    SITES['ckycr']['skip_keywords'] = ['board of directors', 'view your ckyc card', 'about_us', 'integrity pledge', 'fight against corruption']
    SITES['ckycr']['minimum_expected_items'] = 5
    SITES['ckycr']['requires_browser'] = False

# Tighten noisy generic sources onto their actual circular/notification pages.
if 'nism' in SITES:
    SITES['nism']['urls'] = ['https://www.nism.ac.in/circular/']
    SITES['nism']['required_url_terms'] = ['/circular/']
    SITES['nism']['skip_title_terms'] = ['press releases', 'compliance']
    SITES['nism']['minimum_expected_items'] = 2

if 'irdai' in SITES:
    SITES['irdai']['urls'] = ['https://irdai.gov.in/circulars']
    SITES['irdai']['html_strategy'] = 'irdai_circulars'
    SITES['irdai']['allowed_domains'] = ['irdai.gov.in']
    SITES['irdai']['minimum_expected_items'] = 5

if 'icai' in SITES:
    SITES['icai']['urls'] = ['https://www.icai.org/category/notifications']
    SITES['icai']['required_url_terms'] = ['resource.cdn.icai.org']
    SITES['icai']['required_title_terms'] = ['notification', 'result', 'announcement']
    SITES['icai']['minimum_expected_items'] = 3

if 'india_inx' in SITES:
    SITES['india_inx']['urls'] = ['https://www.indiainx.com/markets/Circulars.aspx']
    SITES['india_inx']['required_url_terms'] = ['/circulars/']
    SITES['india_inx']['skip_title_terms'] = ['provider registration form', 'clearing banks', 'indicative margins', 'regulation overview']
    SITES['india_inx']['minimum_expected_items'] = 5

if 'nabard' in SITES:
    SITES['nabard']['urls'] = ['https://www.nabard.org/circulars.aspx?cid=504&id=24']
    SITES['nabard']['html_strategy'] = 'nabard_circulars'
    SITES['nabard']['required_url_terms'] = ['circularpage.aspx', '/auth/writereaddata/tender/']
    SITES['nabard']['skip_url_terms'] = ['/auth/writereaddata/file/', '/auth/cp/']
    SITES['nabard']['skip_title_terms'] = [
        'information centre', 'financial report', 'publication', 'glossary',
        'gender policy', 'internal committee', 'media room', 'unit cost',
        'model bankable projects', 'contact us'
    ]
    SITES['nabard']['minimum_expected_items'] = 5

if 'epfo' in SITES:
    SITES['epfo']['urls'] = ['https://www.epfindia.gov.in/site_en/index.php']
    SITES['epfo']['required_url_terms'] = ['/site_docs/pdfs/circulars/']
    SITES['epfo']['required_title_terms'] = ['guidelines', 'complaints', 'notification', 'circular']
    SITES['epfo']['minimum_expected_items'] = 2

if 'hdfc_mf' in SITES:
    SITES['hdfc_mf']['urls'] = ['https://www.hdfcfund.com/statutory-disclosure/form-disclosures/addenda-notices']
    SITES['hdfc_mf']['required_title_terms'] = ['notice', 'addendum', 'addenda']
    SITES['hdfc_mf']['skip_title_terms'] = ['moa & aoa', 'public caution notice', 'booklet']
    SITES['hdfc_mf']['allowed_domains'] = ['hdfcfund.com', 'files.hdfcfund.com']
    SITES['hdfc_mf']['minimum_expected_items'] = 2

if 'lic' in SITES:
    SITES['lic']['urls'] = ['https://www.licindia.in/web/guest/press-release']
    SITES['lic']['html_strategy'] = 'lic_press_releases'
    SITES['lic']['allowed_domains'] = ['licindia.in']
    SITES['lic']['minimum_expected_items'] = 1

if 'crif_highmark' in SITES:
    SITES['crif_highmark']['urls'] = ['https://www.crifhighmark.com/news-events/rbi-notifications']
    SITES['crif_highmark']['html_strategy'] = 'crif_rbi_notifications'
    SITES['crif_highmark']['allowed_domains'] = ['crifhighmark.com']
    SITES['crif_highmark']['minimum_expected_items'] = 1

if 'ministry_finance' in SITES:
    SITES['ministry_finance']['urls'] = ['https://doe.gov.in/orders-circulars']
    SITES['ministry_finance']['html_strategy'] = 'doe_orders_hub'
    SITES['ministry_finance']['minimum_expected_items'] = 5

if 'rbi_dbod' in SITES:
    SITES['rbi_dbod']['urls'] = ['https://www.rbi.org.in/Scripts/NotificationUser.aspx']
    SITES['rbi_dbod']['html_strategy'] = 'rbi_notifications'
    SITES['rbi_dbod']['rbi_title_keywords'] = [
        'bank', 'banking', 'commercial banks', 'small finance banks',
        'rural co-operative', 'co-operative', 'cooperative', 'nbfc',
        'msme', 'grievance', 'lead bank'
    ]
    SITES['rbi_dbod']['minimum_expected_items'] = 5
    SITES['rbi_dbod']['requires_browser'] = False

if 'rbi_fmrd' in SITES:
    SITES['rbi_fmrd']['urls'] = ['https://www.rbi.org.in/Scripts/NotificationUser.aspx']
    SITES['rbi_fmrd']['html_strategy'] = 'rbi_notifications'
    SITES['rbi_fmrd']['rbi_title_keywords'] = [
        'derivative', 'foreign exchange', 'money market', 'government securities',
        'repo', 'borrowing and lending', 'otc', 'swap', 'call money'
    ]
    SITES['rbi_fmrd']['rbi_detail_keywords'] = [
        'fmrd', 'derivative', 'foreign exchange', 'money market',
        'government securities', 'repo', 'otc'
    ]
    SITES['rbi_fmrd']['minimum_expected_items'] = 3
    SITES['rbi_fmrd']['requires_browser'] = False

if 'dea' in SITES:
    SITES['dea']['skip_keywords'] = ['tender', 'bidding', 'gem-bidding', 'supply and delivery', 'cab & taxi', 'event management company']

if 'cbdt' in SITES:
    SITES['cbdt']['urls'] = ['https://www.incometaxindia.gov.in/circulars']
    SITES['cbdt']['api_strategy'] = 'cbdt_structured_contents'
    SITES['cbdt']['browser_url'] = 'https://www.incometaxindia.gov.in/circulars'
    SITES['cbdt']['page_size'] = 50
    SITES['cbdt']['max_pages'] = 10
    SITES['cbdt']['allowed_domains'] = ['incometaxindia.gov.in']
    SITES['cbdt']['minimum_expected_items'] = 5
    SITES['cbdt']['requires_browser'] = False

if 'sebi_broker_regulations' in SITES:
    SITES['sebi_broker_regulations']['urls'] = ['https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingLegal=yes&sid=1&smid=0&ssid=3']
    SITES['sebi_broker_regulations']['html_strategy'] = 'sebi_legal_listing'
    SITES['sebi_broker_regulations']['browser_urls'] = list(SITES['sebi_broker_regulations']['urls'])
    SITES['sebi_broker_regulations']['browser_html_strategy'] = 'sebi_legal_listing'
    SITES['sebi_broker_regulations']['browser_fallback'] = True
    SITES['sebi_broker_regulations']['browser_fallback_mode'] = 'if_empty_or_error'
    SITES['sebi_broker_regulations']['browser_profile'] = 'openclaw'
    SITES['sebi_broker_regulations']['browser_wait_selector'] = 'table tbody tr'
    SITES['sebi_broker_regulations']['browser_wait_seconds'] = 4
    SITES['sebi_broker_regulations']['allowed_domains'] = ['sebi.gov.in']
    SITES['sebi_broker_regulations']['required_url_terms'] = ['/legal/regulations/']
    SITES['sebi_broker_regulations']['sebi_title_keywords'] = ['stock brokers']
    SITES['sebi_broker_regulations']['minimum_expected_items'] = 1
    SITES['sebi_broker_regulations']['remote_rss_via_ssh'] = 'ubuntu@151.80.232.163'

if 'sebi_broker_master_circulars' in SITES:
    SITES['sebi_broker_master_circulars']['urls'] = ['https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6&smid=0']
    SITES['sebi_broker_master_circulars']['html_strategy'] = 'sebi_legal_listing'
    SITES['sebi_broker_master_circulars']['browser_urls'] = list(SITES['sebi_broker_master_circulars']['urls'])
    SITES['sebi_broker_master_circulars']['browser_html_strategy'] = 'sebi_legal_listing'
    SITES['sebi_broker_master_circulars']['browser_fallback'] = True
    SITES['sebi_broker_master_circulars']['browser_fallback_mode'] = 'if_empty_or_error'
    SITES['sebi_broker_master_circulars']['browser_profile'] = 'openclaw'
    SITES['sebi_broker_master_circulars']['browser_wait_selector'] = 'table tbody tr'
    SITES['sebi_broker_master_circulars']['browser_wait_seconds'] = 4
    SITES['sebi_broker_master_circulars']['allowed_domains'] = ['sebi.gov.in']
    SITES['sebi_broker_master_circulars']['required_url_terms'] = ['/legal/master-circulars/']
    SITES['sebi_broker_master_circulars']['sebi_title_keywords'] = ['stock brokers']
    SITES['sebi_broker_master_circulars']['minimum_expected_items'] = 1
    SITES['sebi_broker_master_circulars']['remote_rss_via_ssh'] = 'ubuntu@151.80.232.163'

if 'mse' in SITES:
    SITES['mse']['urls'] = [
        'https://www.msei.in/downloads/circulars/default',
        'https://www.msei.in/downloads/circulars/circularswithadvancesearch',
    ]
    SITES['mse']['html_strategy'] = 'mse_circulars'
    SITES['mse']['required_url_terms'] = ['/sx-content/circulars/']
    SITES['mse']['minimum_expected_items'] = 5

if 'dfs' in SITES:
    SITES['dfs']['urls'] = ['https://financialservices.gov.in/beta/en/circular-page']
    SITES['dfs']['html_strategy'] = 'dfs_circulars'
    SITES['dfs']['allowed_domains'] = ['financialservices.gov.in']
    SITES['dfs']['required_url_terms'] = ['/sites/default/files/']
    SITES['dfs']['minimum_expected_items'] = 5
    SITES['dfs']['requires_browser'] = False

if 'fiu_ind' in SITES:
    SITES['fiu_ind']['urls'] = ['https://fiuindia.gov.in/files/Compliance_Orders/orders.html']
    SITES['fiu_ind']['html_strategy'] = 'fiu_compliance_orders'
    SITES['fiu_ind']['required_url_terms'] = ['/pdfs/judgements/']
    SITES['fiu_ind']['minimum_expected_items'] = 3

if 'fiu_ind_guidance' in SITES:
    SITES['fiu_ind_guidance']['urls'] = ['https://fiuindia.gov.in/files/downloads/downloads.html']
    SITES['fiu_ind_guidance']['html_strategy'] = 'fiu_guidance_downloads'
    SITES['fiu_ind_guidance']['allowed_domains'] = ['fiuindia.gov.in']
    SITES['fiu_ind_guidance']['required_url_terms'] = ['/pdfs/downloads/', '/pdfs/aml_legislation/']
    SITES['fiu_ind_guidance']['required_title_keywords'] = ['guideline', 'guidelines', 'circular', 'registration', 'non-compliant', 'non compliant', 'aml']
    SITES['fiu_ind_guidance']['skip_title_terms'] = ['annexure', 'user guide', 'format guide', 'validation utility', 'generation utility', 'sample data', 'sample format', 'gateway user guide', 'personal hearing policy']
    SITES['fiu_ind_guidance']['minimum_expected_items'] = 3

if 'uidai_authentication_docs' in SITES:
    SITES['uidai_authentication_docs']['urls'] = ['https://uidai.gov.in/en/ecosystem/authentication-devices-documents/authentication-document.html']
    SITES['uidai_authentication_docs']['html_strategy'] = 'uidai_authentication_docs'
    SITES['uidai_authentication_docs']['allowed_domains'] = ['uidai.gov.in']
    SITES['uidai_authentication_docs']['required_title_keywords'] = ['circular', 'checklist', 'guideline', 'guidelines', 'onboarding', 'supplementary agreement']
    SITES['uidai_authentication_docs']['skip_title_terms'] = ['list of auas', 'list of sub auas']
    SITES['uidai_authentication_docs']['minimum_expected_items'] = 3

if 'gic_re' in SITES:
    SITES['gic_re']['urls'] = ['https://www.gicre.in/en/people-resources/policies-and-guidelines']

if 'cdslindia' in SITES:
    SITES['cdslindia']['urls'] = ['https://www.cvlindia.com/Downloads/Downloads']

if 'stock_exchange_arbitration' in SITES:
    SITES['stock_exchange_arbitration']['urls'] = [
        'https://www.nseindia.com/static/invest/about-arbitration',
        'https://www.nseindia.com/complaints/arbitration-status',
    ]

if 'cdsl' in SITES:
    SITES['cdsl']['urls'] = ['https://www.cdslindia.com/eservices/Publications/Communique']
    SITES['cdsl']['api_strategy'] = 'cdsl_communiques'
    SITES['cdsl']['cdsl_load_url'] = 'https://www.cdslindia.com/eservices/Publications/GetOnLoadCommunique'
    SITES['cdsl']['browser_urls'] = ['https://www.cdslindia.com/eservices/Publications/Communique']
    SITES['cdsl']['browser_html_strategy'] = 'cdsl_communiques'
    SITES['cdsl']['browser_fallback'] = True
    SITES['cdsl']['browser_fallback_mode'] = 'if_empty_or_error'
    SITES['cdsl']['browser_profile'] = 'openclaw'
    SITES['cdsl']['browser_wait_selector'] = '#tblCommuniquDtlBody tr'
    SITES['cdsl']['browser_wait_seconds'] = 5
    SITES['cdsl']['allowed_domains'] = ['cdslindia.com']
    SITES['cdsl']['required_keywords'] = ['communique', 'dp']
    SITES['cdsl']['skip_keywords'] = ['booklet', 'telugu', 'hindi', 'marathi', 'punjabi', 'malayalam']
    SITES['cdsl']['skip_title_terms'] = ['conference call', 'earnings', 'transcript', 'ipo', 'general meeting']
    SITES['cdsl']['minimum_expected_items'] = 1

if 'cestat' in SITES:
    SITES['cestat']['urls'] = ['https://cestat.gov.in/noticestatus']
    SITES['cestat']['html_strategy'] = 'cestat_circulars'
    SITES['cestat']['allowed_domains'] = ['cestat.gov.in']
    SITES['cestat']['minimum_expected_items'] = 3

if 'fimmda' in SITES:
    SITES['fimmda']['urls'] = ['https://www.fimmda.org/Default.aspx']
    SITES['fimmda']['html_strategy'] = 'fimmda_notices'
    SITES['fimmda']['allowed_domains'] = ['fimmda.org']
    SITES['fimmda']['minimum_expected_items'] = 3

if 'cersai' in SITES:
    SITES['cersai']['urls'] = ['https://www.cersai.org.in/CERSAI/notifications.prg']
    SITES['cersai']['browser_url'] = 'https://www.cersai.org.in/CERSAI/notifications.prg'
    SITES['cersai']['browser_strategy'] = 'cersai_notifications'
    SITES['cersai']['browser_profile'] = 'openclaw'
    SITES['cersai']['browser_wait_text'] = 'Pinned Notifications'
    SITES['cersai']['allowed_domains'] = ['cersai.org.in']
    SITES['cersai']['minimum_expected_items'] = 5
    SITES['cersai']['requires_browser'] = True
    SITES['cersai']['special_source_only'] = True

if 'dipp' in SITES:
    SITES['dipp']['urls'] = ['https://www.dpiit.gov.in/']
    SITES['dipp']['api_strategy'] = 'dpiit_documents'
    SITES['dipp']['api_url'] = 'https://www.dpiit.gov.in/cms/wp-json/post-page/documents?limit=10&page=1'
    SITES['dipp']['browser_url'] = 'https://www.dpiit.gov.in/'
    SITES['dipp']['browser_profile'] = 'openclaw'
    SITES['dipp']['allowed_domains'] = ['dpiit.gov.in']
    SITES['dipp']['dpiit_allowed_categories'] = [
        'Gazette Notifications',
        'Orders and Notices',
        'Publications',
        'Guidelines',
        'Press Release',
        'Acts and Policies',
    ]
    SITES['dipp']['minimum_expected_items'] = 4

if 'niti' in SITES:
    SITES['niti']['urls'] = ['https://www.niti.gov.in/disclosures-rti/disclosures/circular-notifications']
    SITES['niti']['html_strategy'] = 'niti_notifications'
    SITES['niti']['allowed_domains'] = ['niti.gov.in']
    SITES['niti']['minimum_expected_items'] = 2

if 'nps_trust' in SITES:
    SITES['nps_trust']['urls'] = ['https://npstrust.org.in/circulars']
    SITES['nps_trust']['html_strategy'] = 'nps_trust_circulars'
    SITES['nps_trust']['allowed_domains'] = ['npstrust.org.in']
    SITES['nps_trust']['minimum_expected_items'] = 5
    SITES['nps_trust']['requires_browser'] = False

if 'fema' in SITES:
    SITES['fema']['urls'] = ['https://www.rbi.org.in/Scripts/NotificationUser.aspx']
    SITES['fema']['html_strategy'] = 'rbi_notifications'
    SITES['fema']['rbi_title_keywords'] = [
        'foreign exchange management act',
        'fema',
        'external commercial borrowing',
        'overseas investment',
        'current account transaction',
        'authorised dealer',
        'authorized dealer',
        'ap (dir series)',
        'import of goods',
        'export of goods',
    ]
    SITES['fema']['rbi_detail_keywords'] = [
        'foreign exchange management act',
        'fema',
        'foreign exchange',
        'ap (dir series)',
        'authorised dealer',
        'authorized dealer',
        'external commercial borrowing',
        'overseas investment',
    ]
    SITES['fema']['allowed_domains'] = ['rbi.org.in', 'rbidocs.rbi.org.in']
    SITES['fema']['minimum_expected_items'] = 3
    SITES['fema']['browser_fallback'] = False

if 'sidbi' in SITES:
    SITES['sidbi']['urls'] = ['https://www.sidbi.in/en/circulars']
    SITES['sidbi']['api_strategy'] = 'sidbi_circulars'
    SITES['sidbi']['api_url'] = 'https://www.sidbi.in/head/engine/json/JSONcirculars.php?show=frontend&language=english'
    SITES['sidbi']['sidbi_uploads_base'] = 'https://www.sidbi.in/uploads/'
    SITES['sidbi']['allowed_domains'] = ['sidbi.in']
    SITES['sidbi']['minimum_expected_items'] = 5
    SITES['sidbi']['browser_fallback'] = False

if 'sbi_funds' in SITES:
    SITES['sbi_funds']['urls'] = ['https://www.sbimf.com/notice-and-addendums']
    SITES['sbi_funds']['api_strategy'] = 'sbi_notice_addendums'
    SITES['sbi_funds']['api_url'] = 'https://www.sbimf.com/ajaxcall/CMS/GetNoticeandAddendumsData'
    SITES['sbi_funds']['sbi_notice_addendum_types'] = ['Scheme Information', 'General Information']
    SITES['sbi_funds']['sbi_notice_addendum_days_back'] = 550
    SITES['sbi_funds']['allowed_domains'] = ['sbimf.com']
    SITES['sbi_funds']['minimum_expected_items'] = 10
    SITES['sbi_funds']['browser_fallback'] = False

if 'pfrda_circulars' in SITES:
    SITES['pfrda_circulars']['urls'] = ['https://pfrda.org.in/regulatory-framework/circulars/active-circulars']

if 'pfrda_master_circulars' in SITES:
    SITES['pfrda_master_circulars']['urls'] = ['https://pfrda.org.in/regulatory-framework/master-circulars/active-master-circulars']

if 'cma_india' in SITES:
    SITES['cma_india']['urls'] = ['https://icmai.in/icmai/']
    SITES['cma_india']['html_strategy'] = 'icmai_notifications'
    SITES['cma_india']['allowed_domains'] = ['icmai.in']
    SITES['cma_india']['minimum_expected_items'] = 5

if 'iba' in SITES:
    SITES['iba']['urls'] = ['https://www.iba.org.in/iba/home/HomeAction.do?doNewslist=yes&sectionIdIndex=5&subSectionIdIndex=0&subSectionIdIndex1=0']
    SITES['iba']['html_strategy'] = 'iba_circulars'
    SITES['iba']['allowed_domains'] = ['iba.org.in']
    SITES['iba']['minimum_expected_items'] = 5

if 'ncdex' in SITES:
    SITES['ncdex']['urls'] = ['https://www.ncdex.com/circulars']
    SITES['ncdex']['browser_urls'] = ['https://www.ncdex.com/circulars']
    SITES['ncdex']['browser_html_strategy'] = 'ncdex_circulars'
    SITES['ncdex']['browser_fallback'] = True
    SITES['ncdex']['browser_fallback_mode'] = 'always'
    SITES['ncdex']['browser_profile'] = 'openclaw'
    SITES['ncdex']['browser_wait_seconds'] = 5
    SITES['ncdex']['allowed_domains'] = ['ncdex.com']
    SITES['ncdex']['minimum_expected_items'] = 5

if 'mcx_ccl' in SITES:
    SITES['mcx_ccl']['urls'] = ['https://www.mcxccl.com/circulars/all-circulars']
    SITES['mcx_ccl']['browser_urls'] = ['https://www.mcxccl.com/circulars/all-circulars']
    SITES['mcx_ccl']['browser_html_strategy'] = 'mcxccl_circulars'
    SITES['mcx_ccl']['browser_fallback'] = True
    SITES['mcx_ccl']['browser_fallback_mode'] = 'always'
    SITES['mcx_ccl']['browser_profile'] = 'openclaw'
    SITES['mcx_ccl']['browser_wait_seconds'] = 5
    SITES['mcx_ccl']['allowed_domains'] = ['mcxccl.com']
    SITES['mcx_ccl']['minimum_expected_items'] = 5

if 'nsdl' in SITES:
    SITES['nsdl']['urls'] = ['https://nsdl.co.in/business/issuers_rts.php']
    SITES['nsdl']['browser_urls'] = ['https://nsdl.co.in/business/issuers_rts.php']
    SITES['nsdl']['browser_html_strategy'] = 'nsdl_circulars'
    SITES['nsdl']['browser_fallback'] = True
    SITES['nsdl']['browser_fallback_mode'] = 'always'
    SITES['nsdl']['browser_profile'] = 'openclaw'
    SITES['nsdl']['browser_wait_seconds'] = 5
    SITES['nsdl']['allowed_domains'] = ['nsdl.co.in']
    SITES['nsdl']['required_title_terms'] = ['circular']
    SITES['nsdl']['skip_keywords'] = ['annexure', 'sebi circular dated']
    SITES['nsdl']['minimum_expected_items'] = 5
    SITES['nsdl']['file_probe_via_browser'] = True
    SITES['nsdl']['file_probe_warm_urls'] = ['https://nsdl.co.in/business/issuers_rts.php']
    SITES['nsdl']['file_probe_warm_seconds'] = 4

if 'nsdl_eservices' in SITES:
    SITES['nsdl_eservices']['urls'] = ['https://nsdl.co.in/business/circular_stat.php']
    SITES['nsdl_eservices']['browser_urls'] = ['https://nsdl.co.in/business/circular_stat.php']
    SITES['nsdl_eservices']['browser_html_strategy'] = 'nsdl_circulars'
    SITES['nsdl_eservices']['browser_fallback'] = True
    SITES['nsdl_eservices']['browser_fallback_mode'] = 'always'
    SITES['nsdl_eservices']['browser_profile'] = 'openclaw'
    SITES['nsdl_eservices']['browser_wait_seconds'] = 5
    SITES['nsdl_eservices']['allowed_domains'] = ['nsdl.co.in']
    SITES['nsdl_eservices']['required_title_terms'] = ['circular']
    SITES['nsdl_eservices']['skip_keywords'] = ['tender offer', 'annexure', 'circular nos']
    SITES['nsdl_eservices']['minimum_expected_items'] = 5
    SITES['nsdl_eservices']['file_probe_via_browser'] = True
    SITES['nsdl_eservices']['file_probe_warm_urls'] = ['https://nsdl.co.in/business/circular_stat.php']
    SITES['nsdl_eservices']['file_probe_warm_seconds'] = 4

for site_key, reason in {
    'ace': 'Agricultural commodities exchange site is outside the broker-alert product scope.',
    'anmi': 'Compliance calendar is not a latest circular stream.',
    'asba': 'Configured public URL resolves to an unrelated badminton association, not a financial circular source.',
    'bcsbi': 'Banking customer-service standards body is outside the broker-alert product scope.',
    'bse_indices': 'Public target exposes index data and historical pages, not a dated latest circular stream.',
    'cag': 'Public site is access denied and does not currently expose a usable circular stream.',
    'care': 'Site does not expose a reliable latest circular or regulatory notices feed.',
    'cibil': 'Public site exposes static policy pages rather than a latest circular stream.',
    'cdslindia': 'Official CVL downloads page is a forms/download library, not a dated latest circular stream.',
    'crisil': 'Public target resolves to press release and login content, not a circular feed.',
    'equifax': 'Public site exposes static policy collateral rather than latest circulars.',
    'experian': 'Public site exposes static policy collateral rather than latest circulars.',
    'exim_bank': 'Public targets resolve to press or disclosure pages, not a circular feed.',
    'gic_re': 'Live GIC Re site page exposes policies, disclosures, and newsletters rather than a latest circular stream.',
    'icici_pru': 'AMC notices/addendums are outside the broker-alert circular scope and the current notices target is effectively dead.',
    'icsi': 'Current public pages expose guidelines and announcements, not a reliable circular stream.',
    'icra': 'Public target resolves to corporate policy or ratings content, not circulars.',
    'lic': 'Public page exposes corporate press releases, not broker-relevant circular alerts.',
    'nafed': 'Current public site does not expose a broker-relevant regulatory circular stream.',
    'nmce': 'Configured target is a dead/domain-sale property, not a live circular source.',
    'nse_indices': 'Public target is a static disclosure/report page, not a latest circular stream.',
    'pdai': 'Primary dealers association feed is outside the current broker-alert scope.',
    'brokers_forum': 'Industry association site is not an official regulatory circular source.',
    'investor_grievance': 'Generic grievance site is not an official broker-regulatory alert source.',
    'nps_trust': 'Pension/NPS trust circulars are optional customer-specific coverage, not core broker-alert scope.',
    'pfrda_circulars': 'Pension circulars are optional customer-specific coverage, not core broker-alert scope.',
    'pfrda_master_circulars': 'Pension master circulars are optional customer-specific coverage, not core broker-alert scope.',
    'sebi_saa': 'Public SAT site is blocked and not a primary circular stream for this product.',
    'sebi_sme': 'This is a filings stream, not a regulatory circular stream.',
    'stock_exchange_arbitration': 'Official NSE arbitration pages are informational/static pages, not a dated latest circular stream.',
    'itat': 'Public tribunal site is blocked and does not behave like a circular feed.',
}.items():
    if site_key in SITES:
        SITES[site_key]['downgrade_reason'] = reason
        SITES[site_key]['browser_fallback'] = False

OPENCLAW_GENERIC_FALLBACK_SITES = sorted(
    site_key
    for site_key, site in SITES.items()
    if not site.get('rss_feeds')
    and not site.get('api_strategy')
    and not site.get('html_strategy')
    and not site.get('browser_strategy')
)

for site_key in OPENCLAW_GENERIC_FALLBACK_SITES:
    site = SITES[site_key]
    site.setdefault('browser_fallback', True)
    site.setdefault('browser_fallback_mode', 'if_empty')
    site.setdefault('browser_profile', 'openclaw')
    site.setdefault('browser_wait_seconds', 4)

# Override extract_items_generic to be less restrictive for better results
def extract_items_generic_enhanced(soup: BeautifulSoup, base_url: str, site_key: str, site: Dict) -> List[Dict[str, Any]]:
    """Enhanced generic extraction - less restrictive, better results"""
    items = []

    # Keywords that indicate circular/regulatory content
    circular_keywords = ['circular', 'notice', 'notification', 'order', 'press release',
                        'guidelines', 'regulation', 'compliance', 'advisory', 'amendment',
                        'clarification', 'directive', 'instruction', 'mandate']

    for link in soup.find_all('a', href=True):
        href = link.get('href')
        title = link.get_text(strip=True)

        if not title or not href:
            continue
        if href.startswith('#') or 'javascript:' in href or 'mailto:' in href:
            continue

        # Skip obvious navigation links
        nav_terms = ['home', 'about', 'contact', 'login', 'logout', 'search', 'sitemap',
                     'privacy', 'terms', 'help', 'faq', 'careers', 'media']
        if any(nav in title.lower() for nav in nav_terms):
            continue

        # For short titles, check if they match circular keywords
        if len(title) < 10:
            if not any(keyword in title.lower() for keyword in circular_keywords):
                continue

        # Prefer links with circular keywords
        has_keyword = any(keyword in title.lower() or keyword in href.lower()
                         for keyword in circular_keywords)

        full_url = href if href.startswith('http') else urljoin(base_url, href)

        # Try to find date in surrounding context
        date_str = find_date_near_link(link)
        if not date_str:
            # Check if date is in the title
            date_str = parse_date(title)
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')

        category = determine_category(title, full_url, site.get("update_types", []))

        # Assign priority based on keywords
        priority = 'high' if has_keyword else 'normal'

        items.append({
            'title': title,
            'link': full_url,
            'pub_date': date_str,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': title[:200],
            'category': category,
            'type': category,
            'site': site_key,
            'source': 'scraped',
            'priority': priority,
            'has_keyword': has_keyword
        })

    # Sort by priority (keyword matches first)
    items.sort(key=lambda x: (not x.get('has_keyword', False), x['title']))

    # Remove the has_keyword field before returning
    for item in items:
        item.pop('has_keyword', None)

    return items

# Replace the extract function
extract_items_generic = extract_items_generic_enhanced

# Update APP metadata
app.title = "GovUpdate API - Broker Enhanced"
app.version = "9.0"
app.description = "Comprehensive API for Indian Financial Regulatory Monitoring - 88 Sources for Stock Brokers"

# Override root endpoint
@app.get("/", tags=["General"])
async def root():
    """Root endpoint with API information"""
    sites_by_category = {}
    new_sources_count = 0

    for key, site in SITES.items():
        category = site.get("category", "other")
        if category not in sites_by_category:
            sites_by_category[category] = []

        site_info = {
            "key": key,
            "name": site["name"],
            "description": site.get("description", ""),
            "update_types": site.get("update_types", [])
        }

        if site.get("new_source"):
            site_info["new"] = True
            new_sources_count += 1

        sites_by_category[category].append(site_info)

    return {
        "name": "GovUpdate API - Broker Enhanced",
        "version": "9.0",
        "status": "running",
        "description": "Comprehensive API for monitoring Indian financial regulatory sources - Optimized for Stock Brokers",
        "features": [
            f"{len(SITES)} verified financial sources ({new_sources_count} newly added in v8-v9)",
            "Enhanced scraping specifically for broker circulars",
            "Clearing corporations (NSE, BSE, MCX clearing)",
            "Broker associations (ANMI, BSE Brokers Forum)",
            "Derivatives & F&O segments",
            "KYC & AML compliance (CKYCR, CERSAI)",
            "Investor protection (IEPF, SCORES)",
            "Market data & indices (NSE Indices, BSE Indices)",
            "SEBI specialized divisions (Enforcement, Intermediaries, MR)",
            "Arbitration & disputes (SAT, Exchange Arbitration)",
            "RIA, RA, and wealth advisory regulations",
            "FDI & FEMA updates",
            "Treasury & debt market circulars",
            "Enhanced security: SSL verification, API key hashing, restricted CORS",
            "Site-specific scraping selectors for accuracy",
            "Webhook delivery with retry logic",
            "Email subscription support",
            "Comprehensive error handling",
            "Full API key management"
        ],
        "new_sources": new_sources_count,
        "sites_by_category": sites_by_category,
        "total_sites": len(SITES),
        "endpoints": {
            "updates": "/api/updates",
            "single_update": "/api/updates/{id}",
            "manual": "/api/manual",
            "status": "/api/status",
            "api_keys": "/api/keys",
            "create_key": "POST /api/keys",
            "webhooks": "/api/webhooks",
            "create_webhook": "POST /api/webhooks",
            "email_subscriptions": "/api/email-subscriptions",
            "create_subscription": "POST /api/email-subscriptions",
            "scraping_logs": "/api/scraping-logs",
            "source_coverage": "/api/source-coverage",
            "docs": "/docs"
        },
        "rate_limits": {
            "default_per_minute": MAX_REQUESTS_PER_MINUTE,
            "default_per_hour": MAX_REQUESTS_PER_HOUR
        },
        "broker_specific_features": {
            "clearing_corporations": ["NSE Clearing", "ICCL (BSE Clearing)", "MCX-SX Clearing"],
            "broker_associations": ["ANMI", "BSE Brokers Forum", "ASBA"],
            "derivatives": ["NSE F&O", "BSE F&O"],
            "investor_protection": ["IEPF", "SCORES", "IGR Cell"],
            "compliance": ["BSE Listing", "NSE Listing"],
            "kyc_aml": ["CKYCR", "CERSAI"],
            "advisory": ["SEBI RIA", "SEBI RA"]
        }
    }

# Update startup message
async def run_startup() -> None:
    """Initialize on startup"""
    logger.info("Initializing GovUpdate API v9.0 - Broker Enhanced Edition")
    init_db()

    admin_key = create_admin_key()

    print("\n" + "=" * 80)
    print("GOVUPDATE API v9.0 - BROKER ENHANCED EDITION")
    print("=" * 80)
    if admin_key:
        print(f"[KEY] Admin Key (SAVE THIS): {admin_key}")
    else:
        print("[KEY] Admin key already exists (stored securely as hash)")

    print(f"\n[INFO] TOTAL SOURCES: {len(SITES)}")
    new_sources = [s['name'] for s in SITES.values() if s.get('new_source')]
    print(f"[INFO] NEW SOURCES IN v8-v9: {len(new_sources)}")

    print("\n[SECURITY] Enhanced Protection:")
    print("  [OK] SSL verification enabled by default")
    print("  [OK] API keys hashed with SHA-256")
    print("  [OK] CORS restricted (configure via ALLOWED_ORIGINS)")
    print("  [OK] Input validation and sanitization")
    print("  [OK] Rate limiter memory leak fixed")

    print("\n[BROKER] Broker-Specific Sources Added:")
    print("  [OK] 3 Clearing Corporations (NSE, BSE, MCX)")
    print("  [OK] 3 Broker Associations (ANMI, BSE Forum, ASBA)")
    print("  [OK] 2 Derivatives Segments (NSE F&O, BSE F&O)")
    print("  [OK] 3 Investor Protection (IEPF, SCORES, IGR)")
    print("  [OK] 2 Compliance (BSE/NSE Listing)")
    print("  [OK] 2 KYC/AML (CKYCR, CERSAI)")
    print("  [OK] 5 SEBI Divisions (Enforcement, Intermediaries, MR, CIR, SME)")
    print("  [OK] 2 Arbitration (SAT, Exchange Arbitration)")
    print("  [OK] 2 Advisory (RIA, RA)")
    print("  [OK] And 7 more broker-relevant sources!")

    print("\n" + "=" * 80)
    print("Starting initial fetch...")
    print("=" * 80 + "\n")

    await process_all_sites()

    scheduler.add_job(
        process_all_sites,
        CronTrigger.from_crontab(CRON_SCHEDULE),
        id='daily_scrape',
        name=f'Daily scrape of all {len(SITES)} verified sites',
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Scheduler started with cron: {CRON_SCHEDULE}")


async def run_shutdown() -> None:
    """Cleanup on shutdown."""
    logger.info("Shutting down broker-enhanced scheduler...")
    if scheduler.running:
        scheduler.shutdown()
    logger.info("Shutdown complete")


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    await run_startup()
    try:
        yield
    finally:
        await run_shutdown()


app.router.lifespan_context = app_lifespan


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting GovUpdate API v9.0 - Broker Enhanced on port {PORT}")
    logger.info(f"Monitoring {len(SITES)} financial sources (including 33 broker-specific sources)")
    logger.info(f"Rate limits: {MAX_REQUESTS_PER_MINUTE}/min, {MAX_REQUESTS_PER_HOUR}/hour")

    uvicorn.run(app, host="0.0.0.0", port=PORT)
