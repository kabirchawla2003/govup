import asyncio
import json
import os
import time
from datetime import datetime, timezone
from importlib import util
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlsplit, urlunsplit

import requests


ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src" / "main-v9-broker-enhanced.py"
LIVE_RESULTS_PATH = ROOT / "live_scrape_results_latest_v8.json"
PDF_RESULTS_PATH = ROOT / "latest_pdf_fetch_results_v6.json"
VERIFICATION_PATH = ROOT / "LIVE_VERIFICATION.md"
BROKER_REPORT_PATH = ROOT / "BROKER_MUST_HAVE_REPORT.md"
BROKER_JSON_PATH = ROOT / "broker_must_have_status_latest.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
)
FILE_HINTS = (
    ".pdf",
    ".zip",
    ".xls",
    ".xlsx",
    ".csv",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".txt",
)
HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
OK_FILE_TYPES = (
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument",
    "text/csv",
    "application/msword",
)

BASE_TRUSTED = {
    "amfi",
    "bse",
    "bse_fo",
    "bse_listing",
    "cbdt",
    "cbic",
    "ccil",
    "cdsl",
    "ckycr",
    "cma_india",
    "cestat",
    "crif_highmark",
    "dea",
    "dicgc",
    "dfs",
    "doe",
    "epfo",
    "fimmda",
    "fiu_ind",
    "gst_council",
    "hdfc_mf",
    "ibbi",
    "icai",
    "iccl",
    "india_inx",
    "irdai",
    "iba",
    "iepf",
    "mca",
    "mcx",
    "mcx_ccl",
    "ministry_finance",
    "nabard",
    "ncdex",
    "nfra",
    "nism",
    "nsdl",
    "nsdl_eservices",
    "npci",
    "nps_trust",
    "niti",
    "nse",
    "nse_clearing",
    "nse_fo",
    "nse_listing",
    "pfrda_circulars",
    "pfrda_master_circulars",
    "rbi",
    "rbi_dbod",
    "rbi_fmrd",
    "fema",
    "scores",
    "sebi",
    "sebi_broker_master_circulars",
    "sebi_broker_regulations",
    "sebi_cir",
    "sebi_enforcement",
    "sebi_intermediaries",
    "sebi_mr",
    "sebi_ra",
    "sebi_ria",
    "cersai",
    "dipp",
    "fiu_ind_guidance",
    "mse",
    "sbi_funds",
    "sidbi",
    "uidai_authentication_docs",
}

BASE_NOISY = {
    "anmi",
    "bse_indices",
    "care",
    "cibil",
    "crisil",
    "equifax",
    "experian",
    "exim_bank",
    "icsi",
    "icra",
    "lic",
    "nse_indices",
    "sebi_sme",
}
EXCLUDED_FROM_ACTIVE_SCOPE = {
    "ace": "Agricultural commodities exchange site is outside the broker-alert product scope.",
    "anmi": "Compliance calendar, not a latest circular stream.",
    "asba": "Wrong site entirely; unrelated badminton association.",
    "bcsbi": "Banking customer-service standards body is outside the broker-alert product scope.",
    "bse_indices": "Index/history pages, not a circular feed.",
    "cag": "Access denied and not a usable live circular source.",
    "care": "No reliable regulatory circular feed on the public site.",
    "cibil": "Policy/disclosure collateral, not a latest circular stream.",
    "cdslindia": "Downloads/forms library, not a dated circular feed.",
    "crisil": "Press/login content, not a circular source.",
    "equifax": "Static policy collateral, not a latest circular stream.",
    "experian": "Static policy collateral, not a latest circular stream.",
    "exim_bank": "Public declarations/disclosures and tenders are outside the broker-alert circular scope.",
    "gic_re": "Policies/newsletters page, not a latest circular feed.",
    "icici_pru": "AMC notices/addendums are not part of the broker-alert product scope.",
    "icsi": "Announcements/guidelines page, not a reliable circular stream.",
    "icra": "Corporate policy/ratings content, not circulars.",
    "lic": "Corporate press releases, not broker-relevant circular alerts.",
    "nafed": "Not a broker-relevant regulatory circular source for this product.",
    "nmce": "Dead/domain-sale property, not a live source.",
    "nse_indices": "Consultation/report pages, not a circular stream.",
    "pdai": "Primary dealers association feed is outside the current broker-alert scope.",
    "brokers_forum": "Industry association site is not an official regulatory circular source.",
    "investor_grievance": "Generic grievance site is not an official broker-regulatory alert source.",
    "nps_trust": "Pension/NPS trust circulars are optional customer-specific coverage, not core broker-alert scope.",
    "pfrda_circulars": "Pension circulars are optional customer-specific coverage, not core broker-alert scope.",
    "pfrda_master_circulars": "Pension master circulars are optional customer-specific coverage, not core broker-alert scope.",
    "sebi_saa": "Blocked SAT site, not a primary circular source.",
    "sebi_sme": "Filings stream, not a regulatory circular stream.",
    "stock_exchange_arbitration": "Informational/arbitration status pages, not a latest circular feed.",
    "itat": "Blocked tribunal site, not a circular feed.",
}
RESULT_STATUS_ORDER = ("working", "empty", "network_failed", "blocked", "browser_failed", "error")

