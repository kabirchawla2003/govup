import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "govupdate.db"
DEFAULT_OUTPUT_PATH = ROOT / "output" / "scraped_updates_export_latest.json"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def chunked(values: Sequence[str], size: int = 500) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def fetch_rows(cursor: sqlite3.Cursor, query: str, params: Sequence[object] = ()) -> List[dict]:
    cursor.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def build_where_clause(site_keys: Sequence[str], since: str | None) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []

    if site_keys:
        placeholders = ",".join("?" for _ in site_keys)
        clauses.append(
            f"""id IN (
                    SELECT DISTINCT update_id
                    FROM update_site_mappings
                    WHERE site IN ({placeholders})
                )"""
        )
        params.extend(site_keys)

    if since:
        clauses.append(
            "COALESCE(fetched_at, published_at, updated_at, created_at, date) >= ?"
        )
        params.append(since)

    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def export_updates(db_path: Path, output_path: Path, site_keys: Sequence[str], since: str | None) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        where_clause, params = build_where_clause(site_keys, since)
        updates = fetch_rows(
            cursor,
            f"""
            SELECT *
            FROM updates
            {where_clause}
            ORDER BY COALESCE(published_at, fetched_at, updated_at, created_at, date) ASC, id ASC
            """,
            params,
        )
        update_ids = [str(row["id"]) for row in updates if row.get("id")]

        mappings: list[dict] = []
        attachments: list[dict] = []
        for group in chunked(update_ids):
            placeholders = ",".join("?" for _ in group)
            mappings.extend(
                fetch_rows(
                    cursor,
                    f"""
                    SELECT *
                    FROM update_site_mappings
                    WHERE update_id IN ({placeholders})
                    ORDER BY update_id ASC, site ASC
                    """,
                    list(group),
                )
            )
            attachments.extend(
                fetch_rows(
                    cursor,
                    f"""
                    SELECT *
                    FROM attachments
                    WHERE update_id IN ({placeholders})
                    ORDER BY update_id ASC, id ASC
                    """,
                    list(group),
                )
            )
    finally:
        conn.close()

    payload = {
        "exported_at": utcnow_iso(),
        "db_path": str(db_path),
        "site_keys": list(site_keys),
        "since": since,
        "counts": {
            "updates": len(updates),
            "site_mappings": len(mappings),
            "attachments": len(attachments),
        },
        "updates": updates,
        "site_mappings": mappings,
        "attachments": attachments,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export persisted scraped updates for server-side import.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Local scraper DB path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Export JSON path.")
    parser.add_argument("--site-key", dest="site_keys", action="append", default=[], help="Optional site key filter. Repeat for multiple values.")
    parser.add_argument("--since", default=None, help="Optional ISO timestamp/date lower bound.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = export_updates(
        db_path=args.db.resolve(),
        output_path=args.output.resolve(),
        site_keys=args.site_keys,
        since=args.since,
    )
    print(json.dumps(payload["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
