import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


ROOT = Path(__file__).resolve().parents[1]
FULL_VERIFICATION_SCRIPT = ROOT / "scripts" / "run_full_latest_verification.py"
RELIABILITY_SNAPSHOT_SCRIPT = ROOT / "scripts" / "run_broker_reliability_snapshot.py"
PERSISTENCE_REFRESH_SCRIPT = ROOT / "scripts" / "run_local_persistence_refresh.py"
EXPORT_UPDATES_SCRIPT = ROOT / "scripts" / "export_scraped_updates.py"
REMOTE_IMPORT_SCRIPT = "scripts/import_scraped_updates.py"
REMOTE_DISPATCH_SCRIPT = "scripts/run_broker_webhook_dispatch.py"
DEFAULT_EXPORT_PATH = ROOT / "output" / "scraped_updates_export_latest.json"

DEFAULT_ARTIFACTS = [
    ROOT / "live_scrape_results_latest_v8.json",
    ROOT / "latest_pdf_fetch_results_v6.json",
    ROOT / "broker_reliability_snapshot_latest.json",
    ROOT / "broker_reliability_history.json",
    ROOT / "broker_alerts_validation_latest.json",
    ROOT / "broker_must_have_status_latest.json",
    ROOT / "BROKER_MUST_HAVE_REPORT.md",
    ROOT / "LIVE_VERIFICATION.md",
]