BROKER_MUST_HAVE = {
    "sebi",
    "sebi_enforcement",
    "sebi_intermediaries",
    "sebi_broker_regulations",
    "sebi_broker_master_circulars",
    "nse",
    "nse_fo",
    "nse_clearing",
    "bse",
    "bse_fo",
    "bse_listing",
    "nse_listing",
    "ccil",
    "iccl",
    "cdsl",
    "nsdl",
    "nsdl_eservices",
    "rbi",
    "rbi_dbod",
    "rbi_fmrd",
    "fema",
    "cbdt",
    "cbic",
    "gst_council",
    "ckycr",
    "cersai",
    "scores",
}

BROKER_RECOMMENDED_ADDITIONS = [
    {
        "site_key": "fiu_ind",
        "priority": "high",
        "reason": "Core AML / suspicious transaction reporting obligations for regulated intermediaries.",
        "status_note": "Currently working and trusted in the general set; kept optional because it is order-heavy rather than a broad circular stream.",
    },
    {
        "site_key": "mca",
        "priority": "medium",
        "reason": "Company-law, beneficial ownership, and corporate compliance changes can affect regulated entities and group companies.",
        "status_note": "Already working in the general trusted set.",
    },
    {
        "site_key": "ministry_finance",
        "priority": "medium",
        "reason": "Department of Economic Affairs / Ministry-level policy orders can affect market infrastructure and financial-sector operations.",
        "status_note": "Already working in the general trusted set.",
    },
    {
        "site_key": "nism",
        "priority": "medium",
        "reason": "Certification, examination, and intermediary competency requirements matter for broker compliance operations.",
        "status_note": "Already working in the general trusted set.",
    },
    {
        "site_key": "amfi",
        "priority": "medium",
        "reason": "Relevant if the business distributes or advises on mutual funds.",
        "status_note": "Already working in the general trusted set.",
    },
    {
        "site_key": "pfrda_circulars",
        "priority": "conditional",
        "reason": "Relevant if the business handles pension distribution, CRA, POP, or retirement products.",
        "status_note": "Already working in the general trusted set.",
    },
    {
        "site_key": "pfrda_master_circulars",
        "priority": "conditional",
        "reason": "Relevant if the business handles pension distribution, CRA, POP, or retirement products.",
        "status_note": "Already working in the general trusted set.",
    },
    {
        "site_key": "irdai",
        "priority": "conditional",
        "reason": "Relevant if the business has insurance broking, distribution, or bancassurance exposure.",
        "status_note": "Already working in the general trusted set.",
    },
]


def load_module():
    spec = util.spec_from_file_location("main_v9", SRC_PATH)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clean_item(item: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not item:
        return None
    cleaned: Dict[str, Any] = {}
    for key, value in item.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key] = value
        elif isinstance(value, list):
            cleaned[key] = [
                element
                for element in value
                if isinstance(element, (str, int, float, bool)) or element is None
            ]
    return cleaned


