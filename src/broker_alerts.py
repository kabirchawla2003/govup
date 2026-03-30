"""
Broker alerts profile, contracts, and event normalization for the SaaS API.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
LIVE_RESULTS_PATH = ROOT / "live_scrape_results_latest_v8.json"
PDF_RESULTS_PATH = ROOT / "latest_pdf_fetch_results_v6.json"

BROKER_ALERTS_PROFILE_KEY = "broker_alerts_v1"
BROKER_ALERTS_PROFILE_VERSION = "2026-03-13"

BROKER_CORE_SOURCES = [
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
]

BROKER_OPTIONAL_SOURCES = [
    "fiu_ind",
    "fiu_ind_guidance",
    "uidai_authentication_docs",
    "mse",
    "mca",
    "ministry_finance",
    "nism",
    "amfi",
    "pfrda_circulars",
    "pfrda_master_circulars",
    "irdai",
]

BROKER_EXCLUDED_SOURCES: Dict[str, str] = {
    "ace": "Agricultural commodities exchange site is not part of the broker-alert product scope.",
    "anmi": "Association calendar page, not a broker-facing latest circular stream.",
    "asba": "Wrong site entirely; resolves to an unrelated badminton association.",
    "bcsbi": "Banking customer-service standards body is outside the broker-alert product scope.",
    "bse_indices": "Index/history pages, not a broker-relevant circular feed.",
    "cag": "Access-denied public page, not a usable live circular source.",
    "care": "Public site does not expose a reliable regulatory circular feed.",
    "cibil": "Public pages are policy/disclosure collateral, not a latest circular stream.",
    "cdslindia": "CVL downloads library, not a dated latest circular feed.",
    "crisil": "Public target resolves to press/login content, not a circular source.",
    "equifax": "Static policy collateral, not a latest circular stream.",
    "experian": "Static policy collateral, not a latest circular stream.",
    "exim_bank": "Public declarations/disclosures and tenders are outside the broker-alert circular scope.",
    "gic_re": "Policies/newsletters page, not a latest circular feed.",
    "icici_pru": "AMC notices/addendums are not part of the broker-alert product scope.",
    "icsi": "Guidelines and announcements, not a reliable circular stream for this product.",
    "icra": "Corporate policy/ratings content, not circulars.",
    "lic": "Corporate press releases, not broker-relevant circular alerts.",
    "nafed": "Not a broker-relevant regulatory circular source for this product.",
    "nmce": "Dead/domain-sale property, not a live source.",
    "nse_indices": "Consultation/report pages, not a broker circular stream.",
    "pdai": "Primary dealers association feed is not part of the current broker-alert scope.",
    "brokers_forum": "Industry association site is not an official regulatory circular source.",
    "investor_grievance": "Generic grievance site is not an official broker-regulatory alert source.",
    "nps_trust": "Pension/NPS trust circulars are customer-specific optional coverage, not core broker-alert scope.",
    "pfrda_circulars": "Pension circulars are customer-specific optional coverage, not core broker-alert scope.",
    "pfrda_master_circulars": "Pension master circulars are customer-specific optional coverage, not core broker-alert scope.",
    "sebi_saa": "SAT site is blocked and not a core circular stream.",
    "sebi_sme": "Filings stream, not a regulatory circular stream.",
    "stock_exchange_arbitration": "Informational/arbitration status pages, not a latest circular feed.",
    "itat": "Tribunal site is blocked and not a circular feed.",
}

SOURCE_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "sebi": {"group": "regulator", "contract": "circulars_orders_notices", "required": True},
    "sebi_enforcement": {"group": "regulator", "contract": "enforcement_orders", "required": True},
    "sebi_intermediaries": {"group": "regulator", "contract": "intermediary_circulars", "required": True},
    "sebi_broker_regulations": {"group": "regulator", "contract": "broker_relevant_regulations", "required": True},
    "sebi_broker_master_circulars": {"group": "regulator", "contract": "broker_master_circulars", "required": True},
    "nse": {"group": "exchange", "contract": "member_circulars", "required": True},
    "nse_fo": {"group": "exchange", "contract": "derivatives_circulars", "required": True},
    "nse_clearing": {"group": "market_infra", "contract": "clearing_circulars", "required": True},
    "bse": {"group": "exchange", "contract": "member_notices", "required": True},
    "bse_fo": {"group": "exchange", "contract": "derivatives_notices", "required": True},
    "bse_listing": {"group": "exchange", "contract": "listing_circulars", "required": True},
    "nse_listing": {"group": "exchange", "contract": "listing_circulars", "required": True},
    "ccil": {"group": "market_infra", "contract": "operational_notifications", "required": True},
    "iccl": {"group": "market_infra", "contract": "clearing_notices", "required": True},
    "cdsl": {"group": "depository", "contract": "depository_communiques", "required": True},
    "nsdl": {"group": "depository", "contract": "issuer_rta_circulars", "required": True},
    "nsdl_eservices": {"group": "depository", "contract": "dp_circulars", "required": True},
    "rbi": {"group": "regulator", "contract": "notifications_press_releases", "required": True},
    "rbi_dbod": {"group": "regulator", "contract": "banking_notifications", "required": True},
    "rbi_fmrd": {"group": "regulator", "contract": "market_notifications", "required": True},
    "fema": {"group": "regulator", "contract": "fema_notifications", "required": True},
    "cbdt": {"group": "tax", "contract": "tax_circulars_notifications", "required": True},
    "cbic": {"group": "tax", "contract": "tax_circulars_notifications", "required": True},
    "gst_council": {"group": "tax", "contract": "gst_circulars", "required": True},
    "ckycr": {"group": "kyc_aml", "contract": "kyc_notifications", "required": True},
    "cersai": {"group": "kyc_aml", "contract": "registry_notifications", "required": True},
    "scores": {"group": "grievance", "contract": "grievance_circulars", "required": True},
    "fiu_ind": {"group": "kyc_aml", "contract": "compliance_orders", "required": False},
    "fiu_ind_guidance": {"group": "kyc_aml", "contract": "guidance_and_registration_circulars", "required": False},
    "uidai_authentication_docs": {"group": "kyc_aml", "contract": "aadhaar_authentication_documents", "required": False},
    "mse": {"group": "exchange", "contract": "member_circulars", "required": False},
    "mca": {"group": "government", "contract": "company_law_updates", "required": False},
    "ministry_finance": {"group": "government", "contract": "policy_orders", "required": False},
    "nism": {"group": "operations", "contract": "certification_updates", "required": False},
    "amfi": {"group": "distribution", "contract": "mutual_fund_circulars", "required": False},
    "pfrda_circulars": {"group": "distribution", "contract": "pension_circulars", "required": False},
    "pfrda_master_circulars": {"group": "distribution", "contract": "pension_master_circulars", "required": False},
    "irdai": {"group": "distribution", "contract": "insurance_circulars", "required": False},
}

CONFIDENCE_RANK = {"degraded": 0, "likely": 1, "verified": 2}
DIRECT_FILE_HINTS = (".pdf", ".zip", ".xls", ".xlsx", ".csv", ".doc", ".docx", ".ppt", ".pptx")
GROUP_PRIORITY = {
    "regulator": 60,
    "tax": 55,
    "kyc_aml": 50,
    "grievance": 45,
    "exchange": 40,
    "market_infra": 35,
    "depository": 30,
    "government": 25,
    "operations": 20,
    "distribution": 15,
}
SOURCE_PRIORITY_OVERRIDES = {
    "sebi_broker_regulations": 12,
    "sebi_broker_master_circulars": 11,
    "sebi": 10,
    "rbi": 9,
    "rbi_dbod": 8,
    "rbi_fmrd": 8,
    "fema": 7,
    "cbdt": 7,
    "cbic": 7,
    "fiu_ind": 7,
    "gst_council": 6,
    "nse": 5,
    "bse": 5,
    "nse_clearing": 4,
    "iccl": 4,
    "ccil": 4,
    "nsdl": 3,
    "nsdl_eservices": 3,
    "cdsl": 3,
}
FILE_PROBE_PRIORITY = {
    "file_ok": 3,
    "no_direct_file": 2,
    "html_wrapper": 1,
    "fetch_failed": 0,
    None: 0,
}


def get_broker_profile_definition() -> Dict[str, Any]:
    sources = []
    for site_key in BROKER_CORE_SOURCES + BROKER_OPTIONAL_SOURCES:
        contract = SOURCE_CONTRACTS.get(site_key, {})
        sources.append(
            {
                "site_key": site_key,
                "group": contract.get("group", "regulatory"),
                "contract": contract.get("contract", "latest_updates"),
                "required": bool(contract.get("required")),
            }
        )

    return {
        "profile_key": BROKER_ALERTS_PROFILE_KEY,
        "profile_version": BROKER_ALERTS_PROFILE_VERSION,
        "name": "Broker Alerts v1",
        "description": "Broker-focused event stream for Indian market-regulatory updates and operational circulars.",
        "core_sources": list(BROKER_CORE_SOURCES),
        "optional_sources": list(BROKER_OPTIONAL_SOURCES),
        "excluded_sources": [
            {"site_key": site_key, "reason": reason}
            for site_key, reason in sorted(BROKER_EXCLUDED_SOURCES.items())
        ],
        "sources": sources,
    }


@lru_cache(maxsize=4)
def load_json_artifact(path_value: str) -> Dict[str, Any]:
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize_date_value(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None

    raw = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", raw, flags=re.IGNORECASE)
    raw = re.sub(r"([A-Za-z])(\d)", r"\1 \2", raw)
    raw = re.sub(r"\s+,", ",", raw)
    raw = re.sub(r",\s*", ", ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d-%B-%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%d %B, %Y",
        "%d %b, %Y",
        "%B, %Y",
        "%B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue

    compact = re.search(r"(20\d{2})[-_/]?(\d{2})[-_/]?(\d{2})", raw)
    if compact:
        try:
            return datetime(int(compact.group(1)), int(compact.group(2)), int(compact.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def normalize_event_url(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    path = parsed.path.rstrip("/") or parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query, ""))


def looks_like_direct_file(url: Optional[str]) -> bool:
    parsed = urlsplit(url or "")
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in DIRECT_FILE_HINTS)


def normalize_tags(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
    return [item.strip() for item in text.split(",") if item.strip()]


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalize_text(value).lower()).strip()


def looks_like_reference_segment(value: str) -> bool:
    text = normalize_text(value).lower()
    if not text:
        return False
    return bool(
        re.search(r"\d{2,}", text)
        or "/" in text
        or re.search(r"\b(?:ref|circular|notice|notification|order|nse|bse|sebi|nsdl|cdsl|rbi)\b", text)
    )


def normalize_title_for_grouping(title: str) -> str:
    text = normalize_text(title)
    if " | " in text:
        left, right = [part.strip() for part in text.split("|", 1)]
        if looks_like_reference_segment(left):
            text = right
    text = re.sub(
        r"^(?:circular|notification|notice|order)\s*(?:no\.?|number)?\s*[:\-]?\s*[A-Za-z0-9/().-]{2,}\s*[:\-]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^(?:subject|sub|re)\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:copy of)\s+", "", text, flags=re.IGNORECASE)
    return normalize_text_key(text)


def normalize_reference_token(value: Any) -> Optional[str]:
    text = normalize_text(value)
    if not text:
        return None
    text = text.replace("No.", " ").replace("No", " ")
    text = re.sub(r"[^A-Za-z0-9/().-]+", "", text)
    return text.lower() or None


def extract_reference_token(reference_number: Any, title: str) -> Optional[str]:
    explicit = normalize_reference_token(reference_number)
    if explicit:
        return explicit

    title_text = normalize_text(title)
    patterns = [
        r"\b(?:order|notification|circular|guideline|guidelines)\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Za-z0-9/().-]{3,})",
        r"\b([A-Z]{2,}(?:/[A-Z0-9().-]+){1,})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, title_text, flags=re.IGNORECASE)
        if match:
            token = normalize_reference_token(match.group(1))
            if token:
                return token
    return None


def stable_content_fingerprint(title: str, published_date: str) -> str:
    title_key = normalize_title_for_grouping(title)
    digest = hashlib.sha256(f"{published_date}|{title_key}".encode("utf-8")).hexdigest()
    return digest[:20]


def build_event_dedupe_key(site_key: str, published_date: str, canonical_url: str, title: str) -> str:
    title_key = normalize_text_key(title)
    return f"{site_key}|{published_date}|{canonical_url}|{title_key}"


def build_event_id(dedupe_key: str) -> str:
    digest = hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()
    return f"evt_{digest[:24]}"


def build_cross_source_key(
    published_date: str,
    title: str,
    reference_token: Optional[str],
) -> str:
    title_key = normalize_title_for_grouping(title)
    reference_key = reference_token or ""
    return f"{published_date}|{reference_key}|{title_key}"


def infer_delivery_state(status: str) -> str:
    if status == "working":
        return "healthy"
    if status in {"network_failed", "browser_failed"}:
        return "degraded"
    if status == "blocked":
        return "blocked"
    if status == "empty":
        return "down"
    return "unknown"


def build_source_health_map() -> Dict[str, Dict[str, Any]]:
    live_payload = load_json_artifact(str(LIVE_RESULTS_PATH))
    pdf_payload = load_json_artifact(str(PDF_RESULTS_PATH))
    pdf_by_site = {
        str(entry.get("site_key")): entry
        for entry in (pdf_payload.get("results") or [])
        if isinstance(entry, dict) and entry.get("site_key")
    }

    health_map: Dict[str, Dict[str, Any]] = {}
    for entry in live_payload.get("results") or []:
        if not isinstance(entry, dict) or not entry.get("site_key"):
            continue
        site_key = str(entry["site_key"])
        stats = entry.get("stats") if isinstance(entry.get("stats"), dict) else {}
        validation = stats.get("validation") if isinstance(stats.get("validation"), dict) else {}
        latest_item = entry.get("latest_item") if isinstance(entry.get("latest_item"), dict) else {}
        pdf_entry = pdf_by_site.get(site_key, {})
        health_map[site_key] = {
            "site_key": site_key,
            "status": entry.get("status", "unknown"),
            "delivery_state": infer_delivery_state(str(entry.get("status", "unknown"))),
            "coverage_status": stats.get("coverage_status") or validation.get("coverage_status") or "unknown",
            "failure_reason": stats.get("failure_reason"),
            "tested_at": live_payload.get("tested_at") or pdf_payload.get("tested_at"),
            "latest_title": latest_item.get("title"),
            "latest_pub_date": latest_item.get("pub_date"),
            "latest_link": latest_item.get("link"),
            "file_probe_status": pdf_entry.get("probe_status"),
            "candidate_file_url": pdf_entry.get("candidate_file_url"),
            "http_status": pdf_entry.get("http_status"),
            "content_type": pdf_entry.get("content_type"),
        }

    for site_key in BROKER_CORE_SOURCES + BROKER_OPTIONAL_SOURCES:
        health_map.setdefault(
            site_key,
            {
                "site_key": site_key,
                "status": "missing",
                "delivery_state": "unknown",
                "coverage_status": "unknown",
                "failure_reason": "No live verification artifact entry found.",
                "tested_at": live_payload.get("tested_at") or pdf_payload.get("tested_at"),
                "latest_title": None,
                "latest_pub_date": None,
                "latest_link": None,
                "file_probe_status": None,
                "candidate_file_url": None,
                "http_status": None,
                "content_type": None,
            },
        )

    return health_map


def resolve_confidence(site_key: str, published_date: Optional[str], canonical_url: Optional[str], health: Dict[str, Any]) -> str:
    if not published_date or not canonical_url:
        return "degraded"
    if health.get("status") == "working" and health.get("delivery_state") == "healthy":
        return "verified"
    if health.get("status") == "working":
        return "likely"
    return "degraded"


def event_source_priority(event: Dict[str, Any]) -> int:
    site_key = str(event.get("source_key") or "")
    group = str(event.get("source_group") or "")
    return (
        (100 if event.get("source_required") else 0)
        + GROUP_PRIORITY.get(group, 0)
        + SOURCE_PRIORITY_OVERRIDES.get(site_key, 0)
    )


def event_preference_key(event: Dict[str, Any]) -> tuple:
    return (
        CONFIDENCE_RANK.get(str(event.get("confidence") or "degraded"), 0),
        event_source_priority(event),
        FILE_PROBE_PRIORITY.get(event.get("file_probe_status"), 0),
        1 if event.get("direct_file_url") else 0,
        event.get("published_at") or "",
        event.get("discovered_at") or "",
        event.get("source_key") or "",
    )


def serialize_mirror_source(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_key": event.get("source_key"),
        "source_group": event.get("source_group"),
        "source_contract": event.get("source_contract"),
        "confidence": event.get("confidence"),
        "canonical_url": event.get("canonical_url"),
        "direct_file_url": event.get("direct_file_url"),
        "file_probe_status": event.get("file_probe_status"),
        "published_date": event.get("published_date"),
        "reference_number": event.get("reference_number"),
        "source_event_id": event.get("source_event_id"),
    }


def build_broker_event(row: Dict[str, Any], health_map: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    site_key = str(row.get("site_key") or row.get("site") or "").strip()
    if site_key not in SOURCE_CONTRACTS:
        return None

    health_map = health_map or build_source_health_map()
    health = health_map.get(site_key, {})
    contract = SOURCE_CONTRACTS.get(site_key, {})

    title = normalize_text(row.get("title"))
    canonical_url = normalize_event_url(row.get("url"))
    if not title or not canonical_url:
        return None

    published_date = (
        normalize_date_value(row.get("date"))
        or normalize_date_value(row.get("published_at"))
        or normalize_date_value(row.get("effective_date"))
    )
    published_at = f"{published_date}T00:00:00+00:00" if published_date else None
    reference_number = normalize_text(row.get("reference_number")) or None
    reference_token = extract_reference_token(reference_number, title)

    discovered_at = normalize_text(row.get("fetched_at") or row.get("updated_at") or row.get("created_at"))
    if discovered_at and "T" not in discovered_at:
        discovered_at = discovered_at.replace(" ", "T") + "+00:00"
    if not discovered_at:
        discovered_at = datetime.now(timezone.utc).isoformat()

    source_dedupe_key = build_event_dedupe_key(site_key, published_date or "", canonical_url, title)
    source_event_id = build_event_id(source_dedupe_key)
    dedupe_key = build_cross_source_key(published_date or "", title, reference_token)
    event_id = build_event_id(dedupe_key)
    latest_probe_url = health.get("candidate_file_url")
    file_url = canonical_url if looks_like_direct_file(canonical_url) else None
    if not file_url and latest_probe_url and normalize_event_url(health.get("latest_link")) == canonical_url:
        file_url = normalize_event_url(latest_probe_url)

    return {
        "event_id": event_id,
        "profile_key": BROKER_ALERTS_PROFILE_KEY,
        "profile_version": BROKER_ALERTS_PROFILE_VERSION,
        "dedupe_key": dedupe_key,
        "source_dedupe_key": source_dedupe_key,
        "source_event_id": source_event_id,
        "content_fingerprint": stable_content_fingerprint(title, published_date or ""),
        "source_key": site_key,
        "source_group": contract.get("group", "regulatory"),
        "source_contract": contract.get("contract", "latest_updates"),
        "source_required": bool(contract.get("required")),
        "source_health": health.get("delivery_state", "unknown"),
        "source_status": health.get("status", "unknown"),
        "confidence": resolve_confidence(site_key, published_date, canonical_url, health),
        "title": title,
        "summary": normalize_text(row.get("description") or row.get("summary") or title),
        "published_date": published_date,
        "published_at": published_at,
        "discovered_at": discovered_at,
        "canonical_url": canonical_url,
        "direct_file_url": file_url,
        "file_probe_status": health.get("file_probe_status") if normalize_event_url(health.get("latest_link")) == canonical_url else None,
        "type": normalize_text(row.get("type") or "update").lower(),
        "category": normalize_text(row.get("category") or row.get("type") or "update").lower(),
        "reference_number": reference_number,
        "effective_date": normalize_date_value(row.get("effective_date")),
        "tags": normalize_tags(row.get("tags")),
        "source_record_id": row.get("id"),
        "source_keys": [site_key],
        "mirror_count": 0,
        "mirror_sources": [],
    }


def merge_cross_source_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for event in events:
        if not event:
            continue
        grouped.setdefault(str(event.get("event_id") or ""), []).append(event)

    merged_events: List[Dict[str, Any]] = []
    for grouped_events in grouped.values():
        ordered = sorted(grouped_events, key=event_preference_key, reverse=True)
        primary = dict(ordered[0])
        primary["source_keys"] = [event.get("source_key") for event in ordered if event.get("source_key")]
        primary["mirror_sources"] = [serialize_mirror_source(event) for event in ordered[1:]]
        primary["mirror_count"] = len(primary["mirror_sources"])
        merged_events.append(primary)

    return merged_events


def event_matches_filters(
    event: Dict[str, Any],
    site_keys: Optional[Iterable[str]] = None,
    search: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    confidence_min: str = "verified",
    include_degraded: bool = False,
) -> bool:
    if not event:
        return False

    if site_keys is not None:
        allowed = {str(site).strip() for site in site_keys if str(site).strip()}
        if allowed and event.get("source_key") not in allowed:
            return False

    if search:
        search_value = search.lower()
        if search_value not in (event.get("title") or "").lower() and search_value not in (event.get("summary") or "").lower():
            return False

    published_date = event.get("published_date") or ""
    since_value = normalize_date_value(since) if since else None
    until_value = normalize_date_value(until) if until else None
    if since_value and published_date and published_date < since_value:
        return False
    if until_value and published_date and published_date > until_value:
        return False

    confidence = event.get("confidence", "degraded")
    if not include_degraded and confidence == "degraded":
        return False
    if CONFIDENCE_RANK.get(confidence, 0) < CONFIDENCE_RANK.get(confidence_min, 2):
        return False

    return True


def sort_events_latest_first(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        events,
        key=lambda event: (
            event.get("published_at") or "",
            event.get("discovered_at") or "",
            event.get("event_id") or "",
        ),
        reverse=True,
    )
