import argparse
import asyncio
import importlib.util
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

from source_coverage import build_source_coverage_report

spec = importlib.util.spec_from_file_location('main_v9', os.path.join(SRC_DIR, 'main-v9-broker-enhanced.py'))
main_v9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_v9)


def print_report(report: dict, limit: int) -> None:
    summary = report['summary']
    print(f"Run ID: {report.get('run_id') or 'latest-known'}")
    print(
        'Summary: '
        f"healthy={summary.get('healthy', 0)}, "
        f"degraded={summary.get('degraded', 0)}, "
        f"failed={summary.get('failed', 0)}, "
        f"missing={summary.get('missing', 0)}, "
        f"total={summary.get('total_sources', 0)}"
    )

    problematic = [
        source for source in report['sources']
        if source['coverage_status'] in {'degraded', 'failed', 'missing'}
    ]

    if not problematic:
        print('All configured sources meet the current scrape contract.')
        return

    print('\nSources needing attention:')
    for source in problematic[:limit]:
        validation = source.get('validation') or {}
        reasons = ', '.join(validation.get('reason_codes', [])) or source['coverage_status']
        print(
            f"- {source['site_key']}: status={source['coverage_status']}, "
            f"strategy={source['strategy']}, updates={source['update_count']}, reasons={reasons}"
        )

    remaining = len(problematic) - limit
    if remaining > 0:
        print(f'... and {remaining} more')


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify scrape coverage for all configured sources.')
    parser.add_argument('--db-path', help='Override the SQLite database path used for verification.')
    parser.add_argument('--run-scrape', action='store_true', help='Run process_all_sites() before checking coverage.')
    parser.add_argument('--run-id', help='Inspect a specific scrape run ID instead of the latest run.')
    parser.add_argument('--show', type=int, default=20, help='How many problematic sources to print.')
    parser.add_argument('--allow-degraded', action='store_true', help='Do not fail when degraded sources exist.')
    args = parser.parse_args()

    if args.db_path:
        resolved_db_path = os.path.abspath(args.db_path)
        main_v9.DB_PATH = resolved_db_path
        if hasattr(main_v9, 'main_v8'):
            main_v9.main_v8.DB_PATH = resolved_db_path

    main_v9.init_db()

    if args.run_scrape:
        asyncio.run(main_v9.process_all_sites())

    with main_v9.get_db_sync() as conn:
        report = build_source_coverage_report(conn, main_v9.SITES, run_id=args.run_id)

    print_report(report, args.show)

    summary = report['summary']
    should_fail = summary.get('failed', 0) > 0 or summary.get('missing', 0) > 0
    if not args.allow_degraded:
        should_fail = should_fail or summary.get('degraded', 0) > 0

    return 1 if should_fail else 0


if __name__ == '__main__':
    raise SystemExit(main())
