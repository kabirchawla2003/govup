import importlib.util
import os
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORT_SCRIPT_PATH = ROOT / "scripts" / "export_scraped_updates.py"
IMPORT_SCRIPT_PATH = ROOT / "scripts" / "import_scraped_updates.py"
API_PATH = ROOT / "src" / "api.py"
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


export_module = load_module("export_scraped_updates_test_module", EXPORT_SCRIPT_PATH)
import_module = load_module("import_scraped_updates_test_module", IMPORT_SCRIPT_PATH)


def create_local_scraper_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE updates (
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
                priority TEXT,
                source TEXT,
                published_at TEXT,
                fetched_at TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE update_site_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_id TEXT NOT NULL,
                site TEXT NOT NULL,
                type TEXT NOT NULL,
                category TEXT,
                source TEXT,
                mapped_at TEXT,
                UNIQUE(update_id, site)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_id TEXT NOT NULL,
                url TEXT NOT NULL,
                filename TEXT,
                file_type TEXT,
                file_size INTEGER
            )
            """
        )
        rows = [
            (
                "upd_1",
                "sebi",
                "circular",
                "circular",
                "SEBI Circular One",
                "2026-03-20",
                "",
                "First circular",
                "",
                "https://www.sebi.gov.in/circulars/one.pdf",
                "SEBI/HO/123",
                None,
                None,
                '["broker"]',
                "normal",
                "scraped",
                "2026-03-20T10:00:00+00:00",
                "2026-03-20T10:01:00+00:00",
                "2026-03-20T10:01:00+00:00",
                "2026-03-20T10:01:00+00:00",
            ),
            (
                "upd_2",
                "sebi",
                "circular",
                "circular",
                "SEBI Circular Two",
                "2026-03-20",
                "",
                "Second circular",
                "",
                "https://www.sebi.gov.in/circulars/two.pdf",
                "SEBI/HO/124",
                None,
                None,
                '["broker"]',
                "normal",
                "scraped",
                "2026-03-20T11:00:00+00:00",
                "2026-03-20T11:01:00+00:00",
                "2026-03-20T11:01:00+00:00",
                "2026-03-20T11:01:00+00:00",
            ),
        ]
        cur.executemany(
            """
            INSERT INTO updates
            (id, site, type, category, title, date, time, summary, content, url, reference_number,
             effective_date, expiry_date, tags, priority, source, published_at, fetched_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        cur.executemany(
            """
            INSERT INTO update_site_mappings (update_id, site, type, category, source, mapped_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("upd_1", "sebi", "circular", "circular", "scraped", "2026-03-20T10:01:00+00:00"),
                ("upd_2", "sebi", "circular", "circular", "scraped", "2026-03-20T11:01:00+00:00"),
            ],
        )
        cur.executemany(
            """
            INSERT INTO attachments (update_id, url, filename, file_type, file_size)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("upd_1", "https://www.sebi.gov.in/circulars/one.pdf", "one.pdf", "pdf", 123),
                ("upd_2", "https://www.sebi.gov.in/circulars/two.pdf", "two.pdf", "pdf", 124),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def load_api_module(db_path: Path):
    os.environ["DB_PATH"] = str(db_path)
    for module_name in [
        "auth_models",
        "broker_alerts",
        "init_api_db",
        "api_import_test_module",
    ]:
        sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location("api_import_test_module", API_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["api_import_test_module"] = module
    spec.loader.exec_module(module)
    return module


def test_export_import_preserves_multiple_same_day_updates(tmp_path: Path):
    local_db = tmp_path / "local.db"
    target_db = tmp_path / "target.db"
    export_path = tmp_path / "export.json"
    create_local_scraper_db(local_db)

    payload = export_module.export_updates(local_db, export_path, site_keys=["sebi"], since=None)
    assert payload["counts"]["updates"] == 2
    assert payload["counts"]["site_mappings"] == 2
    assert payload["counts"]["attachments"] == 2

    result = import_module.import_updates(export_path, target_db)
    assert result["counts"]["updates_inserted"] == 2
    assert result["counts"]["mappings_inserted"] == 2
    assert result["counts"]["attachments_inserted"] == 2

    module = load_api_module(target_db)
    events = module.build_broker_events(requested_site_keys=["sebi"], include_optional=False)
    assert len(events) == 2
    titles = [event["title"] for event in events]
    assert "SEBI Circular One" in titles
    assert "SEBI Circular Two" in titles


def test_import_merges_existing_update_by_url(tmp_path: Path):
    local_db = tmp_path / "local.db"
    target_db = tmp_path / "target.db"
    export_path = tmp_path / "export.json"
    create_local_scraper_db(local_db)

    import_module.ensure_target_schema(target_db)

    conn = sqlite3.connect(target_db)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO updates
            (id, site, type, category, title, date, time, summary, content, url, reference_number,
             effective_date, expiry_date, tags, priority, source, published_at, fetched_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "server_existing",
                "sebi",
                "circular",
                "circular",
                "Old title",
                "2026-03-19",
                "",
                "Old summary",
                "",
                "https://www.sebi.gov.in/circulars/one.pdf",
                None,
                None,
                None,
                None,
                "normal",
                "scraped",
                "2026-03-19T10:00:00+00:00",
                "2026-03-19T10:00:00+00:00",
                "2026-03-19T10:00:00+00:00",
                "2026-03-19T10:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    export_module.export_updates(local_db, export_path, site_keys=["sebi"], since=None)
    result = import_module.import_updates(export_path, target_db)
    assert result["counts"]["updates_inserted"] == 1
    assert result["counts"]["updates_updated"] == 1

    conn = sqlite3.connect(target_db)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        row = cur.execute("SELECT id, title FROM updates WHERE url = ?", ("https://www.sebi.gov.in/circulars/one.pdf",)).fetchone()
        assert row["id"] == "server_existing"
        assert row["title"] == "SEBI Circular One"
    finally:
        conn.close()
