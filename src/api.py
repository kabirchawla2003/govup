"""
GovUpdate broker alerts API.
"""
import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from importlib import util
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
import uvicorn

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

from fastapi import FastAPI, HTTPException

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if load_dotenv:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from auth_models import SourceSubscriptionUpdate, WebhookCreate, WebhookReplayRequest, WebhookUpdate
from broker_alerts import (
    BROKER_ALERTS_PROFILE_KEY,
    build_broker_event,
    build_source_health_map,
    event_matches_filters,
    get_broker_profile_definition,
    merge_cross_source_events,
    sort_events_latest_first,
)
from init_api_db import DB_PATH, init_api_schema

v9_path = os.path.join(os.path.dirname(__file__), "main-v9-broker-enhanced.py")
spec = util.spec_from_file_location("main_v9", v9_path)
main_v9 = util.module_from_spec(spec)
spec.loader.exec_module(main_v9)

app = FastAPI(
    title="GovUpdate Broker Alerts API",
    description=(
        "Open-source broker-focused regulatory alert API for Indian market infrastructure sources. "
        "Provides normalized events, source health, signed webhooks, replay, and delivery observability."
    ),
    version="2.0.0",
    openapi_tags=[
        {"name": "public", "description": "Public metadata and source discovery."},
        {"name": "broker", "description": "Broker alert events, source health, and source filters."},
        {"name": "webhooks", "description": "Webhook configuration, delivery history, and dead letters."},
        {"name": "ops", "description": "Reliability and sync observability endpoints."},
    ],
)

init_api_schema()

