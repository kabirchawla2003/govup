import argparse
import asyncio
import importlib.util
import json
import os
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
API_PATH = SRC_DIR / "api.py"
DISPATCH_SCRIPT_PATH = ROOT / "scripts" / "run_broker_webhook_dispatch.py"
DEFAULT_OUTPUT_PATH = ROOT / "broker_alerts_validation_latest.json"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC_DIR))


def create_updates_table(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE updates (
            id TEXT PRIMARY KEY,
            site TEXT,
            type TEXT,
            category TEXT,
            title TEXT,
            date TEXT,
            time TEXT,
            summary TEXT,
            content TEXT,
            url TEXT,
            reference_number TEXT,
            effective_date TEXT,
            expiry_date TEXT,
            tags TEXT,
            priority TEXT,
            source TEXT,
            published_at TEXT,
            fetched_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def load_api_module(db_path: Path):
    os.environ["DB_PATH"] = str(db_path)
    for module_name in [
        "auth_models",
        "broker_alerts",
        "init_api_db",
        "api_validation_module",
    ]:
        sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location("api_validation_module", API_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["api_validation_module"] = module
    spec.loader.exec_module(module)
    return module


def load_dispatch_module():
    spec = importlib.util.spec_from_file_location("broker_dispatch_validation_module", DISPATCH_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["broker_dispatch_validation_module"] = module
    spec.loader.exec_module(module)
    return module


class RecordingHandler(BaseHTTPRequestHandler):
    records = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        payload = body.decode("utf-8")
        try:
            parsed_body = json.loads(payload)
        except Exception:
            parsed_body = payload
        RecordingHandler.records.append(
            {
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": parsed_body,
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return


def start_recording_server():
    RecordingHandler.records = []
    server = HTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def trim_record(record):
    headers = record.get("headers", {})
    lowered = {str(key).lower(): value for key, value in headers.items()}
    return {
        "path": record.get("path"),
        "headers": {
            "X-GovUpdate-Signature": headers.get("X-GovUpdate-Signature") or lowered.get("x-govupdate-signature"),
            "X-GovUpdate-Event-Id": headers.get("X-GovUpdate-Event-Id") or lowered.get("x-govupdate-event-id"),
            "X-GovUpdate-Delivery-Id": headers.get("X-GovUpdate-Delivery-Id") or lowered.get("x-govupdate-delivery-id"),
            "X-GovUpdate-Webhook-Id": headers.get("X-GovUpdate-Webhook-Id") or lowered.get("x-govupdate-webhook-id"),
            "X-GovUpdate-Source": headers.get("X-GovUpdate-Source") or lowered.get("x-govupdate-source"),
            "Idempotency-Key": headers.get("Idempotency-Key") or lowered.get("idempotency-key"),
        },
        "body": record.get("body"),
    }


def seed_updates(module):
    now = datetime.now(timezone.utc).isoformat()
    seeded_updates = [
        {
            "id": "upd_sebi_1",
            "site": "sebi",
            "type": "order",
            "category": "order",
            "title": "SEBI order on margin reporting",
            "date": "2026-03-12",
            "summary": "SEBI order on margin reporting",
            "url": "https://www.sebi.gov.in/legal/orders/mar-2026/margin-reporting.html",
            "tags": json.dumps(["margin", "compliance"]),
            "published_at": "2026-03-12T00:00:00+00:00",
        },
        {
            "id": "upd_bse_dup_1",
            "site": "bse",
            "type": "notice",
            "category": "notice",
            "title": "BSE Notice | SEBI order on margin reporting",
            "date": "2026-03-12",
            "summary": "Mirror copy of SEBI order on margin reporting",
            "url": "https://www.bseindia.com/markets/notice/sebi-order-on-margin-reporting.pdf",
            "tags": json.dumps(["margin", "compliance", "mirror"]),
            "published_at": "2026-03-12T00:00:00+00:00",
        },
        {
            "id": "upd_nse_1",
            "site": "nse",
            "type": "circular",
            "category": "circular",
            "title": "NSE/CMTR/99999 | New member circular",
            "date": "2026-03-11",
            "summary": "New member circular",
            "url": "https://nsearchives.nseindia.com/content/circulars/CMTR99999.zip",
            "tags": json.dumps(["trading", "member"]),
            "published_at": "2026-03-11T00:00:00+00:00",
        },
        {
            "id": "upd_cbdt_1",
            "site": "cbdt",
            "type": "notification",
            "category": "notification",
            "title": "CBDT notification on tax reporting update",
            "date": "2026-03-10",
            "summary": "CBDT notification on tax reporting update",
            "url": "https://incometaxindia.gov.in/communications/notification/notification-tax-reporting-2026.pdf",
            "tags": json.dumps(["tax", "reporting"]),
            "published_at": "2026-03-10T00:00:00+00:00",
        },
    ]

    with module.get_db() as conn:
        cursor = conn.cursor()
        for row in seeded_updates:
            cursor.execute(
                """
                INSERT INTO updates
                (id, site, type, category, title, date, time, summary, content, url, reference_number,
                 effective_date, expiry_date, tags, priority, source, published_at, fetched_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, '', ?, '', ?, NULL, NULL, NULL, ?, 'normal', 'scraped', ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["site"],
                    row["type"],
                    row["category"],
                    row["title"],
                    row["date"],
                    row["summary"],
                    row["url"],
                    row["tags"],
                    row["published_at"],
                    now,
                    now,
                    now,
                ),
            )
        conn.commit()
    return seeded_updates


def run_validation(output_path: Path) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    with TemporaryDirectory(prefix="broker_alerts_validation_") as temp_dir:
        temp_root = Path(temp_dir)
        db_path = temp_root / "broker_alerts_validation.db"
        create_updates_table(db_path)
        module = load_api_module(db_path)
        dispatch_module = load_dispatch_module()
        seeded_updates = seed_updates(module)
        client = TestClient(module.app)

        server, thread = start_recording_server()
        try:
            profile_response = client.get("/profiles/broker-alerts-v1")
            profile_payload = profile_response.json()
            expected_core_total = len(profile_payload.get("core_sources", []))

            health_response = client.get("/api/source-health")
            subscriptions_before = client.get("/api/source-subscriptions")
            update_subscriptions = client.put(
                "/api/source-subscriptions",
                json={"profile_name": "broker_alerts_v1", "site_keys": ["sebi", "bse", "nse", "cbdt"]},
            )
            events_response = client.get("/api/events")
            events_payload = events_response.json()
            event_id = events_payload["events"][0]["event_id"]
            event_detail_response = client.get(f"/api/events/{event_id}")

            webhook_response = client.post(
                "/api/webhooks",
                json={
                    "url": f"http://127.0.0.1:{server.server_port}/hook",
                    "name": "broker-alerts-validation",
                    "profile_name": "broker_alerts_v1",
                    "site_keys": ["sebi", "bse", "nse", "cbdt"],
                    "confidence_filter": "verified",
                    "retry_count": 1,
                    "timeout_seconds": 10,
                },
            )
            webhook = webhook_response.json()["webhook"]

            dry_run_response = client.post(
                f"/api/webhooks/{webhook['id']}/replay",
                json={"limit": 10, "force": False, "dry_run": True},
            )
            dispatch_result = asyncio.run(
                dispatch_module.dispatch_webhooks(
                    db_path=db_path,
                    webhook_id=webhook["id"],
                    limit=10,
                    dry_run=False,
                )
            )
            second_replay_response = client.post(
                f"/api/webhooks/{webhook['id']}/replay",
                json={"limit": 10, "force": False, "dry_run": False},
            )
            deliveries_response = client.get(f"/api/webhooks/{webhook['id']}/deliveries")
            dead_letters_response = client.get(f"/api/webhooks/{webhook['id']}/dead-letters")
            webhook_health_response = client.get(f"/api/webhooks/{webhook['id']}/health")
            ops_response = client.get("/api/ops/latest-sync")

            records = [trim_record(record) for record in RecordingHandler.records]
        finally:
            server.shutdown()
            thread.join(timeout=2)

    health_payload = health_response.json()
    subscriptions_before_payload = subscriptions_before.json()
    subscriptions_after_payload = update_subscriptions.json()
    dry_run_payload = dry_run_response.json()
    second_replay_payload = second_replay_response.json()
    deliveries_payload = deliveries_response.json()
    dead_letters_payload = dead_letters_response.json()
    webhook_health_payload = webhook_health_response.json()
    ops_payload = ops_response.json()

    validation_checks = {
        "profile_read_ok": profile_response.status_code == 200,
        "source_health_ok": health_response.status_code == 200,
        "subscriptions_read_ok": subscriptions_before.status_code == 200,
        "subscriptions_update_ok": update_subscriptions.status_code == 200,
        "events_read_ok": events_response.status_code == 200 and events_payload.get("total", 0) >= 3,
        "event_detail_ok": event_detail_response.status_code == 200,
        "webhook_create_ok": webhook_response.status_code == 200,
        "webhook_dry_run_ok": dry_run_response.status_code == 200 and dry_run_payload.get("delivered") == dry_run_payload.get("processed"),
        "dispatch_worker_ok": dispatch_result.get("delivered", 0) >= 1,
        "webhook_dedupe_ok": second_replay_response.status_code == 200 and second_replay_payload.get("delivered") == 0,
        "deliveries_visible_ok": deliveries_response.status_code == 200 and len(deliveries_payload.get("deliveries", [])) >= 1,
        "dead_letters_clear_ok": dead_letters_response.status_code == 200 and dead_letters_payload.get("total") == 0,
        "webhook_health_ok": webhook_health_response.status_code == 200 and webhook_health_payload.get("summary", {}).get("open_dead_letters") == 0,
        "ops_endpoint_ok": ops_response.status_code == 200 and "webhook_ops" in ops_payload,
        "signed_delivery_ok": bool(records and records[0]["headers"].get("X-GovUpdate-Signature")),
        "idempotency_ok": bool(records and records[0]["headers"].get("Idempotency-Key")),
        "internal_fields_hidden_ok": bool(records and "dedupe_key" not in ((records[0].get("body") or {}).get("event") or {})),
        "core_source_count_ok": health_payload.get("total") == expected_core_total,
    }

    artifact = {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "all_checks_passed": all(validation_checks.values()),
        "validation_checks": validation_checks,
        "seeded_updates": seeded_updates,
        "profile": profile_payload,
        "source_health": health_payload,
        "subscriptions": {
            "before": subscriptions_before_payload,
            "after": subscriptions_after_payload,
        },
        "events": {
            "total": events_payload.get("total", 0),
            "site_keys": [event.get("source_key") for event in events_payload.get("events", [])],
            "sample_event": events_payload.get("events", [None])[0],
            "event_detail": event_detail_response.json() if event_detail_response.status_code == 200 else None,
        },
        "webhook": {
            "created": webhook_response.json(),
            "dry_run": dry_run_payload,
            "dispatch_worker": dispatch_result,
            "second_replay": second_replay_payload,
            "deliveries": deliveries_payload,
            "dead_letters": dead_letters_payload,
            "health": webhook_health_payload,
            "records": records,
        },
        "ops": ops_payload,
    }
    output_path.resolve().write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the broker alerts API and webhook flow.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    artifact = run_validation(args.output.resolve())
    status = "passed" if artifact["all_checks_passed"] else "failed"
    print(f"Broker alerts validation {status}. Latest artifact written to {args.output.resolve()}")
    return 0 if artifact["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
