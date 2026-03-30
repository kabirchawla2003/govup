import argparse
import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
API_PATH = SRC_DIR / "api.py"
DEFAULT_OUTPUT_PATH = ROOT / "broker_webhook_dispatch_latest.json"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC_DIR))


def load_api_module(db_path: Path):
    os.environ["DB_PATH"] = str(db_path)
    for module_name in [
        "auth_models",
        "broker_alerts",
        "init_api_db",
        "api_dispatch_module",
    ]:
        sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location("api_dispatch_module", API_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["api_dispatch_module"] = module
    spec.loader.exec_module(module)
    return module


def get_active_webhooks(module, webhook_id: Optional[int] = None) -> list[dict]:
    with module.get_db() as conn:
        cursor = conn.cursor()
        if webhook_id is not None:
            cursor.execute(
                """
                SELECT id
                FROM webhooks
                WHERE id = ? AND is_active = 1
                """,
                (webhook_id,),
            )
        else:
            cursor.execute(
                """
                SELECT id
                FROM webhooks
                WHERE is_active = 1
                ORDER BY id ASC
                """
            )
        rows = [dict(row) for row in cursor.fetchall()]

    webhooks = []
    for row in rows:
        webhook = module.get_webhook(row["id"], include_secret=True)
        if webhook:
            webhooks.append(webhook)
    return webhooks


async def dispatch_webhooks(db_path: Path, webhook_id: Optional[int], limit: int, dry_run: bool) -> dict:
    module = load_api_module(db_path)
    webhooks = get_active_webhooks(module, webhook_id=webhook_id)

    results = []
    total_processed = 0
    total_delivered = 0
    total_skipped = 0

    for webhook in webhooks:
        result = await module.replay_webhook_events(
            webhook=webhook,
            limit=limit,
            force=False,
            dry_run=dry_run,
        )
        results.append(result)
        total_processed += result.get("processed", 0)
        total_delivered += result.get("delivered", 0)
        total_skipped += result.get("skipped", 0)

    return {
        "db_path": str(db_path),
        "webhook_count": len(webhooks),
        "processed": total_processed,
        "delivered": total_delivered,
        "skipped": total_skipped,
        "dry_run": dry_run,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch broker alert webhooks for all active webhook targets.")
    parser.add_argument("--db", type=Path, required=True, help="Path to the broker alerts database.")
    parser.add_argument("--webhook-id", type=int, default=None, help="Optional single webhook id to dispatch.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum events per webhook.")
    parser.add_argument("--dry-run", action="store_true", help="Compute deliveries without sending requests.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path for the JSON dispatch artifact.",
    )
    args = parser.parse_args()

    artifact = asyncio.run(
        dispatch_webhooks(
            db_path=args.db.resolve(),
            webhook_id=args.webhook_id,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    )
    args.output.resolve().write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"Dispatch complete. Artifact written to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