RELIABILITY_SNAPSHOT_PATH = Path(os.getenv("BROKER_RELIABILITY_SNAPSHOT_PATH", "broker_reliability_snapshot_latest.json"))
RELIABILITY_HISTORY_PATH = Path(os.getenv("BROKER_RELIABILITY_HISTORY_PATH", "broker_reliability_history.json"))
LOCAL_SYNC_MANIFEST_PATH = Path(os.getenv("LOCAL_SYNC_MANIFEST_PATH", "output/local_scrape_sync_latest.json"))


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_file(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def get_circulars_source(cursor) -> Optional[str]:
    cursor.execute("SELECT name FROM sqlite_master WHERE (type='table' OR type='view') AND name='circulars'")
    row = cursor.fetchone()
    if row:
        return "circulars"

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='updates'")
    row = cursor.fetchone()
    if row:
        return "updates"

    return None


def get_circulars_columns(source_name: str) -> dict:
    if source_name == "updates":
        return {
            "site_key": "site",
            "description": "summary",
        }

    return {
        "site_key": "site_key",
        "description": "description",
    }


# region summaries
def build_latest_sync_summary() -> Dict[str, Any]:
    manifest_path = LOCAL_SYNC_MANIFEST_PATH
    if not manifest_path.exists():
        fallback_path = Path(manifest_path.name)
        if fallback_path.exists():
            manifest_path = fallback_path

    manifest = load_json_file(manifest_path, {})
    completed_at = manifest.get("completed_at")
    age_seconds: Optional[int] = None
    state = "missing"
    if completed_at:
        try:
            completed_dt = datetime.fromisoformat(str(completed_at))
            if completed_dt.tzinfo is None:
                completed_dt = completed_dt.replace(tzinfo=timezone.utc)
            age_seconds = int((datetime.now(timezone.utc) - completed_dt.astimezone(timezone.utc)).total_seconds())
            state = "fresh" if age_seconds <= 36 * 3600 else "stale"
        except Exception:
            state = "invalid"

    validation = manifest.get("validation") or {}
    remote_check = validation.get("remote_artifact_check") or {}
    public_check = validation.get("public_health_check") or {}
    return {
        "path": str(LOCAL_SYNC_MANIFEST_PATH),
        "resolved_path": str(manifest_path),
        "completed_at": completed_at,
        "state": state,
        "age_seconds": age_seconds,
        "ssh_target": manifest.get("ssh_target"),
        "server_service": manifest.get("server_service"),
        "remote_updates_count": remote_check.get("updates_count"),
        "remote_mappings_count": remote_check.get("mappings_count"),
        "remote_attachments_count": remote_check.get("attachments_count"),
        "remote_source_count": remote_check.get("source_count"),
        "remote_sebi_status": remote_check.get("sebi_status"),
        "public_health_status_code": public_check.get("status_code"),
        "restart_ok": bool((manifest.get("restart_log") or "").strip().endswith("active")),
        "import_ran": bool(manifest.get("remote_import_log")),
        "dispatch_ran": bool(manifest.get("remote_dispatch_log")),
    }


def build_webhook_ops_summary() -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_webhooks,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_webhooks,
                SUM(CASE WHEN auto_paused = 1 THEN 1 ELSE 0 END) AS auto_paused_webhooks,
                SUM(dead_letter_count) AS dead_letters,
                SUM(CASE WHEN last_delivery_status = 'failed' THEN 1 ELSE 0 END) AS failed_webhooks
            FROM webhooks
            """
        )
        totals = dict(cursor.fetchone() or {})
        cursor.execute(
            """
            SELECT COUNT(*) AS open_dead_letters
            FROM webhook_dead_letters
            WHERE resolved_at IS NULL
            """
        )
        dead_letters = dict(cursor.fetchone() or {})

    return {
        "total_webhooks": int(totals.get("total_webhooks") or 0),
        "active_webhooks": int(totals.get("active_webhooks") or 0),
        "auto_paused_webhooks": int(totals.get("auto_paused_webhooks") or 0),
        "failed_webhooks": int(totals.get("failed_webhooks") or 0),
        "dead_letters_total": int(totals.get("dead_letters") or 0),
        "open_dead_letters": int(dead_letters.get("open_dead_letters") or 0),
    }


def build_reliability_summary() -> Dict[str, Any]:
    snapshot = load_json_file(RELIABILITY_SNAPSHOT_PATH, {})
    history = load_json_file(RELIABILITY_HISTORY_PATH, [])

    full_verification = snapshot.get("full_verification") or {}
    broker_validation = snapshot.get("broker_validation") or {}
    status_counts = full_verification.get("status_counts") or {}

    latest_entry = history[-1] if history else {}
    previous_entry = history[-2] if len(history) >= 2 else {}

    def delta(key: str) -> Optional[int]:
        if key not in latest_entry or key not in previous_entry:
            return None
        latest_value = latest_entry.get(key)
        previous_value = previous_entry.get(key)
        if latest_value is None or previous_value is None:
            return None
        return int(latest_value) - int(previous_value)

    return {
        "captured_at": snapshot.get("completed_at"),
        "run_health": full_verification.get("run_health") or {},
        "status_counts": status_counts,
        "broker_must_have": {
            "working": full_verification.get("broker_must_have_working"),
            "total": full_verification.get("broker_must_have_total"),
        },
        "validation": {
            "all_checks_passed": broker_validation.get("all_checks_passed", False),
            "events_total": broker_validation.get("events_total"),
            "dispatch_delivered": broker_validation.get("dispatch_delivered"),
            "validation_checks": broker_validation.get("validation_checks") or {},
        },
        "deltas": {
            "working_sources": delta("working_sources"),
            "network_failed_sources": delta("network_failed_sources"),
            "blocked_sources": delta("blocked_sources"),
            "broker_must_have_working": delta("broker_must_have_working"),
            "events_total": delta("events_total"),
            "dispatch_delivered": delta("dispatch_delivered"),
        },
        "latest_sync": build_latest_sync_summary(),
        "webhook_ops": build_webhook_ops_summary(),
        "history_entries": len(history),
    }
# endregion summaries


# region source filters and events
def parse_site_keys_json(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except Exception:
        pass
    return [item.strip() for item in str(value).split(",") if item.strip()]


def serialize_site_keys(site_keys: Optional[List[str]]) -> Optional[str]:
    cleaned = [str(site).strip() for site in (site_keys or []) if str(site).strip()]
    return json.dumps(cleaned) if cleaned else None


def parse_site_keys_query(site_keys: Optional[str]) -> List[str]:
    return [item.strip() for item in str(site_keys or "").split(",") if item.strip()]


def allowed_broker_site_keys() -> List[str]:
    profile = get_broker_profile_definition()
    return list(profile["core_sources"]) + list(profile["optional_sources"])


def normalize_requested_site_keys(site_keys: Optional[List[str]]) -> List[str]:
    allowed = set(allowed_broker_site_keys())
    cleaned: List[str] = []
    for site_key in site_keys or []:
        site_value = str(site_key).strip()
        if site_value and site_value in allowed and site_value not in cleaned:
            cleaned.append(site_value)
    return cleaned


def get_source_subscriptions(profile_name: str = BROKER_ALERTS_PROFILE_KEY) -> List[str]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT site_key
            FROM source_subscriptions
            WHERE profile_name = ?
            ORDER BY site_key
            """,
            (profile_name,),
        )
        return [str(row["site_key"]) for row in cursor.fetchall()]


def replace_source_subscriptions(profile_name: str, site_keys: List[str]) -> List[str]:
    normalized_site_keys = normalize_requested_site_keys(site_keys)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM source_subscriptions WHERE profile_name = ?", (profile_name,))
        for site_key in normalized_site_keys:
            cursor.execute(
                """
                INSERT INTO source_subscriptions (profile_name, site_key, updated_at)
                VALUES (?, ?, ?)
                """,
                (profile_name, site_key, utcnow_iso()),
            )
        conn.commit()
    return normalized_site_keys


def resolve_effective_site_keys(
    requested_site_keys: Optional[List[str]] = None,
    profile_name: str = BROKER_ALERTS_PROFILE_KEY,
    include_optional: bool = False,
) -> List[str]:
    if requested_site_keys:
        return normalize_requested_site_keys(requested_site_keys)

    configured = get_source_subscriptions(profile_name)
    if configured:
        return configured

    profile = get_broker_profile_definition()
    site_keys = list(profile["core_sources"])
    if include_optional:
        site_keys.extend(profile["optional_sources"])
    return site_keys


