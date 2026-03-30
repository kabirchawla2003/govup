import json
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse


def _normalize_domain(value: str) -> str:
    domain = (value or '').strip().lower()
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


def infer_allowed_domains(site: Dict[str, Any]) -> List[str]:
    domains = set()
    for url in site.get('urls', []):
        parsed = urlparse(url)
        if parsed.netloc:
            domains.add(_normalize_domain(parsed.netloc))
    return sorted(domain for domain in domains if domain)


def infer_scrape_strategy(site: Dict[str, Any]) -> str:
    if site.get('selectors'):
        return 'selectors'
    if site.get('requires_browser'):
        return 'browser'
    return 'generic'


def normalize_site_contract(site_key: str, site: Dict[str, Any]) -> Dict[str, Any]:
    expected_keywords = site.get('expected_keywords') or site.get('update_types') or []
    expected_keywords = [str(keyword).lower() for keyword in expected_keywords if keyword]

    return {
        'site_key': site_key,
        'site_name': site.get('name', site_key),
        'strategy': site.get('scrape_strategy', infer_scrape_strategy(site)),
        'minimum_expected_items': int(site.get('minimum_expected_items', 1)),
        'allow_zero_results': bool(site.get('allow_zero_results', False)),
        'expected_keywords': expected_keywords,
        'allowed_domains': site.get('allowed_domains') or infer_allowed_domains(site),
        'has_selectors': bool(site.get('selectors')),
        'requires_browser': bool(site.get('requires_browser')),
        'configured_urls': list(site.get('urls', [])),
    }


def item_matches_allowed_domains(item: Dict[str, Any], allowed_domains: Iterable[str]) -> bool:
    link = item.get('link') or item.get('url') or ''
    if not link:
        return False

    link_domain = _normalize_domain(urlparse(link).netloc)
    if not link_domain:
        return False

    for allowed_domain in allowed_domains:
        normalized_allowed = _normalize_domain(allowed_domain)
        if not normalized_allowed:
            continue
        if link_domain == normalized_allowed or link_domain.endswith(f'.{normalized_allowed}'):
            return True

    return False


def item_matches_expected_keywords(item: Dict[str, Any], expected_keywords: Iterable[str]) -> bool:
    text = ' '.join(
        str(item.get(field, '')).lower()
        for field in ('title', 'link', 'url', 'category', 'type', 'content_snippet')
    )
    return any(keyword in text for keyword in expected_keywords if keyword)


def item_looks_like_template_artifact(item: Dict[str, Any]) -> bool:
    text = ' '.join(
        str(item.get(field, ''))
        for field in ('title', 'link', 'url', 'content_snippet')
    )
    return bool(re.search(r'{{[^}]+}}|<%[^%]+%>', text))


