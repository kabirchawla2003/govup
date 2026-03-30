"""
Initialize and upgrade the open-source broker alerts schema.
"""
import os
import sqlite3
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

if load_dotenv:
    load_dotenv(Path(__file__).resolve().parent / ".env")

DB_PATH = os.getenv("DB_PATH", "./data/govupdate.db")


def table_exists(cursor, name: str) -> bool:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cursor.fetchone() is not None


def view_exists(cursor, name: str) -> bool:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='view' AND name=?", (name,))
    return cursor.fetchone() is not None


def get_columns(cursor, table_name: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def ensure_column(cursor, table_name: str, column_name: str, column_definition: str) -> None:
    existing_columns = set(get_columns(cursor, table_name))
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def ensure_circulars_view(cursor) -> None:
    """Expose scraper updates through a stable circulars view."""
    if table_exists(cursor, "circulars"):
        return

    if view_exists(cursor, "circulars"):
        cursor.execute("DROP VIEW circulars")

    if table_exists(cursor, "updates") and table_exists(cursor, "update_site_mappings"):
        cursor.execute(
            """
            CREATE VIEW circulars AS
            SELECT
                updates.id AS id,
                COALESCE(update_site_mappings.site, updates.site) AS site_key,
                updates.site AS primary_site,
                COALESCE(update_site_mappings.type, updates.type) AS type,
                COALESCE(update_site_mappings.category, updates.category) AS category,
                updates.title AS title,
                updates.date AS date,
                updates.time AS time,
                updates.summary AS description,
                updates.summary AS summary,
                updates.content AS content,
                updates.url AS url,
                updates.reference_number AS reference_number,
                updates.effective_date AS effective_date,
                updates.expiry_date AS expiry_date,
                updates.tags AS tags,
                updates.priority AS priority,
                COALESCE(update_site_mappings.source, updates.source) AS source,
                updates.published_at AS published_at,
                updates.fetched_at AS fetched_at,
                updates.created_at AS created_at,
                updates.updated_at AS updated_at
            FROM updates
            LEFT JOIN update_site_mappings
                ON update_site_mappings.update_id = updates.id
            """
        )
    elif table_exists(cursor, "updates"):
        cursor.execute(
            """
            CREATE VIEW circulars AS
            SELECT
                id,
                site AS site_key,
                site AS primary_site,
                type,
                category,
                title,
                date,
                time,
                summary AS description,
                summary,
                content,
                url,
                reference_number,
                effective_date,
                expiry_date,
                tags,
                priority,
                published_at,
                fetched_at,
                source,
                created_at,
                updated_at
            FROM updates
            """
        )


def migrate_legacy_webhooks(cursor) -> None:
    if not table_exists(cursor, "user_webhooks") or not table_exists(cursor, "webhooks"):
        return

    cursor.execute("SELECT COUNT(*) FROM webhooks")
    if cursor.fetchone()[0]:
        return

    cursor.execute(
        """
        INSERT INTO webhooks
        (
            id, url, name, secret, profile_name, site_filter, type_filter, category_filter,
            site_keys_json, confidence_filter, include_degraded, is_active, retry_count,
            timeout_seconds, success_count, failure_count, consecutive_failure_count,
            dead_letter_count, pause_on_failure_threshold, auto_paused, last_triggered,
            last_success, last_failure, last_delivery_status, last_delivery_http_status,
            last_delivery_latency_ms, last_error, last_event_published_at, last_event_id,
            created_at, updated_at
        )
        SELECT
            id, url, name, secret, COALESCE(profile_name, 'broker_alerts_v1'),
            site_filter, type_filter, category_filter, site_keys_json,
            COALESCE(confidence_filter, 'verified'), COALESCE(include_degraded, 0),
            is_active, retry_count, timeout_seconds, success_count, failure_count,
            consecutive_failure_count, dead_letter_count, pause_on_failure_threshold,
            auto_paused, last_triggered, last_success, last_failure, last_delivery_status,
            last_delivery_http_status, last_delivery_latency_ms, last_error,
            last_event_published_at, last_event_id, created_at, updated_at
        FROM user_webhooks
        ORDER BY id
        """
    )


def migrate_legacy_source_subscriptions(cursor) -> None:
    if not table_exists(cursor, "user_source_subscriptions") or not table_exists(cursor, "source_subscriptions"):
        return

    cursor.execute("SELECT COUNT(*) FROM source_subscriptions")
    if cursor.fetchone()[0]:
        return

    cursor.execute(
        """
        INSERT OR IGNORE INTO source_subscriptions (profile_name, site_key, created_at, updated_at)
        SELECT profile_name, site_key, MIN(created_at), MAX(updated_at)
        FROM user_source_subscriptions
        GROUP BY profile_name, site_key
        """
    )


def migrate_legacy_delivery_tables(cursor) -> None:
    if table_exists(cursor, "webhook_deliveries_legacy") or table_exists(cursor, "webhook_dead_letters_legacy"):
        return

    if table_exists(cursor, "webhook_deliveries"):
        columns = set(get_columns(cursor, "webhook_deliveries"))
        if "user_id" in columns:
            cursor.execute("ALTER TABLE webhook_deliveries RENAME TO webhook_deliveries_legacy")

    if table_exists(cursor, "webhook_dead_letters"):
        columns = set(get_columns(cursor, "webhook_dead_letters"))
        if "user_id" in columns:
            cursor.execute("ALTER TABLE webhook_dead_letters RENAME TO webhook_dead_letters_legacy")


def backfill_legacy_delivery_rows(cursor) -> None:
    if table_exists(cursor, "webhook_deliveries_legacy") and table_exists(cursor, "webhook_deliveries"):
        cursor.execute("SELECT COUNT(*) FROM webhook_deliveries")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                """
                INSERT INTO webhook_deliveries
                (
                    id, webhook_id, event_id, delivery_id, replayed, status, attempt_count,
                    http_status, request_headers, request_body, response_body, error,
                    latency_ms, sent_at, created_at
                )
                SELECT
                    id, webhook_id, event_id, delivery_id, replayed, status, attempt_count,
                    http_status, request_headers, request_body, response_body, error,
                    latency_ms, sent_at, created_at
                FROM webhook_deliveries_legacy
                ORDER BY id
                """
            )

    if table_exists(cursor, "webhook_dead_letters_legacy") and table_exists(cursor, "webhook_dead_letters"):
        cursor.execute("SELECT COUNT(*) FROM webhook_dead_letters")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                """
                INSERT INTO webhook_dead_letters
                (
                    id, webhook_id, event_id, delivery_id, request_headers, request_body,
                    http_status, error, response_body, created_at, resolved_at, resolution_status
                )
                SELECT
                    id, webhook_id, event_id, delivery_id, request_headers, request_body,
                    http_status, error, response_body, created_at, resolved_at, resolution_status
                FROM webhook_dead_letters_legacy
                ORDER BY id
                """
            )