def fetch_circular_rows_for_sites(site_keys: List[str]) -> List[Dict[str, Any]]:
    if not site_keys:
        return []

    with get_db() as conn:
        cursor = conn.cursor()
        source_name = get_circulars_source(cursor)
        if not source_name:
            return []

        columns = get_circulars_columns(source_name)
        placeholders = ",".join("?" for _ in site_keys)
        cursor.execute(
            f"SELECT * FROM {source_name} WHERE {columns['site_key']} IN ({placeholders})",
            tuple(site_keys),
        )
        rows = []
        for row in cursor.fetchall():
            payload = dict(row)
            payload["site_key"] = payload.get(columns["site_key"])
            payload["description"] = payload.get(columns["description"])
            rows.append(payload)
        return rows


def build_broker_events(
    requested_site_keys: Optional[List[str]] = None,
    search: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    confidence_min: str = "verified",
    include_degraded: bool = False,
    include_optional: bool = False,
    profile_name: str = BROKER_ALERTS_PROFILE_KEY,
) -> List[Dict[str, Any]]:
    site_keys = resolve_effective_site_keys(
        requested_site_keys=requested_site_keys,
        profile_name=profile_name,
        include_optional=include_optional,
    )
    health_map = build_source_health_map()
    candidate_events: List[Dict[str, Any]] = []

    for row in fetch_circular_rows_for_sites(site_keys):
        event = build_broker_event(row, health_map)
        if not event:
            continue
        if not event_matches_filters(
            event,
            site_keys=site_keys,
            search=search,
            since=since,
            until=until,
            confidence_min=confidence_min,
            include_degraded=include_degraded,
        ):
            continue
        candidate_events.append(event)

    return sort_events_latest_first(merge_cross_source_events(candidate_events))


def get_broker_event_by_id(
    event_id: str,
    requested_site_keys: Optional[List[str]] = None,
    include_optional: bool = True,
) -> Optional[Dict[str, Any]]:
    events = build_broker_events(
        requested_site_keys=requested_site_keys,
        include_optional=include_optional,
        confidence_min="degraded",
        include_degraded=True,
    )
    for event in events:
        if event.get("event_id") == event_id:
            return event
    return None


def serialize_public_event(event: Dict[str, Any]) -> Dict[str, Any]:
    public_fields = [
        "event_id",
        "profile_key",
        "profile_version",
        "source_key",
        "source_group",
        "source_contract",
        "source_required",
        "source_health",
        "source_status",
        "confidence",
        "title",
        "summary",
        "published_date",
        "published_at",
        "discovered_at",
        "canonical_url",
        "direct_file_url",
        "file_probe_status",
        "type",
        "category",
        "reference_number",
        "effective_date",
        "tags",
        "source_keys",
        "mirror_count",
        "mirror_sources",
    ]
    payload = {field: event.get(field) for field in public_fields}
    sanitized_mirrors = []
    for mirror in payload.get("mirror_sources") or []:
        sanitized_mirrors.append(
            {
                "source_key": mirror.get("source_key"),
                "source_group": mirror.get("source_group"),
                "source_contract": mirror.get("source_contract"),
                "confidence": mirror.get("confidence"),
                "canonical_url": mirror.get("canonical_url"),
                "direct_file_url": mirror.get("direct_file_url"),
                "file_probe_status": mirror.get("file_probe_status"),
                "published_date": mirror.get("published_date"),
                "reference_number": mirror.get("reference_number"),
            }
        )
    payload["mirror_sources"] = sanitized_mirrors
    return payload
# endregion source filters and events


# region webhooks
def serialize_webhook_row(row: Dict[str, Any], include_secret: bool = False) -> Dict[str, Any]:
    payload = dict(row)
    payload["site_keys"] = parse_site_keys_json(payload.get("site_keys_json"))
    payload.pop("site_keys_json", None)
    payload["include_degraded"] = bool(payload.get("include_degraded"))
    payload["is_active"] = bool(payload.get("is_active"))
    payload["auto_paused"] = bool(payload.get("auto_paused"))
    if not include_secret:
        payload.pop("secret", None)
    return payload


def generate_webhook_secret() -> str:
    return uuid4().hex


def get_webhook(webhook_id: int, include_secret: bool = False) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,))
        row = cursor.fetchone()
    return serialize_webhook_row(dict(row), include_secret=include_secret) if row else None


