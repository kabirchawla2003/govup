import argparse
import asyncio
import importlib.util
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
MODULE_PATH = SRC_DIR / "main-v9-broker-enhanced.py"
DEFAULT_DB_PATH = ROOT / "data" / "govupdate.db"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_module(db_path: Path):
    os.environ["DB_PATH"] = str(db_path)
    sys.path.insert(0, str(SRC_DIR))
    for name in ["main_v8", "main_v9", "additional_sources"]:
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location("main_v9", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["main_v9"] = module
    spec.loader.exec_module(module)
    return module


def db_counts(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        result = {}
        for table in ("updates", "update_site_mappings", "attachments", "scraping_logs"):
            try:
                result[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                result[table] = None
        return result
    finally:
        conn.close()


async def run_refresh(db_path: Path) -> dict:
    module = load_module(db_path)
    module.init_db()
    before = db_counts(db_path)
    started_at = utcnow_iso()
    await module.process_all_sites()
    after = db_counts(db_path)
    return {
        "started_at": started_at,
        "completed_at": utcnow_iso(),
        "db_path": str(db_path),
        "before": before,
        "after": after,
        "delta": {
            key: (after.get(key) or 0) - (before.get(key) or 0)
            for key in after.keys()
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full local persistence refresh into the scraper DB.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Target local scraper DB path.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON summary path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(run_refresh(args.db.resolve()))
    if args.output:
        args.output.resolve().write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