def evaluate_scrape_quality(
    site_key: str,
    site: Dict[str, Any],
    items: List[Dict[str, Any]],
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    stats = stats or {}
    contract = normalize_site_contract(site_key, site)
    reasons: List[str] = []

    items_found = int(stats.get('items_found', len(items)))
    missing_required_fields = 0
    domain_matches = 0
    keyword_matches = 0
    template_artifact_count = 0

    for item in items:
        if not item.get('title') or not (item.get('link') or item.get('url')):
            missing_required_fields += 1
            continue

        if item_looks_like_template_artifact(item):
            template_artifact_count += 1

        if item_matches_allowed_domains(item, contract['allowed_domains']):
            domain_matches += 1

        if item_matches_expected_keywords(item, contract['expected_keywords']):
            keyword_matches += 1

    if stats.get('status') == 'failed':
        coverage_status = 'failed'
        reasons.append('scrape_failed')
    elif items_found == 0 and not contract['allow_zero_results']:
        coverage_status = 'degraded'
        reasons.append('no_items_found')
    elif items_found < contract['minimum_expected_items'] and not contract['allow_zero_results']:
        coverage_status = 'degraded'
        reasons.append('below_minimum_expected_items')
    elif missing_required_fields:
        coverage_status = 'degraded'
        reasons.append('items_missing_required_fields')
    elif template_artifact_count:
        coverage_status = 'degraded'
        reasons.append('template_artifact_items')
    else:
        coverage_status = 'healthy'

    return {
        **contract,
        'coverage_status': coverage_status,
        'meets_contract': coverage_status == 'healthy',
        'items_found': items_found,
        'missing_required_fields': missing_required_fields,
        'template_artifact_count': template_artifact_count,
        'domain_match_count': domain_matches,
        'keyword_match_count': keyword_matches,
        'reason_codes': reasons,
    }


def serialize_validation_details(details: Dict[str, Any]) -> str:
    return json.dumps(details, sort_keys=True)


def parse_validation_details(raw_value: Optional[str]) -> Dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_source_coverage_report(
    conn: Any,
    sites: Dict[str, Dict[str, Any]],
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    cursor = conn.cursor()
    has_site_mapping_table = bool(
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'update_site_mappings'"
        ).fetchone()
    )

    effective_run_id = run_id
    if effective_run_id is None:
        row = cursor.execute(
            'SELECT run_id FROM scraping_logs WHERE run_id IS NOT NULL ORDER BY started_at DESC LIMIT 1'
        ).fetchone()
        if row:
            effective_run_id = row[0] if not hasattr(row, 'keys') else row['run_id']

    sources = []
    summary = {
        'total_sources': len(sites),
        'healthy': 0,
        'degraded': 0,
        'failed': 0,
        'missing': 0,
    }

    for site_key, site in sites.items():
        contract = normalize_site_contract(site_key, site)

        if effective_run_id:
            log_row = cursor.execute(
                '''
                SELECT *
                FROM scraping_logs
                WHERE site = ? AND run_id = ?
                ORDER BY started_at DESC
                LIMIT 1
                ''',
                (site_key, effective_run_id),
            ).fetchone()
        else:
            log_row = cursor.execute(
                '''
                SELECT *
                FROM scraping_logs
                WHERE site = ?
                ORDER BY started_at DESC
                LIMIT 1
                ''',
                (site_key,),
            ).fetchone()

        if has_site_mapping_table:
            update_row = cursor.execute(
                '''
                SELECT COUNT(DISTINCT u.id) AS update_count, MAX(u.published_at) AS last_published_at
                FROM updates u
                JOIN update_site_mappings usm ON usm.update_id = u.id
                WHERE usm.site = ?
                ''',
                (site_key,),
            ).fetchone()
        else:
            update_row = cursor.execute(
                '''
                SELECT COUNT(*) AS update_count, MAX(published_at) AS last_published_at
                FROM updates
                WHERE site = ?
                ''',
                (site_key,),
            ).fetchone()

        update_count = update_row[0] if not hasattr(update_row, 'keys') else update_row['update_count']
        last_published_at = update_row[1] if not hasattr(update_row, 'keys') else update_row['last_published_at']

        if log_row:
            if hasattr(log_row, 'keys'):
                log_data = dict(log_row)
                effective_status = log_data.get('coverage_status') or (
                    'failed' if log_data.get('status') == 'failed' else 'healthy'
                )
                validation = parse_validation_details(log_data.get('validation_details'))
            else:
                log_data = {}
                effective_status = 'healthy'
                validation = {}
        else:
            log_data = {}
            effective_status = 'missing'
            validation = {}

        summary[effective_status] = summary.get(effective_status, 0) + 1

        sources.append(
            {
                **contract,
                'run_id': effective_run_id,
                'coverage_status': effective_status,
                'last_scrape': log_data or None,
                'validation': validation,
                'update_count': update_count or 0,
                'last_published_at': last_published_at,
            }
        )

    return {
        'run_id': effective_run_id,
        'summary': summary,
        'sources': sources,
    }