def build_webhook_signature(secret: str, raw_body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def already_delivered(webhook_id: int, event_id: str, replayed: bool = False) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM webhook_deliveries
            WHERE webhook_id = ? AND event_id = ? AND replayed = ? AND status = 'success'
            LIMIT 1
            """,
            (webhook_id, event_id, int(replayed)),
        )
        return cursor.fetchone() is not None


def persist_webhook_delivery(
    webhook: Dict[str, Any],
    event_id: str,
    delivery_id: str,
    replayed: bool,
    status_value: str,
    attempt_count: int,
    request_headers: Dict[str, Any],
    request_body: str,
    http_status: Optional[int] = None,
    response_body: Optional[str] = None,
    error: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> None:
    now = utcnow_iso()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO webhook_deliveries
            (webhook_id, event_id, delivery_id, replayed, status, attempt_count, http_status,
             request_headers, request_body, response_body, error, latency_ms, sent_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                webhook["id"],
                event_id,
                delivery_id,
                int(replayed),
                status_value,
                attempt_count,
                http_status,
                json.dumps(request_headers, ensure_ascii=False),
                request_body,
                response_body,
                error,
                latency_ms,
                now,
                now,
            ),
        )
        if status_value == "success":
            cursor.execute(
                """
                UPDATE webhooks
                SET success_count = success_count + 1,
                    consecutive_failure_count = 0,
                    last_triggered = ?,
                    last_success = ?,
                    last_delivery_status = 'success',
                    last_delivery_http_status = ?,
                    last_delivery_latency_ms = ?,
                    last_error = NULL,
                    auto_paused = 0,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, http_status, latency_ms, now, webhook["id"]),
            )
        else:
            next_consecutive_failure_count = int(webhook.get("consecutive_failure_count") or 0) + 1
            threshold = int(webhook.get("pause_on_failure_threshold") or 0)
            auto_pause_now = threshold > 0 and next_consecutive_failure_count >= threshold
            cursor.execute(
                """
                UPDATE webhooks
                SET failure_count = failure_count + 1,
                    consecutive_failure_count = consecutive_failure_count + 1,
                    last_triggered = ?,
                    last_failure = ?,
                    last_delivery_status = 'failed',
                    last_delivery_http_status = ?,
                    last_delivery_latency_ms = ?,
                    last_error = ?,
                    auto_paused = ?,
                    is_active = CASE WHEN ? THEN 0 ELSE is_active END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    now,
                    now,
                    http_status,
                    latency_ms,
                    error,
                    int(auto_pause_now),
                    int(auto_pause_now),
                    now,
                    webhook["id"],
                ),
            )
        conn.commit()


def persist_dead_letter(
    webhook: Dict[str, Any],
    event_id: str,
    delivery_id: str,
    request_headers: Dict[str, Any],
    request_body: str,
    http_status: Optional[int],
    response_body: Optional[str],
    error: Optional[str],
) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO webhook_dead_letters
            (webhook_id, event_id, delivery_id, request_headers, request_body, http_status, error, response_body, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                webhook["id"],
                event_id,
                delivery_id,
                json.dumps(request_headers, ensure_ascii=False),
                request_body,
                http_status,
                error,
                response_body,
                utcnow_iso(),
            ),
        )
        cursor.execute(
            """
            UPDATE webhooks
            SET dead_letter_count = dead_letter_count + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (utcnow_iso(), webhook["id"]),
        )
        conn.commit()


async def deliver_event_to_webhook(
    webhook: Dict[str, Any],
    event: Dict[str, Any],
    replayed: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    delivery_id = f"dlv_{uuid4().hex}"
    payload = {
        "delivery_id": delivery_id,
        "profile_key": BROKER_ALERTS_PROFILE_KEY,
        "sent_at": utcnow_iso(),
        "event": serialize_public_event(event),
    }
    raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-GovUpdate-Event-Id": event["event_id"],
        "X-GovUpdate-Delivery-Id": delivery_id,
        "X-GovUpdate-Webhook-Id": str(webhook["id"]),
        "X-GovUpdate-Source": event["source_key"],
        "Idempotency-Key": event["event_id"],
    }
    if webhook.get("secret"):
        headers["X-GovUpdate-Signature"] = build_webhook_signature(webhook["secret"], raw_body)

    if dry_run:
        return {
            "delivery_id": delivery_id,
            "status": "dry_run",
            "event_id": event["event_id"],
            "target_url": webhook["url"],
        }

    attempts_allowed = int(webhook.get("retry_count") or 0) + 1
    last_error = None
    last_status = None
    response_body = None
    latency_ms = None

    async with httpx.AsyncClient(timeout=float(webhook.get("timeout_seconds") or 30)) as client:
        for attempt in range(1, attempts_allowed + 1):
            try:
                started_at = time.perf_counter()
                response = await client.post(webhook["url"], content=raw_body, headers=headers)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                last_status = response.status_code
                response_body = response.text[:4000]
                if 200 <= response.status_code < 300:
                    persist_webhook_delivery(
                        webhook=webhook,
                        event_id=event["event_id"],
                        delivery_id=delivery_id,
                        replayed=replayed,
                        status_value="success",
                        attempt_count=attempt,
                        request_headers=headers,
                        request_body=raw_body.decode("utf-8"),
                        http_status=response.status_code,
                        response_body=response_body,
                        latency_ms=latency_ms,
                    )
                    return {
                        "delivery_id": delivery_id,
                        "status": "success",
                        "event_id": event["event_id"],
                        "http_status": response.status_code,
                        "latency_ms": latency_ms,
                    }
                last_error = f"Webhook returned HTTP {response.status_code}"
            except Exception as exc:
                latency_ms = None
                last_error = str(exc)

            if attempt < attempts_allowed:
                await asyncio.sleep(min(5, attempt))

    persist_webhook_delivery(
        webhook=webhook,
        event_id=event["event_id"],
        delivery_id=delivery_id,
        replayed=replayed,
        status_value="failed",
        attempt_count=attempts_allowed,
        request_headers=headers,
        request_body=raw_body.decode("utf-8"),
        http_status=last_status,
        response_body=response_body,
        error=last_error,
        latency_ms=latency_ms,
    )
    persist_dead_letter(
        webhook=webhook,
        event_id=event["event_id"],
        delivery_id=delivery_id,
        request_headers=headers,
        request_body=raw_body.decode("utf-8"),
        http_status=last_status,
        response_body=response_body,
        error=last_error,
    )
    return {
        "delivery_id": delivery_id,
        "status": "failed",
        "event_id": event["event_id"],
        "http_status": last_status,
        "error": last_error,
        "latency_ms": latency_ms,
        "auto_paused": bool((int(webhook.get("consecutive_failure_count") or 0) + 1) >= int(webhook.get("pause_on_failure_threshold") or 0) > 0),
        "dead_lettered": True,
    }


