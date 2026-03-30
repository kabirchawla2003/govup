import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "sync_local_scrape_to_server.py"

spec = importlib.util.spec_from_file_location("sync_local_scrape_to_server_test_module", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_build_scp_commands_covers_all_artifacts():
    artifacts = [Path("a.json"), Path("b.json")]
    commands = module.build_scp_commands(artifacts, "ubuntu@example.com", "/srv/app")

    assert commands == [
        ["scp", "a.json", "ubuntu@example.com:/srv/app/"],
        ["scp", "b.json", "ubuntu@example.com:/srv/app/"],
    ]


def test_remote_validation_snippet_mentions_expected_artifacts():
    snippet = module.build_remote_validation_snippet("/srv/app", "/srv/app/data/govupdate.db")

    assert "build_source_health_map" in snippet
    assert "live_scrape_results_latest_v8.json" in snippet
    assert "latest_pdf_fetch_results_v6.json" in snippet
    assert "sebi_status" in snippet
    assert "updates_count" in snippet
