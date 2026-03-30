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

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
API_PATH = SRC_DIR / "api.py"
DISPATCH_SCRIPT_PATH = ROOT / "scripts" / "run_broker_webhook_dispatch.py"
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
        "api_test_module",
    ]:
        sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location("api_test_module", API_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["api_test_module"] = module
    spec.loader.exec_module(module)
    return module


def load_dispatch_module():
    spec = importlib.util.spec_from_file_location("broker_dispatch_test_module", DISPATCH_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["broker_dispatch_test_module"] = module
    spec.loader.exec_module(module)
    return module


class RecordingHandler(BaseHTTPRequestHandler):
    records = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        RecordingHandler.records.append(
            {
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": body.decode("utf-8"),
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return


class FailingHandler(BaseHTTPRequestHandler):
    records = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        FailingHandler.records.append(
            {
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": body.decode("utf-8"),
            }
        )
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b"fail")

    def log_message(self, format, *args):
        return


def start_recording_server():
    RecordingHandler.records = []
    server = HTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def start_failing_server():
    FailingHandler.records = []
    server = HTTPServer(("127.0.0.1", 0), FailingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def seed_events(module, now=None):
    now = now or datetime.now(timezone.utc)
    with module.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO updates
            (id, site, type, category, title, date, time, summary, content, url, reference_number,
             effective_date, expiry_date, tags, priority, source, published_at, fetched_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, '', ?, '', ?, NULL, NULL, NULL, ?, 'normal', 'scraped', ?, ?, ?, ?)
            """,
            (
                "upd_sebi_1",
                "sebi",
                "order",
                "order",
                "SEBI order on margin reporting",
                "2026-03-12",
                "SEBI order on margin reporting",
                "https://www.sebi.gov.in/legal/orders/mar-2026/margin-reporting.html",
                '["margin","compliance"]',
                "2026-03-12T00:00:00+00:00",
                now.isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        cursor.execute(
            """
            INSERT INTO updates
            (id, site, type, category, title, date, time, summary, content, url, reference_number,
             effective_date, expiry_date, tags, priority, source, published_at, fetched_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, '', ?, '', ?, NULL, NULL, NULL, ?, 'normal', 'scraped', ?, ?, ?, ?)
            """,
            (
                "upd_bse_dup_1",
                "bse",
                "notice",
                "notice",
                "BSE Notice | SEBI order on margin reporting",
                "2026-03-12",
                "Mirror copy of SEBI order on margin reporting",
                "https://www.bseindia.com/markets/notice/sebi-order-on-margin-reporting.pdf",
                '["margin","compliance","mirror"]',
                "2026-03-12T00:00:00+00:00",
                now.isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        cursor.execute(
            """
            INSERT INTO updates
            (id, site, type, category, title, date, time, summary, content, url, reference_number,
             effective_date, expiry_date, tags, priority, source, published_at, fetched_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, '', ?, '', ?, NULL, NULL, NULL, ?, 'normal', 'scraped', ?, ?, ?, ?)
            """,
            (
                "upd_nse_1",
                "nse",
                "circular",
                "circular",
                "NSE/CMTR/99999 | New member circular",
                "2026-03-11",
                "New member circular",
                "https://nsearchives.nseindia.com/content/circulars/CMTR99999.zip",
                '["trading","member"]',
                "2026-03-11T00:00:00+00:00",
                now.isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        conn.commit()


def build_client(tmp_path: Path):
    db_path = tmp_path / "alerts_test.db"
    create_updates_table(db_path)
    module = load_api_module(db_path)
    seed_events(module)
    client = TestClient(module.app)
    return module, client


def build_client_with_now(tmp_path: Path, now: datetime):
    db_path = tmp_path / "alerts_test.db"
    create_updates_table(db_path)
    module = load_api_module(db_path)
    seed_events(module, now=now)
    client = TestClient(module.app)
    return module, client


def build_client_with_db(tmp_path: Path, now=None):
    db_path = tmp_path / "alerts_test.db"
    create_updates_table(db_path)
    module = load_api_module(db_path)
    seed_events(module, now=now)
    client = TestClient(module.app)
    return module, client, db_path


def test_broker_profile_and_events_flow(tmp_path):
    _, client = build_client(tmp_path)

    profile_response = client.get("/profiles/broker-alerts-v1")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["profile_key"] == "broker_alerts_v1"
    assert "sebi" in profile["core_sources"]
    excluded = {entry["site_key"]: entry["reason"] for entry in profile["excluded_sources"]}
    assert "asba" in excluded
    assert "wrong site" in excluded["asba"].lower()

    events_response = client.get("/api/events")
    assert events_response.status_code == 200
    payload = events_response.json()
    assert payload["total"] == 2
    assert payload["events"][0]["event_id"].startswith("evt_")
    assert payload["events"][0]["confidence"] == "verified"
    assert payload["events"][0]["source_key"] == "sebi"
    assert payload["events"][0]["source_keys"] == ["sebi", "bse"]
    assert payload["events"][0]["mirror_count"] == 1
    assert payload["events"][1]["direct_file_url"].endswith(".zip")


def test_source_subscriptions_filter_event_feed(tmp_path):
    _, client = build_client(tmp_path)

    put_response = client.put(
        "/api/source-subscriptions",
        json={"profile_name": "broker_alerts_v1", "site_keys": ["sebi"]},
    )
    assert put_response.status_code == 200
    assert put_response.json()["site_keys"] == ["sebi"]

    events_response = client.get("/api/events")
    assert events_response.status_code == 200
    payload = events_response.json()
    assert payload["total"] == 1
    assert payload["events"][0]["source_key"] == "sebi"


def test_cross_source_dedupe_respects_site_filters(tmp_path):
    _, client = build_client(tmp_path)

    put_response = client.put(
        "/api/source-subscriptions",
        json={"profile_name": "broker_alerts_v1", "site_keys": ["bse"]},
    )
    assert put_response.status_code == 200

    events_response = client.get("/api/events")
    payload = events_response.json()
    assert payload["total"] == 1
    assert payload["events"][0]["source_key"] == "bse"
    assert payload["events"][0]["source_keys"] == ["bse"]
    assert payload["events"][0]["mirror_count"] == 0


def test_public_event_payload_hides_internal_fields(tmp_path):
    _, client = build_client(tmp_path)

    event = client.get("/api/events").json()["events"][0]
    assert "dedupe_key" not in event
    assert "source_dedupe_key" not in event
    assert "content_fingerprint" not in event
    assert "source_record_id" not in event
    assert event["canonical_url"].startswith("https://")


def test_webhook_replay_sends_signed_events_and_dedupes(tmp_path):
    _, client = build_client(tmp_path)
    server, thread = start_recording_server()
    try:
        webhook_response = client.post(
            "/api/webhooks",
            json={
                "url": f"http://127.0.0.1:{server.server_port}/hook",
                "name": "broker-alerts",
                "profile_name": "broker_alerts_v1",
                "site_keys": ["sebi", "nse"],
                "confidence_filter": "verified",
                "retry_count": 1,
                "timeout_seconds": 10,
            },
        )
        assert webhook_response.status_code == 200
        webhook = webhook_response.json()["webhook"]
        assert "secret" not in webhook
        assert webhook_response.json()["signing_secret"]

        replay_response = client.post(
            f"/api/webhooks/{webhook['id']}/replay",
            json={"limit": 10, "force": False, "dry_run": False},
        )
        assert replay_response.status_code == 200
        replay_payload = replay_response.json()
        assert replay_payload["delivered"] == 2
        assert len(RecordingHandler.records) == 2
        assert all(record["headers"].get("X-GovUpdate-Signature", "").startswith("sha256=") for record in RecordingHandler.records)
        assert all(record["headers"].get("Idempotency-Key", "").startswith("evt_") for record in RecordingHandler.records)
        delivered_event = json.loads(RecordingHandler.records[0]["body"])["event"]
        assert "dedupe_key" not in delivered_event
        assert "source_dedupe_key" not in delivered_event
        assert "content_fingerprint" not in delivered_event
        assert "source_record_id" not in delivered_event

        second_response = client.post(
            f"/api/webhooks/{webhook['id']}/replay",
            json={"limit": 10, "force": False, "dry_run": False},
        )
        second_payload = second_response.json()
        assert second_payload["delivered"] == 0
        assert second_payload["skipped"] >= 1
        assert len(RecordingHandler.records) == 2

        deliveries_response = client.get(f"/api/webhooks/{webhook['id']}/deliveries")
        deliveries = deliveries_response.json()["deliveries"]
        assert len(deliveries) >= 2
        assert all(item["status"] == "success" for item in deliveries[:2])

        list_response = client.get("/api/webhooks")
        assert "secret" not in list_response.json()["webhooks"][0]
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_webhook_auto_pauses_and_creates_dead_letter_on_repeated_failure(tmp_path):
    _, client = build_client(tmp_path)
    server, thread = start_failing_server()
    try:
        webhook_response = client.post(
            "/api/webhooks",
            json={
                "url": f"http://127.0.0.1:{server.server_port}/hook",
                "name": "failing-webhook",
                "profile_name": "broker_alerts_v1",
                "site_keys": ["sebi"],
                "confidence_filter": "verified",
                "retry_count": 1,
                "pause_on_failure_threshold": 1,
                "timeout_seconds": 5,
            },
        )
        webhook = webhook_response.json()["webhook"]
        assert webhook["auto_paused"] is False

        replay_response = client.post(
            f"/api/webhooks/{webhook['id']}/replay",
            json={"limit": 10, "force": False, "dry_run": False},
        )
        replay_payload = replay_response.json()
        assert replay_payload["delivered"] == 0
        assert replay_payload["deliveries"][0]["status"] == "failed"
        assert replay_payload["deliveries"][0]["dead_lettered"] is True
        assert replay_payload["deliveries"][0]["auto_paused"] is True

        refreshed = client.get("/api/webhooks").json()["webhooks"][0]
        assert refreshed["is_active"] is False
        assert refreshed["auto_paused"] is True
        assert refreshed["dead_letter_count"] == 1
        assert refreshed["consecutive_failure_count"] >= 1
        assert refreshed["last_delivery_status"] == "failed"

        dead_letters = client.get(f"/api/webhooks/{webhook['id']}/dead-letters").json()["dead_letters"]
        assert len(dead_letters) == 1
        assert dead_letters[0]["event_id"].startswith("evt_")
        assert dead_letters[0]["http_status"] == 500

        health = client.get(f"/api/webhooks/{webhook['id']}/health").json()["summary"]
        assert health["is_paused"] is True
        assert health["auto_paused"] is True
        assert health["open_dead_letters"] == 1
        assert health["failed_deliveries"] >= 1
        assert health["last_delivery_status"] == "failed"
        assert health["last_delivery_http_status"] == 500
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_broker_endpoints_accept_timezone_aware_dates(tmp_path):
    aware_now = datetime.now(timezone.utc)
    _, client = build_client_with_now(tmp_path, aware_now)

    response = client.get("/api/source-health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_key"] == "broker_alerts_v1"
    assert any(item["site_key"] == "sebi" for item in payload["sources"])


def test_root_and_circular_endpoints_are_public(tmp_path):
    _, client = build_client(tmp_path)

    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["service"] == "GovUpdate Broker Alerts API"

    circulars = client.get("/api/circulars")
    assert circulars.status_code == 200
    assert circulars.json()["total"] >= 3


def test_reliability_summary_exposes_sync_and_webhook_ops(tmp_path):
    previous_sync_manifest = os.environ.get("LOCAL_SYNC_MANIFEST_PATH")
    sync_manifest = tmp_path / "sync_manifest.json"
    sync_manifest.write_text(
        json.dumps(
            {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "ssh_target": "ubuntu@test",
                "server_service": "govup-test.service",
                "restart_log": "active",
                "remote_import_log": "import ok",
                "validation": {
                    "remote_artifact_check": {
                        "updates_count": 42,
                        "mappings_count": 50,
                        "attachments_count": 3,
                        "source_count": 96,
                        "sebi_status": "working",
                    },
                    "public_health_check": {"status_code": 200},
                },
            }
        ),
        encoding="utf-8",
    )
    os.environ["LOCAL_SYNC_MANIFEST_PATH"] = str(sync_manifest)
    try:
        _, client = build_client(tmp_path)
        payload = client.get("/api/ops/latest-sync").json()
        assert payload["latest_sync"]["state"] == "fresh"
        assert payload["latest_sync"]["remote_updates_count"] == 42
        assert payload["latest_sync"]["import_ran"] is True
        assert payload["webhook_ops"]["total_webhooks"] >= 0

        reliability_payload = client.get("/api/reliability/latest").json()
        assert reliability_payload["latest_sync"]["state"] == "fresh"
        assert "webhook_ops" in reliability_payload
    finally:
        if previous_sync_manifest is None:
            os.environ.pop("LOCAL_SYNC_MANIFEST_PATH", None)
        else:
            os.environ["LOCAL_SYNC_MANIFEST_PATH"] = previous_sync_manifest


def test_dispatch_script_replays_active_webhooks(tmp_path):
    _, client, db_path = build_client_with_db(tmp_path)
    dispatch_module = load_dispatch_module()
    server, thread = start_recording_server()
    try:
        webhook_response = client.post(
            "/api/webhooks",
            json={
                "url": f"http://127.0.0.1:{server.server_port}/hook",
                "name": "dispatch-worker",
                "profile_name": "broker_alerts_v1",
                "site_keys": ["sebi", "nse"],
                "retry_count": 0,
                "timeout_seconds": 10,
            },
        )
        webhook_id = webhook_response.json()["webhook"]["id"]

        result = asyncio.run(
            dispatch_module.dispatch_webhooks(
                db_path=db_path,
                webhook_id=webhook_id,
                limit=10,
                dry_run=False,
            )
        )

        assert result["webhook_count"] == 1
        assert result["delivered"] == 2
        assert len(RecordingHandler.records) == 2
    finally:
        server.shutdown()
        thread.join(timeout=2)
