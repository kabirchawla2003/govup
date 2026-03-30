import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
API_PATH = SRC_DIR / "api.py"
DEFAULT_OUTPUT_PATH = ROOT / "ops_monitor_latest.json"
DEFAULT_REPORT_PATH = ROOT / "ops_monitor_latest.md"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC_DIR))


def load_api_module():
    for module_name in [
        "auth_models",
        "broker_alerts",
        "init_api_db",
        "api_ops_monitor_module",
    ]:
        sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location("api_ops_monitor_module", API_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["api_ops_monitor_module"] = module
    spec.loader.exec_module(module)
    return module


def build_report(payload: dict) -> str:
    checks = payload.get("checks") or {}
    reliability = payload.get("reliability") or {}
    latest_sync = reliability.get("latest_sync") or {}
    webhook_ops = reliability.get("webhook_ops") or {}
    broker = reliability.get("broker_must_have") or {}
    return "\n".join(
        [
            "# Ops Monitor",
            "",
            f"- Captured at: {payload.get('captured_at')}",
            f"- Overall status: {'pass' if payload.get('all_checks_passed') else 'fail'}",
            "",
            "## Checks",
            f"- Sync fresh: {checks.get('sync_fresh')}",
            f"- Sync import ran: {checks.get('sync_import_ran')}",
            f"- Public health ok: {checks.get('public_health_ok')}",
            f"- Broker validation passed: {checks.get('broker_validation_passed')}",
            f"- Broker core fully working: {checks.get('broker_core_full')}",
            f"- Webhook dead letters clear: {checks.get('webhook_dead_letters_clear')}",
            f"- Webhook auto-paused clear: {checks.get('webhook_auto_paused_clear')}",
            "",
            "## Snapshot",
            f"- Latest sync state: {latest_sync.get('state')}",
            f"- Latest sync age seconds: {latest_sync.get('age_seconds')}",
            f"- Remote updates count: {latest_sync.get('remote_updates_count')}",
            f"- Broker must-have: {broker.get('working')}/{broker.get('total')}",
            f"- Open dead letters: {webhook_ops.get('open_dead_letters')}",
            f"- Auto-paused webhooks: {webhook_ops.get('auto_paused_webhooks')}",
        ]
    )


def run_monitor() -> dict:
    module = load_api_module()
    reliability = module.build_reliability_summary()
    latest_sync = reliability.get("latest_sync") or {}
    validation = reliability.get("validation") or {}
    broker = reliability.get("broker_must_have") or {}
    webhook_ops = reliability.get("webhook_ops") or {}

    checks = {
        "sync_fresh": latest_sync.get("state") == "fresh",
        "sync_import_ran": bool(latest_sync.get("import_ran")),
        "public_health_ok": latest_sync.get("public_health_status_code") == 200,
        "broker_validation_passed": bool(validation.get("all_checks_passed")),
        "broker_core_full": broker.get("working") == broker.get("total"),
        "webhook_dead_letters_clear": int(webhook_ops.get("open_dead_letters") or 0) == 0,
        "webhook_auto_paused_clear": int(webhook_ops.get("auto_paused_webhooks") or 0) == 0,
    }
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "all_checks_passed": all(checks.values()),
        "checks": checks,
        "reliability": reliability,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the broker ops monitor over sync freshness, broker coverage, and webhook health.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    payload = run_monitor()
    args.output.resolve().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    args.report.resolve().write_text(build_report(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
