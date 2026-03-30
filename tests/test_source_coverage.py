import importlib.util
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from source_coverage import build_source_coverage_report, evaluate_scrape_quality, normalize_site_contract

spec = importlib.util.spec_from_file_location(
    'main_v9',
    os.path.join(os.path.dirname(__file__), '..', 'src', 'main-v9-broker-enhanced.py')
)
main_v9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_v9)


def test_all_configured_sites_have_normalized_contracts():
    assert len(main_v9.SITES) >= 88

    for site_key, site in main_v9.SITES.items():
        contract = normalize_site_contract(site_key, site)
        assert contract['site_key'] == site_key
        assert contract['site_name']
        assert contract['strategy'] in {'generic', 'browser', 'selectors'}
        assert contract['minimum_expected_items'] >= 1
        assert contract['configured_urls']
        assert contract['allowed_domains']


def test_evaluate_scrape_quality_marks_zero_results_degraded():
    site = {
        'name': 'Example Regulator',
        'urls': ['https://example.com/circulars'],
        'update_types': ['circular', 'notice'],
    }

    result = evaluate_scrape_quality('example', site, [], {'status': 'success', 'items_found': 0})

    assert result['coverage_status'] == 'degraded'
    assert result['meets_contract'] is False
    assert 'no_items_found' in result['reason_codes']


def test_evaluate_scrape_quality_marks_failed_scrape_failed():
    site = {
        'name': 'Example Regulator',
        'urls': ['https://example.com/circulars'],
        'update_types': ['circular'],
    }

    result = evaluate_scrape_quality('example', site, [], {'status': 'failed', 'items_found': 0})

    assert result['coverage_status'] == 'failed'
    assert result['meets_contract'] is False
    assert 'scrape_failed' in result['reason_codes']


def test_evaluate_scrape_quality_marks_template_artifacts_degraded():
    site = {
        'name': 'Example Exchange',
        'urls': ['https://example.com/notices'],
        'update_types': ['notice'],
    }
    items = [
        {
            'title': '{{id.UNDERLYINGNAME}}',
            'link': 'https://example.com/item-1',
            'url': 'https://example.com/item-1',
            'content_snippet': '{{id.UNDERLYINGNAME}}',
        }
    ]

    result = evaluate_scrape_quality('example', site, items, {'status': 'success', 'items_found': 1})

    assert result['coverage_status'] == 'degraded'
    assert result['template_artifact_count'] == 1
    assert 'template_artifact_items' in result['reason_codes']


def test_build_source_coverage_report_summarizes_run_statuses():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute(
        '''
        CREATE TABLE updates (
            id TEXT,
            site TEXT,
            published_at TEXT
        )
        '''
    )
    conn.execute(
        '''
        CREATE TABLE scraping_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT NOT NULL,
            url TEXT NOT NULL,
            run_id TEXT,
            status TEXT NOT NULL,
            coverage_status TEXT,
            items_found INTEGER DEFAULT 0,
            items_added INTEGER DEFAULT 0,
            error_message TEXT,
            validation_details TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            duration_seconds REAL
        )
        '''
    )

    sites = {
        'healthy_site': {
            'name': 'Healthy Site',
            'urls': ['https://healthy.example.com'],
            'update_types': ['circular'],
        },
        'degraded_site': {
            'name': 'Degraded Site',
            'urls': ['https://degraded.example.com'],
            'update_types': ['circular'],
        },
        'missing_site': {
            'name': 'Missing Site',
            'urls': ['https://missing.example.com'],
            'update_types': ['circular'],
        },
    }

    conn.execute(
        "INSERT INTO updates (id, site, published_at) VALUES (?, ?, ?)",
        ('u1', 'healthy_site', '2026-03-08T00:00:00+00:00'),
    )
    conn.execute(
        '''
        INSERT INTO scraping_logs
        (site, url, run_id, status, coverage_status, items_found, validation_details, started_at, completed_at, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'healthy_site',
            'https://healthy.example.com',
            'run-1',
            'success',
            'healthy',
            3,
            '{"reason_codes": []}',
            '2026-03-08T00:00:00+00:00',
            '2026-03-08T00:00:05+00:00',
            5.0,
        ),
    )
    conn.execute(
        '''
        INSERT INTO scraping_logs
        (site, url, run_id, status, coverage_status, items_found, validation_details, started_at, completed_at, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'degraded_site',
            'https://degraded.example.com',
            'run-1',
            'success',
            'degraded',
            0,
            '{"reason_codes": ["no_items_found"]}',
            '2026-03-08T00:01:00+00:00',
            '2026-03-08T00:01:03+00:00',
            3.0,
        ),
    )
    conn.commit()

    report = build_source_coverage_report(conn, sites, run_id='run-1')

    assert report['run_id'] == 'run-1'
    assert report['summary']['healthy'] == 1
    assert report['summary']['degraded'] == 1
    assert report['summary']['missing'] == 1
    assert report['summary']['failed'] == 0

    sources = {source['site_key']: source for source in report['sources']}
    assert sources['healthy_site']['coverage_status'] == 'healthy'
    assert sources['degraded_site']['validation']['reason_codes'] == ['no_items_found']
    assert sources['missing_site']['coverage_status'] == 'missing'
