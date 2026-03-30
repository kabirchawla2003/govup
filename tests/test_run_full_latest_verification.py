import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "run_full_latest_verification.py"

spec = importlib.util.spec_from_file_location("run_full_latest_verification_test_module", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_classify_sources_separates_operational_failure_buckets():
    live_results = [
        {"site_key": "sebi", "status": "working"},
        {"site_key": "dfs", "status": "working"},
        {"site_key": "care", "status": "working"},
        {"site_key": "bse_indices", "status": "working"},
        {"site_key": "mca", "status": "network_failed"},
        {"site_key": "cibil", "status": "blocked"},
        {"site_key": "cersai", "status": "browser_failed"},
        {"site_key": "nmce", "status": "empty"},
        {"site_key": "cma_india", "status": "working"},
    ]

    trusted, noisy, unreviewed, empty, network_failed, blocked, browser_failed = module.classify_sources(live_results)

    assert trusted == ["cma_india", "dfs", "sebi"]
    assert noisy == ["bse_indices", "care"]
    assert unreviewed == []
    assert empty == ["nmce"]
    assert network_failed == ["mca"]
    assert blocked == ["cibil"]
    assert browser_failed == ["cersai"]


def test_assess_run_health_marks_degraded_when_many_trusted_sites_fail_operationally():
    live_results = [{"site_key": site, "status": "working"} for site in sorted(module.BASE_TRUSTED)]
    degraded_sites = sorted(module.BASE_TRUSTED)[: module.assess_run_health(live_results)["threshold"]]
    for site in degraded_sites:
        for entry in live_results:
            if entry["site_key"] == site:
                entry["status"] = "network_failed"

    run_health = module.assess_run_health(live_results)

    assert run_health["state"] == "degraded"
    assert run_health["threshold"] >= 5
    assert sorted(run_health["network_failed_trusted"]) == sorted(degraded_sites)


def test_classify_broker_profile_tracks_status_and_file_access():
    live_results = [
        {"site_key": "sebi", "status": "working", "latest_item": {"link": "https://example.com/sebi.pdf"}},
        {"site_key": "nse", "status": "network_failed", "latest_item": None},
        {"site_key": "bse", "status": "blocked", "latest_item": None},
        {"site_key": "scores", "status": "working", "latest_item": {"link": "https://example.com/scores"}},
    ]
    pdf_results = {
        "results": [
            {"site_key": "sebi", "probe_status": "file_ok"},
            {"site_key": "scores", "probe_status": "no_direct_file"},
        ]
    }

    profile = module.classify_broker_profile(live_results, pdf_results)

    assert profile["must_have_total"] == len(module.BROKER_MUST_HAVE)
    assert profile["working"] == ["scores", "sebi"]
    assert profile["network_failed"] == ["nse"]
    assert profile["blocked"] == ["bse"]
    assert profile["file_ok"] == ["sebi"]
    assert profile["no_direct_file"] == ["scores"]


def test_build_broker_profile_markdown_mentions_recommended_additions():
    profile = {
        "must_have_total": 3,
        "working": ["sebi"],
        "empty": ["nse"],
        "network_failed": [],
        "blocked": [],
        "browser_failed": [],
        "error": [],
        "missing": [],
        "file_ok": ["sebi"],
        "no_direct_file": [],
        "html_wrapper": [],
        "fetch_failed": [],
    }

    markdown = module.build_broker_profile_markdown("2026-03-12T00:00:00+00:00", profile)

    assert "# Broker Must-Have Coverage" in markdown
    assert "`working`: `1`" in markdown
    assert "`nse`" in markdown
    assert "Additional sources to consider" in markdown
    assert "`fiu_ind` [high]" in markdown


def test_build_live_verification_markdown_mentions_excluded_scope_sources():
    markdown = module.build_live_verification_markdown(
        tested_at="2026-03-13T00:00:00+00:00",
        configured_sources=96,
        status_counts={"working": 62, "empty": 23, "network_failed": 8, "blocked": 3, "browser_failed": 0, "error": 0},
        trusted=["dfs", "sebi"],
        noisy=["lic"],
        unreviewed=[],
        empty=["asba", "icici_pru"],
        network_failed=["pfrda_circulars"],
        blocked=["cibil"],
        browser_failed=[],
        pdf_results={"results": []},
        run_health={"state": "normal"},
    )

    assert "Active product-facing review scope" in markdown
    assert "Explicitly excluded from the active product-facing scope" in markdown
    assert "`asba`" in markdown
    assert "`cibil`" in markdown
    assert "Current rerun status: `empty`." in markdown


def test_build_pdf_probe_results_uses_browser_fallback_for_configured_sites():
    live_results = [
        {
            "site_key": "nsdl",
            "status": "working",
            "latest_item": {"link": "https://example.com/circular.pdf"},
        }
    ]

    class DummyModule:
        SITES = {
            "nsdl": {
                "file_probe_via_browser": True,
                "urls": ["https://example.com/listing"],
            }
        }

    original_probe = module.probe_candidate_file
    original_browser_probe = module.probe_candidate_file_via_browser
    module.probe_candidate_file = lambda session, url: {
        "candidate_file_url": url,
        "probe_status": "fetch_failed",
        "http_status": 403,
    }
    module.probe_candidate_file_via_browser = lambda loaded_module, site_key, site, url: {
        "candidate_file_url": url,
        "probe_status": "file_ok",
        "http_status": 200,
        "probe_method": "browser",
    }
    try:
        pdf_results = module.build_pdf_probe_results(live_results, module=DummyModule())
    finally:
        module.probe_candidate_file = original_probe
        module.probe_candidate_file_via_browser = original_browser_probe

    result = pdf_results["results"][0]
    assert result["probe_status"] == "file_ok"
    assert result["probe_method"] == "browser"
    assert result["raw_probe_status"] == "fetch_failed"
    assert result["raw_http_status"] == 403


def test_probe_candidate_file_via_browser_waits_for_eventual_success():
    calls = {"requests": 0}

    class DummyModule:
        def get_openclaw_profile(self, site):
            return "openclaw"

        def openclaw_browser_request(self, method, path, profile, json_body=None, timeout=60):
            if path == "/start":
                return {}
            if path == "/tabs/open":
                return {"targetId": f"tab-{json_body['url'].split('/')[-1]}"}
            if path == "/requests":
                calls["requests"] += 1
                status = 503 if calls["requests"] == 1 else 200
                return {
                    "requests": [
                        {
                            "url": "https://example.com/file.pdf",
                            "status": status,
                            "resourceType": "document",
                        }
                    ]
                }
            if path.startswith("/tabs/"):
                return {}
            raise AssertionError(path)

    result = module.probe_candidate_file_via_browser(
        DummyModule(),
        "cbdt",
        {"urls": ["https://example.com/listing"], "file_probe_browser_timeout_seconds": 2},
        "https://example.com/file.pdf",
    )

    assert result["probe_status"] == "file_ok"
    assert result["http_status"] == 200
    assert calls["requests"] >= 2


def test_probe_candidate_file_via_browser_matches_encoded_request_urls():
    class DummyModule:
        def get_openclaw_profile(self, site):
            return "openclaw"

        def openclaw_browser_request(self, method, path, profile, json_body=None, timeout=60):
            if path == "/start":
                return {}
            if path == "/tabs/open":
                return {"targetId": "tab-1"}
            if path == "/requests":
                return {
                    "requests": [
                        {
                            "url": "https://example.com/files/policy-%20notice.pdf",
                            "status": 200,
                            "resourceType": "document",
                        }
                    ]
                }
            if path.startswith("/tabs/"):
                return {}
            raise AssertionError(path)

    result = module.probe_candidate_file_via_browser(
        DummyModule(),
        "nsdl_eservices",
        {"urls": ["https://example.com/listing"], "file_probe_browser_timeout_seconds": 1},
        "https://example.com/files/policy- notice.pdf",
    )

    assert result["probe_status"] == "file_ok"
    assert result["http_status"] == 200