async def replay_webhook_events(
    webhook: Dict[str, Any],
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 50,
    force: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    site_keys = webhook.get("site_keys") or parse_site_keys_json(webhook.get("site_filter"))
    events = build_broker_events(
        requested_site_keys=site_keys,
        since=since or webhook.get("last_event_published_at"),
        until=until,
        confidence_min=webhook.get("confidence_filter") or "verified",
        include_degraded=bool(webhook.get("include_degraded")),
        include_optional=True,
    )
    ordered_events = list(reversed(events[:limit]))

    deliveries = []
    delivered_count = 0
    skipped_count = 0
    for event in ordered_events:
        if not force and already_delivered(webhook["id"], event["event_id"], replayed=False):
            skipped_count += 1
            deliveries.append({"event_id": event["event_id"], "status": "skipped"})
            continue
        delivery_result = await deliver_event_to_webhook(webhook, event, replayed=force, dry_run=dry_run)
        deliveries.append(delivery_result)
        if delivery_result["status"] in {"success", "dry_run"}:
            delivered_count += 1

    if deliveries and not dry_run:
        last_event = ordered_events[-1]
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE webhooks
                SET last_event_published_at = ?, last_event_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    last_event.get("published_date"),
                    last_event.get("event_id"),
                    utcnow_iso(),
                    webhook["id"],
                ),
            )
            conn.commit()

    return {
        "webhook_id": webhook["id"],
        "processed": len(ordered_events),
        "delivered": delivered_count,
        "skipped": skipped_count,
        "dry_run": dry_run,
        "deliveries": deliveries,
    }
# endregion webhooks


async def run_startup() -> None:
    init_saas_schema()


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    await run_startup()
    yield


app.router.lifespan_context = app_lifespan


# region endpoints
@app.get("/", tags=["public"], summary="API index")
async def root():
    return {
        "service": "GovUpdate Broker Alerts API",
        "version": app.version,
        "sources": len(main_v9.SITES),
        "endpoints": {
            "events": "/api/events",
            "source_health": "/api/source-health",
            "source_subscriptions": "/api/source-subscriptions",
            "webhooks": "/api/webhooks",
            "broker_profile": "/profiles/broker-alerts-v1",
            "docs": "/docs",
        },
    }


@app.get("/health", tags=["public"], summary="Public health check")
async def health_check():
    return {"status": "healthy", "version": app.version}


@app.get("/sources", tags=["public"], summary="List configured source coverage")
async def list_sources():
    sources = []
    for key, site in main_v9.SITES.items():
        sources.append(
            {
                "key": key,
                "name": site["name"],
                "description": site.get("description", ""),
                "category": site.get("category", "regulatory"),
                "types": site.get("update_types", []),
            }
        )
    return {"total": len(sources), "sources": sources}


@app.get("/profiles/broker-alerts-v1", tags=["public", "broker"], summary="Get the broker alerts profile")
async def get_broker_alerts_profile():
    return get_broker_profile_definition()


