import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = ROOT / "output" / "scraped_updates_export_latest.json"
DEFAULT_TARGET_DB = ROOT / "data" / "govupdate.db"
sys.path.insert(0, str(ROOT))


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_target_schema(target_db: Path) -> None:
    os.environ["DB_PATH"] = str(target_db)
    import init_api_db

    init_api_db.DB_PATH = str(target_db)
    init_api_db.init_api_schema()

    conn = sqlite3.connect(str(target_db))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS updates (
                id TEXT PRIMARY KEY,
                site TEXT NOT NULL,
                type TEXT NOT NULL,
                category TEXT,
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT,
                summary TEXT,
                content TEXT,
                url TEXT NOT NULL UNIQUE,
                reference_number TEXT,
                effective_date TEXT,
                expiry_date TEXT,
                tags TEXT,
                priority TEXT DEFAULT 'normal',
                source TEXT NOT NULL DEFAULT 'scraped',
                published_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS update_site_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_id TEXT NOT NULL,
                site TEXT NOT NULL,
                type TEXT NOT NULL,
                category TEXT,
                source TEXT NOT NULL DEFAULT 'scraped',
                mapped_at TEXT NOT NULL,
                FOREIGN KEY (update_id) REFERENCES updates(id) ON DELETE CASCADE,
                UNIQUE(update_id, site)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_id TEXT NOT NULL,
                url TEXT NOT NULL,
                filename TEXT,
                file_type TEXT,
                file_size INTEGER,
                FOREIGN KEY (update_id) REFERENCES updates(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_updates_url ON updates(url)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_update_site_mappings_update_id ON update_site_mappings(update_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_update_site_mappings_site ON update_site_mappings(site)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_attachments_update_id ON attachments(update_id)")
        init_api_db.ensure_circulars_view(cur)
        conn.commit()
    finally:
        conn.close()


def load_export(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def upsert_update(cursor: sqlite3.Cursor, row: dict) -> str:
    existing = cursor.execute("SELECT id FROM updates WHERE url = ?", (row["url"],)).fetchone()
    if existing:
        update_id = str(existing["id"])
        cursor.execute(
            """
            UPDATE updates
            SET site = ?,
                type = ?,
                category = ?,
                title = ?,
                date = ?,
                time = ?,
                summary = ?,
                content = ?,
                reference_number = ?,
                effective_date = ?,
                expiry_date = ?,
                tags = ?,
                priority = ?,
                source = ?,
                published_at = ?,
                fetched_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                row.get("site"),
                row.get("type"),
                row.get("category"),
                row.get("title"),
                row.get("date"),
                row.get("time"),
                row.get("summary"),
                row.get("content"),
                row.get("reference_number"),
                row.get("effective_date"),
                row.get("expiry_date"),
                row.get("tags"),
                row.get("priority"),
                row.get("source"),
                row.get("published_at"),
                row.get("fetched_at"),
                row.get("updated_at") or utcnow_iso(),
                update_id,
            ),
        )
        return update_id

    update_id = str(row["id"])
    cursor.execute(
        """
        INSERT INTO updates
        (id, site, type, category, title, date, time, summary, content, url,
         reference_number, effective_date, expiry_date, tags, priority, source,
         published_at, fetched_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            update_id,
            row.get("site"),
            row.get("type"),
            row.get("category"),
            row.get("title"),
            row.get("date"),
            row.get("time"),
            row.get("summary"),
            row.get("content"),
            row.get("url"),
            row.get("reference_number"),
            row.get("effective_date"),
            row.get("expiry_date"),
            row.get("tags"),
            row.get("priority"),
            row.get("source"),
            row.get("published_at"),
            row.get("fetched_at"),
            row.get("created_at") or utcnow_iso(),
            row.get("updated_at") or utcnow_iso(),
        ),
    )
    return update_id


def upsert_mapping(cursor: sqlite3.Cursor, row: dict, update_id: str) -> bool:
    existing = cursor.execute(
        "SELECT id FROM update_site_mappings WHERE update_id = ? AND site = ?",
        (update_id, row["site"]),
    ).fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE update_site_mappings
            SET type = ?, category = ?, source = ?, mapped_at = ?
            WHERE id = ?
            """,
            (
                row.get("type"),
                row.get("category"),
                row.get("source"),
                row.get("mapped_at") or utcnow_iso(),
                existing["id"],
            ),
        )
        return False

    cursor.execute(
        """
        INSERT INTO update_site_mappings (update_id, site, type, category, source, mapped_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            update_id,
            row.get("site"),
            row.get("type"),
            row.get("category"),
            row.get("source"),
            row.get("mapped_at") or utcnow_iso(),
        ),
    )
    return True


def upsert_attachment(cursor: sqlite3.Cursor, row: dict, update_id: str) -> bool:
    existing = cursor.execute(
        "SELECT id FROM attachments WHERE update_id = ? AND url = ?",
        (update_id, row["url"]),
    ).fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE attachments
            SET filename = ?, file_type = ?, file_size = ?
            WHERE id = ?
            """,
            (
                row.get("filename"),
                row.get("file_type"),
                row.get("file_size") if row.get("file_size") is not None else row.get("size_bytes"),
                existing["id"],
            ),
        )
        return False

    cursor.execute(
        """
        INSERT INTO attachments (update_id, url, filename, file_type, file_size)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            update_id,
            row.get("url"),
            row.get("filename"),
            row.get("file_type"),
            row.get("file_size") if row.get("file_size") is not None else row.get("size_bytes"),
        ),
    )
    return True


def import_updates(input_path: Path, target_db: Path) -> dict:
    ensure_target_schema(target_db)
    payload = load_export(input_path)
    update_id_map: dict[str, str] = {}

    conn = sqlite3.connect(str(target_db))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()

        inserted_updates = 0
        updated_updates = 0
        for row in payload.get("updates") or []:
            existing = cursor.execute("SELECT id FROM updates WHERE url = ?", (row["url"],)).fetchone()
            update_id = upsert_update(cursor, row)
            update_id_map[str(row["id"])] = update_id
            if existing:
                updated_updates += 1
            else:
                inserted_updates += 1

        inserted_mappings = 0
        updated_mappings = 0
        for row in payload.get("site_mappings") or []:
            update_id = update_id_map.get(str(row["update_id"]))
            if not update_id:
                continue
            inserted = upsert_mapping(cursor, row, update_id)
            if inserted:
                inserted_mappings += 1
            else:
                updated_mappings += 1

        inserted_attachments = 0
        updated_attachments = 0
        for row in payload.get("attachments") or []:
            update_id = update_id_map.get(str(row["update_id"]))
            if not update_id:
                continue
            inserted = upsert_attachment(cursor, row, update_id)
            if inserted:
                inserted_attachments += 1
            else:
                updated_attachments += 1

        conn.commit()
    finally:
        conn.close()

    return {
        "imported_at": utcnow_iso(),
        "target_db": str(target_db),
        "input_path": str(input_path),
        "counts": {
            "updates_inserted": inserted_updates,
            "updates_updated": updated_updates,
            "mappings_inserted": inserted_mappings,
            "mappings_updated": updated_mappings,
            "attachments_inserted": inserted_attachments,
            "attachments_updated": updated_attachments,
            "updates_in_payload": len(payload.get("updates") or []),
            "mappings_in_payload": len(payload.get("site_mappings") or []),
            "attachments_in_payload": len(payload.get("attachments") or []),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge-import scraped updates into the broker alerts API database.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH, help="Export JSON path.")
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB, help="Target SaaS DB path.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON summary output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = import_updates(args.input.resolve(), args.target_db.resolve())
    if args.output:
        args.output.resolve().write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