def init_saas_schema():
    """Create or upgrade the OSS broker alerts schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        migrate_legacy_delivery_tables(cursor)

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                name TEXT NOT NULL,
                secret TEXT,
                profile_name TEXT NOT NULL DEFAULT 'broker_alerts_v1',
                site_filter TEXT,
                type_filter TEXT,
                category_filter TEXT,
                site_keys_json TEXT,
                confidence_filter TEXT DEFAULT 'verified',
                include_degraded BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                retry_count INTEGER DEFAULT 3,
                timeout_seconds INTEGER DEFAULT 30,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                consecutive_failure_count INTEGER DEFAULT 0,
                dead_letter_count INTEGER DEFAULT 0,
                pause_on_failure_threshold INTEGER DEFAULT 5,
                auto_paused BOOLEAN DEFAULT 0,
                last_triggered TIMESTAMP,
                last_success TIMESTAMP,
                last_failure TIMESTAMP,
                last_delivery_status TEXT,
                last_delivery_http_status INTEGER,
                last_delivery_latency_ms INTEGER,
                last_error TEXT,
                last_event_published_at TEXT,
                last_event_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS source_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_name TEXT NOT NULL DEFAULT 'broker_alerts_v1',
                site_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(profile_name, site_key)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_id INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                delivery_id TEXT NOT NULL,
                replayed BOOLEAN DEFAULT 0,
                status TEXT NOT NULL,
                attempt_count INTEGER DEFAULT 0,
                http_status INTEGER,
                request_headers TEXT,
                request_body TEXT,
                response_body TEXT,
                error TEXT,
                latency_ms INTEGER,
                sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (webhook_id) REFERENCES webhooks(id) ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS webhook_dead_letters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_id INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                delivery_id TEXT NOT NULL,
                request_headers TEXT,
                request_body TEXT,
                http_status INTEGER,
                error TEXT,
                response_body TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                resolution_status TEXT,
                FOREIGN KEY (webhook_id) REFERENCES webhooks(id) ON DELETE CASCADE
            )
            """
        )

        ensure_column(cursor, "webhooks", "profile_name", "TEXT DEFAULT 'broker_alerts_v1'")
        ensure_column(cursor, "webhooks", "site_keys_json", "TEXT")
        ensure_column(cursor, "webhooks", "confidence_filter", "TEXT DEFAULT 'verified'")
        ensure_column(cursor, "webhooks", "include_degraded", "BOOLEAN DEFAULT 0")
        ensure_column(cursor, "webhooks", "last_event_published_at", "TEXT")
        ensure_column(cursor, "webhooks", "last_event_id", "TEXT")
        ensure_column(cursor, "webhooks", "consecutive_failure_count", "INTEGER DEFAULT 0")
        ensure_column(cursor, "webhooks", "dead_letter_count", "INTEGER DEFAULT 0")
        ensure_column(cursor, "webhooks", "pause_on_failure_threshold", "INTEGER DEFAULT 5")
        ensure_column(cursor, "webhooks", "auto_paused", "BOOLEAN DEFAULT 0")
        ensure_column(cursor, "webhooks", "last_delivery_status", "TEXT")
        ensure_column(cursor, "webhooks", "last_delivery_http_status", "INTEGER")
        ensure_column(cursor, "webhooks", "last_delivery_latency_ms", "INTEGER")
        ensure_column(cursor, "webhook_deliveries", "latency_ms", "INTEGER")

        migrate_legacy_webhooks(cursor)
        migrate_legacy_source_subscriptions(cursor)
        backfill_legacy_delivery_rows(cursor)
        ensure_circulars_view(cursor)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhooks_active ON webhooks(is_active)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhooks_profile ON webhooks(profile_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_subscriptions_profile ON source_subscriptions(profile_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_event ON webhook_deliveries(event_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status ON webhook_deliveries(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_dead_letters_webhook ON webhook_dead_letters(webhook_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_dead_letters_event ON webhook_dead_letters(event_id)")

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


init_api_schema = init_saas_schema


if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_api_schema()
    print("Broker alerts database schema initialized.")