@app.get("/api/circulars", tags=["public", "broker"], summary="List circulars from the local dataset")
async def get_circulars(
    site: Optional[str] = None,
    type: Optional[str] = None,
    category: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    with get_db() as conn:
        cursor = conn.cursor()
        source_name = get_circulars_source(cursor)
        if not source_name:
            return {
                "total": 0,
                "limit": limit,
                "offset": offset,
                "circulars": [],
                "message": "No circulars data available. Run scraper to populate data.",
            }

        columns = get_circulars_columns(source_name)
        query = f"SELECT * FROM {source_name} WHERE 1=1"
        params: List[Any] = []
        if site:
            query += f" AND {columns['site_key']} = ?"
            params.append(site)
        if type:
            query += " AND type = ?"
            params.append(type)
        if category:
            query += " AND category = ?"
            params.append(category)
        if since:
            query += " AND date >= ?"
            params.append(since)
        if until:
            query += " AND date <= ?"
            params.append(until)
        if search:
            query += f" AND (title LIKE ? OR {columns['description']} LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term])

        query += " ORDER BY date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, params)
        circulars = [dict(row) for row in cursor.fetchall()]

        count_query = query.split("ORDER BY")[0].replace("SELECT *", "SELECT COUNT(*)")
        cursor.execute(count_query, params[:-2])
        total = cursor.fetchone()[0]

    return {"total": total, "limit": limit, "offset": offset, "circulars": circulars}


@app.get("/api/circulars/{circular_id}", tags=["public", "broker"], summary="Get one circular by id")
async def get_circular_by_id(circular_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        source_name = get_circulars_source(cursor)
        if not source_name:
            raise HTTPException(status_code=404, detail="Circular not found")
        cursor.execute(f"SELECT * FROM {source_name} WHERE id = ?", (circular_id,))
        circular = cursor.fetchone()
    if not circular:
        raise HTTPException(status_code=404, detail="Circular not found")
    return dict(circular)


@app.get("/api/sites", tags=["public", "broker"], summary="Get source coverage with local counts")
async def get_sites_detailed():
    with get_db() as conn:
        cursor = conn.cursor()
        source_name = get_circulars_source(cursor)
        circulars_exists = source_name is not None
        columns = get_circulars_columns(source_name) if source_name else {}

        sites_data = []
        for key, site in main_v9.SITES.items():
            if circulars_exists:
                cursor.execute(f"SELECT COUNT(*) FROM {source_name} WHERE {columns['site_key']} = ?", (key,))
                count = cursor.fetchone()[0]
                cursor.execute(f"SELECT date FROM {source_name} WHERE {columns['site_key']} = ? ORDER BY date DESC LIMIT 1", (key,))
                latest = cursor.fetchone()
                latest_date = latest[0] if latest else None
            else:
                count = 0
                latest_date = None
            sites_data.append(
                {
                    "key": key,
                    "name": site["name"],
                    "description": site.get("description", ""),
                    "category": site.get("category", "regulatory"),
                    "circular_count": count,
                    "latest_circular_date": latest_date,
                }
            )

    return {"sites": sites_data, "total": len(sites_data)}


@app.get("/api/source-health", tags=["broker"], summary="Get broker source health")
async def get_source_health(include_optional: bool = False, site_keys: Optional[str] = None):
    requested_site_keys = parse_site_keys_query(site_keys)
    resolved_site_keys = resolve_effective_site_keys(
        requested_site_keys=requested_site_keys or None,
        include_optional=include_optional,
    )
    health_map = build_source_health_map()
    sources = [health_map.get(site_key, {"site_key": site_key, "status": "missing"}) for site_key in resolved_site_keys]
    return {
        "profile_key": BROKER_ALERTS_PROFILE_KEY,
        "total": len(sources),
        "sources": sources,
        "tested_at": next((item.get("tested_at") for item in sources if item.get("tested_at")), None),
    }


@app.get("/api/source-subscriptions", tags=["broker"], summary="Get configured broker source filters")
async def get_source_subscriptions_endpoint():
    site_keys = get_source_subscriptions(BROKER_ALERTS_PROFILE_KEY)
    return {
        "profile_key": BROKER_ALERTS_PROFILE_KEY,
        "site_keys": site_keys,
        "available_site_keys": allowed_broker_site_keys(),
    }


@app.put("/api/source-subscriptions", tags=["broker"], summary="Replace broker source filters")
async def put_source_subscriptions(data: SourceSubscriptionUpdate):
    if data.profile_name != BROKER_ALERTS_PROFILE_KEY:
        raise HTTPException(status_code=400, detail="Only broker_alerts_v1 is supported right now.")
    site_keys = replace_source_subscriptions(data.profile_name, data.site_keys)
    return {
        "profile_key": data.profile_name,
        "site_keys": site_keys,
        "available_site_keys": allowed_broker_site_keys(),
    }


@app.get("/api/events", tags=["broker"], summary="List broker alert events")
async def get_broker_events(
    site_keys: Optional[str] = None,
    search: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    confidence_min: str = "verified",
    include_degraded: bool = False,
    include_optional: bool = False,
):
    events = build_broker_events(
        requested_site_keys=parse_site_keys_query(site_keys) or None,
        search=search,
        since=since,
        until=until,
        confidence_min=confidence_min,
        include_degraded=include_degraded,
        include_optional=include_optional,
    )
    return {
        "profile_key": BROKER_ALERTS_PROFILE_KEY,
        "total": len(events),
        "events": [serialize_public_event(event) for event in events],
    }


@app.get("/api/events/{event_id}", tags=["broker"], summary="Get one broker alert event")
async def get_broker_event(event_id: str, site_keys: Optional[str] = None):
    event = get_broker_event_by_id(
        event_id=event_id,
        requested_site_keys=parse_site_keys_query(site_keys) or None,
        include_optional=True,
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return serialize_public_event(event)


@app.get("/api/webhooks", tags=["webhooks"], summary="List configured webhooks")
async def list_webhooks():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM webhooks ORDER BY created_at DESC, id DESC")
        webhooks = [serialize_webhook_row(dict(row)) for row in cursor.fetchall()]
    return {"webhooks": webhooks, "total": len(webhooks)}


@app.post("/api/webhooks", tags=["webhooks"], summary="Create a webhook")
async def create_webhook(data: WebhookCreate):
    if data.profile_name != BROKER_ALERTS_PROFILE_KEY:
        raise HTTPException(status_code=400, detail="Only broker_alerts_v1 is supported right now.")

    normalized_site_keys = normalize_requested_site_keys(data.site_keys)
    secret = data.secret or generate_webhook_secret()
    now = utcnow_iso()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO webhooks
            (
                url, name, secret, profile_name, site_filter, type_filter, category_filter,
                site_keys_json, confidence_filter, include_degraded, is_active, retry_count,
                timeout_seconds, pause_on_failure_threshold, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            """,
            (
                data.url,
                data.name,
                secret,
                data.profile_name,
                data.site_filter,
                data.type_filter,
                data.category_filter,
                serialize_site_keys(normalized_site_keys),
                data.confidence_filter,
                int(data.include_degraded),
                data.retry_count,
                data.timeout_seconds,
                data.pause_on_failure_threshold,
                now,
                now,
            ),
        )
        webhook_id = cursor.lastrowid
        conn.commit()

    webhook = get_webhook(webhook_id)
    return {"webhook": webhook, "signing_secret": secret}


@app.patch("/api/webhooks/{webhook_id}", tags=["webhooks"], summary="Update a webhook")
async def update_webhook(webhook_id: int, data: WebhookUpdate):
    webhook = get_webhook(webhook_id, include_secret=True)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if data.profile_name and data.profile_name != BROKER_ALERTS_PROFILE_KEY:
        raise HTTPException(status_code=400, detail="Only broker_alerts_v1 is supported right now.")

    updates: Dict[str, Any] = {}
    if data.url is not None:
        updates["url"] = data.url
    if data.name is not None:
        updates["name"] = data.name
    if data.profile_name is not None:
        updates["profile_name"] = data.profile_name
    if data.site_filter is not None:
        updates["site_filter"] = data.site_filter
    if data.type_filter is not None:
        updates["type_filter"] = data.type_filter
    if data.category_filter is not None:
        updates["category_filter"] = data.category_filter
    if data.site_keys is not None:
        updates["site_keys_json"] = serialize_site_keys(normalize_requested_site_keys(data.site_keys))
    if data.confidence_filter is not None:
        updates["confidence_filter"] = data.confidence_filter
    if data.include_degraded is not None:
        updates["include_degraded"] = int(data.include_degraded)
    if data.retry_count is not None:
        updates["retry_count"] = data.retry_count
    if data.pause_on_failure_threshold is not None:
        updates["pause_on_failure_threshold"] = data.pause_on_failure_threshold
    if data.timeout_seconds is not None:
        updates["timeout_seconds"] = data.timeout_seconds
    if data.is_active is not None:
        updates["is_active"] = int(data.is_active)
        if data.is_active:
            updates["auto_paused"] = 0
    if data.secret is not None:
        updates["secret"] = data.secret
    updates["updated_at"] = utcnow_iso()

    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates.keys())
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE webhooks SET {assignments} WHERE id = ?", (*updates.values(), webhook_id))
            conn.commit()

    return {"webhook": get_webhook(webhook_id)}


@app.delete("/api/webhooks/{webhook_id}", tags=["webhooks"], summary="Delete a webhook")
async def delete_webhook(webhook_id: int):
    if not get_webhook(webhook_id):
        raise HTTPException(status_code=404, detail="Webhook not found")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
        conn.commit()
    return {"message": "Webhook deleted"}


@app.get("/api/webhooks/{webhook_id}/deliveries", tags=["webhooks"], summary="List webhook deliveries")
async def list_webhook_deliveries(webhook_id: int):
    webhook = get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, event_id, delivery_id, replayed, status, attempt_count, http_status, error, latency_ms, sent_at, created_at
            FROM webhook_deliveries
            WHERE webhook_id = ?
            ORDER BY id DESC
            """,
            (webhook_id,),
        )
        deliveries = [dict(row) for row in cursor.fetchall()]
    return {"webhook": webhook, "deliveries": deliveries, "total": len(deliveries)}


@app.get("/api/webhooks/{webhook_id}/dead-letters", tags=["webhooks"], summary="List webhook dead letters")
async def list_webhook_dead_letters(webhook_id: int):
    webhook = get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, event_id, delivery_id, http_status, error, response_body, created_at, resolved_at, resolution_status
            FROM webhook_dead_letters
            WHERE webhook_id = ?
            ORDER BY id DESC
            """,
            (webhook_id,),
        )
        dead_letters = [dict(row) for row in cursor.fetchall()]
    return {"webhook": webhook, "dead_letters": dead_letters, "total": len(dead_letters)}


@app.get("/api/webhooks/{webhook_id}/health", tags=["webhooks"], summary="Get webhook health summary")
async def get_webhook_health(webhook_id: int):
    webhook = get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_deliveries,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_deliveries,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_deliveries
            FROM webhook_deliveries
            WHERE webhook_id = ?
            """,
            (webhook_id,),
        )
        delivery_counts = dict(cursor.fetchone() or {})
        cursor.execute(
            """
            SELECT COUNT(*) AS open_dead_letters
            FROM webhook_dead_letters
            WHERE webhook_id = ? AND resolved_at IS NULL
            """,
            (webhook_id,),
        )
        dead_letter_row = dict(cursor.fetchone() or {})

    total_deliveries = int(delivery_counts.get("total_deliveries") or 0)
    success_deliveries = int(delivery_counts.get("success_deliveries") or 0)
    failed_deliveries = int(delivery_counts.get("failed_deliveries") or 0)
    success_rate = round((success_deliveries / total_deliveries) * 100, 2) if total_deliveries else 0.0

    return {
        "webhook": webhook,
        "summary": {
            "total_deliveries": total_deliveries,
            "success_deliveries": success_deliveries,
            "failed_deliveries": failed_deliveries,
            "success_rate": success_rate,
            "open_dead_letters": int(dead_letter_row.get("open_dead_letters") or 0),
            "is_paused": bool(webhook.get("auto_paused")) or not bool(webhook.get("is_active")),
            "auto_paused": bool(webhook.get("auto_paused")),
            "consecutive_failure_count": int(webhook.get("consecutive_failure_count") or 0),
            "pause_on_failure_threshold": int(webhook.get("pause_on_failure_threshold") or 0),
            "last_delivery_status": webhook.get("last_delivery_status"),
            "last_delivery_http_status": webhook.get("last_delivery_http_status"),
            "last_delivery_latency_ms": webhook.get("last_delivery_latency_ms"),
            "last_success": webhook.get("last_success"),
            "last_failure": webhook.get("last_failure"),
            "last_error": webhook.get("last_error"),
        },
    }


@app.post("/api/webhooks/{webhook_id}/test", tags=["webhooks"], summary="Send a sample event to a webhook")
async def test_webhook(webhook_id: int):
    webhook = get_webhook(webhook_id, include_secret=True)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    events = build_broker_events(
        requested_site_keys=webhook.get("site_keys"),
        include_optional=True,
        confidence_min=webhook.get("confidence_filter") or "verified",
        include_degraded=bool(webhook.get("include_degraded")),
    )
    if events:
        event = events[0]
    else:
        today = datetime.now(timezone.utc).date().isoformat()
        event = {
            "event_id": f"evt_test_{uuid4().hex[:12]}",
            "profile_key": BROKER_ALERTS_PROFILE_KEY,
            "profile_version": get_broker_profile_definition()["profile_version"],
            "dedupe_key": "test",
            "content_fingerprint": "test",
            "source_key": "sebi",
            "source_group": "regulator",
            "source_contract": "test_event",
            "source_required": True,
            "source_health": "healthy",
            "source_status": "working",
            "confidence": "verified",
            "title": "Test broker alert event",
            "summary": "Synthetic delivery used to verify webhook connectivity.",
            "published_date": today,
            "published_at": f"{today}T00:00:00+00:00",
            "discovered_at": utcnow_iso(),
            "canonical_url": "https://example.com/test-broker-alert",
            "direct_file_url": None,
            "file_probe_status": None,
            "type": "test",
            "category": "test",
            "reference_number": None,
            "effective_date": None,
            "tags": ["test"],
            "source_record_id": None,
            "source_keys": ["sebi"],
            "mirror_count": 0,
            "mirror_sources": [],
        }

    result = await deliver_event_to_webhook(webhook, event, replayed=True, dry_run=False)
    return {"webhook": serialize_webhook_row(webhook), "result": result, "event": serialize_public_event(event)}


@app.post("/api/webhooks/{webhook_id}/replay", tags=["webhooks"], summary="Replay broker events to a webhook")
async def replay_webhook(webhook_id: int, data: WebhookReplayRequest):
    webhook = get_webhook(webhook_id, include_secret=True)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return await replay_webhook_events(
        webhook=webhook,
        since=data.since,
        until=data.until,
        limit=data.limit,
        force=data.force,
        dry_run=data.dry_run,
    )


@app.get("/api/reliability/latest", tags=["ops"], summary="Get latest broker reliability summary")
async def get_latest_reliability_summary():
    return build_reliability_summary()


@app.get("/api/ops/latest-sync", tags=["ops"], summary="Get latest sync freshness and webhook ops summary")
async def get_latest_sync_ops():
    return {
        "latest_sync": build_latest_sync_summary(),
        "webhook_ops": build_webhook_ops_summary(),
    }
# endregion endpoints


if __name__ == "__main__":
    print("=" * 70)
    print("GovUpdate Broker Alerts API - Starting")
    print("=" * 70)
    print(f"Sources: {len(main_v9.SITES)}")
    print(f"Database: {DB_PATH}")
    print("API Docs: http://localhost:8000/docs")
    print("=" * 70)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
