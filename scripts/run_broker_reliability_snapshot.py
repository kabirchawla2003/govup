import argparse
import asyncio
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
FULL_VERIFICATION_PATH = ROOT / "scripts" / "run_full_latest_verification.py"
BROKER_VALIDATION_PATH = ROOT / "scripts" / "run_broker_alerts_validation.py"
DEFAULT_OUTPUT_PATH = ROOT / "broker_reliability_snapshot_latest.json"
DEFAULT_HISTORY_PATH = ROOT / "broker_reliability_history.json"
DEFAULT_VALIDATION_OUTPUT_PATH = ROOT / "broker_alerts_validation_latest.json"
DEFAULT_REPORT_PATH = ROOT / "broker_reliability_report_latest.md"
LIVE_RESULTS_PATH = ROOT / "live_scrape_results_latest_v8.json"
BROKER_STATUS_PATH = ROOT / "broker_must_have_status_latest.json"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_history(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [
                entry
                for entry in payload
                if isinstance(entry, dict)
                and entry.get("captured_at")
                and entry.get("broker_must_have_total") is not None
            ]
    except Exception:
        pass
    return []


def load_existing_verification_summary() -> Dict[str, Any]:
    live_payload: Dict[str, Any] = {}
    broker_payload: Dict[str, Any] = {}
    try:
        live_payload = json.loads(LIVE_RESULTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        live_payload = {}
    try:
        broker_payload = json.loads(BROKER_STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        broker_payload = {}

    broker_profile = broker_payload.get("profile") or {}
    return {
        "live_results_path": str(LIVE_RESULTS_PATH),
        "broker_json_path": str(BROKER_STATUS_PATH),
        "status_counts": live_payload.get("status_counts") or {},
        "run_health": live_payload.get("run_health") or {},
        "trusted_count": None,
        "noisy_count": None,
        "unreviewed_count": None,
        "empty_count": (live_payload.get("status_counts") or {}).get("empty"),
        "broker_must_have_working": len(broker_profile.get("working") or []),
        "broker_must_have_total": broker_profile.get("must_have_total"),
    }


def build_markdown_report(snapshot: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
    full_verification = snapshot.get("full_verification") or {}
    broker_validation = snapshot.get("broker_validation") or {}
    status_counts = full_verification.get("status_counts") or {}
    latest_entry = history[-1] if history else {}
    previous_entry = history[-2] if len(history) >= 2 else {}

    def delta_line(key: str, label: str) -> str:
        latest_value = latest_entry.get(key)
        previous_value = previous_entry.get(key)
        if latest_value is None or previous_value is None:
            return f"- {label}: {latest_value}"
        delta = int(latest_value) - int(previous_value)
        sign = "+" if delta > 0 else ""
        return f"- {label}: {latest_value} ({sign}{delta} vs previous)"

    return "\n".join(
        [
            "# Broker Reliability Report",
            "",
            f"- Captured at: {snapshot.get('completed_at')}",
            f"- Validation passed: {broker_validation.get('all_checks_passed', False)}",
            f"- Run health: {(full_verification.get('run_health') or {}).get('status', 'unknown')}",
            "",
            "## Coverage",
            delta_line("working_sources", "Working sources"),
            delta_line("network_failed_sources", "Network failed"),
            delta_line("blocked_sources", "Blocked"),
            delta_line("broker_must_have_working", "Broker must-have working"),
            f"- Broker must-have total: {full_verification.get('broker_must_have_total')}",
            "",
            "## Validation",
            f"- Events total: {broker_validation.get('events_total')}",
            f"- Dispatch delivered: {broker_validation.get('dispatch_delivered')}",
            f"- Validation checks: {json.dumps(broker_validation.get('validation_checks') or {}, sort_keys=True)}",
            "",
            "## Status Counts",
            f"- Working: {status_counts.get('working')}",
            f"- Empty: {status_counts.get('empty')}",
            f"- Network failed: {status_counts.get('network_failed')}",
            f"- Blocked: {status_counts.get('blocked')}",
            f"- Browser failed: {status_counts.get('browser_failed')}",
            "",
        ]
    )


def run_snapshot(
    output_path: Path,
    history_path: Path,
    validation_output_path: Path,
    report_path: Path,
    skip_full: bool = False,
) -> Dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    verification_summary: Dict[str, Any] = {}

    if not skip_full:
        verification_module = load_module(FULL_VERIFICATION_PATH, "broker_reliability_full_verification")
        verification_summary = asyncio.run(verification_module.run_full_scrape())
    else:
        verification_summary = load_existing_verification_summary()

    validation_module = load_module(BROKER_VALIDATION_PATH, "broker_reliability_validation")
    validation_artifact = validation_module.run_validation(validation_output_path.resolve())

    snapshot = {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "output_version": "2026-03-13",
        "full_verification": verification_summary,
        "broker_validation": {
            "all_checks_passed": validation_artifact.get("all_checks_passed", False),
            "source_health_summary": validation_artifact.get("source_health_summary", {}),
            "events_total": (validation_artifact.get("events") or {}).get("total"),
            "event_site_keys": (validation_artifact.get("events") or {}).get("site_keys", []),
            "dispatch_delivered": ((validation_artifact.get("webhook") or {}).get("dispatch_worker") or {}).get("delivered"),
            "validation_checks": validation_artifact.get("validation_checks", {}),
        },
    }

    history = load_history(history_path.resolve())
    history.append(
        {
            "captured_at": snapshot["completed_at"],
            "working_sources": (verification_summary.get("status_counts") or {}).get("working"),
            "network_failed_sources": (verification_summary.get("status_counts") or {}).get("network_failed"),
            "blocked_sources": (verification_summary.get("status_counts") or {}).get("blocked"),
            "broker_must_have_working": verification_summary.get("broker_must_have_working"),
            "broker_must_have_total": verification_summary.get("broker_must_have_total"),
            "validation_passed": snapshot["broker_validation"]["all_checks_passed"],
            "events_total": snapshot["broker_validation"]["events_total"],
            "dispatch_delivered": snapshot["broker_validation"]["dispatch_delivered"],
        }
    )

    output_path.resolve().write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    history_path.resolve().write_text(json.dumps(history, indent=2), encoding="utf-8")
    report_path.resolve().write_text(build_markdown_report(snapshot, history), encoding="utf-8")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the broker full verification plus broker-alert validation and append a reliability history entry."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path for the latest reliability snapshot JSON.",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY_PATH,
        help="Path for the reliability history JSON file.",
    )
    parser.add_argument(
        "--validation-output",
        type=Path,
        default=DEFAULT_VALIDATION_OUTPUT_PATH,
        help="Path for the broker alerts validation artifact.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Path for the latest reliability markdown report.",
    )
    parser.add_argument(
        "--skip-full",
        action="store_true",
        help="Skip the expensive full scrape and record only the broker validation snapshot.",
    )
    args = parser.parse_args()

    snapshot = run_snapshot(
        output_path=args.output,
        history_path=args.history,
        validation_output_path=args.validation_output,
        report_path=args.report,
        skip_full=args.skip_full,
    )
    status = "passed" if snapshot["broker_validation"]["all_checks_passed"] else "failed"
    print(f"Broker reliability snapshot {status}. Latest artifact written to {args.output.resolve()}")
    return 0 if snapshot["broker_validation"]["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