DEFAULT_SSH_TARGET = os.getenv("GOVUP_SSH_TARGET", "ubuntu@151.80.232.163")
DEFAULT_SERVER_APP_PATH = os.getenv("GOVUP_SERVER_APP_PATH", "/home/ubuntu/apps/govup-test/backend")
DEFAULT_SERVER_SERVICE = os.getenv("GOVUP_SERVER_SERVICE", "govup-test.service")
DEFAULT_PUBLIC_BASE_URL = os.getenv("GOVUP_PUBLIC_BASE_URL", "https://test.ktoolz.in")
DEFAULT_REMOTE_PYTHON = os.getenv("GOVUP_REMOTE_PYTHON", "/home/ubuntu/apps/govup-test/.venv/bin/python")
DEFAULT_REMOTE_DB_PATH = os.getenv("GOVUP_REMOTE_DB_PATH", "/home/ubuntu/apps/govup-test/shared/govupdate.db")
DEFAULT_MANIFEST_PATH = ROOT / "output" / "local_scrape_sync_latest.json"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(command: List[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
    )


def ensure_artifacts_exist(paths: Iterable[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing scrape artifacts: {missing}")


def build_remote_validation_snippet(server_app_path: str, remote_db_path: str) -> str:
    return (
        "import json\n"
        "from pathlib import Path\n"
        "import sqlite3\n"
        "import src.broker_alerts as broker_alerts\n"
        "health = broker_alerts.build_source_health_map()\n"
        "sebi = health.get('sebi', {})\n"
        f"conn = sqlite3.connect({remote_db_path!r})\n"
        "conn.row_factory = sqlite3.Row\n"
        "cur = conn.cursor()\n"
        "updates_count = cur.execute('SELECT COUNT(*) FROM updates').fetchone()[0]\n"
        "mappings_count = cur.execute('SELECT COUNT(*) FROM update_site_mappings').fetchone()[0]\n"
        "attachments_count = cur.execute('SELECT COUNT(*) FROM attachments').fetchone()[0]\n"
        "conn.close()\n"
        "print(json.dumps({"
        "'sebi_status': sebi.get('status'), "
        "'sebi_tested_at': sebi.get('tested_at'), "
        "'source_count': len(health), "
        "'updates_count': updates_count, "
        "'mappings_count': mappings_count, "
        "'attachments_count': attachments_count, "
        "'live_exists': Path('live_scrape_results_latest_v8.json').exists(), "
        "'pdf_exists': Path('latest_pdf_fetch_results_v6.json').exists()"
        "}))\n"
    )


def build_scp_commands(paths: Iterable[Path], ssh_target: str, server_app_path: str) -> List[List[str]]:
    commands: List[List[str]] = []
    for path in paths:
        commands.append(["scp", str(path), f"{ssh_target}:{server_app_path}/"])
    return commands


def sync_artifacts(paths: Iterable[Path], ssh_target: str, server_app_path: str) -> List[str]:
    logs: List[str] = []
    for command in build_scp_commands(paths, ssh_target, server_app_path):
        result = run_command(command)
        logs.append(f"{' '.join(command)}\n{result.stdout}{result.stderr}".strip())
    return logs


def restart_remote_service(ssh_target: str, service_name: str) -> str:
    command = ["ssh", ssh_target, f"sudo systemctl restart {shlex.quote(service_name)} && systemctl is-active {shlex.quote(service_name)}"]
    result = run_command(command)
    return f"{' '.join(command)}\n{result.stdout}{result.stderr}".strip()


def run_remote_import(
    ssh_target: str,
    server_app_path: str,
    remote_python: str,
    remote_db_path: str,
    remote_export_path: str,
) -> str:
    command = [
        "ssh",
        ssh_target,
        (
            f"cd {shlex.quote(server_app_path)} && "
            f"{shlex.quote(remote_python)} {shlex.quote(REMOTE_IMPORT_SCRIPT)} "
            f"--input {shlex.quote(remote_export_path)} "
            f"--target-db {shlex.quote(remote_db_path)}"
        ),
    ]
    result = run_command(command)
    return f"{' '.join(command)}\n{result.stdout}{result.stderr}".strip()


def run_remote_dispatch(
    ssh_target: str,
    server_app_path: str,
    remote_python: str,
    remote_db_path: str,
) -> str:
    command = [
        "ssh",
        ssh_target,
        (
            f"cd {shlex.quote(server_app_path)} && "
            f"{shlex.quote(remote_python)} {shlex.quote(REMOTE_DISPATCH_SCRIPT)} "
            f"--db {shlex.quote(remote_db_path)}"
        ),
    ]
    result = run_command(command)
    return f"{' '.join(command)}\n{result.stdout}{result.stderr}".strip()


def validate_remote_artifacts(
    ssh_target: str,
    server_app_path: str,
    remote_python: str,
    public_base_url: str,
    remote_db_path: str,
) -> dict:
    remote_script = build_remote_validation_snippet(server_app_path, remote_db_path)
    remote_command = [
        "ssh",
        ssh_target,
        f"cd {shlex.quote(server_app_path)} && {shlex.quote(remote_python)} - <<'PY'\n{remote_script}PY",
    ]
    remote_result = run_command(remote_command)
    remote_payload = json.loads(remote_result.stdout.strip().splitlines()[-1])

    health_result = run_command(
        [
            sys.executable,
            "-c",
            (
                "import json, requests; "
                f"r=requests.get('{public_base_url}/health', timeout=20); "
                "print(json.dumps({'status_code': r.status_code, 'body': r.text}))"
            ),
        ]
    )
    health_payload = json.loads(health_result.stdout.strip())
    return {
        "remote_artifact_check": remote_payload,
        "public_health_check": health_payload,
    }


def run_local_generation(skip_full: bool) -> List[str]:
    logs: List[str] = []
    if not skip_full:
        result = run_command([sys.executable, str(FULL_VERIFICATION_SCRIPT)], cwd=ROOT)
        logs.append(f"full_verification\n{result.stdout}{result.stderr}".strip())
    snapshot_command = [sys.executable, str(RELIABILITY_SNAPSHOT_SCRIPT), "--skip-full"]
    result = run_command(snapshot_command, cwd=ROOT)
    logs.append(f"reliability_snapshot\n{result.stdout}{result.stderr}".strip())
    return logs


def run_local_persistence_refresh(db_path: Path) -> str:
    result = run_command([sys.executable, str(PERSISTENCE_REFRESH_SCRIPT), "--db", str(db_path)], cwd=ROOT)
    return f"local_persistence_refresh\n{result.stdout}{result.stderr}".strip()


def run_local_export(db_path: Path, export_path: Path) -> str:
    result = run_command(
        [sys.executable, str(EXPORT_UPDATES_SCRIPT), "--db", str(db_path), "--output", str(export_path)],
        cwd=ROOT,
    )
    return f"local_updates_export\n{result.stdout}{result.stderr}".strip()


def write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local scrape artifact generation on this machine and sync the outputs to the server."
    )
    parser.add_argument("--skip-full", action="store_true", help="Skip the expensive full live verification run.")
    parser.add_argument("--skip-generate", action="store_true", help="Skip local artifact generation and sync existing files only.")
    parser.add_argument("--skip-persistence", action="store_true", help="Skip the DB export/import path entirely.")
    parser.add_argument("--skip-persistence-refresh", action="store_true", help="Skip the local scraper DB refresh but still export/import the current DB.")
    parser.add_argument("--skip-restart", action="store_true", help="Do not restart the remote backend service after syncing.")
    parser.add_argument("--skip-dispatch", action="store_true", help="Skip remote webhook dispatch after import.")
    parser.add_argument("--ssh-target", default=DEFAULT_SSH_TARGET, help="SSH target for the remote server.")
    parser.add_argument("--server-app-path", default=DEFAULT_SERVER_APP_PATH, help="Remote backend directory that should receive the artifacts.")
    parser.add_argument("--server-service", default=DEFAULT_SERVER_SERVICE, help="Remote systemd service to restart after syncing.")
    parser.add_argument("--public-base-url", default=DEFAULT_PUBLIC_BASE_URL, help="Public base URL used for post-sync health verification.")
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON, help="Remote Python interpreter used for server-side validation.")
    parser.add_argument("--remote-db-path", default=DEFAULT_REMOTE_DB_PATH, help="Remote SQLite DB path used by the SaaS backend.")
    parser.add_argument("--local-db-path", type=Path, default=ROOT / "data" / "govupdate.db", help="Local scraper DB path for persistence refresh/export.")
    parser.add_argument("--export-path", type=Path, default=DEFAULT_EXPORT_PATH, help="Local export file path.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH, help="Path for the latest sync manifest.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generation_logs: List[str] = []
    persistence_log = None
    export_log = None
    if not args.skip_generate:
        generation_logs = run_local_generation(skip_full=args.skip_full)
    if not args.skip_persistence:
        if not args.skip_persistence_refresh:
            persistence_log = run_local_persistence_refresh(args.local_db_path.resolve())
        export_log = run_local_export(args.local_db_path.resolve(), args.export_path.resolve())

    artifact_paths = list(DEFAULT_ARTIFACTS)
    if not args.skip_persistence:
        artifact_paths.append(args.export_path.resolve())
    ensure_artifacts_exist(artifact_paths)
    sync_logs = sync_artifacts(artifact_paths, args.ssh_target, args.server_app_path)

    remote_import_log = None
    if not args.skip_persistence:
        remote_import_log = run_remote_import(
            ssh_target=args.ssh_target,
            server_app_path=args.server_app_path,
            remote_python=args.remote_python,
            remote_db_path=args.remote_db_path,
            remote_export_path=f"{args.server_app_path.rstrip('/')}/{args.export_path.name}",
        )

    restart_log = None
    if not args.skip_restart:
        restart_log = restart_remote_service(args.ssh_target, args.server_service)

    remote_dispatch_log = None
    if not args.skip_persistence and not args.skip_dispatch:
        remote_dispatch_log = run_remote_dispatch(
            ssh_target=args.ssh_target,
            server_app_path=args.server_app_path,
            remote_python=args.remote_python,
            remote_db_path=args.remote_db_path,
        )

    validation = validate_remote_artifacts(
        ssh_target=args.ssh_target,
        server_app_path=args.server_app_path,
        remote_python=args.remote_python,
        public_base_url=args.public_base_url,
        remote_db_path=args.remote_db_path,
    )

    manifest = {
        "completed_at": utcnow_iso(),
        "ssh_target": args.ssh_target,
        "server_app_path": args.server_app_path,
        "server_service": args.server_service,
        "public_base_url": args.public_base_url,
        "artifacts": [str(path) for path in DEFAULT_ARTIFACTS],
        "persistence_log": persistence_log,
        "export_log": export_log,
        "generation_logs": generation_logs,
        "sync_logs": sync_logs,
        "remote_import_log": remote_import_log,
        "restart_log": restart_log,
        "remote_dispatch_log": remote_dispatch_log,
        "validation": validation,
    }
    write_manifest(args.manifest, manifest)
    manifest_sync_logs = sync_artifacts([args.manifest.resolve()], args.ssh_target, args.server_app_path)
    manifest["manifest_sync_logs"] = manifest_sync_logs
    write_manifest(args.manifest, manifest)

    if validation["public_health_check"]["status_code"] != 200:
        raise SystemExit(1)
    if validation["remote_artifact_check"].get("sebi_status") != "working":
        raise SystemExit(1)

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
