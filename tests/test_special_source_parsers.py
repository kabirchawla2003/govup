import asyncio
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "main-v8-improved.py"
sys.path.insert(0, str(ROOT / "src"))

spec = importlib.util.spec_from_file_location("main_v8_test_module", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules["main_v8_test_module"] = module
spec.loader.exec_module(module)

MODULE_V9_PATH = ROOT / "src" / "main-v9-broker-enhanced.py"
spec_v9 = importlib.util.spec_from_file_location("main_v9_test_module", MODULE_V9_PATH)
module_v9 = importlib.util.module_from_spec(spec_v9)
sys.modules["main_v9_test_module"] = module_v9
spec_v9.loader.exec_module(module_v9)


def test_sebi_is_forced_to_rss_only_with_openclaw_fallback():
    site = module_v9.SITES["sebi"]

    assert site["urls"] == ["https://www.sebi.gov.in/sebirss.xml"]
    assert site["rss_feeds"] == ["https://www.sebi.gov.in/sebirss.xml"]
    assert site["rss_only"] is True
    assert site["rss_browser_fallback"] is True
    assert site["rss_browser_page_url"] == "https://www.sebi.gov.in/rss.html"
    assert site["remote_rss_via_ssh"] == "ubuntu@151.80.232.163"
    assert site["browser_profile"] == "openclaw"


def test_broker_source_configs_enforce_strict_fallback_and_new_cbdt_path():
    assert module_v9.SITES["bse_fo"]["special_source_only"] is True
    assert module_v9.SITES["bse_fo"]["bse_previous_day_lookback"] == 7
    assert module_v9.SITES["cersai"]["special_source_only"] is True
    assert module_v9.SITES["cbdt"]["api_strategy"] == "cbdt_structured_contents"
    assert module_v9.SITES["cbdt"]["urls"] == ["https://www.incometaxindia.gov.in/circulars"]
    assert module_v9.SITES["nsdl"]["required_title_terms"] == ["circular"]
    assert module_v9.SITES["nsdl_eservices"]["required_title_terms"] == ["circular"]


def test_extract_items_from_mca_home_html_parses_cards_and_marquee():
    html = """
    <html>
      <body>
        <div class="marquee-container">
          <p>
            The system implementation of the establishment of new RDs and ROCs for companies and LLPs will be effective from 16th February 2026.
            <a href="/content/dam/mca/pdf/ROC-RD-Split-details-20260212.pdf">Please click here for more details.</a>
          </p>
        </div>
        <div class="titleSizeDate">
          <span class="doc-link">
            <a href="/content/dam/mca/pdf/document-82-new-20240219.pdf">
              <p class="titleSearchTabs">General Circular No.02/2024 - Deployment and usage of Change Request Form (CRF) on MCA-21</p>
            </a>
            <p class="doc-date">19-02-2024</p>
          </span>
        </div>
      </body>
    </html>
    """
    site = {"update_types": ["circular", "notification", "general-circular", "tribunal-order"]}

    items = module.extract_items_from_mca_home_html(
        html,
        "https://www.mca.gov.in/content/mca/global/en/home.html",
        "mca",
        site,
    )

    assert len(items) == 2
    assert any(item["title"].startswith("The system implementation of the establishment") for item in items)
    assert any(item["pub_date"] == "2026-02-12" for item in items)
    assert any(item["title"].startswith("General Circular No.02/2024") for item in items)
    assert all(item["link"].startswith("https://www.mca.gov.in/") for item in items)


def test_extract_items_from_rss_respects_required_and_skip_keywords():
    xml = """
    <rss version="2.0">
      <channel>
        <item>
          <title>Guidelines for Investment Advisers</title>
          <link>https://www.sebi.gov.in/legal/circulars/mar-2026/guidelines-for-investment-advisers_123.html</link>
          <description>Investment adviser framework update</description>
          <pubDate>Thursday, March 06, 2026</pubDate>
        </item>
        <item>
          <title>Complaint Registration</title>
          <link>https://scores.sebi.gov.in/en/investor-complaint</link>
          <description>File an investor complaint</description>
          <pubDate>Thursday, March 06, 2026</pubDate>
        </item>
      </channel>
    </rss>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(xml)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_rss(
                "sebi_ria",
                {
                    "rss_feeds": ["https://www.sebi.gov.in/sebirss.xml"],
                    "required_keywords": ["investment adviser"],
                    "skip_keywords": ["complaint registration"],
                    "update_types": ["circular"],
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "Guidelines for Investment Advisers"
    assert items[0]["pub_date"] == "2026-03-06"


def test_extract_items_from_rss_matches_broader_sebi_intermediary_terms():
    xml = """
    <rss version="2.0">
      <channel>
        <item>
          <title>Circular on Forms for registration of stock brokers and clearing members</title>
          <link>https://www.sebi.gov.in/legal/circulars/mar-2026/forms-for-registration-of-stock-brokers-and-clearing-members_123.html</link>
          <description>Updated forms for stock brokers and clearing members</description>
          <pubDate>11 Mar, 2026 +0530</pubDate>
        </item>
        <item>
          <title>Creation/Invocation of pledge of securities through depository system</title>
          <link>https://www.sebi.gov.in/legal/circulars/mar-2026/creation-invocation-of-pledge-of-securities-through-depository-system_124.html</link>
          <description>Depository system update</description>
          <pubDate>10 Mar, 2026 +0530</pubDate>
        </item>
      </channel>
    </rss>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(xml)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_rss(
                "sebi_intermediaries",
                {
                    "rss_feeds": ["https://www.sebi.gov.in/sebirss.xml"],
                    "required_keywords": ["stock brokers", "clearing members", "depository system"],
                    "skip_keywords": ["complaint registration"],
                    "update_types": ["circular"],
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 2
    assert items[0]["pub_date"] == "2026-03-11"
    assert items[1]["pub_date"] == "2026-03-10"


def test_parse_rss_pub_date_handles_plaintext_feed_dates():
    assert module.parse_rss_pub_date("Thursday, March 06, 2026") == "2026-03-06"
    assert module.parse_rss_pub_date("11 Mar, 2026 +0530") == "2026-03-11"


def test_normalize_item_date_handles_named_month_formats():
    assert module.normalize_item_date("March 6, 2026") == "2026-03-06"
    assert module.normalize_item_date("02-Mar-26") == "2026-03-02"
    assert module.normalize_item_date("09 March , 2026") == "2026-03-09"
    assert module.normalize_item_date("06 Mar, 2026") == "2026-03-06"
    assert module.normalize_item_date("December 30th 2025") == "2025-12-30"
    assert module.normalize_item_date("January 9th ,2020") == "2020-01-09"
    assert module.normalize_item_date("March28th, 2022") == "2022-03-28"
    assert module.normalize_item_date("24.10.2025") == "2025-10-24"
    assert module.normalize_item_date("sebi_circ_300903.pdf") == "2003-09-30"
    assert module.normalize_item_date("Notice - IDCW Record Date - RD March 05, 2026") == "2026-03-05"
    assert module.normalize_item_date("September, 2025") == "2025-09-01"


def test_extract_items_from_sebi_legal_listing_html_filters_broker_rows():
    html = """
    <html>
      <body>
        <table>
          <tbody>
            <tr>
              <td>Jan 22, 2026</td>
              <td><a href="/legal/regulations/jan-2026/lodr-amendment_99336.html">SEBI (LODR) (Amendment) Regulations, 2026</a></td>
            </tr>
            <tr>
              <td>Jan 08, 2026</td>
              <td><a href="/legal/regulations/jan-2026/stock-brokers-regulations-2026_98974.html">Securities and Exchange Board of India (Stock Brokers) Regulations, 2026</a></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_sebi_legal_listing_html(
        html,
        "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingLegal=yes&sid=1&smid=0&ssid=3",
        "sebi_broker_regulations",
        {
            "required_url_terms": ["/legal/regulations/"],
            "sebi_title_keywords": ["stock brokers"],
        },
    )

    assert len(items) == 1
    assert items[0]["title"] == "Securities and Exchange Board of India (Stock Brokers) Regulations, 2026"
    assert items[0]["pub_date"] == "2026-01-08"
    assert items[0]["type"] == "regulation"


def test_extract_items_from_sebi_news_listing_html_filters_topic_rows():
    html = """
    <html>
      <body>
        <table>
          <tr><th>Date</th><th>Type</th><th>Title</th></tr>
          <tr>
            <td>Feb 26, 2026</td>
            <td>Circulars</td>
            <td><a href="/legal/circulars/feb-2026/ease-of-doing-investment-disclosure-of-registered-name-and-registration-number-by-sebi-regulated-entities-and-their-agents-on-social-media-platforms-smp-_99863.html">Ease of Doing Investment (EoDI)- Disclosure of registered name and registration number by SEBI regulated entities and their agents on Social Media Platforms (SMPs)</a></td>
          </tr>
          <tr>
            <td>Feb 06, 2026</td>
            <td>Master Circulars</td>
            <td><a href="/legal/master-circulars/feb-2026/master-circular-for-investment-advisers_99395.html">Master Circular for Investment Advisers</a></td>
          </tr>
          <tr>
            <td>Aug 07, 2023</td>
            <td>Others</td>
            <td><a href="/other/faqs/investment-advisers-faq.html">Frequently Asked Questions (FAQs) on SEBI Registered Investment Advisers</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_sebi_news_listing_html(
        html,
        "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&search=Investment+Advisers",
        "sebi_ria",
        {
            "required_keywords": ["investment adviser", "investment advisers"],
            "skip_keywords": ["frequently asked questions"],
            "sebi_listing_types": ["Circulars", "Master Circulars"],
        },
    )

    assert len(items) == 1
    assert items[0]["title"] == "Master Circular for Investment Advisers"
    assert items[0]["pub_date"] == "2026-02-06"
    assert items[0]["type"] == "master-circular"


def test_extract_items_from_fiu_guidance_downloads_html_skips_hub_and_static_docs():
    html = """
    <html>
      <body>
        <div id="Others">
          <a href="https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6&smid=0">Master Circulars issued by SEBI</a>
          <a href="../../pdfs/downloads/NonCompliantNBFC28022026.pdf">List of non-compliant NBFCs which have not fulfilled their obligation under PML Act and rules relating to registration on FINnet2.0 portal of FIU-IND as on 28thFebruary 2026</a>
          <a href="../../pdfs/downloads/VDA08012026.pdf">AML &amp; CFT Guidelines for Reporting Entities Providing Services Related to Virtual Digital Assets - Updated as on 8thJanuary 2026</a>
          <a href="../../pdfs/downloads/Guidance_UserManual_Dealers.pdf">Annexure A</a>
          <a href="../../pdfs/downloads/ReportingEntityRegistration.pdf">Reporting Entity Registration</a>
        </div>
      </body>
    </html>
    """

    items = module.extract_items_from_fiu_guidance_downloads_html(
        html,
        "https://fiuindia.gov.in/files/downloads/downloads.html",
        "fiu_ind_guidance",
        {
            "required_url_terms": ["/pdfs/downloads/", "/pdfs/aml_legislation/"],
            "required_title_keywords": ["guideline", "guidelines", "circular", "registration", "non-compliant", "aml"],
            "skip_title_terms": ["annexure", "user guide", "format guide", "validation utility", "generation utility", "sample data", "sample format", "gateway user guide", "personal hearing policy"],
        },
    )

    assert len(items) == 2
    assert items[0]["pub_date"] == "2026-02-28"
    assert items[1]["pub_date"] == "2026-01-08"
    assert all("fiuindia.gov.in" in item["link"] for item in items)


def test_extract_items_from_dfs_circulars_html_parses_real_table_rows():
    html = """
    <html>
      <body>
        <table>
          <tbody>
            <tr>
              <td class="views-field views-field-counter">1</td>
              <td class="views-field views-field-field-location">F.No.8/1/2025-RRB</td>
              <td headers="view-field-attached-table-column" class="views-field views-field-field-location">
                <span class="file file--mime-application-pdf file--application-pdf">
                  <a href="/beta/sites/default/files/c-Transfer-Policy-for-RRBs-2025.pdf" type="application/pdf">Transfer Policy for RRBs 2025 (1.19 MB)</a>
                </span>
              </td>
              <td class="views-field views-field-field-start-date"><time datetime="2025-05-20T12:00:00Z">20/05/2025</time></td>
              <td class="views-field views-field-field-tags">RRB</td>
              <td class="views-field views-field-body"><p>Chairpersons, Regional Rural Banks</p></td>
            </tr>
            <tr>
              <td class="views-field views-field-counter">2</td>
              <td class="views-field views-field-field-location">CG-DL-E-07042025-262329</td>
              <td headers="view-field-attached-table-column" class="views-field views-field-field-location">
                <span class="file file--mime-application-pdf file--application-pdf">
                  <a href="/beta/sites/default/files/RRBs-Amalgamation-Notification.pdf" type="application/pdf">Amalgamation of RRBs - One State One RRB (1.13 MB)</a>
                </span>
              </td>
              <td class="views-field views-field-field-start-date"><time datetime="2025-04-05T12:00:00Z">05/04/2025</time></td>
              <td class="views-field views-field-field-tags">RRB</td>
              <td class="views-field views-field-body"></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_dfs_circulars_html(
        html,
        "https://financialservices.gov.in/beta/en/circular-page",
        "dfs",
        {},
    )

    assert len(items) == 2
    assert items[0]["title"].startswith("Transfer Policy for RRBs 2025")
    assert items[0]["pub_date"] == "2025-05-20"
    assert items[0]["reference_number"] == "F.No.8/1/2025-RRB"
    assert items[0]["candidate_file_url"].endswith("c-Transfer-Policy-for-RRBs-2025.pdf")
    assert "Chairpersons, Regional Rural Banks" in items[0]["content_snippet"]
    assert items[1]["pub_date"] == "2025-04-05"


def test_extract_items_from_uidai_authentication_docs_html_parses_list_group_items():
    html = """
    <html>
      <body>
        <ul class="list-group">
          <li class="list-group-item">
            <div class="row">
              <div class="field-list-title col-xs-10 col-md-10">
                <a href="https://uidai.gov.in/images/Circular_no_2_of_2026.pdf">1. Circular no 2 of 2026 regarding Aadhaar face authentication onboarding audit checklist version 2.0 for requesting entities</a>
                <span>3 Mar 2026</span>
              </div>
            </div>
          </li>
          <li class="list-group-item">
            <div class="row">
              <div class="field-list-title col-xs-10 col-md-10">
                <a href="https://uidai.gov.in/images/AUA_KUA_Pre-Onboarding.pdf">2. Pre-Onboarding AUA/ KUA Checklist</a>
                <span>21 Jan 2026</span>
              </div>
            </div>
          </li>
          <li class="list-group-item">
            <div class="row">
              <div class="field-list-title col-xs-10 col-md-10">
                <a href="https://uidai.gov.in/images/List_of_AUAs_KUAs_as_on_30102025.pdf">3. List of AUAs KUAs as on 30.10.2025</a>
                <span>11 Nov 2025</span>
              </div>
            </div>
          </li>
        </ul>
      </body>
    </html>
    """

    items = module.extract_items_from_uidai_authentication_docs_html(
        html,
        "https://uidai.gov.in/en/ecosystem/authentication-devices-documents/authentication-document.html",
        "uidai_authentication_docs",
        {
            "required_title_keywords": ["circular", "checklist", "guideline", "guidelines", "onboarding", "supplementary agreement"],
            "skip_title_terms": ["list of auas", "list of sub auas"],
        },
    )

    assert len(items) == 2
    assert items[0]["pub_date"] == "2026-03-03"
    assert items[1]["type"] == "checklist"
    assert all(item["link"].startswith("https://uidai.gov.in/images/") for item in items)


def test_should_try_openclaw_browser_fallback_respects_mode():
    assert module.should_try_openclaw_browser_fallback(
        {"browser_fallback": True, "browser_fallback_mode": "if_empty"},
        [],
        {"errors": []},
    )
    assert not module.should_try_openclaw_browser_fallback(
        {"browser_fallback": True, "browser_fallback_mode": "if_empty"},
        [{"title": "Existing item"}],
        {"errors": []},
    )
    assert module.should_try_openclaw_browser_fallback(
        {"browser_fallback": True, "browser_fallback_mode": "if_empty_or_error"},
        [{"title": "Existing item"}],
        {"errors": ["Error fetching page: 404 Not Found"]},
    )


def test_classify_scrape_result_distinguishes_network_blocked_and_browser_failures():
    assert module.classify_scrape_result([], {"errors": ["Error fetching https://example.com: [Errno 11001] getaddrinfo failed"]})["result_status"] == "network_failed"
    assert module.classify_scrape_result([], {"errors": ["Client error '403 Forbidden' for url 'https://example.com/'"]})["result_status"] == "blocked"
    assert module.classify_scrape_result([], {"errors": ["OpenClaw browser fallback failed: Server error '500 Internal Server Error' for url 'http://127.0.0.1:18791/tabs/open?profile=openclaw'"]})["result_status"] == "browser_failed"
    assert module.classify_scrape_result([], {"errors": ["OpenClaw browser fallback returned no items"]})["result_status"] == "empty"
    assert module.classify_scrape_result([{"title": "x"}], {"errors": []})["result_status"] == "working"


def test_apply_source_downgrade_clears_items_and_records_reason():
    stats = {"errors": []}
    items = [{"title": "Static policy"}]

    downgraded = module.apply_source_downgrade(
        {"downgrade_reason": "Static policy page is not a circular stream."},
        items,
        stats,
    )

    assert downgraded == []
    assert stats["errors"] == ["Source downgraded: Static policy page is not a circular stream."]


def test_fetch_openclaw_rendered_html_retries_and_reuses_shared_tab():
    calls = []
    state = {"opened": 0}
    original = module.openclaw_browser_request
    original_wait = module.wait_for_openclaw_page
    original_tabs = dict(module.OPENCLAW_SHARED_TABS)
    module.OPENCLAW_SHARED_TABS.clear()

    def fake_request(method, path, profile, json_body=None, timeout=120.0):
        calls.append((method, path, json_body))
        if path == "/start":
            return {}
        if path == "/tabs/open":
            state["opened"] += 1
            if state["opened"] == 1:
                raise RuntimeError("Server error '500 Internal Server Error' for url 'http://127.0.0.1:18791/tabs/open?profile=openclaw'")
            return {"targetId": "tab-1"}
        if path == "/tabs/focus":
            return {}
        if path == "/act":
            fn = (json_body or {}).get("fn", "")
            if "outerHTML" in fn:
                return {"result": "<html><body>ok</body></html>"}
            return {"result": "https://example.com/two"}
        if path.startswith("/tabs/"):
            return {}
        raise AssertionError(path)

    module.openclaw_browser_request = fake_request
    module.wait_for_openclaw_page = lambda site, profile: {"readyState": "complete"}
    try:
        first = module.fetch_openclaw_rendered_html("https://example.com/one", {"browser_wait_seconds": 0})
        second = module.fetch_openclaw_rendered_html("https://example.com/two", {"browser_wait_seconds": 0})
    finally:
        module.openclaw_browser_request = original
        module.wait_for_openclaw_page = original_wait
        module.OPENCLAW_SHARED_TABS.clear()
        module.OPENCLAW_SHARED_TABS.update(original_tabs)

    assert first == "<html><body>ok</body></html>"
    assert second == "<html><body>ok</body></html>"
    assert state["opened"] == 2
    assert sum(1 for _, path, _ in calls if path == "/tabs/open") == 2
    assert sum(1 for _, path, _ in calls if path == "/tabs/focus") >= 2
    assert sum(1 for _, path, body in calls if path == "/act" and "window.location.href" in ((body or {}).get("fn") or "")) >= 1


def test_get_or_create_openclaw_tab_focuses_newly_opened_tab():
    original = module.openclaw_browser_request
    original_tabs = dict(module.OPENCLAW_SHARED_TABS)
    module.OPENCLAW_SHARED_TABS.clear()
    calls = []

    def fake_request(method, path, profile, json_body=None, timeout=120.0):
        calls.append((method, path, json_body))
        if path == "/tabs/open":
            return {"targetId": "fresh-tab"}
        if path == "/tabs/focus":
            return {"ok": True}
        raise AssertionError(path)

    module.openclaw_browser_request = fake_request
    try:
        target_id, created = module.get_or_create_openclaw_tab("openclaw", "https://www.sebi.gov.in/sebirss.xml", 30)
    finally:
        module.openclaw_browser_request = original
        module.OPENCLAW_SHARED_TABS.clear()
        module.OPENCLAW_SHARED_TABS.update(original_tabs)

    assert created is True
    assert target_id == "fresh-tab"
    assert calls == [
        ("POST", "/tabs/open", {"url": "https://www.sebi.gov.in/sebirss.xml"}),
        ("POST", "/tabs/focus", {"targetId": "fresh-tab"}),
    ]


def test_fetch_openclaw_xml_text_reads_chromium_xml_viewer_payload():
    html = """
    <html>
      <body>
        <div id="webkit-xml-viewer-source-xml">
          <rss version="2.0"><channel><title>SEBI RSS Feed</title></channel></rss>
        </div>
      </body>
    </html>
    """
    original = module.fetch_openclaw_rendered_html
    module.fetch_openclaw_rendered_html = lambda browser_url, site=None: html
    try:
        xml_text = module.fetch_openclaw_xml_text("https://www.sebi.gov.in/sebirss.xml", {})
    finally:
        module.fetch_openclaw_rendered_html = original

    assert "<rss" in xml_text
    assert "SEBI RSS Feed" in xml_text


def test_fetch_openclaw_xml_text_raises_clear_error_for_browser_network_failure():
    html = """
    <html>
      <body>
        This site can't be reached
        The connection was reset.
        ERR_CONNECTION_RESET
      </body>
    </html>
    """
    original = module.fetch_openclaw_rendered_html
    module.fetch_openclaw_rendered_html = lambda browser_url, site=None: html
    try:
        try:
            module.fetch_openclaw_xml_text("https://www.sebi.gov.in/sebirss.xml", {})
            assert False, "Expected OpenClaw network failure"
        except RuntimeError as exc:
            assert "OpenClaw could not load https://www.sebi.gov.in/sebirss.xml" in str(exc)
            assert "ERR_CONNECTION_RESET" in str(exc)
    finally:
        module.fetch_openclaw_rendered_html = original


def test_fetch_openclaw_xml_text_uses_page_fetch_fallback_when_direct_navigation_fails():
    original_rendered = module.fetch_openclaw_rendered_html
    original_page_fetch = module.fetch_openclaw_xml_text_via_page_fetch
    module.fetch_openclaw_rendered_html = lambda browser_url, site=None: (_ for _ in ()).throw(RuntimeError("direct failed"))
    module.fetch_openclaw_xml_text_via_page_fetch = lambda browser_url, page_url, site=None: "<rss><channel><title>SEBI RSS Feed</title></channel></rss>"
    try:
        xml_text = module.fetch_openclaw_xml_text(
            "https://www.sebi.gov.in/sebirss.xml",
            {"rss_browser_page_url": "https://www.sebi.gov.in/rss.html"},
        )
    finally:
        module.fetch_openclaw_rendered_html = original_rendered
        module.fetch_openclaw_xml_text_via_page_fetch = original_page_fetch

    assert "SEBI RSS Feed" in xml_text


def test_extract_items_from_rss_raises_browser_fallback_error_when_no_feed_items_return():
    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry
        original_xml = module.fetch_openclaw_xml_text

        async def fake_fetch(url, client, retries):
            return None

        def fake_xml(url, site=None):
            raise RuntimeError("OpenClaw page fetch failed for https://www.sebi.gov.in/sebirss.xml: TypeError: Failed to fetch")

        module.fetch_with_retry = fake_fetch
        module.fetch_openclaw_xml_text = fake_xml
        try:
            await module.extract_items_from_rss(
                "sebi",
                {
                    "rss_feeds": ["https://www.sebi.gov.in/sebirss.xml"],
                    "rss_browser_fallback": True,
                    "rss_browser_page_url": "https://www.sebi.gov.in/rss.html",
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original
            module.fetch_openclaw_xml_text = original_xml

    import asyncio

    try:
        asyncio.run(run())
        assert False, "Expected browser fallback failure to propagate"
    except RuntimeError as exc:
        assert "Failed to fetch" in str(exc)


def test_extract_items_from_rss_uses_browser_fallback_after_direct_fetch_exception():
    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry
        original_xml = module.fetch_openclaw_xml_text

        async def fake_fetch(url, client, retries):
            raise RuntimeError("direct reset")

        def fake_xml(url, site=None):
            return """
            <rss version="2.0">
              <channel>
                <item>
                  <title>SEBI Circular Test</title>
                  <link>https://www.sebi.gov.in/legal/circulars/mar-2026/test_123.html</link>
                  <pubDate>Thursday, March 06, 2026</pubDate>
                </item>
              </channel>
            </rss>
            """

        module.fetch_with_retry = fake_fetch
        module.fetch_openclaw_xml_text = fake_xml
        try:
            return await module.extract_items_from_rss(
                "sebi",
                {
                    "rss_feeds": ["https://www.sebi.gov.in/sebirss.xml"],
                    "rss_browser_fallback": True,
                    "rss_browser_page_url": "https://www.sebi.gov.in/rss.html",
                    "update_types": ["circular"],
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original
            module.fetch_openclaw_xml_text = original_xml

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "SEBI Circular Test"
    assert items[0]["pub_date"] == "2026-03-06"


def test_extract_items_from_rss_uses_remote_ssh_fallback_after_direct_and_browser_failures():
    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry
        original_xml = module.fetch_openclaw_xml_text
        original_remote = module.fetch_remote_rss_text_via_ssh

        async def fake_fetch(url, client, retries):
            raise RuntimeError("direct reset")

        def fake_xml(url, site=None):
            raise RuntimeError("browser failed")

        def fake_remote(url, site=None):
            return """
            <rss version="2.0">
              <channel>
                <item>
                  <title>SEBI Remote Circular Test</title>
                  <link>https://www.sebi.gov.in/legal/circulars/mar-2026/remote-test_123.html</link>
                  <pubDate>Thursday, March 07, 2026</pubDate>
                </item>
              </channel>
            </rss>
            """

        module.fetch_with_retry = fake_fetch
        module.fetch_openclaw_xml_text = fake_xml
        module.fetch_remote_rss_text_via_ssh = fake_remote
        try:
            return await module.extract_items_from_rss(
                "sebi",
                {
                    "rss_feeds": ["https://www.sebi.gov.in/sebirss.xml"],
                    "rss_browser_fallback": True,
                    "rss_browser_page_url": "https://www.sebi.gov.in/rss.html",
                    "remote_rss_via_ssh": "ubuntu@151.80.232.163",
                    "update_types": ["circular"],
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original
            module.fetch_openclaw_xml_text = original_xml
            module.fetch_remote_rss_text_via_ssh = original_remote

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "SEBI Remote Circular Test"
    assert items[0]["pub_date"] == "2026-03-07"


def test_scrape_site_retries_rss_only_source_after_empty_result():
    import asyncio

    original_extract = module.extract_items_from_rss
    original_get_db_async = module.get_db_async

    class DummyAsyncConn:
        def execute(self, *args, **kwargs):
            return None

        def commit(self):
            return None

    class DummyAsyncConnCtx:
        async def __aenter__(self):
            return DummyAsyncConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    calls = {"count": 0}

    async def fake_extract(site_key, site, client):
        calls["count"] += 1
        if calls["count"] == 1:
            return []
        return [
            {
                "title": "Order in the matter of CapitalVia Global Research Limited",
                "link": "https://www.sebi.gov.in/enforcement/orders/mar-2026/order-in-the-matter-of-capitalvia-global-research-limited_100464.html",
                "url": "https://www.sebi.gov.in/enforcement/orders/mar-2026/order-in-the-matter-of-capitalvia-global-research-limited_100464.html",
                "pub_date": "2026-03-18",
                "isoDate": "2026-03-19T19:05:19+00:00",
                "content_snippet": "Order in the matter of CapitalVia Global Research Limited",
                "category": "order",
                "type": "order",
                "site": site_key,
                "source": "scraped",
            }
        ]

    module.extract_items_from_rss = fake_extract
    module.get_db_async = lambda: DummyAsyncConnCtx()

    async def run():
        return await module.scrape_site(
            "sebi_enforcement",
            {
                "name": "SEBI Enforcement",
                "urls": ["https://www.sebi.gov.in/sebirss.xml"],
                "rss_feeds": ["https://www.sebi.gov.in/sebirss.xml"],
                "rss_only": True,
                "retry_on_empty": 1,
                "retry_on_empty_delay_seconds": 0,
                "minimum_expected_items": 1,
                "required_keywords": ["order"],
                "allowed_domains": ["sebi.gov.in"],
                "update_types": ["order"],
            },
        )

    try:
        items, stats = asyncio.run(run())
    finally:
        module.extract_items_from_rss = original_extract
        module.get_db_async = original_get_db_async

    assert calls["count"] == 2
    assert len(items) == 1
    assert items[0]["title"] == "Order in the matter of CapitalVia Global Research Limited"
    assert stats["result_status"] == "working"
    assert "Used RSS feed" in stats["errors"]


def test_extract_items_via_openclaw_browser_uses_rendered_html_and_dedupes():
    html = """
    <html>
      <body>
        <a href="/docs/circular-20260311.pdf">Circular dated 11 March 2026</a>
        <a href="/docs/circular-20260311.pdf">Circular dated 11 March 2026</a>
      </body>
    </html>
    """
    original = module.fetch_openclaw_rendered_html
    module.fetch_openclaw_rendered_html = lambda browser_url, site: html
    try:
        items = module.extract_items_via_openclaw_browser(
            "demo_site",
            {
                "urls": ["https://example.com/updates"],
                "required_keywords": ["circular"],
            },
        )
    finally:
        module.fetch_openclaw_rendered_html = original

    assert len(items) == 1
    assert items[0]["link"] == "https://example.com/docs/circular-20260311.pdf"
    assert items[0]["pub_date"] == "2026-03-11"


def test_extract_items_from_cersai_notifications_html_parses_pinned_and_regular_rows():
    html = """
    <html>
      <body>
        <div>
          <h2>Pinned Notifications</h2>
          <p>10-03-2026 - Corrigendum-1-Proposal(RFP)on Government e-Marketplace(GeM)for procurement</p>
          <p>09-03-2026 - Survey questionnaire to banks on co-lending cases</p>
          <h2>Regular Notifications</h2>
          <p>06-03-2026 - Updated Batch master is now available under download section.</p>
        </div>
      </body>
    </html>
    """

    items = module.extract_items_from_cersai_notifications_html(
        html,
        "https://www.cersai.org.in/CERSAI/notifications.prg",
        "cersai",
        {},
    )

    assert len(items) == 3


def test_extract_items_from_cdsl_communiques_html_parses_rendered_table_rows():
    html = """
    <html>
      <body>
        <table id="tblCommuniqueDtl">
          <tbody id="tblCommuniquDtlBody">
            <tr>
              <td>DP2026-166</td>
              <td><a href="../Publications/DownloadFile?eventID=DP2026-166&amp;method=communique">DETAILS OF SECURITIES ADMITTED WITH CDSL</a></td>
              <td>11-Mar-2026</td>
            </tr>
            <tr>
              <td>DP2026-169</td>
              <td><a href="../Publications/DownloadFile?eventID=DP2026-169&amp;method=communique">STAMP DUTY PAYMENT AND TRANSACTION PROCESSING</a></td>
              <td>11-Mar-2026</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_cdsl_communiques_html(
        html,
        "https://www.cdslindia.com/eservices/Publications/Communique",
        "cdsl",
        {},
    )

    assert len(items) == 2
    assert items[0]["title"].startswith("DP2026-166 - DETAILS OF SECURITIES ADMITTED WITH CDSL")
    assert items[0]["pub_date"] == "2026-03-11"
    assert items[0]["candidate_file_url"].endswith("eventID=DP2026-166&method=communique")


def test_extract_items_from_cdsl_communiques_html_does_not_default_blank_dates_to_today():
    html = """
    <html>
      <body>
        <table id="tblCommuniqueDtl">
          <tbody id="tblCommuniquDtlBody">
            <tr>
              <td>DP2012-004</td>
              <td><a href="../Publications/DownloadFile?eventID=DP2012-004&amp;method=communique">SEBI Circular dated January 4, 2012 on operational changes</a></td>
              <td></td>
            </tr>
            <tr>
              <td>DPXXXX-000</td>
              <td><a href="../Publications/DownloadFile?eventID=DPXXXX-000&amp;method=communique">Undated communique with no parseable date</a></td>
              <td></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_cdsl_communiques_html(
        html,
        "https://www.cdslindia.com/eservices/Publications/Communique",
        "cdsl",
        {},
    )

    assert len(items) == 1
    assert items[0]["title"].startswith("DP2012-004 - SEBI Circular dated January 4, 2012")
    assert items[0]["pub_date"] == "2012-01-04"


def test_extract_items_from_cdsl_communiques_api_uses_json_dates_and_attachment_urls():
    class FakeResponse:
        def __init__(self, *, text="", json_data=None):
            self.text = text
            self._json_data = json_data

        def raise_for_status(self):
            return None

        def json(self):
            return self._json_data

    class FakeClient:
        async def get(self, url, headers=None):
            return FakeResponse(text="<html></html>")

        async def post(self, url, data=None, headers=None):
            return FakeResponse(
                json_data=[
                    {
                        "comM_ID": "DP2026-195",
                        "subject": "WITHDRAWAL OF SECURITIES FROM CDSL",
                        "description": "WITHDRAWAL OF SECURITIES FROM CDSL",
                        "comM_DATE": "20-Mar-2026",
                        "attachmenT_URL": "\\communiques\\dp\\DP-195-Withdrawal-of-securities-from-CDSL-19-03-2026.pdf",
                    },
                    {
                        "comM_ID": "DP2012-004",
                        "subject": "SEBI Circular dated January 4, 2012 on operational changes",
                        "description": "SEBI Circular dated January 4, 2012 on operational changes",
                        "comM_DATE": "",
                        "attachmenT_URL": "",
                    },
                ]
            )

    items = asyncio.run(
        module.extract_items_from_cdsl_communiques_api(
            "cdsl",
            {
                "urls": ["https://www.cdslindia.com/eservices/Publications/Communique"],
                "cdsl_load_url": "https://www.cdslindia.com/eservices/Publications/GetOnLoadCommunique",
            },
            FakeClient(),
        )
    )

    assert len(items) == 2
    assert items[0]["title"].startswith("DP2026-195 - WITHDRAWAL OF SECURITIES FROM CDSL")
    assert items[0]["pub_date"] == "2026-03-20"
    assert items[0]["link"] == "https://www.cdslindia.com/eservices/Publications/DownloadFile?eventID=DP2026-195&method=communique"
    assert items[1]["pub_date"] == "2012-01-04"
    assert items[1]["candidate_file_url"].endswith("eventID=DP2012-004&method=communique")


def test_extract_items_from_cestat_circulars_html_parses_circular_table_only():
    html = """
    <html>
      <body>
        <table id="notice">
          <tbody>
            <tr>
              <td>1</td>
              <td>Old Notice</td>
              <td>2025-11-12</td>
              <td><a href="https://cestat.gov.in/openfile/2/9355">View</a></td>
            </tr>
          </tbody>
        </table>
        <table id="circular">
          <tbody>
            <tr>
              <td>1</td>
              <td>Order No 20 of 2026 Revised</td>
              <td>2026-03-09</td>
              <td><a href="https://cestat.gov.in/openfile/2/9614">View</a></td>
            </tr>
            <tr>
              <td>2</td>
              <td>Order No 25 of 2026</td>
              <td>2026-03-05</td>
              <td><a href="https://cestat.gov.in/openfile/2/9607">View</a></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_cestat_circulars_html(
        html,
        "https://cestat.gov.in/noticestatus",
        "cestat",
        {},
    )

    assert len(items) == 2
    assert items[0]["title"] == "Order No 20 of 2026 Revised"
    assert items[0]["candidate_file_url"] == "https://cestat.gov.in/openfile/2/9614"
    assert all(item["title"] != "Old Notice" for item in items)


def test_extract_items_from_mse_circulars_html_keeps_table_rows_and_skips_navigation():
    html = """
    <html>
      <body>
        <a href="https://www.msei.in/downloads/Circulars/default.aspx">Back to Circulars</a>
        <table class="table table-striped t-listview">
          <tbody class="hed-bg">
            <tr>
              <th>Date</th><th>Circular No</th><th>Segments</th><th>Department</th><th>Title</th>
            </tr>
            <tr class="alt">
              <td class="txtcntr">12-Mar-2026</td>
              <td class="txtlft">18729</td>
              <td class="txtlft">Capital Market</td>
              <td class="txtlft">Surveillance</td>
              <td class="txtlft"><a href="https://www.msei.in/SX-Content/Circulars/2026/March/Circular-18729.pdf">List of security under Stage II of Graded Surveillance Measure (GSM)</a></td>
            </tr>
            <tr class="alt1">
              <td class="txtcntr">11-Mar-2026</td>
              <td class="txtlft">18721</td>
              <td class="txtlft">Capital Market</td>
              <td class="txtlft">Listing</td>
              <td class="txtlft"><a href="https://www.msei.in/SX-Content/Circulars/2026/March/Circular-18721.pdf">Listing of additional securities of Candour Techtex Limited issued on Preferential Basis</a></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_mse_circulars_html(
        html,
        "https://www.msei.in/downloads/circulars/default",
        "mse",
        {},
    )

    assert len(items) == 2
    assert items[0]["title"] == "List of security under Stage II of Graded Surveillance Measure (GSM)"
    assert items[0]["pub_date"] == "2026-03-12"
    assert items[0]["candidate_file_url"] == "https://www.msei.in/SX-Content/Circulars/2026/March/Circular-18729.pdf"
    assert "Circular No. 18729" in items[0]["content_snippet"]


def test_extract_items_from_fiu_compliance_orders_html_parses_orders_section_only():
    html = """
    <html>
      <body>
        <div id="orders">
          <div class="accordion-item">
            <h4 class="accordion-header">2025</h4>
            <div class="accordion-body">
              <table class="table table-bordered">
                <tr>
                  <th>S.No.</th><th>Date</th><th>Description</th><th>Document Size</th><th>Document</th>
                </tr>
                <tr>
                  <td>1</td>
                  <td>December 30th 2025</td>
                  <td>The Gandhinagar Nagarik Cooperative Bank Limited Order in original No. 03/DIR/FIU-IND/2025 u/s Section 13</td>
                  <td>143KB</td>
                  <td><a href="../../pdfs/judgements/TGNCBL_Order_3_2025.pdf"><img alt="pdf"/></a></td>
                </tr>
                <tr>
                  <td>2</td>
                  <td>December 22nd 2025</td>
                  <td>The Rajgurunagar Sahakari Bank Limited Order in original No. 02/DIR/FIU-IND/2025 u/s Section 13</td>
                  <td>143KB</td>
                  <td><a href="../../pdfs/judgements/TRSBL_Order_2_2025.pdf"><img alt="pdf"/></a></td>
                </tr>
              </table>
            </div>
          </div>
        </div>
        <div id="judgement">
          <table class="table table-bordered">
            <tr>
              <td>1</td>
              <td>July 9th 2015</td>
              <td>Muthoot Finance Limited Dated: 9th July 2015</td>
              <td>90KB</td>
              <td><a href="../../pdfs/judgements/MFL_J_2015.pdf"><img alt="pdf"/></a></td>
            </tr>
          </table>
        </div>
      </body>
    </html>
    """

    items = module.extract_items_from_fiu_compliance_orders_html(
        html,
        "https://fiuindia.gov.in/files/Compliance_Orders/orders.html",
        "fiu_ind",
        {},
    )

    assert len(items) == 2
    assert items[0]["title"].startswith("The Gandhinagar Nagarik Cooperative Bank Limited")
    assert items[0]["pub_date"] == "2025-12-30"
    assert items[0]["candidate_file_url"] == "https://fiuindia.gov.in/pdfs/judgements/TGNCBL_Order_3_2025.pdf"
    assert all("Muthoot Finance Limited" not in item["title"] for item in items)


def test_extract_items_from_crif_rbi_notifications_html_parses_dated_cards():
    html = """
    <html>
      <body>
        <ul class="list-unstyled listing-type-one">
          <li>
            <div class="article-type-one">
              <span class="date">04th Dec 2025</span>
              <a href="/news-events/rbi-notifications/2025/dec-2025/reserve-bank-of-india-credit-information-companies-amendment-directions-2025">
                <p class="highlight-text">Reserve Bank of India (Credit Information Companies) Amendment Directions-2025</p>
              </a>
              <p>The Reserve Bank had issued Reserve Bank of India (Credit Information Companies) Directions, 2025...</p>
            </div>
          </li>
          <li>
            <div class="article-type-one">
              <span class="date">28th Nov 2025</span>
              <a href="/news-events/rbi-notifications/2025/nov-2025/reserve-bank-of-india-credit-information-companies-directions-2025">
                <p class="highlight-text">Reserve Bank of India (Credit Information Companies) Directions 2025</p>
              </a>
              <p>RBI/DOR/2025-26/378</p>
            </div>
          </li>
        </ul>
      </body>
    </html>
    """

    items = module.extract_items_from_crif_rbi_notifications_html(
        html,
        "https://www.crifhighmark.com/news-events/rbi-notifications",
        "crif_highmark",
        {},
    )

    assert len(items) == 2
    assert items[0]["title"] == "Reserve Bank of India (Credit Information Companies) Amendment Directions-2025"
    assert items[0]["pub_date"] == "2025-12-04"
    assert items[0]["link"].endswith("/reserve-bank-of-india-credit-information-companies-amendment-directions-2025")


def test_extract_items_from_fimmda_notices_html_keeps_circular_stream_and_order():
    html = """
    <html>
      <body>
        <marquee>
          <span><a href="UploadPopupPageFiles/FIMCIR_2025_26_42.pdf">FIMCIR2025-26 42 Liquid Securities for the month of March</a></span>
          <span><a href="UploadPopupPageFiles/Draft_Valuation_of_Investment_20Feb2026.docx">Draft Valuation of Investment 2026</a></span>
          <span><a href="UploadPopupPageFiles/FIMNOT_2025_26_08.pdf">FIMNOT/2025-26/08-Corporate Bonds: Daily publication of Spread and Yield Matrices</a></span>
          <span><a href="UploadPopupPageFiles/FIMCIR_2025_26_40.pdf">FIMCIR/2025-26/40- Eligible liquid securities for the month of January 2026</a></span>
        </marquee>
      </body>
    </html>
    """

    items = module.extract_items_from_fimmda_notices_html(
        html,
        "https://www.fimmda.org/Default.aspx",
        "fimmda",
        {},
    )

    assert len(items) == 3
    assert items[0]["title"].startswith("FIMCIR2025-26 42")
    assert items[0]["pub_date"] == "2026-03-01"
    assert all("Draft Valuation" not in item["title"] for item in items)


def test_extract_items_from_lic_press_releases_html_parses_dated_table_rows():
    html = """
    <html>
      <body>
        <table class="custom-table table-hover">
          <tbody>
            <tr>
              <th>Sr</th>
              <th>Date</th>
              <th>Details of Press Release - 2025_2026</th>
              <th>English</th>
              <th>Hindi</th>
            </tr>
            <tr>
              <td>1.</td>
              <td>05.02.2026</td>
              <td>PERFORMANCE UPDATE for Nine months Ended December 31st 2025 (9M-FY26)</td>
              <td><a href="/documents/d/guest/final-press-release-dated-05-02-2026-2-">PDF</a></td>
              <td><a href="/documents/d/guest/final-press-release-hindi">PDF</a></td>
            </tr>
            <tr>
              <td>2.</td>
              <td>29.01.2026</td>
              <td>LIC Hosts All India Public Sector Table Tennis Tournament 2025-26</td>
              <td><a href="/documents/d/guest/lic-table-tennis-tournament">PDF</a></td>
              <td></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_lic_press_releases_html(
        html,
        "https://www.licindia.in/web/guest/press-release",
        "lic",
        {},
    )

    assert len(items) == 2
    assert items[0]["title"] == "PERFORMANCE UPDATE for Nine months Ended December 31st 2025 (9M-FY26)"
    assert items[0]["pub_date"] == "2026-02-05"
    assert items[0]["link"] == "https://www.licindia.in/documents/d/guest/final-press-release-dated-05-02-2026-2-"
    assert items[0]["type"] == "press-release"


def test_build_dpiit_document_items_prefers_browser_link_map_and_normalizes_dates():
    posts = [
        {
            "post_title": "Notification No. P-1 dated 05.03.2026",
            "post_slug": "notification-no-p-1",
            "acf_data": {
                "title": "Notification No. P-1 dated 05.03.2026",
                "date": "06/03/2026",
                "file": [{"type": "PDF", "external_link": "", "file": [123]}],
            },
            "documents_category": [{"name": "Gazette Notifications"}],
        },
        {
            "post_title": "GI Catalogue",
            "post_slug": "gi-catalogue",
            "acf_data": {
                "title": "GI Catalogue",
                "date": "03/03/2026",
                "file": [{"type": "Link", "external_link": "https://example.com/catalogue"}],
            },
            "documents_category": [{"name": "Publications"}],
        },
    ]

    items = module.build_dpiit_document_items(
        posts,
        "dipp",
        {
            "dpiit_allowed_categories": ["Gazette Notifications", "Publications"],
        },
        link_map={
            module.normalize_title_key("Notification No. P-1 dated 05.03.2026"): "https://www.dpiit.gov.in/static/uploads/latest.pdf"
        },
    )

    assert len(items) == 2
    assert items[0]["link"] == "https://www.dpiit.gov.in/static/uploads/latest.pdf"
    assert items[0]["pub_date"] == "2026-03-06"
    assert items[1]["link"] == "https://example.com/catalogue"
    assert items[1]["category"] == "publications"
    assert module.normalize_item_date("Feburary 11, 2020") == "2020-02-11"


def test_extract_candidate_date_ignores_reference_numbers():
    assert module.extract_candidate_date("RBI/2025-26/208") is None
    assert (
        module.extract_candidate_date(
            "Notice - IDCW Record Date - RD March 05, 2026 https://files.hdfcfund.com/s3fs-public/2026-03/2058-notice.pdf"
        )
        == "2026-03-05"
    )
    assert module.extract_candidate_date("Issue Date 7 March 2025") == "2025-03-07"


def test_extract_items_from_soup_skips_navigation_noise_and_keeps_document_links():
    html = """
    <html>
      <body>
        <a href="/branch">Branch Locator</a>
        <a href="/web/guest/mission/vision">Mission/Vision</a>
        <div class="notice-row">
          <span>06/03/2026</span>
          <a href="/documents/circular-20260306.pdf">Circular on settlement process for members</a>
        </div>
      </body>
    </html>
    """

    items = module.extract_items_from_soup(
        module.BeautifulSoup(html, "html.parser"),
        "https://example.com/notices",
        "example_site",
        {"update_types": ["circular", "notice"]},
    )

    assert len(items) == 1
    assert items[0]["title"] == "Circular on settlement process for members"
    assert items[0]["pub_date"] == "2026-03-06"
    assert items[0]["attachments"][0]["url"] == "https://example.com/documents/circular-20260306.pdf"


def test_collect_item_attachments_adds_direct_pdf_link():
    attachments = module.collect_item_attachments(
        {"link": "https://nsearchives.nseindia.com/web/circular/2026-03/NSE_Circular_02032026.pdf"}
    )

    assert attachments == [
        {
            "url": "https://nsearchives.nseindia.com/web/circular/2026-03/NSE_Circular_02032026.pdf",
            "filename": "NSE_Circular_02032026.pdf",
            "file_type": "pdf",
        }
    ]


def test_collect_item_attachments_uses_candidate_file_url_without_extension():
    attachments = module.collect_item_attachments(
        {
            "link": "https://example.com/detail-page",
            "candidate_file_url": "https://example.com/DownloadFile?eventID=DP2026-194&method=communique",
        }
    )

    assert attachments == [
        {
            "url": "https://example.com/DownloadFile?eventID=DP2026-194&method=communique",
            "filename": "DownloadFile",
            "file_type": None,
        }
    ]


def test_collect_item_attachments_merges_filename_metadata_for_duplicate_url():
    attachments = module.collect_item_attachments(
        {
            "candidate_file_url": "https://example.com/DownloadFile?eventID=DP2026-194&method=communique",
            "attachments": [
                {
                    "url": "https://example.com/DownloadFile?eventID=DP2026-194&method=communique",
                    "filename": "DP-194-Securities-Admitted-With-CDSL-19032026.pdf",
                    "file_type": "pdf",
                }
            ],
        }
    )

    assert attachments == [
        {
            "url": "https://example.com/DownloadFile?eventID=DP2026-194&method=communique",
            "filename": "DP-194-Securities-Admitted-With-CDSL-19032026.pdf",
            "file_type": "pdf",
        }
    ]


def test_extract_discovered_document_urls_normalizes_compound_links():
    urls = module.extract_discovered_document_urls(
        "https://dea.gov.in/files/press_release_documents/english.pdf, /files/press_release_documents/hindi.pdf",
        "https://dea.gov.in/",
    )

    assert urls == [
        "https://dea.gov.in/files/press_release_documents/english.pdf",
        "https://dea.gov.in/files/press_release_documents/hindi.pdf",
    ]


def test_extract_items_from_soup_normalizes_backslash_document_paths():
    html = """
    <html>
      <body>
        <div>
          <span>06/03/2026</span>
          <a href="/circulars/20260306-3\\20260306-3.pdf">Annual Clearing Membership Fees from financial year 2026-2027</a>
        </div>
      </body>
    </html>
    """

    items = module.extract_items_from_soup(
        module.BeautifulSoup(html, "html.parser"),
        "https://www.indiainx.com/markets/Circulars.aspx",
        "india_inx",
        {"update_types": ["circular"], "required_url_terms": ["/circulars/"]},
    )

    assert len(items) == 1
    assert items[0]["link"] == "https://www.indiainx.com/circulars/20260306-3/20260306-3.pdf"


def test_extract_items_from_iccl_notices_parses_table_rows():
    html = """
    <html>
      <body>
        <table id="GridView2">
          <tr>
            <th>Date</th><th>Notice No</th><th>Subject</th><th>Segment</th><th>Category</th><th>Department</th>
          </tr>
          <tr>
            <td>March 06, 2026</td>
            <td>20260306-37</td>
            <td><a href="DispNoticesNCirculars.aspx?page=20260306-37">Accessing RTRMS applications through SSO</a></td>
            <td>General</td>
            <td>Settlement/RMS</td>
            <td>Post Trade</td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_iccl_notices(
                "iccl",
                {"urls": ["https://www.icclindia.com/DynamicPages/NoticesCirculars.aspx"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "Accessing RTRMS applications through SSO"
    assert items[0]["pub_date"] == "2026-03-06"
    assert items[0]["link"] == "https://www.icclindia.com/DynamicPages/DispNoticesNCirculars.aspx?page=20260306-37"


def test_extract_items_from_ccil_notifications_parses_table_rows():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th>No</th><th>Date</th><th>Notification</th><th>Segment</th><th>Category</th><th>Topic</th>
          </tr>
          <tr>
            <td>1</td>
            <td>02-Mar-26</td>
            <td><a href="https://www.ccilindia.com/documents/d/ccil/sig_25_12_mar_2026-pdf">CCIL contribution towards pre-funded default handling resources</a></td>
            <td>Risk Management-General</td>
            <td></td>
            <td></td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_ccil_notifications(
                "ccil",
                {"urls": ["https://www.ccilindia.com/ccil-notification-view-all"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "CCIL contribution towards pre-funded default handling resources"
    assert items[0]["pub_date"] == "2026-03-02"
    assert items[0]["link"] == "https://www.ccilindia.com/documents/d/ccil/sig_25_12_mar_2026-pdf"


def test_extract_items_from_ccil_notifications_honors_skip_url_terms():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th>No</th><th>Date</th><th>Notification</th><th>Segment</th>
          </tr>
          <tr>
            <td>1</td>
            <td>10-Mar-26</td>
            <td><a href="https://www.ccilindia.com/documents/d/ccil/effectiveness-of-spread-feb-2026-xlsx">Back-testing results Effectiveness of yield spreads</a></td>
            <td>Risk Management-General</td>
          </tr>
          <tr>
            <td>2</td>
            <td>02-Mar-26</td>
            <td><a href="https://www.ccilindia.com/documents/d/ccil/sig_25_12_mar_2026-pdf">CCIL contribution towards pre-funded default handling resources</a></td>
            <td>Risk Management-General</td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_ccil_notifications(
                "ccil",
                {
                    "urls": ["https://www.ccilindia.com/ccil-notification-view-all"],
                    "skip_url_terms": ["-xls", "-xlsx"],
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "CCIL contribution towards pre-funded default handling resources"


def test_extract_items_from_ckycr_notifications_parses_cards_from_notification_pages():
    notification_html = """
    <html>
      <body>
        <div class="col-md-12 notification">
          <div class="col-md-10 nsection1">
            <p>State, District and Pincode Masters' update</p>
            <h5>March 13, 2025</h5>
          </div>
          <div class="col-md-2 nsectionimg">
            <a href="../ckyc/assets/doc/State_District_and_Pincode_Masters_update_01_OPT.pdf">PDF</a>
          </div>
        </div>
      </body>
    </html>
    """
    communique_html = """
    <html>
      <body>
        <div class="col-md-12 notification">
          <div class="col-md-10 nsection1">
            <p>Communique Introduction of watermarking of OVD images in CKYCRR</p>
            <h5>February 10, 2026</h5>
          </div>
          <div class="col-md-2 nsectionimg">
            <a href="../ckyc/assets/doc/ovd-watermarking.pdf">PDF</a>
          </div>
        </div>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            if "Communiques.php" in url:
                return DummyResponse(communique_html)
            return DummyResponse(notification_html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_ckycr_notifications(
                "ckycr",
                {
                    "urls": [
                        "https://www.ckycindia.in/ckyc/index.php?r=notification",
                        "https://www.ckycindia.in/ckyc/Communiques.php",
                    ]
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 2
    assert items[0]["title"] == "State, District and Pincode Masters' update"
    assert items[0]["pub_date"] == "2025-03-13"
    assert items[0]["link"] == "https://www.ckycindia.in/ckyc/assets/doc/State_District_and_Pincode_Masters_update_01_OPT.pdf"
    assert items[1]["category"] == "communique"
    assert items[1]["pub_date"] == "2026-02-10"


def test_extract_items_from_nabard_circulars_uses_detail_page_dates():
    listing_html = """
    <html>
      <body>
        <a href="CircularPage.aspx?cid=504&id=20211">Issue of Master Direction on CRR/SLR by RBI – Withdrawal of NABARD's Circulars on CRR/SLR</a>
        <a href="CircularPage.aspx?cid=504&id=20152">Sanction of term loans to State Governments</a>
      </body>
    </html>
    """
    detail_pages = {
        "https://www.nabard.org/CircularPage.aspx?cid=504&id=20211": """
            <html><body><div>Issue of Master Direction on CRR/SLR by RBI – Withdrawal of NABARD's Circulars on CRR/SLR 07 March 2025 Ref. No. NB. HO. DoS. Pol. / 159398 / 2024-25</div></body></html>
        """,
        "https://www.nabard.org/CircularPage.aspx?cid=504&id=20152": """
            <html><body><div>Sanction of term loans to State Governments 01 July 2025 Ref. No. 158/2025-26</div></body></html>
        """,
    }

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            if "circulars.aspx" in url:
                return DummyResponse(listing_html)
            return DummyResponse(detail_pages[url])

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_nabard_circulars(
                "nabard",
                {"urls": ["https://www.nabard.org/circulars.aspx?cid=504&id=24"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 2
    assert items[0]["pub_date"] == "2025-03-07"
    assert items[0]["link"] == "https://www.nabard.org/CircularPage.aspx?cid=504&id=20211"
    assert items[1]["pub_date"] == "2025-07-01"


def test_extract_items_from_bse_listing_api_parses_json_rows():
    payload = {
        "Table": [
            {
                "mr_date": "March 6, 2026",
                "mr_heading": "Update on single filing system through API-based integration between Stock Exchanges",
                "mr_cat": "Circulars Listed Companies",
                "articleid": "20260306-25",
                "Rd_Flag": "NTC",
            }
        ]
    }

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class DummyClient:
        async def get(self, url, headers=None, timeout=None):
            return DummyResponse()

    import asyncio

    items = asyncio.run(
        module.extract_items_from_bse_listing_api(
            "bse_listing",
            {
                "api_url": "https://api.bseindia.com/BseIndiaAPI/api/GetDataCirToListComp/w",
                "referer": "https://www.bseindia.com/corporates/CirularToListedComp.html",
            },
            DummyClient(),
        )
    )
    assert len(items) == 1
    assert items[0]["title"].startswith("Update on single filing system")
    assert items[0]["pub_date"] == "2026-03-06"
    assert items[0]["link"].endswith("page=20260306-25")


def test_extract_items_from_bse_notices_filters_by_include_terms():
    html = """
    <html>
      <body>
        <table id="ContentPlaceHolder1_GridView1">
          <tr>
            <td>20260310-8</td>
            <td><a href="/markets/MarketInfo/DispNewNoticesCirculars.aspx?page=20260310-8">Review of Margin Framework for Commodity Derivatives Segment</a></td>
            <td>Commodity Derivatives</td>
            <td>Margin</td>
            <td>Trading Operations</td>
          </tr>
          <tr>
            <td>20260310-9</td>
            <td><a href="/markets/MarketInfo/DispNewNoticesCirculars.aspx?page=20260310-9">Equity market holiday notice</a></td>
            <td>Equity</td>
            <td>Holiday</td>
            <td>Operations</td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_bse_notices(
                "bse_fo",
                {
                    "urls": ["https://www.bseindia.com/markets/MarketInfo/NoticesCirculars.aspx"],
                    "bse_include_terms": ["commodity derivatives", "derivatives"],
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "Review of Margin Framework for Commodity Derivatives Segment"
    assert items[0]["pub_date"] == "2026-03-10"


def test_extract_items_from_bse_notices_walks_previous_days_until_match():
    current_html = """
    <html>
      <body>
        <form>
          <input type="hidden" name="__VIEWSTATE" value="state-1" />
          <input type="hidden" name="__EVENTVALIDATION" value="valid-1" />
          <a id="ContentPlaceHolder1_lnkPreviousDay" href="javascript:__doPostBack('ctl00$ContentPlaceHolder1$lnkPreviousDay','')">Previous Day</a>
          <table id="ContentPlaceHolder1_GridView1">
            <tr>
              <th>Notice No</th><th>Subject</th><th>Segment Name</th><th>Category Name</th><th>Department</th><th>PDF</th>
            </tr>
            <tr>
              <td>20260320-01</td>
              <td><a href="/downloads/UploadDocs/Notices/20260320-01/20260320-01.pdf">Daily Bulletin</a></td>
              <td>General</td>
              <td>Company related</td>
              <td>Listing Operations</td>
              <td></td>
            </tr>
          </table>
        </form>
      </body>
    </html>
    """

    previous_html = """
    <html>
      <body>
        <form>
          <input type="hidden" name="__VIEWSTATE" value="state-2" />
          <input type="hidden" name="__EVENTVALIDATION" value="valid-2" />
          <table id="ContentPlaceHolder1_GridView1">
            <tr>
              <th>Notice No</th><th>Subject</th><th>Segment Name</th><th>Category Name</th><th>Department</th><th>PDF</th>
            </tr>
            <tr>
              <td>20260318-13</td>
              <td><a href="/downloads/UploadDocs/Notices/20260318-13/20260318-13.pdf">Mock Trading on Saturday, March 21, 2026, for Equity Derivatives segment</a></td>
              <td>Derivatives</td>
              <td>Trading</td>
              <td>Trading Operations</td>
              <td></td>
            </tr>
            <tr>
              <td>20260318-15</td>
              <td><a href="/downloads/UploadDocs/Notices/20260318-15/20260318-15.pdf">Mock Trading on Saturday, March 21, 2026 for Currency Derivatives segment</a></td>
              <td>Currency Derivatives</td>
              <td>Trading</td>
              <td>Trading Operations</td>
              <td></td>
            </tr>
          </table>
        </form>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text, url="https://www.bseindia.com/markets/MarketInfo/NoticesCirculars.aspx"):
            self.text = text
            self.url = url

        def raise_for_status(self):
            return None

    class DummyClient:
        async def post(self, url, data=None, headers=None):
            assert data["__EVENTTARGET"] == "ctl00$ContentPlaceHolder1$lnkPreviousDay"
            return DummyResponse(previous_html)

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(current_html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_bse_notices(
                "bse_fo",
                {
                    "urls": ["https://www.bseindia.com/markets/MarketInfo/NoticesCirculars.aspx"],
                    "bse_include_terms": ["commodity derivatives", "currency derivatives", "derivatives"],
                    "bse_previous_day_lookback": 3,
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 2
    assert {item["pub_date"] for item in items} == {"2026-03-18"}
    assert all(item["content_snippet"] == "Derivatives | Trading | Trading Operations" or item["content_snippet"] == "Currency Derivatives | Trading | Trading Operations" for item in items)


def test_generic_extractor_prefers_context_date_over_title_effective_date():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <td>11 March 2026</td>
            <td>ACTIVE</td>
            <td><a href="/downloadables/pdf/11_Circular_Trading_Window_Closure_Period_effective_1_April_2026.pdf">11 Circular_Trading Window Closure Period effective 1 April 2026</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_soup(
        module.BeautifulSoup(html, "html.parser"),
        "https://nsdl.co.in/business/issuers_rts.php",
        "nsdl",
        {
            "required_title_terms": ["circular"],
            "required_keywords": ["circular"],
        },
    )

    assert len(items) == 1
    assert items[0]["pub_date"] == "2026-03-11"


def test_extract_items_from_gst_council_circulars_html_parses_rows_and_attachments():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th>Sr. No.</th><th>Circular No</th><th>Circular File</th><th>Date of issue</th><th>Subject</th>
          </tr>
          <tr>
            <td>1</td>
            <td>248/05/2025-GST</td>
            <td>
              <a href="/sites/default/files/2025-04/circular-no-248-05-2025.pdf">View</a>
              <a href="/sites/default/files/2025-04/circular-no-10h-2025.pdf">View</a>
            </td>
            <td>27-03-2025</td>
            <td>Various issues related to availment of benefit of Section 128A of the CGST Act, 2017</td>
          </tr>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_gst_council_circulars_html(
        html,
        "https://gstcouncil.gov.in/cgst-circulars",
        "gst_council",
        {},
    )

    assert len(items) == 1
    assert items[0]["title"].startswith("Various issues related to availment")
    assert items[0]["pub_date"] == "2025-03-27"
    assert items[0]["link"] == "https://gstcouncil.gov.in/sites/default/files/2025-04/circular-no-248-05-2025.pdf"
    assert items[0]["attachments"] == [
        {
            "url": "https://gstcouncil.gov.in/sites/default/files/2025-04/circular-no-10h-2025.pdf",
            "filename": "circular-no-10h-2025.pdf",
            "file_type": "pdf",
        }
    ]


def test_extract_items_from_cdsl_home_cards_html_uses_card_titles():
    html = """
    <html>
      <body>
        <div class="more-new-box">
          <h4 class="news-small-title">SEBI Circular- Relaxation in timelines for compliance with regulatory requirements</h4>
          <a href="./downloads/DP-229-SEBI-Relaxation-in-timelines-for-compliance.pdf">Read More</a>
        </div>
        <div class="more-new-box">
          <h4 class="news-small-title">Conference Call updates for Financial Year 21-22 Q2 Earnings</h4>
          <a href="https://www.cdslindia.com/downloads/IPO/GeneralMeeting/Q2TranscripttoNSE.pdf">Read More</a>
        </div>
      </body>
    </html>
    """

    items = module.extract_items_from_cdsl_home_cards_html(
        html,
        "https://www.cdslindia.com/",
        "cdsl",
        {
            "required_keywords": ["circular", "communique", "sebi"],
            "skip_title_terms": ["conference call", "earnings", "transcript", "ipo", "general meeting"],
        },
    )

    assert len(items) == 1
    assert items[0]["title"].startswith("SEBI Circular- Relaxation in timelines")
    assert items[0]["link"] == "https://www.cdslindia.com/downloads/DP-229-SEBI-Relaxation-in-timelines-for-compliance.pdf"
    assert items[0]["pub_date"] == ""


def test_extract_items_from_cbdt_communications_html_parses_js_links():
    html = """
    <html>
      <body>
        <div class="search_result">
          <div class="NotificationNumber">Circular No.15/2025 :</div>
          <div>Extension of timelines for filing of various reports of audit and Income Tax Returns (ITRs) for the Assessment Year 2025-26</div>
          <div class="publishDate">29 October 2025</div>
          <a href="javascript:void(0)" onclick="javascript:OpenFormByType('https://incometaxindia.gov.in/communications/circular/circular-15-2025.pdf&amp;k=&amp;opt=')">View</a>
          <div>F. No. 225/131/2025/ITA-II</div>
        </div>
      </body>
    </html>
    """

    items = module.extract_items_from_cbdt_communications_html(
        html,
        "https://incometaxindia.gov.in/Pages/communications/circulars.aspx?c=23",
        "cbdt",
        {},
    )

    assert len(items) == 1
    assert items[0]["title"] == "Circular No.15/2025 | Extension of timelines for filing of various reports of audit and Income Tax Returns (ITRs) for the Assessment Year 2025-26"
    assert items[0]["pub_date"] == "2025-10-29"
    assert items[0]["link"] == "https://incometaxindia.gov.in/communications/circular/circular-15-2025.pdf"


def test_extract_items_from_cbdt_structured_contents_parses_search_api_results():
    html = """
    <html>
      <script>
        Liferay.authToken = 'token123';
        Liferay.ThemeDisplay = {
          getScopeGroupId: function () { return '20117'; }
        };
      </script>
      <etds-circular-notification structureid="36050"></etds-circular-notification>
    </html>
    """

    search_payload = {
        "page": 1,
        "lastPage": 1,
        "items": [
            {
                "title": "Income-tax Rules, 2026 : Notification No. 22/2026",
                "itemURL": "https://www.incometaxindia.gov.in/o/headless-delivery/v1.0/structured-contents/16316874",
                "embedded": {
                    "contentFields": [
                        {"name": "circularNotificationNumber", "contentFieldValue": {"data": "Notification No. 22/2026"}},
                        {"name": "circularNotificationDate", "contentFieldValue": {"data": "2026-03-20T00:00:00Z"}},
                        {"name": "uploadDate", "contentFieldValue": {"data": "2026-03-20T00:00:00Z"}},
                        {"name": "summary", "contentFieldValue": {"data": "<p>CBDT update</p>"}},
                        {
                            "name": "reportFile",
                            "contentFieldValue": {
                                "document": {
                                    "contentUrl": "/documents/d/guest/en-notified-it-rules-2026-20-03-2026-pdf",
                                    "title": "En-Notified-IT-Rules-2026-20-03-2026.pdf",
                                    "fileExtension": "pdf",
                                }
                            },
                        },
                    ]
                },
            },
            {
                "title": "Due date for furnishing challan-cum-statement",
                "itemURL": "https://www.incometaxindia.gov.in/o/headless-delivery/v1.0/structured-contents/15484006",
                "embedded": {
                    "contentFields": [
                        {"name": "uploadDate", "contentFieldValue": {"data": "2026-01-20T00:00:00Z"}},
                    ]
                },
            },
        ],
    }

    class DummyResponse:
        def __init__(self, text="", json_data=None):
            self.text = text
            self._json_data = json_data or {}

        def json(self):
            return self._json_data

        def raise_for_status(self):
            return None

    class DummyClient:
        async def post(self, url, params=None, headers=None, json=None):
            return DummyResponse(json_data=search_payload)

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(text=html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_cbdt_structured_contents(
                "cbdt",
                {"urls": ["https://www.incometaxindia.gov.in/circulars"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "Income-tax Rules, 2026 : Notification No. 22/2026"
    assert items[0]["pub_date"] == "2026-03-20"
    assert items[0]["link"] == "https://www.incometaxindia.gov.in/documents/d/guest/en-notified-it-rules-2026-20-03-2026-pdf"
    assert items[0]["reference_number"] == "Notification No. 22/2026"


def test_extract_items_from_icmai_notifications_html_uses_notification_tab_only():
    html = """
    <html>
      <body>
        <div id="Notification_Updates">
          <ul>
            <li><a href="https://icmai.in/upload/Institute/Notifications/Notification_Varanasi_Chapter_1003_26.pdf">Notification - Constitution of Varanasi Chapter of The Institute of Cost Accountants of India <font color="red">New</font></a></li>
            <li><a href="https://icmai.in/upload/pd/UDIN-18102025.pdf">Revision in the time limit for UDIN generation. <font color="red">New</font></a></li>
          </ul>
        </div>
        <div id="Tenders">
          <a href="https://icmai.in/upload/Institute/Tenders/EOI_Hiring_Busses.pdf">Expression of Interest for Hiring of buses</a>
        </div>
      </body>
    </html>
    """

    items = module.extract_items_from_icmai_notifications_html(
        html,
        "https://icmai.in/icmai/",
        "cma_india",
        {},
    )

    assert len(items) == 2
    assert items[0]["title"] == "Notification - Constitution of Varanasi Chapter of The Institute of Cost Accountants of India"
    assert items[0]["pub_date"] == "2026-03-10"
    assert items[0]["link"] == "https://icmai.in/upload/Institute/Notifications/Notification_Varanasi_Chapter_1003_26.pdf"
    assert all("Hiring of buses" not in item["title"] for item in items)


def test_extract_items_from_iba_circulars_html_parses_table_rows():
    html = """
    <html>
      <body>
        <table>
          <tr><th>Sr.</th><th>Date</th><th>Title</th></tr>
          <tr>
            <td>1</td>
            <td>06-02-2026</td>
            <td><a href="https://www.iba.org.in/circulars/dearness-relief-payable_1860.html">Dearness Relief payable for the period February 2026 to July 2026</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_iba_circulars_html(
        html,
        "https://www.iba.org.in/iba/home/HomeAction.do?doNewslist=yes&sectionIdIndex=5&subSectionIdIndex=0&subSectionIdIndex1=0",
        "iba",
        {},
    )

    assert len(items) == 1
    assert items[0]["title"] == "Dearness Relief payable for the period February 2026 to July 2026"
    assert items[0]["pub_date"] == "2026-02-06"
    assert items[0]["link"] == "https://www.iba.org.in/circulars/dearness-relief-payable_1860.html"


def test_extract_items_from_sidbi_circulars_uses_json_endpoint_rows():
    payload = {
        "data": [
            {
                "circulars_title": "&lt;p&gt;Revision of Interest Rate Structure under Fixed Deposit Scheme (FDS)&lt;/p&gt;",
                "circulars_date": "24/06/2025",
                "filename": "TRMV_Anexure_No.03_2025-26.pdf",
                "file_format": "PDF",
            }
        ]
    }

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(payload)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_sidbi_circulars(
                "sidbi",
                {
                    "api_url": "https://www.sidbi.in/head/engine/json/JSONcirculars.php?show=frontend&language=english",
                    "sidbi_uploads_base": "https://www.sidbi.in/uploads/",
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "Revision of Interest Rate Structure under Fixed Deposit Scheme (FDS)"
    assert items[0]["pub_date"] == "2025-06-24"
    assert items[0]["link"] == "https://www.sidbi.in/uploads/TRMV_Anexure_No.03_2025-26.pdf"


def test_extract_items_from_sbi_notice_addendums_html_parses_rows():
    html = """
    <table>
      <tbody>
        <tr>
          <td><a href="/docs/default-source/sif-forms/riskometer-mom-change---february-2026.pdf?sfvrsn=1c015ba1_0">Riskometer MoM Change - February 2026</a></td>
          <td><img alt="PDF" /></td>
          <td>599 KB</td>
          <td>10 Mar, 2026</td>
        </tr>
        <tr>
          <td><a href="/docs/default-source/sif-forms/notice-cum-addendum.pdf?sfvrsn=d2e3b409_0">Notice cum addendum - Additional incentives</a></td>
          <td><img alt="PDF" /></td>
          <td>850 KB</td>
          <td>27 Feb, 2026</td>
        </tr>
      </tbody>
    </table>
    """

    items = module.extract_items_from_sbi_notice_addendums_html(
        html,
        "https://www.sbimf.com/notice-and-addendums",
        "sbi_funds",
        {},
    )

    assert len(items) == 2
    assert items[0]["title"] == "Riskometer MoM Change - February 2026"
    assert items[0]["pub_date"] == "2026-03-10"
    assert items[0]["link"].startswith("https://www.sbimf.com/docs/default-source/")


def test_extract_items_from_ncdex_circulars_html_parses_pdf_rows():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th>Date</th><th>Circular No.</th><th>Department</th><th>Subject</th><th>English</th><th>Hindi</th>
          </tr>
          <tr>
            <td>10-Mar-2026</td>
            <td>NCDEX/MEMBERSHIP-009/2026</td>
            <td>Membership</td>
            <td>Guidelines in pursuance of amendment to SEBI KYC (Know Your client) Registration Agency (KRA) Regulations, 2011</td>
            <td><a href="https://www.ncdex.com/public/uploads/circulars/Guidelines.pdf"></a></td>
            <td>-</td>
          </tr>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_ncdex_circulars_html(
        html,
        "https://www.ncdex.com/circulars",
        "ncdex",
        {},
    )

    assert len(items) == 1
    assert items[0]["title"].startswith("Guidelines in pursuance of amendment")
    assert items[0]["pub_date"] == "2026-03-10"
    assert items[0]["link"] == "https://www.ncdex.com/public/uploads/circulars/Guidelines.pdf"


def test_extract_items_from_mcxccl_circulars_html_parses_direct_pdf_links():
    html = """
    <html>
      <body>
        <table>
          <tr><th>Date</th><th>Category</th><th>Title</th><th>Circular No.</th></tr>
          <tr>
            <td>10 Mar 2026</td>
            <td>Risk and Collaterals</td>
            <td><a href="https://www.mcxccl.com/docs/librariesprovider2/circulars/2026/march/cicular-051---2026.pdf?sfvrsn=78079e_0">Revision in Threshold Limits for Concentration Margin</a></td>
            <td>51</td>
          </tr>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_mcxccl_circulars_html(
        html,
        "https://www.mcxccl.com/circulars/all-circulars",
        "mcx_ccl",
        {},
    )

    assert len(items) == 1
    assert items[0]["title"] == "Revision in Threshold Limits for Concentration Margin"
    assert items[0]["pub_date"] == "2026-03-10"
    assert items[0]["link"].startswith("https://www.mcxccl.com/docs/librariesprovider2/circulars/2026/march/cicular-051---2026.pdf")


def test_extract_items_from_nsdl_circulars_html_parses_table_links_and_skips_noise():
    html = """
    <html>
      <body>
        <table>
          <tr><th>Date</th><th>Status</th><th>Subject</th></tr>
          <tr>
            <td>09 March 2026</td>
            <td>ACTIVE</td>
            <td><a href="/downloadables/pdf/10_Circular_for_SEBI_Circular.pdf">10 Circular for SEBI Circular on Revised Norms for appointment of an independent third-party reviewer</a></td>
          </tr>
          <tr>
            <td>08 March 2026</td>
            <td>ACTIVE</td>
            <td><a href="/downloadables/pdf/Tender_Offer.pdf">Tender Offer - Sample Co</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    items = module.extract_items_from_nsdl_circulars_html(
        html,
        "https://nsdl.co.in/business/issuers_rts.php",
        "nsdl_eservices",
        {"skip_keywords": ["tender offer"]},
    )

    assert len(items) == 1
    assert items[0]["title"].startswith("10 Circular for SEBI Circular")
    assert items[0]["pub_date"] == "2026-03-09"
    assert items[0]["link"] == "https://nsdl.co.in/downloadables/pdf/10_Circular_for_SEBI_Circular.pdf"


def test_strict_special_source_does_not_fall_back_to_generic_html_noise():
    original_extract = module.extract_items_from_special_source
    original_original_scrape = module.ORIGINAL_SCRAPE_SITE

    async def fake_special_source(site_key, site, client):
        return []

    async def fake_original_scrape(site_key, site):
        return ([{
            "title": "{{$t('circulars')}}",
            "link": "https://www.cersai.org.in/CERSAI/circulars.prg",
            "url": "https://www.cersai.org.in/CERSAI/circulars.prg",
            "pub_date": "2026-03-21",
            "isoDate": "2026-03-21T00:00:00Z",
            "content_snippet": "junk",
            "category": "notice",
            "type": "notice",
            "site": "cersai",
            "source": "scraped",
        }], {"status": "success", "items_found": 1, "items_added": 0, "errors": []})

    module.extract_items_from_special_source = fake_special_source
    module.ORIGINAL_SCRAPE_SITE = fake_original_scrape
    try:
        items, stats = asyncio.run(module.scrape_site("cersai", {
            "name": "CERSAI",
            "urls": ["https://www.cersai.org.in/CERSAI/notifications.prg"],
            "browser_strategy": "cersai_notifications",
            "special_source_only": True,
            "minimum_expected_items": 1,
        }))
    finally:
        module.extract_items_from_special_source = original_extract
        module.ORIGINAL_SCRAPE_SITE = original_original_scrape

    assert items == []
    assert "Special source returned no items" in stats["errors"]


def test_extract_items_from_nse_circulars_api_filters_by_company():
    payload = {
        "data": [
            {
                "circFilelink": "https://nsearchives.nseindia.com/content/circulars/CMPT73190.pdf",
                "sub": "Member Interface Testing of Two-way portability across Clearing Corporations",
                "circDisplayNo": "NCL/CMPT/73190",
                "cirDate": "20260306",
                "circCategory": "Clearing",
                "circDepartment": "NSE Clearing - Capital Market",
                "circCompany": "NCL",
                "circFileSize": "335 KB",
            },
            {
                "circFilelink": "https://nsearchives.nseindia.com/content/circulars/NSE73126.pdf",
                "sub": "Live trading session from Disaster Recovery (DR) site",
                "circDisplayNo": "NSE/MSD/73126",
                "cirDate": "20260305",
                "circCategory": "Clearing",
                "circDepartment": "Securities Lending & Borrowing Scheme",
                "circCompany": "NSE",
                "circFileSize": "140 KB",
            },
        ]
    }

    class DummyResponse:
        def json(self):
            return payload

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse()

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_nse_circulars_api(
                "nse_clearing",
                {
                    "nse_circular_company": "NCL",
                    "nse_circular_days": 365,
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"].startswith("NCL/CMPT/73190")
    assert items[0]["pub_date"] == "2026-03-06"


def test_extract_items_from_nse_circulars_api_filters_by_company_list():
    payload = {
        "data": [
            {
                "circFilelink": "https://nsearchives.nseindia.com/content/circulars/NSE123.pdf",
                "sub": "Exchange circular",
                "circDisplayNo": "NSE/MSD/123",
                "cirDate": "20260306",
                "circCategory": "Circular",
                "circDepartment": "Member Service Department",
                "circCompany": "NSE",
                "circFileSize": "100 KB",
            },
            {
                "circFilelink": "https://nsearchives.nseindia.com/content/circulars/NSEIL124.pdf",
                "sub": "Subsidiary circular",
                "circDisplayNo": "NSEIL/OPS/124",
                "cirDate": "20260305",
                "circCategory": "Circular",
                "circDepartment": "Operations",
                "circCompany": "NSEIL",
                "circFileSize": "90 KB",
            },
            {
                "circFilelink": "https://nsearchives.nseindia.com/content/circulars/CMPT125.pdf",
                "sub": "Clearing circular",
                "circDisplayNo": "NCL/CMPT/125",
                "cirDate": "20260304",
                "circCategory": "Clearing",
                "circDepartment": "NSE Clearing - Capital Market",
                "circCompany": "NCL",
                "circFileSize": "80 KB",
            },
        ]
    }

    class DummyResponse:
        def json(self):
            return payload

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse()

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_nse_circulars_api(
                "nse",
                {
                    "nse_circular_companies": ["NSE", "NSEIL"],
                    "nse_circular_days": 30,
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 2
    assert {item["title"] for item in items} == {"NSE/MSD/123 | Exchange circular", "NSEIL/OPS/124 | Subsidiary circular"}


def test_extract_items_from_nse_listing_pages_parses_archive_links():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <td class="text-align-justify">Revised Norms for appointment of an independent third-party reviewer/ certifier for green debt security</td>
            <td>02/03/2026 <a href="https://nsearchives.nseindia.com/web/circular/2026-03/NSE_Circular_02032026.pdf"><img src="/assets/images/icon-pdf.svg" /></a><p>(232.46 KB)</p></td>
            <td>27/02/2026 <a href="https://nsearchives.nseindia.com/web/circular/2026-03/SEBI_Circular_27022026.pdf"><img src="/assets/images/icon-pdf.svg" /></a><p>(236.78 KB)</p></td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_nse_listing_pages(
                "nse_listing",
                {"urls": ["https://www.nseindia.com/companies-listing/circular-for-listed-companies-debt-market"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 2
    assert all(item["title"].startswith("Revised Norms for appointment") for item in items)
    assert {item["pub_date"] for item in items} == {"2026-03-02", "2026-02-27"}


def test_extract_items_from_cbic_tables_parses_rows():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th>Sr.No.</th><th>Circular No / F.NO.</th><th>Date</th><th>Year</th><th>Subject</th><th>CBIC Web-Link</th>
          </tr>
          <tr>
            <td>1</td>
            <td>Circular No. 15/2024-Customs</td>
            <td>12.09.2024</td>
            <td>2024</td>
            <td>Extending export related benefits for exports made through courier mode-reg</td>
            <td><a href="advisory/2024/Circular-No-15-2024.pdf">View Link</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_cbic_tables(
                "cbic",
                {"urls": ["https://courier.cbic.gov.in/circular.jsp"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"].startswith("Extending export related benefits")
    assert items[0]["pub_date"] == "2024-09-12"
    assert items[0]["link"] == "https://courier.cbic.gov.in/advisory/2024/Circular-No-15-2024.pdf"


def test_extract_items_from_nps_trust_circulars_parses_table_rows():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th>Sr.No</th><th>Title</th><th>Date</th><th>Document</th>
          </tr>
          <tr>
            <td>1</td>
            <td>Registration of Pension Funds - Guidelines, 2026</td>
            <td>12-01-2026</td>
            <td><a href="/sites/default/files/circulars-documents/GuidelinesforRegistrationofPFs2025.pdf">Download</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_nps_trust_circulars(
                "nps_trust",
                {"urls": ["https://npstrust.org.in/circulars"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "Registration of Pension Funds - Guidelines, 2026"
    assert items[0]["pub_date"] == "2026-01-12"
    assert items[0]["link"] == "https://npstrust.org.in/sites/default/files/circulars-documents/GuidelinesforRegistrationofPFs2025.pdf"


def test_extract_items_from_niti_notifications_parses_table_rows():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th>Sr.No</th><th>Title</th><th>Date</th><th>File</th>
          </tr>
          <tr>
            <td>1</td>
            <td>Relieving Notification Shri Gaurav Kumar, Adviser, NITI Aayog</td>
            <td>September, 2025</td>
            <td><a href="/sites/default/files/2025-09/Relieving-Notification.pdf">PDF</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_niti_notifications(
                "niti",
                {"urls": ["https://www.niti.gov.in/disclosures-rti/disclosures/circular-notifications"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"] == "Relieving Notification Shri Gaurav Kumar, Adviser, NITI Aayog"
    assert items[0]["pub_date"] == "2025-09-01"
    assert items[0]["link"] == "https://www.niti.gov.in/sites/default/files/2025-09/Relieving-Notification.pdf"


def test_extract_items_from_doe_circulars_parses_rows():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th>Sr. No.</th><th>Title</th><th>Date</th><th>Download</th>
          </tr>
          <tr>
            <td>1</td>
            <td>Training program on Public Procurement at Indian Institute of Management, Visakhapatnam (IIMV) – change of dates reg.</td>
            <td>16/02/2026</td>
            <td><a href="/files/circulars_document/OM_16022026.pdf">Download</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_doe_circulars(
                "doe",
                {"urls": ["https://doe.gov.in/circulars"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"].startswith("Training program on Public Procurement")
    assert items[0]["pub_date"] == "2026-02-16"
    assert items[0]["link"] == "https://doe.gov.in/files/circulars_document/OM_16022026.pdf"


def test_extract_items_from_nfra_circulars_parses_rows():
    html = """
    <html>
      <body>
        <table class="data-table-1 doc-table">
          <tr>
            <th>Title</th><th>Date</th><th>View / Download</th>
          </tr>
          <tr>
            <td>NFRA Circular on Maintenance, archival and submission of Audit File to NFRA.</td>
            <td>17/12/2025</td>
            <td><a href="https://cdnbbsr.s3waas.gov.in/uploads/2025/12/example.pdf">View</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_nfra_circulars(
                "nfra",
                {"urls": ["https://nfra.gov.in/document-category/circulars/"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"].startswith("NFRA Circular on Maintenance")
    assert items[0]["pub_date"] == "2025-12-17"
    assert items[0]["link"] == "https://cdnbbsr.s3waas.gov.in/uploads/2025/12/example.pdf"


def test_extract_items_from_ibbi_circulars_parses_rows_and_pagination():
    page_one_html = """
    <html>
      <body>
        <table>
          <tr>
            <th>Sr. No.</th><th>Date</th><th>Subject</th><th>PDF(English)</th><th>PDF(Hindi)</th>
          </tr>
          <tr>
            <td>1</td>
            <td>06 Mar, 2026</td>
            <td>Circular- Filing Forms to monitor insolvency resolution processes.</td>
            <td><a href="javascript:void(0)" onclick="javascript:newwindow1('https://ibbi.gov.in/uploads/legalframwork/example-1.pdf');">(532.42 KB)</a></td>
            <td></td>
          </tr>
        </table>
        <a href="/legal-framework/circulars?page=2">2</a>
      </body>
    </html>
    """
    page_two_html = """
    <html>
      <body>
        <table>
          <tr>
            <td>2</td>
            <td>05 Jan, 2026</td>
            <td>Launch of Revised Forms for Liquidation Process</td>
            <td><a href="javascript:void(0)" onclick="javascript:newwindow1('https://ibbi.gov.in/uploads/legalframwork/example-2.pdf');">(537.39 KB)</a></td>
            <td></td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            if url.endswith("page=2"):
                return DummyResponse(page_two_html)
            return DummyResponse(page_one_html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_ibbi_circulars(
                "ibbi",
                {"urls": ["https://ibbi.gov.in/legal-framework/circulars"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 2
    assert {item["pub_date"] for item in items} == {"2026-03-06", "2026-01-05"}
    assert items[0]["link"].startswith("https://ibbi.gov.in/uploads/legalframwork/")


def test_extract_items_from_pfrda_listing_parses_cards_and_pagination():
    page_one_html = """
    <html>
      <body>
        <div id="accordionListing">
          <div class="accordianCard">
            <a class="text-decoration-none" href="https://www.pfrda.org.in/web/pfrda/w/notice-one">
              <div class="card-header accordian-header">
                <h2 class="accordian-title">Notification of effective date of NPS Vatsalya Scheme Guidelines 2025</h2>
                <span class="tag">Promotion and Development - NPS</span>
                <div class="accordian-dateReference date-display">
                  <div>Reference Number: PFRDA/2026/14/NPS-Vatsalya/02</div>
                  <div>Issue Date: 27-02-2026</div>
                </div>
              </div>
            </a>
          </div>
        </div>
        <ul class="pagination">
          <li><a href="/web/pfrda/regulatory-framework/circulars/active-circulars?delta=10&amp;start=2">2</a></li>
        </ul>
      </body>
    </html>
    """
    page_two_html = """
    <html>
      <body>
        <div id="accordionListing">
          <div class="accordianCard">
            <a class="text-decoration-none" href="https://www.pfrda.org.in/web/pfrda/w/notice-two">
              <div class="card-header accordian-header">
                <h2 class="accordian-title">Sharing of Subscriber Information under Multiple Scheme Framework (MSF) with Pension Funds</h2>
                <span class="tag">Pension Fund</span>
                <div class="accordian-dateReference date-display">
                  <div>Reference Number: PFRDA/2026/04/REG-PF/02</div>
                  <div>Issue Date: 12-01-2026</div>
                </div>
              </div>
            </a>
          </div>
        </div>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            if "start=2" in url:
                return DummyResponse(page_two_html)
            return DummyResponse(page_one_html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_pfrda_listing(
                "pfrda_circulars",
                {
                    "urls": ["https://www.pfrda.org.in/web/pfrda/regulatory-framework/circulars/active-circulars"],
                    "pfrda_page_key": "/web/pfrda/regulatory-framework/circulars/active-circulars",
                },
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 2
    assert {item["pub_date"] for item in items} == {"2026-02-27", "2026-01-12"}
    assert all(item["link"].startswith("https://www.pfrda.org.in/web/pfrda/w/") for item in items)


def test_extract_items_from_irdai_circulars_parses_table_rows():
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th></th><th>Archive</th><th>Short Description</th><th>Sub Title</th><th>Last Updated</th><th>Documents</th>
          </tr>
          <tr>
            <td></td>
            <td>Non-Archived</td>
            <td>Clarifications on provisions with respect to investment in Alternative Investment Funds(AIFs)</td>
            <td>Clarifications on provisions with respect to investment in Alternative Investment Funds(AIFs)</td>
            <td>12-02-2026</td>
            <td><a href="/documents/37343/620662/aif-clarification.pdf">Clarifications on provisions ...</a></td>
          </tr>
        </table>
      </body>
    </html>
    """

    class DummyResponse:
        def __init__(self, text):
            self.text = text

    class DummyClient:
        pass

    async def run():
        original = module.fetch_with_retry

        async def fake_fetch(url, client, retries):
            return DummyResponse(html)

        module.fetch_with_retry = fake_fetch
        try:
            return await module.extract_items_from_irdai_circulars(
                "irdai",
                {"urls": ["https://irdai.gov.in/circulars"]},
                DummyClient(),
            )
        finally:
            module.fetch_with_retry = original

    import asyncio

    items = asyncio.run(run())
    assert len(items) == 1
    assert items[0]["title"].startswith("Clarifications on provisions")
    assert items[0]["pub_date"] == "2026-02-12"
    assert items[0]["link"] == "https://irdai.gov.in/documents/37343/620662/aif-clarification.pdf"
