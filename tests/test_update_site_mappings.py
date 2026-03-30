import asyncio
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "main-v7-fixed.py"
sys.path.insert(0, str(ROOT / "src"))

spec = importlib.util.spec_from_file_location("main_v7_test_module", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules["main_v7_test_module"] = module
spec.loader.exec_module(module)


async def _noop_async(*args, **kwargs):
    return None


def test_save_update_creates_one_canonical_row_with_multiple_site_mappings(tmp_path):
    db_path = tmp_path / "schema-test.db"
    module.DB_PATH = str(db_path)
    module.trigger_webhook = _noop_async
    module.send_email_alert = _noop_async
    module.init_db()

    item = {
        "site": "sebi",
        "title": "Shared circular",
        "link": "https://example.com/shared-circular.pdf",
        "type": "circular",
        "category": "circular",
        "pub_date": "2026-03-08T00:00:00+00:00",
        "content_snippet": "Shared circular",
        "source": "scraped",
    }
    alias_item = {
        **item,
        "site": "sebi_intermediaries",
    }

    async def run():
        conn = module.get_db()
        try:
            first_id = await module.save_update(conn, item)
            second_id = await module.save_update(conn, alias_item)
            third_id = await module.save_update(conn, alias_item)

            update_count = conn.execute("SELECT COUNT(*) FROM updates").fetchone()[0]
            mapping_count = conn.execute("SELECT COUNT(*) FROM update_site_mappings").fetchone()[0]
            sites = [
                row["site"]
                for row in conn.execute(
                    "SELECT site FROM update_site_mappings WHERE update_id = ? ORDER BY site",
                    (first_id,),
                ).fetchall()
            ]
            return first_id, second_id, third_id, update_count, mapping_count, sites
        finally:
            conn.close()

    first_id, second_id, third_id, update_count, mapping_count, sites = asyncio.run(run())

    assert first_id is not None
    assert second_id == first_id
    assert third_id is None
    assert update_count == 1
    assert mapping_count == 2
    assert sites == ["sebi", "sebi_intermediaries"]