def choose_latest(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return clean_item(items[0]) if items else None


def build_status_counts() -> Dict[str, int]:
    return {status: 0 for status in RESULT_STATUS_ORDER}


def looks_like_file_url(url: str) -> bool:
    lower = (url or "").lower()
    if any(hint in lower for hint in FILE_HINTS):
        return True
    return "download=true" in lower or "/download/" in lower or "downloadables/" in lower


def infer_candidate_file_url(item: Dict[str, Any]) -> Optional[str]:
    for key in ("candidate_file_url", "file_url", "pdf_url", "document_url", "attachment_url"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key in ("attachment_urls", "attachments", "files"):
        value = item.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, str) and entry.strip():
                    return entry.strip()
                if isinstance(entry, dict):
                    for nested_key in ("url", "link", "href"):
                        nested_value = entry.get(nested_key)
                        if isinstance(nested_value, str) and nested_value.strip():
                            return nested_value.strip()

    link = item.get("link") or item.get("url")
    if isinstance(link, str) and looks_like_file_url(link):
        return link.strip()
    return None


def canonicalize_probe_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    encoded_path = quote(parts.path, safe="/:%")
    return urlunsplit((parts.scheme, parts.netloc, encoded_path, parts.query, parts.fragment))


def probe_candidate_file(session: requests.Session, url: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"candidate_file_url": url}
    try:
        response = session.get(
            url,
            headers={"User-Agent": USER_AGENT, "Range": "bytes=0-2047"},
            timeout=45,
            allow_redirects=True,
            stream=True,
        )
        status_code = response.status_code
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        result["http_status"] = status_code
        if content_type:
            result["content_type"] = content_type

        if status_code in (200, 206) and (
            content_type in OK_FILE_TYPES
            or any(content_type.startswith(prefix) for prefix in ("application/", "image/"))
            and content_type not in HTML_CONTENT_TYPES
        ):
            result["probe_status"] = "file_ok"
        elif status_code in (200, 206) and content_type in HTML_CONTENT_TYPES:
            result["probe_status"] = "html_wrapper"
        else:
            result["probe_status"] = "fetch_failed"
        response.close()
    except Exception as exc:
        result["probe_status"] = "fetch_failed"
        result["error"] = str(exc)
    return result


def close_browser_tab(module: Any, profile: str, target_id: Optional[str]) -> None:
    if not target_id:
        return
    try:
        module.openclaw_browser_request("DELETE", f"/tabs/{target_id}", profile, timeout=15)
    except Exception:
        pass


def probe_candidate_file_via_browser(
    module: Any,
    site_key: str,
    site: Dict[str, Any],
    url: str,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "candidate_file_url": url,
        "probe_method": "browser",
    }
    canonical_url = canonicalize_probe_url(url)
    profile = module.get_openclaw_profile(site)
    warm_target: Optional[str] = None
    file_target: Optional[str] = None

    try:
        module.openclaw_browser_request("POST", "/start", profile, timeout=60)

        warm_urls = site.get("file_probe_warm_urls") or site.get("browser_urls") or site.get("urls") or []
        if warm_urls:
            warmed = module.openclaw_browser_request(
                "POST",
                "/tabs/open",
                profile,
                json_body={"url": warm_urls[0]},
                timeout=120,
            )
            warm_target = warmed.get("targetId")
            time.sleep(float(site.get("file_probe_warm_seconds", 4)))

        opened = module.openclaw_browser_request(
            "POST",
            "/tabs/open",
            profile,
            json_body={"url": url},
            timeout=120,
        )
        file_target = opened.get("targetId")

        matched_request: Optional[Dict[str, Any]] = None
        successful_request: Optional[Dict[str, Any]] = None
        deadline = time.time() + float(site.get("file_probe_browser_timeout_seconds", 15))
        while time.time() < deadline:
            request_log = module.openclaw_browser_request("GET", "/requests", profile, timeout=60)
            requests_list = request_log.get("requests", []) if isinstance(request_log, dict) else []
            for request_entry in reversed(requests_list):
                if not isinstance(request_entry, dict):
                    continue
                request_url = str(request_entry.get("url") or "")
                canonical_request_url = canonicalize_probe_url(request_url)
                if (
                    request_url == url
                    or request_url.startswith(url)
                    or canonical_request_url == canonical_url
                    or canonical_request_url.startswith(canonical_url)
                ):
                    matched_request = request_entry
                    if request_entry.get("status") in (200, 206):
                        successful_request = request_entry
                        break
            if successful_request:
                break
            time.sleep(1)

        if successful_request:
            matched_request = successful_request

        if matched_request:
            status_code = matched_request.get("status")
            if isinstance(status_code, int):
                result["http_status"] = status_code
            if matched_request.get("resourceType"):
                result["resource_type"] = matched_request["resourceType"]
            result["probe_status"] = "file_ok" if status_code in (200, 206) else "fetch_failed"
            if status_code is None:
                result["error"] = "Browser request matched but did not finish with an HTTP status."
        else:
            result["probe_status"] = "fetch_failed"
            result["error"] = "Browser request log did not capture the candidate file URL."
    except Exception as exc:
        result["probe_status"] = "fetch_failed"
        result["error"] = str(exc)
    finally:
        close_browser_tab(module, profile, file_target)
        close_browser_tab(module, profile, warm_target)

    return result


def build_pdf_probe_results(live_results: List[Dict[str, Any]], module: Optional[Any] = None) -> Dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    working = [entry for entry in live_results if entry["status"] == "working" and entry.get("latest_item")]
    output_results: List[Dict[str, Any]] = []

    for entry in working:
        latest_item = entry["latest_item"] or {}
        probe_entry: Dict[str, Any] = {
            "site_key": entry["site_key"],
            "title": latest_item.get("title", ""),
            "pub_date": latest_item.get("pub_date", "") or "",
            "latest_link": latest_item.get("link") or latest_item.get("url"),
        }
        candidate = infer_candidate_file_url(latest_item)
        if candidate:
            raw_probe = probe_candidate_file(session, candidate)
            probe_entry.update(raw_probe)
            site_config = ((getattr(module, "SITES", {}) or {}).get(entry["site_key"]) if module else None) or {}
            should_browser_probe = (
                raw_probe.get("probe_status") == "fetch_failed"
                and module is not None
                and bool(site_config.get("file_probe_via_browser"))
            )
            if should_browser_probe:
                browser_probe = probe_candidate_file_via_browser(module, entry["site_key"], site_config, candidate)
                probe_entry["raw_probe_status"] = raw_probe.get("probe_status")
                if "http_status" in raw_probe:
                    probe_entry["raw_http_status"] = raw_probe["http_status"]
                if raw_probe.get("error"):
                    probe_entry["raw_error"] = raw_probe["error"]
                probe_entry.update(browser_probe)
        else:
            probe_entry["candidate_file_url"] = None
            probe_entry["probe_status"] = "no_direct_file"
        output_results.append(probe_entry)

    return {
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "working_sources": len(working),
        "results": output_results,
    }


def classify_sources(
    live_results: List[Dict[str, Any]]
) -> Tuple[List[str], List[str], List[str], List[str], List[str], List[str], List[str]]:
    working_keys = [entry["site_key"] for entry in live_results if entry["status"] == "working"]
    empty_keys = [entry["site_key"] for entry in live_results if entry["status"] == "empty"]
    network_failed = [entry["site_key"] for entry in live_results if entry["status"] == "network_failed"]
    blocked = [entry["site_key"] for entry in live_results if entry["status"] == "blocked"]
    browser_failed = [entry["site_key"] for entry in live_results if entry["status"] == "browser_failed"]

    trusted = sorted(key for key in working_keys if key in BASE_TRUSTED)
    noisy = sorted(key for key in working_keys if key in BASE_NOISY)
    unreviewed = sorted(key for key in working_keys if key not in BASE_TRUSTED and key not in BASE_NOISY)
    empty = sorted(empty_keys)
    return (
        trusted,
        noisy,
        unreviewed,
        empty,
        sorted(network_failed),
        sorted(blocked),
        sorted(browser_failed),
    )


def assess_run_health(live_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    baseline = sorted(BASE_TRUSTED)
    by_key = {entry["site_key"]: entry["status"] for entry in live_results}
    network_failed = sorted(site for site in baseline if by_key.get(site) == "network_failed")
    browser_failed = sorted(site for site in baseline if by_key.get(site) == "browser_failed")
    blocked = sorted(site for site in baseline if by_key.get(site) == "blocked")
    degraded_failures = network_failed + browser_failed
    threshold = max(5, len(baseline) // 6)
    return {
        "state": "degraded" if len(degraded_failures) >= threshold else "normal",
        "trusted_baseline_size": len(baseline),
        "network_failed_trusted": network_failed,
        "browser_failed_trusted": browser_failed,
        "blocked_trusted": blocked,
        "threshold": threshold,
    }


def build_pdf_results_by_site(pdf_results: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        entry["site_key"]: entry
        for entry in pdf_results.get("results", [])
        if isinstance(entry, dict) and entry.get("site_key")
    }


def classify_broker_profile(
    live_results: List[Dict[str, Any]],
    pdf_results: Dict[str, Any],
) -> Dict[str, Any]:
    by_key = {entry["site_key"]: entry for entry in live_results}
    pdf_by_site = build_pdf_results_by_site(pdf_results)

    working: List[str] = []
    empty: List[str] = []
    network_failed: List[str] = []
    blocked: List[str] = []
    browser_failed: List[str] = []
    error: List[str] = []
    missing: List[str] = []
    file_ok: List[str] = []
    no_direct_file: List[str] = []
    html_wrapper: List[str] = []
    fetch_failed: List[str] = []

    for site_key in sorted(BROKER_MUST_HAVE):
        entry = by_key.get(site_key)
        if not entry:
            missing.append(site_key)
            continue

        status = entry.get("status")
        if status == "working":
            working.append(site_key)
            probe = pdf_by_site.get(site_key, {})
            probe_status = probe.get("probe_status")
            if probe_status == "file_ok":
                file_ok.append(site_key)
            elif probe_status == "no_direct_file":
                no_direct_file.append(site_key)
            elif probe_status == "html_wrapper":
                html_wrapper.append(site_key)
            elif probe_status == "fetch_failed":
                fetch_failed.append(site_key)
        elif status == "empty":
            empty.append(site_key)
        elif status == "network_failed":
            network_failed.append(site_key)
        elif status == "blocked":
            blocked.append(site_key)
        elif status == "browser_failed":
            browser_failed.append(site_key)
        else:
            error.append(site_key)

    return {
        "must_have_total": len(BROKER_MUST_HAVE),
        "working": working,
        "empty": empty,
        "network_failed": network_failed,
        "blocked": blocked,
        "browser_failed": browser_failed,
        "error": error,
        "missing": missing,
        "file_ok": file_ok,
        "no_direct_file": no_direct_file,
        "html_wrapper": html_wrapper,
        "fetch_failed": fetch_failed,
    }


def build_broker_profile_markdown(
    tested_at: str,
    broker_profile: Dict[str, Any],
) -> str:
    lines = [
        "# Broker Must-Have Coverage",
        "",
        f"Date: {datetime.now().strftime('%B %d, %Y')}",
        "Module tested: `src/main-v9-broker-enhanced.py`",
        f"Latest artifact time: `{tested_at}`",
        "",
        "This report focuses on the high-value source set for a broker / financial-services compliance team that needs to follow the latest circulars across regulators, exchanges, depositories, tax, KYC/AML, grievances, and market infrastructure.",
        "",
        "## Coverage summary",
        "",
        f"- `must-have sources`: `{broker_profile['must_have_total']}`",
        f"- `working`: `{len(broker_profile['working'])}`",
        f"- `empty`: `{len(broker_profile['empty'])}`",
        f"- `network_failed`: `{len(broker_profile['network_failed'])}`",
        f"- `blocked`: `{len(broker_profile['blocked'])}`",
        f"- `browser_failed`: `{len(broker_profile['browser_failed'])}`",
        f"- `error`: `{len(broker_profile['error'])}`",
        "",
        "## Working now",
        "",
    ]
    lines.extend(f"- `{site}`" for site in broker_profile["working"])

    for section_title, key in [
        ("Empty now", "empty"),
        ("Network failed now", "network_failed"),
        ("Blocked now", "blocked"),
        ("Browser failed now", "browser_failed"),
        ("Error now", "error"),
        ("Missing from artifact", "missing"),
    ]:
        values = broker_profile[key]
        if values:
            lines.extend(["", f"## {section_title}", ""])
            lines.extend(f"- `{site}`" for site in values)

    lines.extend(
        [
            "",
            "## Latest-file access on working must-have sources",
            "",
            f"- `file_ok`: `{len(broker_profile['file_ok'])}`",
            f"- `no_direct_file`: `{len(broker_profile['no_direct_file'])}`",
            f"- `html_wrapper`: `{len(broker_profile['html_wrapper'])}`",
            f"- `fetch_failed`: `{len(broker_profile['fetch_failed'])}`",
            "",
        ]
    )

    for section_title, key in [
        ("Direct file works", "file_ok"),
        ("No direct file on latest item", "no_direct_file"),
        ("HTML wrapper on latest link", "html_wrapper"),
        ("Latest-file fetch failed", "fetch_failed"),
    ]:
        values = broker_profile[key]
        if values:
            lines.extend([f"### {section_title}", ""])
            lines.extend(f"- `{site}`" for site in values)
            lines.append("")

    lines.extend(
        [
            "## Additional sources to consider",
            "",
            "These are not part of the strict broker must-have set for every firm, but they are worth adding when the business lines require them.",
            "",
        ]
    )
    for item in BROKER_RECOMMENDED_ADDITIONS:
        lines.append(
            f"- `{item['site_key']}` [{item['priority']}]: {item['reason']} {item['status_note']}"
        )

    return "\n".join(lines) + "\n"


def build_live_verification_markdown(
    tested_at: str,
    configured_sources: int,
    status_counts: Dict[str, int],
    trusted: List[str],
    noisy: List[str],
    unreviewed: List[str],
    empty: List[str],
    network_failed: List[str],
    blocked: List[str],
    browser_failed: List[str],
    pdf_results: Dict[str, Any],
    run_health: Dict[str, Any],
) -> str:
    probe_counts = {
        "file_ok": 0,
        "html_wrapper": 0,
        "no_direct_file": 0,
        "fetch_failed": 0,
    }
    failed_sites: List[str] = []
    html_wrapper_sites: List[str] = []

    for entry in pdf_results["results"]:
        status = entry.get("probe_status", "fetch_failed")
        probe_counts[status] = probe_counts.get(status, 0) + 1
        if status == "fetch_failed":
            failed_sites.append(entry["site_key"])
        elif status == "html_wrapper":
            html_wrapper_sites.append(entry["site_key"])

    active_scope_size = configured_sources - len(EXCLUDED_FROM_ACTIVE_SCOPE)
    excluded_by_status = {
        "working": sorted(site for site in trusted + noisy if site in EXCLUDED_FROM_ACTIVE_SCOPE),
        "empty": sorted(site for site in empty if site in EXCLUDED_FROM_ACTIVE_SCOPE),
        "network_failed": sorted(site for site in network_failed if site in EXCLUDED_FROM_ACTIVE_SCOPE),
        "blocked": sorted(site for site in blocked if site in EXCLUDED_FROM_ACTIVE_SCOPE),
        "browser_failed": sorted(site for site in browser_failed if site in EXCLUDED_FROM_ACTIVE_SCOPE),
    }
    active_empty = [site for site in empty if site not in EXCLUDED_FROM_ACTIVE_SCOPE]
    active_network_failed = [site for site in network_failed if site not in EXCLUDED_FROM_ACTIVE_SCOPE]
    active_blocked = [site for site in blocked if site not in EXCLUDED_FROM_ACTIVE_SCOPE]
    active_browser_failed = [site for site in browser_failed if site not in EXCLUDED_FROM_ACTIVE_SCOPE]

    lines = [
        "# Live Verification Snapshot",
        "",
        f"Date: {datetime.now().strftime('%B %d, %Y')}",
        "Module tested: `src/main-v9-broker-enhanced.py`",
        f"Latest-only artifact time: `{tested_at}`",
        f"Configured sources: `{configured_sources}`",
        f"Active product-facing review scope: `{active_scope_size}`",
        f"Explicitly excluded from active scope: `{len(EXCLUDED_FROM_ACTIVE_SCOPE)}`",
        "",
        "Artifacts:",
        "",
        "- `live_scrape_results_latest_v8.json`: latest item snapshot for every configured source after the latest full rerun",
        "- `latest_pdf_fetch_results_v6.json`: direct-file probe for the latest item on every working source",
        "",
        "## Current status",
        "",
        f"- `{status_counts['working']}` sources returned at least one item.",
        f"- `{status_counts['empty']}` sources returned zero items.",
        f"- `{status_counts['network_failed']}` sources failed because of transport/DNS/timeout issues.",
        f"- `{status_counts['blocked']}` sources were blocked by upstream access controls.",
        f"- `{status_counts['browser_failed']}` sources failed at the browser-control layer.",
        f"- `{status_counts['error']}` sources crashed with scraper exceptions.",
        "",
        "## Verified reliable latest-item sources",
        "",
        "These sources returned a latest item that looks like an actual circular, order, notice, guideline, operational memo, or comparable regulatory update.",
        "",
        f"Count: `{len(trusted)}`",
        "",
    ]
    if run_health.get("state") == "degraded":
        lines.extend(
            [
                "Run health: `degraded`",
                "",
                "This rerun should not be treated as a normal scraper-quality snapshot because too many previously trusted sources failed on transport or browser-control issues.",
                "",
            ]
        )
    lines.extend(f"- `{site}`" for site in trusted)

    lines.extend(
        [
            "",
            "## Working but not safe to trust as latest circular data",
            "",
            "These sources returned items, but the latest item still looks like marketing, static policy collateral, a disclosure page, a section landing page, an undated card, or otherwise ambiguous/non-circular content.",
            "",
            f"Count: `{len(noisy)}`",
            "",
        ]
    )
    lines.extend(f"- `{site}`" for site in noisy)

    if unreviewed:
        lines.extend(
            [
                "",
                "## Working but not yet manually reclassified in this snapshot",
                "",
                "These sources returned items in the rerun, but they were not in the prior trusted/noisy review buckets. Treat them as unreviewed until manually checked.",
                "",
                f"Count: `{len(unreviewed)}`",
                "",
            ]
        )
        lines.extend(f"- `{site}`" for site in unreviewed)

    lines.extend(["", "## Truly empty in the active review scope", ""])
    lines.extend(f"- `{site}`" for site in active_empty)

    if active_network_failed:
        lines.extend(["", "## Network failed in the active review scope", ""])
        lines.extend(f"- `{site}`" for site in active_network_failed)

    if active_blocked:
        lines.extend(["", "## Blocked in the active review scope", ""])
        lines.extend(f"- `{site}`" for site in active_blocked)

    if active_browser_failed:
        lines.extend(["", "## Browser failed in the active review scope", ""])
        lines.extend(f"- `{site}`" for site in active_browser_failed)

    excluded_sites = sorted(EXCLUDED_FROM_ACTIVE_SCOPE)
    if excluded_sites:
        lines.extend(
            [
                "",
                "## Explicitly excluded from the active product-facing scope",
                "",
                "These sources are intentionally not part of the broker product backlog because they are dead, blocked, wrong-contract, or otherwise not a real latest-circular source for this SaaS.",
                "",
            ]
        )
        for site in excluded_sites:
            current_status = "not_seen"
            if site in excluded_by_status["working"]:
                current_status = "working"
            elif site in excluded_by_status["empty"]:
                current_status = "empty"
            elif site in excluded_by_status["network_failed"]:
                current_status = "network_failed"
            elif site in excluded_by_status["blocked"]:
                current_status = "blocked"
            elif site in excluded_by_status["browser_failed"]:
                current_status = "browser_failed"
            lines.append(f"- `{site}`: {EXCLUDED_FROM_ACTIVE_SCOPE[site]} Current rerun status: `{current_status}`.")

    lines.extend(
        [
            "",
            "## Direct-file probe",
            "",
            "Working-source latest-item file probe summary from `latest_pdf_fetch_results_v6.json`:",
            "",
            f"- `{probe_counts.get('file_ok', 0)}` latest items exposed a directly fetchable file and returned PDF/Excel/binary content.",
            f"- `{probe_counts.get('html_wrapper', 0)}` latest links returned an HTML wrapper instead of the file payload.",
            f"- `{probe_counts.get('no_direct_file', 0)}` working sources did not expose a direct file on their latest item.",
            f"- `{probe_counts.get('fetch_failed', 0)}` latest-file probes failed outright.",
            "",
        ]
    )

    if failed_sites:
        lines.extend(["Latest-file probe failures:", ""])
        lines.extend(f"- `{site}`" for site in sorted(failed_sites))
        lines.append("")

    if html_wrapper_sites:
        lines.extend(["HTML-wrapper responses on latest-file probes:", ""])
        lines.extend(f"- `{site}`" for site in sorted(html_wrapper_sites))
        lines.append("")

    promoted = [site for site in ("cersai", "dipp") if site in trusted]
    lines.extend(
        [
            "## Interpretation",
            "",
            '- "Working" means the scraper extracted at least one item.',
            '- "Verified reliable" means the latest item also looked like the right kind of latest regulatory/update data.',
            '- "Network failed", "blocked", and "browser failed" are operational failure buckets and should not be conflated with genuine empty sources.',
            '- "Excluded from active product-facing scope" means the source is intentionally not part of the broker-alert backlog even if it still exists in the wider research/scraper config.',
        ]
    )

    if promoted:
        promoted_text = ", ".join(f"`{site}`" for site in promoted)
        lines.append(f"- This snapshot reuses the established trusted/noisy review buckets and includes {promoted_text} in the trusted set based on the browser-backed parsers and focused live checks.")

    if unreviewed:
        lines.append('- Any "not yet manually reclassified" source should be treated as untrusted until reviewed.')

    return "\n".join(lines) + "\n"


async def run_full_scrape() -> Dict[str, Any]:
    module = load_module()
    tested_at = datetime.now(timezone.utc).isoformat()
    results: List[Dict[str, Any]] = []
    status_counts = build_status_counts()

    for index, (site_key, site) in enumerate(module.SITES.items(), start=1):
        print(f"[{index:02d}/{len(module.SITES):02d}] {site_key} ...", flush=True)
        try:
            items, stats = await module.scrape_site(site_key, site)
            latest_item = choose_latest(items)
            classification = module.classify_scrape_result(items, stats)
            status = classification["result_status"]
            stats["result_status"] = status
            if classification.get("failure_category"):
                stats["failure_category"] = classification["failure_category"]
            if classification.get("failure_reason"):
                stats["failure_reason"] = classification["failure_reason"]
            status_counts[status] += 1
            results.append(
                {
                    "site_key": site_key,
                    "site_name": site["name"],
                    "status": status,
                    "items_found": len(items),
                    "stats": stats,
                    "latest_item": latest_item,
                }
            )
            print(f"    -> {status} ({len(items)} items)", flush=True)
        except Exception as exc:
            status_counts["error"] += 1
            results.append(
                {
                    "site_key": site_key,
                    "site_name": site["name"],
                    "status": "error",
                    "items_found": 0,
                    "stats": {"status": "error", "errors": [str(exc)]},
                    "latest_item": None,
                }
            )
            print(f"    -> error ({exc})", flush=True)

    run_health = assess_run_health(results)
    live_payload = {
        "tested_at": tested_at,
        "configured_sources": len(module.SITES),
        "status_counts": status_counts,
        "run_health": run_health,
        "results": results,
    }
    LIVE_RESULTS_PATH.write_text(json.dumps(live_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    pdf_payload = build_pdf_probe_results(results, module=module)
    PDF_RESULTS_PATH.write_text(json.dumps(pdf_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    trusted, noisy, unreviewed, empty, network_failed, blocked, browser_failed = classify_sources(results)
    verification_md = build_live_verification_markdown(
        tested_at=tested_at,
        configured_sources=len(module.SITES),
        status_counts=status_counts,
        trusted=trusted,
        noisy=noisy,
        unreviewed=unreviewed,
        empty=empty,
        network_failed=network_failed,
        blocked=blocked,
        browser_failed=browser_failed,
        pdf_results=pdf_payload,
        run_health=run_health,
    )
    VERIFICATION_PATH.write_text(verification_md, encoding="utf-8")

    broker_profile = classify_broker_profile(results, pdf_payload)
    broker_payload = {
        "tested_at": tested_at,
        "must_have_sources": sorted(BROKER_MUST_HAVE),
        "profile": broker_profile,
        "recommended_additions": BROKER_RECOMMENDED_ADDITIONS,
    }
    BROKER_JSON_PATH.write_text(json.dumps(broker_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    BROKER_REPORT_PATH.write_text(
        build_broker_profile_markdown(tested_at=tested_at, broker_profile=broker_profile),
        encoding="utf-8",
    )

    summary = {
        "live_results_path": str(LIVE_RESULTS_PATH),
        "pdf_results_path": str(PDF_RESULTS_PATH),
        "verification_path": str(VERIFICATION_PATH),
        "broker_report_path": str(BROKER_REPORT_PATH),
        "broker_json_path": str(BROKER_JSON_PATH),
        "status_counts": status_counts,
        "run_health": run_health,
        "trusted_count": len(trusted),
        "noisy_count": len(noisy),
        "unreviewed_count": len(unreviewed),
        "empty_count": len(empty),
        "broker_must_have_working": len(broker_profile["working"]),
        "broker_must_have_total": broker_profile["must_have_total"],
    }
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    os.chdir(ROOT)
    asyncio.run(run_full_scrape())
