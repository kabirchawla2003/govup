# v8 compatibility wrapper over the intact v7-fixed module.

import asyncio
import base64
import html as html_lib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import httpx
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from uuid import uuid4

from bs4 import BeautifulSoup
from fastapi import Depends

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException as SeleniumTimeoutException
    from selenium.webdriver.edge.options import Options as EdgeOptions
except Exception:
    webdriver = None
    SeleniumTimeoutException = Exception
    EdgeOptions = None

from source_coverage import build_source_coverage_report, evaluate_scrape_quality, serialize_validation_details

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_V7_PATH = os.path.join(CURRENT_DIR, 'main-v7-fixed.py')

spec = importlib.util.spec_from_file_location('main_v7_fixed_base', BASE_V7_PATH)
main_v7_fixed_base = importlib.util.module_from_spec(spec)
sys.modules['main_v7_fixed_base'] = main_v7_fixed_base
spec.loader.exec_module(main_v7_fixed_base)

for name, value in main_v7_fixed_base.__dict__.items():
    if name.startswith('__') and name not in {'__doc__', '__all__'}:
        continue
    globals()[name] = value

ORIGINAL_INIT_DB = main_v7_fixed_base.init_db
ORIGINAL_SCRAPE_SITE = main_v7_fixed_base.scrape_site
ORIGINAL_PROCESS_ALL_SITES = main_v7_fixed_base.process_all_sites
SCRAPE_RUN_ID = ContextVar('scrape_run_id', default=None)


@contextmanager
def get_db_sync():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def ensure_table_column(conn, table_name: str, column_name: str, column_definition: str):
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def init_db():
    ORIGINAL_INIT_DB()
    conn = get_db()
    try:
        ensure_table_column(conn, 'scraping_logs', 'run_id', 'TEXT')
        ensure_table_column(conn, 'scraping_logs', 'coverage_status', 'TEXT')
        ensure_table_column(conn, 'scraping_logs', 'validation_details', 'TEXT')
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scraping_logs_run_id ON scraping_logs(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scraping_logs_coverage_status ON scraping_logs(coverage_status)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_attachments_update_url_unique ON attachments(update_id, url)")
        conn.commit()
    finally:
        conn.close()


OPENCLAW_CONFIG_PATH = os.path.expanduser('~/.openclaw/openclaw.json')
OPENCLAW_DEFAULT_CONTROL_URL = 'http://127.0.0.1:18791'
OPENCLAW_WAIT_ERROR_TERMS = [
    'this site can’t be reached',
    "this site can't be reached",
    'err_',
    'error occurred',
    'access denied',
]
OPENCLAW_SHARED_TABS: Dict[str, str] = {}
SCRAPE_NETWORK_FAILURE_TERMS = [
    'getaddrinfo failed',
    'all connection attempts failed',
    'temporary failure in name resolution',
    'name or service not known',
    'network is unreachable',
    'no route to host',
    'connecterror',
    'connection refused',
    'connection reset',
    'connection aborted',
    'failed to fetch',
    'timed out',
    'timeout',
    'ssl',
    'tls',
    'remote protocol error',
]
SCRAPE_BLOCKED_TERMS = [
    '403 forbidden',
    '401 unauthorized',
    '429 too many requests',
    'access denied',
    'captcha',
    'request blocked',
    'forbidden',
]
SCRAPE_BROWSER_FAILURE_TERMS = [
    'openclaw browser fallback failed',
    'tabs/open',
    '/act?profile=',
    'target closed',
    'internal server error',
    'browser control',
]


@lru_cache(maxsize=1)
def load_openclaw_config() -> Dict[str, Any]:
    try:
        with open(OPENCLAW_CONFIG_PATH, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_openclaw_control_url() -> str:
    env_url = os.getenv('OPENCLAW_BROWSER_CONTROL_URL')
    if env_url:
        return env_url.rstrip('/')

    config = load_openclaw_config()
    browser_config = config.get('browser') if isinstance(config.get('browser'), dict) else {}
    gateway_config = config.get('gateway') if isinstance(config.get('gateway'), dict) else {}
    port = browser_config.get('controlPort')
    if not port:
        gateway_port = gateway_config.get('port', 18789)
        try:
            port = int(gateway_port) + 2
        except Exception:
            port = 18791
    return f'http://127.0.0.1:{port}'


def get_openclaw_token() -> Optional[str]:
    token = os.getenv('OPENCLAW_GATEWAY_TOKEN')
    if token:
        return token

    config = load_openclaw_config()
    gateway_config = config.get('gateway') if isinstance(config.get('gateway'), dict) else {}
    auth_config = gateway_config.get('auth') if isinstance(gateway_config.get('auth'), dict) else {}
    token = auth_config.get('token') or gateway_config.get('token') or config.get('token')
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def get_openclaw_profile(site: Optional[Dict[str, Any]] = None) -> str:
    if site and site.get('browser_profile'):
        return str(site['browser_profile'])
    env_profile = os.getenv('OPENCLAW_BROWSER_PROFILE')
    if env_profile:
        return env_profile
    config = load_openclaw_config()
    browser_config = config.get('browser') if isinstance(config.get('browser'), dict) else {}
    return str(browser_config.get('defaultProfile') or 'openclaw')


def openclaw_browser_request(
    method: str,
    path: str,
    profile: str,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    token = get_openclaw_token()
    if not token:
        raise RuntimeError('OpenClaw gateway token not configured')

    headers = {'Authorization': f'Bearer {token}'}
    url = f"{get_openclaw_control_url()}{path}"
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.request(
            method,
            url,
            headers=headers,
            params={'profile': profile},
            json=json_body,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {'result': payload}


def clear_openclaw_shared_tab(profile: str, close_remote: bool = False) -> None:
    target_id = OPENCLAW_SHARED_TABS.pop(profile, None)
    if close_remote and target_id:
        try:
            openclaw_browser_request('DELETE', f'/tabs/{target_id}', profile, timeout=15)
        except Exception:
            pass


def should_retry_openclaw_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if any(term in message for term in ['tabs/open', '/act?profile=', 'internal server error', 'target closed']):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    if isinstance(exc, httpx.HTTPError):
        return True
    return False


def get_or_create_openclaw_tab(profile: str, browser_url: str, open_timeout: float) -> Tuple[str, bool]:
    cached_target = OPENCLAW_SHARED_TABS.get(profile)
    if cached_target:
        try:
            openclaw_browser_request(
                'POST',
                '/tabs/focus',
                profile,
                json_body={'targetId': cached_target},
                timeout=20,
            )
            return cached_target, False
        except Exception:
            clear_openclaw_shared_tab(profile)

    opened = openclaw_browser_request(
        'POST',
        '/tabs/open',
        profile,
        json_body={'url': browser_url},
        timeout=open_timeout,
    )
    target_id = opened.get('targetId')
    if not target_id:
        raise RuntimeError(f'OpenClaw did not return a targetId for {browser_url}')
    openclaw_browser_request(
        'POST',
        '/tabs/focus',
        profile,
        json_body={'targetId': target_id},
        timeout=20,
    )
    OPENCLAW_SHARED_TABS[profile] = target_id
    return target_id, True


def navigate_openclaw_tab(profile: str, target_id: str, browser_url: str, open_timeout: float) -> None:
    openclaw_browser_request(
        'POST',
        '/tabs/focus',
        profile,
        json_body={'targetId': target_id},
        timeout=20,
    )
    navigate_script = f"() => {{ window.location.href = {json.dumps(browser_url)}; return window.location.href; }}"
    openclaw_browser_request(
        'POST',
        '/act',
        profile,
        json_body={'kind': 'evaluate', 'fn': navigate_script},
        timeout=open_timeout,
    )


def classify_scrape_result(items: List[Dict[str, Any]], stats: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    stats = stats or {}
    errors = [str(error) for error in (stats.get('errors') or []) if error]
    error_blob = ' '.join(errors).lower()
    result_status = 'working' if items else 'empty'
    failure_category = None

    if not items:
        is_blocked = any(term in error_blob for term in SCRAPE_BLOCKED_TERMS)
        is_browser_failure = any(term in error_blob for term in SCRAPE_BROWSER_FAILURE_TERMS)
        is_transport_failure = (
            any(term in error_blob for term in SCRAPE_NETWORK_FAILURE_TERMS)
            or ('error fetching ' in error_blob and not is_blocked and '404 not found' not in error_blob)
        )

        if is_blocked:
            result_status = 'blocked'
            failure_category = 'blocked'
        elif is_transport_failure:
            result_status = 'network_failed'
            failure_category = 'network_failed'
        elif is_browser_failure:
            result_status = 'browser_failed'
            failure_category = 'browser_failed'
        elif stats.get('status') == 'failed':
            result_status = 'error'
            failure_category = 'error'

    return {
        'result_status': result_status,
        'failure_category': failure_category,
        'failure_reason': errors[0] if errors else None,
        'had_errors': bool(errors),
    }


def apply_source_downgrade(site: Dict[str, Any], items: List[Dict[str, Any]], stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    reason = ' '.join(str(site.get('downgrade_reason') or '').split()).strip()
    if not reason:
        return items
    downgrade_message = f'Source downgraded: {reason}'
    errors = stats.setdefault('errors', [])
    if downgrade_message not in errors:
        errors.append(downgrade_message)
    return []


def wait_for_openclaw_page(site: Dict[str, Any], profile: str) -> Dict[str, Any]:
    deadline = time.time() + float(site.get('browser_timeout_seconds', 45))
    selector = site.get('browser_wait_selector')
    text = site.get('browser_wait_text')
    selector_json = json.dumps(selector) if selector else 'null'
    text_json = json.dumps(str(text).lower()) if text else 'null'
    wait_script = (
        "() => {"
        f"const selector = {selector_json};"
        f"const wantedText = {text_json};"
        "const bodyText = document.body ? document.body.innerText : '';"
        "return {"
        "readyState: document.readyState,"
        "hasSelector: selector ? !!document.querySelector(selector) : true,"
        "hasText: wantedText ? bodyText.toLowerCase().includes(wantedText) : true,"
        "bodyText: bodyText.slice(0, 2000)"
        "};"
        "}"
    )

    last_state: Dict[str, Any] = {}
    while time.time() < deadline:
        state = openclaw_browser_request(
            'POST',
            '/act',
            profile,
            json_body={'kind': 'evaluate', 'fn': wait_script},
            timeout=60,
        ).get('result', {})
        if isinstance(state, dict):
            last_state = state
            body_text = str(state.get('bodyText') or '').lower()
            if any(term in body_text for term in OPENCLAW_WAIT_ERROR_TERMS):
                return state
            if (
                state.get('readyState') == 'complete'
                and state.get('hasSelector', True)
                and state.get('hasText', True)
            ):
                return state
        time.sleep(1.0)
    return last_state


def fetch_openclaw_rendered_html(browser_url: str, site: Optional[Dict[str, Any]] = None) -> str:
    site = site or {}
    profile = get_openclaw_profile(site)
    open_timeout = float(site.get('browser_open_timeout_seconds', 120))
    eval_timeout = float(site.get('browser_eval_timeout_seconds', 120))
    for attempt in range(2):
        openclaw_browser_request('POST', '/start', profile, timeout=60)
        try:
            target_id, created = get_or_create_openclaw_tab(profile, browser_url, open_timeout)
            if not created:
                navigate_openclaw_tab(profile, target_id, browser_url, open_timeout)

            initial_wait = float(site.get('browser_wait_seconds', 3))
            if initial_wait > 0:
                time.sleep(initial_wait)
            wait_for_openclaw_page(site, profile)

            html_result = openclaw_browser_request(
                'POST',
                '/act',
                profile,
                json_body={'kind': 'evaluate', 'fn': '() => document.documentElement.outerHTML'},
                timeout=eval_timeout,
            ).get('result')
            if not isinstance(html_result, str) or not html_result.strip():
                raise RuntimeError(f'OpenClaw returned empty HTML for {browser_url}')
            return html_result
        except Exception as exc:
            clear_openclaw_shared_tab(profile, close_remote=True)
            if attempt == 0 and should_retry_openclaw_error(exc):
                time.sleep(1.0)
                continue
            raise


def fetch_openclaw_xml_text(browser_url: str, site: Optional[Dict[str, Any]] = None) -> str:
    site = site or {}
    try:
        html = fetch_openclaw_rendered_html(browser_url, site)
    except Exception:
        page_url = site.get('rss_browser_page_url')
        if page_url:
            return fetch_openclaw_xml_text_via_page_fetch(browser_url, page_url, site)
        raise
    html_text = (html or '').lstrip()
    if html_text.startswith('<rss') or html_text.startswith('<?xml'):
        return html_text

    soup = BeautifulSoup(html, 'html.parser')
    viewer_root = soup.select_one('#webkit-xml-viewer-source-xml')
    if viewer_root:
        rss_node = viewer_root.find('rss')
        if rss_node:
            return str(rss_node)
        inner = viewer_root.decode_contents().strip()
        if inner:
            return inner

    body_text = soup.get_text('\n', strip=True)
    lowered_body = body_text.lower()
    if 'this site can’t be reached' in lowered_body or "this site can't be reached" in lowered_body:
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        summary = ' | '.join(lines[:4])
        raise RuntimeError(f'OpenClaw could not load {browser_url}: {summary}')
    rss_start = body_text.find('<rss')
    if rss_start != -1:
        return body_text[rss_start:]

    raise RuntimeError(f'OpenClaw did not expose XML content for {browser_url}')


def fetch_openclaw_xml_text_via_page_fetch(
    browser_url: str,
    page_url: str,
    site: Optional[Dict[str, Any]] = None,
) -> str:
    site = site or {}
    profile = get_openclaw_profile(site)
    open_timeout = float(site.get('browser_open_timeout_seconds', 120))
    eval_timeout = float(site.get('browser_eval_timeout_seconds', 120))
    fetch_script = (
        "() => fetch("
        f"{json.dumps(browser_url)}, "
        "{credentials: 'same-origin'}"
        ").then(async response => ({"
        "ok: response.ok,"
        "status: response.status,"
        "text: await response.text()"
        "})).catch(error => ({ok: false, error: String(error)}))"
    )

    for attempt in range(2):
        openclaw_browser_request('POST', '/start', profile, timeout=60)
        try:
            target_id, created = get_or_create_openclaw_tab(profile, page_url, open_timeout)
            if not created:
                navigate_openclaw_tab(profile, target_id, page_url, open_timeout)
            initial_wait = float(site.get('browser_wait_seconds', 3))
            if initial_wait > 0:
                time.sleep(initial_wait)
            wait_for_openclaw_page(site, profile)

            result = openclaw_browser_request(
                'POST',
                '/act',
                profile,
                json_body={'kind': 'evaluate', 'fn': fetch_script},
                timeout=eval_timeout,
            ).get('result')
            if not isinstance(result, dict):
                raise RuntimeError(f'OpenClaw page fetch returned unexpected payload for {browser_url}')

            if not result.get('ok'):
                error_text = str(result.get('error') or f"HTTP {result.get('status')}")
                raise RuntimeError(f'OpenClaw page fetch failed for {browser_url}: {error_text}')

            xml_text = str(result.get('text') or '').lstrip()
            if xml_text.startswith('<rss') or xml_text.startswith('<?xml'):
                return xml_text
            raise RuntimeError(f'OpenClaw page fetch did not return XML content for {browser_url}')
        except Exception as exc:
            clear_openclaw_shared_tab(profile, close_remote=True)
            if attempt == 0 and should_retry_openclaw_error(exc):
                time.sleep(1.0)
                continue
            raise


def fetch_remote_text_via_ssh(
    target_url: str,
    site: Optional[Dict[str, Any]] = None,
    accept_header: str = '*/*',
) -> str:
    site = site or {}
    ssh_target = str(site.get('remote_rss_via_ssh') or '').strip()
    if not ssh_target:
        raise RuntimeError('Remote RSS SSH target not configured')

    timeout = int(site.get('remote_rss_timeout_seconds') or 60)
    remote_script = (
        "import base64, requests, sys\n"
        f"url = {json.dumps(target_url)}\n"
        f"accept_header = {json.dumps(accept_header)}\n"
        "headers = {\n"
        "    'User-Agent': 'Mozilla/5.0',\n"
        "    'Accept': accept_header,\n"
        "}\n"
        "last_exc = None\n"
        "for verify in (True, False):\n"
        "    try:\n"
        "        response = requests.get(url, timeout=30, verify=verify, headers=headers)\n"
        "        response.raise_for_status()\n"
        "        sys.stdout.write(base64.b64encode(response.content).decode('ascii'))\n"
        "        sys.stdout.flush()\n"
        "        raise SystemExit(0)\n"
        "    except Exception as exc:\n"
        "        last_exc = exc\n"
        "raise SystemExit(str(last_exc) if last_exc else 'remote rss fetch failed')\n"
    )

    result = subprocess.run(
        ['ssh', ssh_target, 'python3', '-'],
        input=remote_script.encode('utf-8'),
        capture_output=True,
        text=False,
        timeout=timeout,
        check=False,
    )
    stdout_text = (result.stdout or b'').decode('utf-8', errors='replace')
    stderr_text = (result.stderr or b'').decode('utf-8', errors='replace')
    if result.returncode != 0:
        error_text = (stderr_text or stdout_text or '').strip()
        raise RuntimeError(f'Remote fetch failed for {target_url}: {error_text}')

    stdout_text = stdout_text.strip()
    if not stdout_text:
        raise RuntimeError(f'Remote fetch returned empty content for {target_url}')
    try:
        decoded_text = base64.b64decode(stdout_text).decode('utf-8', errors='replace')
    except Exception as exc:
        raise RuntimeError(f'Remote fetch returned undecodable content for {target_url}: {exc}')

    xml_text = decoded_text.lstrip()
    if not xml_text:
        raise RuntimeError(f'Remote fetch returned empty content for {target_url}')
    return xml_text


def fetch_remote_rss_text_via_ssh(feed_url: str, site: Optional[Dict[str, Any]] = None) -> str:
    return fetch_remote_text_via_ssh(
        feed_url,
        site,
        accept_header='application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8',
    )


def fetch_remote_html_text_via_ssh(page_url: str, site: Optional[Dict[str, Any]] = None) -> str:
    return fetch_remote_text_via_ssh(
        page_url,
        site,
        accept_header='text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    )


def should_try_openclaw_browser_fallback(site: Dict[str, Any], items: List[Dict[str, Any]], stats: Dict[str, Any]) -> bool:
    if not site.get('browser_fallback'):
        return False

    mode = str(site.get('browser_fallback_mode') or 'if_empty').lower()
    if mode == 'always':
        return True
    if mode == 'if_empty':
        return not items
    if mode == 'if_empty_or_error':
        if not items:
            return True
        errors_blob = ' '.join(str(error) for error in stats.get('errors', [])).lower()
        retry_terms = ['404', '403', 'timeout', 'ssl', 'connection', 'redirect', 'forbidden']
        return any(term in errors_blob for term in retry_terms)
    return False


def extract_items_from_browser_rendered_html(
    html: str,
    base_url: str,
    site_key: str,
    site: Dict[str, Any],
) -> List[Dict[str, Any]]:
    browser_html_strategy = site.get('browser_html_strategy')
    if browser_html_strategy == 'cdsl_home_cards':
        return extract_items_from_cdsl_home_cards_html(html, base_url, site_key, site)
    if browser_html_strategy == 'cdsl_communiques':
        return extract_items_from_cdsl_communiques_html(html, base_url, site_key, site)
    if browser_html_strategy == 'ncdex_circulars':
        return extract_items_from_ncdex_circulars_html(html, base_url, site_key, site)
    if browser_html_strategy == 'mcxccl_circulars':
        return extract_items_from_mcxccl_circulars_html(html, base_url, site_key, site)
    if browser_html_strategy == 'nsdl_circulars':
        return extract_items_from_nsdl_circulars_html(html, base_url, site_key, site)
    if browser_html_strategy == 'sebi_legal_listing':
        return extract_items_from_sebi_legal_listing_html(html, base_url, site_key, site)
    if browser_html_strategy == 'fiu_guidance_downloads':
        return extract_items_from_fiu_guidance_downloads_html(html, base_url, site_key, site)
    if browser_html_strategy == 'uidai_authentication_docs':
        return extract_items_from_uidai_authentication_docs_html(html, base_url, site_key, site)

    soup = BeautifulSoup(html, 'html.parser')
    return extract_items_from_soup(soup, base_url, site_key, site)


def extract_items_via_openclaw_browser(site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    browser_urls = site.get('browser_urls') or site.get('urls', [])
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for browser_url in browser_urls:
        html = fetch_openclaw_rendered_html(browser_url, site)
        extracted = extract_items_from_browser_rendered_html(html, browser_url, site_key, site)
        for item in extracted:
            link = item.get('link') or item.get('url')
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            items.append(item)

    return sort_items_latest_first(items)


def extract_items_from_soup(soup: BeautifulSoup, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Keep generic extraction compatible with save/dedupe by populating both link and url."""
    items: List[Dict[str, Any]] = []
    nav_terms = ['home', 'about', 'contact', 'login', 'logout', 'search', 'sitemap', 'privacy', 'terms', 'help', 'faq', 'careers', 'media']
    skip_title_terms = ['follow us', 'subscribe', 'copyright', 'website policies', 'disclaimer', 'web information manager']
    skip_url_terms = ['twitter.com', 'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'wa.me/', 'feedburner.com', '/rss-feed']
    required_keywords = [str(keyword).lower() for keyword in site.get('required_keywords', []) if keyword] or GENERIC_REGULATORY_KEYWORDS
    skip_keywords = [str(keyword).lower() for keyword in site.get('skip_keywords', []) if keyword]
    required_url_terms = [str(term).lower() for term in site.get('required_url_terms', []) if term]
    required_title_terms = [str(term).lower() for term in site.get('required_title_terms', []) if term]
    site_skip_title_terms = [str(term).lower() for term in site.get('skip_title_terms', []) if term]
    site_skip_url_terms = [str(term).lower() for term in site.get('skip_url_terms', []) if term]

    for link in soup.find_all('a', href=True):
        href = (link.get('href') or '').strip()
        title = ' '.join(link.get_text(' ', strip=True).split())

        if not title or not href:
            continue
        if href.startswith('#') or 'javascript:' in href or 'mailto:' in href or href.startswith('tel:'):
            continue
        if title in ['View All', 'Read More', 'More', 'Click here', 'Next', 'Previous']:
            continue
        if any(nav_term in title.lower() for nav_term in nav_terms):
            continue
        if any(term in title.lower() for term in skip_title_terms):
            continue
        if any(term in title.lower() for term in site_skip_title_terms):
            continue
        document_urls = extract_discovered_document_urls(href, base_url)
        full_url = document_urls[0] if document_urls else normalize_discovered_url(href, base_url)
        if should_skip_generic_item(title, full_url):
            continue
        if not document_urls and not looks_like_document_url(full_url):
            normalized_base = strip_url_query(base_url).rstrip('/')
            normalized_link = strip_url_query(full_url).rstrip('/')
            if normalized_base and normalized_base == normalized_link:
                continue

        context_node = link.find_parent(['tr', 'li', 'div', 'p']) or link.parent
        context_text = ' '.join(context_node.get_text(' ', strip=True).split()) if context_node else title
        text_blob = f'{title} {full_url} {context_text}'.lower()
        has_document_link = bool(document_urls) or looks_like_document_url(full_url)
        has_keyword_signal = any(keyword in text_blob for keyword in required_keywords)
        has_path_signal = any(term in full_url.lower() for term in GENERIC_REGULATORY_PATH_TERMS)
        # Prefer contextual/table dates over dates embedded in titles or filenames.
        # This avoids misreading effective dates inside titles as publication dates.
        date_str = (
            extract_candidate_date(context_text)
            or extract_candidate_date(title)
            or extract_candidate_date(full_url)
        )

        if len(title) < 10 and not has_document_link:
            continue
        if skip_keywords and any(keyword in text_blob for keyword in skip_keywords):
            continue
        if any(term in text_blob for term in skip_url_terms):
            continue
        if site_skip_url_terms and any(term in full_url.lower() for term in site_skip_url_terms):
            continue
        if required_url_terms and not any(term in full_url.lower() for term in required_url_terms):
            continue
        if required_title_terms and not any(term in title.lower() for term in required_title_terms):
            continue
        if not (has_document_link or has_keyword_signal or has_path_signal):
            continue
        if not has_document_link and not (date_str or has_path_signal):
            continue

        category = 'notice'
        for cat in site.get('update_types', []):
            if cat.lower() in full_url.lower() or cat.lower() in title.lower():
                category = cat
                break

        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')

        items.append({
            'title': title,
            'link': full_url,
            'url': full_url,
            'pub_date': date_str,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': context_text[:200] if context_text else title[:200],
            'category': category,
            'type': category,
            'site': site_key,
            'source': 'scraped',
            'attachments': collect_item_attachments({
                'link': full_url,
                'attachments': [{'url': url} for url in document_urls[1:]],
                'base_url': base_url,
            }),
        })

    return items


def normalize_title_key(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (value or '').lower()).strip()


def build_fragment_item_link(base_url: str, title: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', (title or '').lower()).strip('-')[:96]
    if not slug:
        slug = 'item'
    return f'{base_url}#{slug}'


def get_rss_httpx_client(verify_ssl: bool):
    try:
        return get_httpx_client(verify_ssl=verify_ssl)
    except TypeError:
        return get_httpx_client()


def determine_item_category(title: str, link: str, site: Dict[str, Any]) -> str:
    text_blob = f'{title} {link}'.lower()
    for category in site.get('update_types', []):
        if category.lower() in text_blob:
            return category
    return site.get('update_types', ['notice'])[0] if site.get('update_types') else 'notice'


DOCUMENT_EXTENSIONS = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip')
GENERIC_REGULATORY_KEYWORDS = [
    'circular', 'notification', 'notice', 'order', 'press release',
    'guideline', 'guidelines', 'advisory', 'regulation', 'regulations',
    'master circular', 'public notice', 'clarification', 'compliance',
    'framework', 'filing', 'disclosure', 'listing', 'settlement',
    'grievance', 'directions', 'instruction', 'amendment',
]
GENERIC_SKIP_TITLE_TERMS = [
    'about us', 'about-us', 'contact us', 'branch locator', 'mission/vision',
    'mission vision', 'objectives of', 'website policy', 'website policies',
    'web information manager', 'privacy policy', 'terms of use',
    'sitemap', 'careers', 'investor charter', 'customer care',
    'download app', 'whistle blower', 'whistleblowing',
]
GENERIC_SKIP_URL_TERMS = [
    'twitter.com', 'facebook.com', 'instagram.com', 'linkedin.com',
    'youtube.com', 'wa.me/', '/contact', '/about', '/privacy',
    '/terms', '/careers', '/branch', '/mission', '/vision',
]
GENERIC_REGULATORY_PATH_TERMS = [
    '/circular', '/circulars', '/notification', '/notifications', '/notice',
    '/notices', '/order', '/orders', '/press-release', '/pressreleases',
    '/guideline', '/guidelines', '/compliance', '/listing', '/disclosure',
    '/framework', '/regulation', '/regulations',
]


def parse_normalized_item_date(raw_value: str) -> Optional[str]:
    value = (raw_value or '').strip()
    if not value:
        return None
    value = re.sub(r'\s+,', ',', value)
    value = re.sub(r'(\d{1,2})(st|nd|rd|th)\b', r'\1', value, flags=re.IGNORECASE)
    value = re.sub(r'([A-Za-z])(\d)', r'\1 \2', value)
    value = re.sub(r',\s*', ', ', value)
    value = re.sub(r'\s+', ' ', value).strip()
    month_corrections = {
        'feburary': 'february',
    }
    for incorrect, corrected in month_corrections.items():
        value = re.sub(incorrect, corrected, value, flags=re.IGNORECASE)

    named_date_formats = [
        '%B %d, %Y', '%b %d, %Y', '%B %d %Y', '%b %d %Y',
        '%d %B, %Y', '%d %b, %Y',
        '%d %B %Y', '%d %b %Y', '%B, %Y', '%b, %Y', '%B %Y', '%b %Y',
    ]
    for fmt in named_date_formats + ['%d-%b-%Y', '%d-%B-%Y', '%d-%b-%y', '%d-%B-%y', '%d-%m-%y', '%d.%m.%Y', '%d-%m-%Y', '%d/%m/%Y']:
        try:
            return datetime.strptime(value, fmt).strftime('%Y-%m-%d')
        except Exception:
            continue

    for pattern in [
        r'([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})',
        r'(\d{1,2}\s+[A-Za-z]{3,9},\s+\d{4})',
        r'(\d{1,2}\s+[A-Za-z]{3,9}\s*,\s*\d{4})',
        r'([A-Za-z]{3,9},\s+\d{4})',
        r'([A-Za-z]{3,9}\s+\d{4})',
    ]:
        match = re.search(pattern, value)
        if not match:
            continue
        named_value = match.group(1)
        for fmt in named_date_formats:
            try:
                return datetime.strptime(named_value, fmt).strftime('%Y-%m-%d')
            except Exception:
                continue

    for pattern in [r'(\d{2})[-/](\d{2})[-/](\d{4})', r'(\d{4})[-/](\d{2})[-/](\d{2})']:
        match = re.search(pattern, value)
        if not match:
            continue
        parts = match.groups()
        try:
            if len(parts[0]) == 4:
                return datetime(int(parts[0]), int(parts[1]), int(parts[2])).strftime('%Y-%m-%d')
            return datetime(int(parts[2]), int(parts[1]), int(parts[0])).strftime('%Y-%m-%d')
        except ValueError:
            continue

    compact_match = re.search(r'(20\d{2})(\d{2})(\d{2})', value)
    if compact_match:
        try:
            return datetime(
                int(compact_match.group(1)),
                int(compact_match.group(2)),
                int(compact_match.group(3)),
            ).strftime('%Y-%m-%d')
        except ValueError:
            pass

    compact_ddmmyyyy_match = re.search(r'(\d{2})(\d{2})(20\d{2})', value)
    if compact_ddmmyyyy_match:
        day, month, year = compact_ddmmyyyy_match.groups()
        try:
            return datetime(int(year), int(month), int(day)).strftime('%Y-%m-%d')
        except ValueError:
            pass

    compact_ddmmyy_match = re.search(r'(\d{2})(\d{2})(\d{2})', value)
    if compact_ddmmyy_match:
        day, month, year_suffix = compact_ddmmyy_match.groups()
        year = int(year_suffix)
        year_prefix = '20' if year <= 50 else '19'
        try:
            return datetime(int(f'{year_prefix}{year_suffix}'), int(month), int(day)).strftime('%Y-%m-%d')
        except ValueError:
            pass

    separated_ddmmyy_match = re.search(r'(\d{2})[_-](\d{2})[_-](\d{2})', value)
    if separated_ddmmyy_match:
        day, month, year_suffix = separated_ddmmyy_match.groups()
        year = int(year_suffix)
        year_prefix = '20' if year <= 50 else '19'
        try:
            return datetime(int(f'{year_prefix}{year_suffix}'), int(month), int(day)).strftime('%Y-%m-%d')
        except ValueError:
            pass

    compact_with_suffix_match = re.search(r'(\d{2})(\d{2})[_-](\d{2})', value)
    if compact_with_suffix_match:
        day, month, year_suffix = compact_with_suffix_match.groups()
        year = int(year_suffix)
        year_prefix = '20' if year <= 50 else '19'
        try:
            return datetime(int(f'{year_prefix}{year_suffix}'), int(month), int(day)).strftime('%Y-%m-%d')
        except ValueError:
            pass

    return None


def normalize_item_date(raw_value: str, fallback: Optional[str] = None) -> str:
    for candidate in [raw_value, fallback]:
        parsed_value = parse_normalized_item_date(candidate or '')
        if parsed_value:
            return parsed_value

    return datetime.now().strftime('%Y-%m-%d')


def looks_like_document_url(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return any(path.endswith(extension) for extension in DOCUMENT_EXTENSIONS)


def normalize_discovered_url(raw_url: str, base_url: str = '') -> str:
    value = ' '.join((raw_url or '').split())
    if not value:
        return ''

    value = value.replace('\\', '/')
    if value.startswith('//'):
        parsed_base = urlsplit(base_url) if base_url else None
        scheme = parsed_base.scheme if parsed_base and parsed_base.scheme else 'https'
        value = f'{scheme}:{value}'

    if value.startswith(('http://', 'https://')):
        return value
    if base_url:
        return urljoin(base_url, value)
    return value


def extract_discovered_document_urls(raw_value: str, base_url: str = '') -> List[str]:
    value = ' '.join((raw_value or '').split())
    if not value:
        return []

    candidate_parts = [value]
    if ',' in value:
        split_parts = [part.strip() for part in value.split(',') if part.strip()]
        if split_parts:
            candidate_parts = split_parts

    document_urls: List[str] = []
    seen_urls = set()
    for part in candidate_parts:
        normalized_url = normalize_discovered_url(part, base_url)
        if not normalized_url or normalized_url in seen_urls:
            continue
        if not looks_like_document_url(normalized_url):
            continue
        seen_urls.add(normalized_url)
        document_urls.append(normalized_url)

    return document_urls


def extract_candidate_date(raw_value: str) -> Optional[str]:
    value = ' '.join((raw_value or '').split())
    if not value:
        return None

    patterns = [
        r'[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}',
        r'\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}',
        r'\d{1,2}\s+[A-Za-z]{3,9}\s*,\s*\d{4}',
        r'[A-Za-z]{3,9},\s+\d{4}',
        r'\d{1,2}-[A-Za-z]{3,9}-\d{4}',
        r'\d{2}[-/]\d{2}[-/]\d{4}',
        r'\d{4}[-/]\d{2}[-/]\d{2}',
        r'\d{2}\.\d{2}\.\d{4}',
        r'\d{1,2}[-/]\d{2}[-/]\d{2}',
        r'\d{2}[_-]\d{2}[_-]\d{2}',
        r'\d{4}[_-]\d{2}',
        r'\d{8}',
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if not match:
            continue
        normalized_date = parse_normalized_item_date(match.group(0))
        if normalized_date:
            return normalized_date

    return None


def should_skip_generic_item(title: str, full_url: str) -> bool:
    normalized_title = ' '.join(title.split()).strip().lower()
    lower_url = (full_url or '').lower()

    if not normalized_title:
        return True
    if re.fullmatch(r'[\+\d()\-\s]{7,}', normalized_title):
        return True
    if '@' in normalized_title:
        return True
    if normalized_title.startswith('www.'):
        return True
    if any(term in normalized_title for term in GENERIC_SKIP_TITLE_TERMS):
        return True
    if any(term in lower_url for term in GENERIC_SKIP_URL_TERMS):
        return True

    return False


def infer_attachment_file_type(url: str) -> Optional[str]:
    path = urlsplit(url).path.lower()
    for extension in DOCUMENT_EXTENSIONS:
        if path.endswith(extension):
            return extension[1:]
    return None


def collect_item_attachments(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    attachments: List[Dict[str, Any]] = []
    seen_urls = set()
    attachment_index_by_url: Dict[str, int] = {}
    base_url = item.get('base_url') or item.get('source_url') or ''

    def append_attachment_url(raw_url: str, *, filename: Optional[str] = None, file_type: Optional[str] = None) -> None:
        normalized_url = normalize_discovered_url(raw_url, base_url)
        if not normalized_url:
            return
        if normalized_url in seen_urls:
            existing = attachments[attachment_index_by_url[normalized_url]]
            existing_basename = os.path.basename(urlsplit(normalized_url).path) or None
            if filename and (
                not existing.get('filename')
                or (existing_basename and existing.get('filename') == existing_basename)
            ):
                existing['filename'] = filename
            if file_type and not existing.get('file_type'):
                existing['file_type'] = file_type
            return
        seen_urls.add(normalized_url)
        attachment_index_by_url[normalized_url] = len(attachments)
        attachments.append({
            'url': normalized_url,
            'filename': filename or os.path.basename(urlsplit(normalized_url).path) or None,
            'file_type': file_type or infer_attachment_file_type(normalized_url),
        })

    direct_link = item.get('link') or item.get('url') or ''
    direct_link_urls = extract_discovered_document_urls(direct_link, base_url)
    if not direct_link_urls and direct_link:
        normalized_direct_link = normalize_discovered_url(direct_link, base_url)
        if looks_like_document_url(normalized_direct_link):
            direct_link_urls = [normalized_direct_link]

    for direct_link_url in direct_link_urls:
        append_attachment_url(direct_link_url)

    candidate_file_url = item.get('candidate_file_url') or ''
    if candidate_file_url:
        append_attachment_url(candidate_file_url)

    for attachment in item.get('attachments', []) or []:
        attachment_url = (attachment or {}).get('url')
        normalized_attachment_urls = extract_discovered_document_urls(attachment_url, base_url)
        if not normalized_attachment_urls and attachment_url:
            normalized_attachment_urls = [attachment_url]
        for normalized_attachment_url in normalized_attachment_urls:
            append_attachment_url(
                normalized_attachment_url,
                filename=(attachment or {}).get('filename'),
                file_type=(attachment or {}).get('file_type'),
            )

    return attachments


def persist_item_attachments(conn, update_id: str, item: Dict[str, Any]) -> None:
    for attachment in collect_item_attachments(item):
        conn.execute(
            """
            INSERT OR IGNORE INTO attachments (update_id, url, filename, file_type, file_size)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                update_id,
                attachment['url'],
                attachment.get('filename'),
                attachment.get('file_type'),
                attachment.get('file_size'),
            ),
        )


def sort_items_latest_first(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            item.get('pub_date') or '',
            item.get('isoDate') or '',
            item.get('title') or '',
        ),
        reverse=True,
    )


def build_mca_edge_options():
    if EdgeOptions is None:
        raise RuntimeError('selenium Edge options unavailable')

    options = EdgeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument('--headless=new')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1440,1200')
    options.add_argument('--lang=en-US')
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
    )
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    return options


def fetch_mca_home_html(browser_url: str) -> str:
    if webdriver is None:
        raise RuntimeError('selenium not available')

    last_exception = None
    for attempt in range(2):
        driver = webdriver.Edge(options=build_mca_edge_options())
        try:
            driver.set_page_load_timeout(45)
            try:
                driver.get(browser_url)
            except SeleniumTimeoutException:
                driver.execute_script('window.stop();')
            time.sleep(6)
            page_source = driver.page_source or ''
            if page_source and (
                'titleSearchTabs' in page_source
                or 'marquee-container' in page_source
                or attempt == 1
            ):
                return page_source
        except Exception as exc:
            last_exception = exc
            if attempt == 1:
                raise
        finally:
            driver.quit()
        time.sleep(2)

    if last_exception:
        raise last_exception
    raise RuntimeError(f'Unable to fetch browser HTML for {browser_url}')


def extract_items_from_mca_home_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    keywords = [
        'circular', 'notification', 'notice', 'order', 'adjudication'
    ]
    card_skip_terms = [
        'webinar', 'presentation', 'help kit', 'user manual', 'user guide',
        'training', 'awareness', 'brochure'
    ]
    marquee_skip_terms = [
        'faq', 'faqs', 'webinar', 'presentation', 'video demo', 'go live',
        'login registration', 'professional staff member'
    ]

    def add_item(title: str, href: str, raw_date: str, snippet: str = ''):
        if not title or not href:
            return
        if href.startswith(('javascript:', 'mailto:', 'tel:')):
            return

        link = href if href.startswith('http') else urljoin(base_url, href)
        if link in seen_links:
            return

        category = determine_item_category(title, link, site)
        pub_date = normalize_item_date(raw_date, fallback=f'{title} {link}')
        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': (snippet or title)[:200],
            'category': category,
            'type': category,
            'site': site_key,
            'source': 'scraped'
        })

    for title_node in soup.select('p.titleSearchTabs'):
        title = ' '.join(title_node.get_text(' ', strip=True).split())
        anchor = title_node.find_parent('a')
        href = anchor.get('href') if anchor else None
        if not title or not href:
            continue

        normalized_title = title.lower()
        if any(term in normalized_title for term in card_skip_terms):
            continue

        text_blob = f'{title} {href}'.lower()
        if not any(keyword in text_blob for keyword in keywords):
            continue

        title_container = title_node.find_parent(class_='titleSizeDate') or title_node.parent
        date_node = title_container.find('p', class_='doc-date') if title_container else None
        raw_date = date_node.get_text(' ', strip=True) if date_node else ''
        add_item(title, href, raw_date, snippet=title)

    for marquee_link in soup.select('div.marquee-container a[href]'):
        href = marquee_link.get('href')
        if not href:
            continue

        anchor_text = ' '.join(marquee_link.get_text(' ', strip=True).split())
        if anchor_text.lower() in {'', 'ddegov@mca.gov.in'}:
            continue

        title = anchor_text
        if anchor_text.lower() == 'please click here for more details.':
            title = ' '.join(str(marquee_link.previous_sibling or '').split()).rstrip('.')
            if len(title) < 12:
                context_node = marquee_link.find_parent(['p', 'li']) or marquee_link.parent
                context_parts = []
                if context_node:
                    for child in context_node.children:
                        if child == marquee_link:
                            break
                        child_text = ' '.join(str(getattr(child, 'get_text', lambda *args, **kwargs: child)(' ', strip=True)).split()) if hasattr(child, 'get_text') else ' '.join(str(child).split())
                        if child_text:
                            context_parts.append(child_text)
                title = ' '.join(context_parts).rstrip('.')

        if len(title) < 12:
            continue

        normalized_title = title.lower()
        if any(term in normalized_title for term in marquee_skip_terms):
            continue

        text_blob = f'{title} {href}'.lower()
        if not looks_like_document_url(urljoin(base_url, href)) and not any(keyword in text_blob for keyword in keywords):
            continue

        add_item(title, href, href, snippet=title)

    return items


def parse_rss_pub_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized_value = re.sub(r'\s+', ' ', value.strip())
    try:
        dt = parsedate_to_datetime(normalized_value)
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%d')
    except Exception:
        trimmed_value = re.sub(r'\s*[+-]\d{4}$', '', normalized_value).strip()
        for fmt in [
            '%A, %B %d, %Y',
            '%A, %b %d, %Y',
            '%d %B %Y',
            '%d %b %Y',
            '%d %B, %Y',
            '%d %b, %Y',
        ]:
            try:
                return datetime.strptime(trimmed_value, fmt).strftime('%Y-%m-%d')
            except Exception:
                continue
        parse_date_fn = getattr(main_v7_fixed_base, 'parse_date', None)
        return parse_date_fn(trimmed_value) if parse_date_fn else None


def parse_yyyymmdd_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y%m%d').strftime('%Y-%m-%d')
    except Exception:
        return None


def strip_url_query(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))


async def extract_items_from_bse_notices(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    include_terms = [str(term).lower() for term in site.get('bse_include_terms', []) if term]
    max_previous_days = max(0, int(site.get('bse_previous_day_lookback') or 7))
    items: List[Dict[str, Any]] = []

    def parse_rows(page_html: str, page_url: str) -> List[Dict[str, Any]]:
        page_items: List[Dict[str, Any]] = []
        seen_links = set()
        soup = BeautifulSoup(page_html, 'html.parser')
        table_rows = soup.select('#ContentPlaceHolder1_GridView1 tr') or soup.select('table tr')
        for row in table_rows:
            cells = row.find_all('td')
            if len(cells) < 5:
                continue

            values = [cell.get_text(' ', strip=True) for cell in cells[:5]]
            notice_no, title_text, segment_name, category_name, department_name = values
            row_text = ' '.join(values).lower()
            if include_terms and not any(term in row_text for term in include_terms):
                continue

            subject_link = cells[1].find('a', href=True)
            if not subject_link:
                continue

            title = subject_link.get_text(' ', strip=True)
            if not title:
                continue

            link = urljoin(page_url, subject_link['href'])
            if not link or link in seen_links:
                continue

            pub_date = parse_yyyymmdd_date((notice_no or '').split('-')[0])
            if not pub_date:
                continue

            summary = ' | '.join(
                part for part in [segment_name, category_name, department_name] if part
            )
            page_items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': pub_date,
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': summary[:200] if summary else title[:200],
                'category': 'notice',
                'type': 'notice',
                'site': site_key,
                'source': 'scraped'
            })
            seen_links.add(link)
        return page_items

    def build_postback_form(soup: BeautifulSoup) -> Dict[str, str]:
        form_data: Dict[str, str] = {}
        for input_tag in soup.select('input[name]'):
            name = input_tag.get('name')
            if not name:
                continue
            input_type = (input_tag.get('type') or '').lower()
            if input_type in {'checkbox', 'radio', 'submit', 'image', 'button', 'file'}:
                continue
            form_data[name] = input_tag.get('value', '')
        form_data['__EVENTTARGET'] = 'ctl00$ContentPlaceHolder1$lnkPreviousDay'
        form_data['__EVENTARGUMENT'] = ''
        return form_data

    for url in site.get('urls', []):
        response = await fetch_with_retry(url, client, SCRAPER_MAX_RETRIES)
        if not response:
            continue

        current_html = response.text
        current_url = getattr(response, 'url', None) or url
        for day_offset in range(max_previous_days + 1):
            page_items = parse_rows(current_html, str(current_url))
            if page_items:
                items.extend(page_items)
                break

            if day_offset >= max_previous_days:
                break

            soup = BeautifulSoup(current_html, 'html.parser')
            previous_link = soup.find(id='ContentPlaceHolder1_lnkPreviousDay')
            if not previous_link:
                break

            form_data = build_postback_form(soup)
            try:
                post_response = await client.post(
                    url,
                    data=form_data,
                    headers={
                        'User-Agent': 'Mozilla/5.0',
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Referer': url,
                        'Origin': 'https://www.bseindia.com',
                    },
                )
                post_response.raise_for_status()
            except Exception:
                break

            current_html = post_response.text
            current_url = getattr(post_response, 'url', None) or url

    return items


async def extract_items_from_cbdt_structured_contents(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    page_url = site.get('browser_url') or (site.get('urls') or ['https://www.incometaxindia.gov.in/circulars'])[0]
    response = await fetch_with_retry(page_url, client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    html = response.text
    auth_match = re.search(r"Liferay\.authToken\s*=\s*'([^']+)'", html)
    scope_group_match = re.search(r"getScopeGroupId:\s*function\s*\(\)\s*\{\s*return '(\d+)';", html)
    structure_match = re.search(r'<etds-circular-notification[^>]+structureid="(\d+)"', html, re.IGNORECASE)
    if not auth_match or not scope_group_match or not structure_match:
        return []

    auth_token = auth_match.group(1)
    structure_id = structure_match.group(1)
    search_url = 'https://www.incometaxindia.gov.in/o/search/v1.0/search'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Accept-Language': 'en-US',
        'x-csrf-token': auth_token,
        'Origin': 'https://www.incometaxindia.gov.in',
        'Referer': page_url,
    }

    items: List[Dict[str, Any]] = []
    seen_links = set()
    page = 1
    last_page = 1

    max_pages = max(1, int(site.get('max_pages') or 10))
    while page <= last_page and page <= max_pages:
        params = {
            'page': page,
            'pageSize': int(site.get('page_size') or 50),
            'restrictFields': 'actions,creator',
            'nestedFields': 'embedded',
            'fields': 'embedded.taxonomyCategoryBriefs,embedded.contentFields,itemURL,title',
            'search': '',
        }
        payload = {
            'attributes': {
                'search.empty.search': True,
                'search.experiences.blueprint.external.reference.code': 'RELATED_ITEMS_DATE_BP_ERC',
                'search.experiences.sortOrder': 'desc',
                'search.experiences.structure_id': structure_id,
            }
        }
        search_response = await client.post(search_url, params=params, headers=headers, json=payload)
        search_response.raise_for_status()
        search_payload = search_response.json()
        last_page = int(search_payload.get('lastPage') or 1)

        for row in search_payload.get('items') or []:
            embedded = row.get('embedded') or {}
            content_fields = embedded.get('contentFields') or []
            field_map = {}
            for field in content_fields:
                value = field.get('contentFieldValue') or {}
                field_map[field.get('name') or ''] = value

            circular_number = (field_map.get('circularNotificationNumber') or {}).get('data') or ''
            circular_date = (field_map.get('circularNotificationDate') or {}).get('data') or ''
            upload_date = (field_map.get('uploadDate') or {}).get('data') or ''
            report_file = (field_map.get('reportFile') or {}).get('document') or {}
            document_content = (field_map.get('documentContent') or {}).get('data') or ''

            if not circular_number:
                continue

            title = ' '.join((row.get('title') or '').split())
            if not title:
                continue

            link = ''
            attachments: List[Dict[str, Any]] = []
            report_file_url = report_file.get('contentUrl')
            if report_file_url:
                link = urljoin('https://www.incometaxindia.gov.in', report_file_url)
                attachments.append({
                    'url': link,
                    'filename': report_file.get('title') or os.path.basename(urlsplit(link).path) or None,
                    'file_type': report_file.get('fileExtension') or infer_attachment_file_type(link),
                })
            else:
                detail_url = row.get('itemURL') or ''
                if detail_url:
                    link = normalize_discovered_url(detail_url, 'https://www.incometaxindia.gov.in')
                else:
                    continue

            if link in seen_links:
                continue
            seen_links.add(link)

            summary = ''
            for summary_field in ['summary', 'shortDescription', 'description']:
                value = (field_map.get(summary_field) or {}).get('data') or ''
                if value:
                    summary = BeautifulSoup(value, 'html.parser').get_text(' ', strip=True)
                    break
            if not summary:
                summary = circular_number

            pub_date = normalize_item_date(circular_date, fallback=upload_date)
            items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': pub_date,
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': summary[:200] if summary else title[:200],
                'category': 'notification',
                'type': 'notification',
                'site': site_key,
                'source': 'scraped',
                'attachments': attachments,
                'reference_number': circular_number,
            })

        page += 1

    return sort_items_latest_first(items)


def extract_items_from_gst_council_circulars_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for row in soup.select('table tr'):
        cells = row.find_all('td')
        if len(cells) < 5:
            continue

        circular_no = ' '.join(cells[1].get_text(' ', strip=True).split())
        raw_date = cells[3].get_text(' ', strip=True)
        title = ' '.join(cells[4].get_text(' ', strip=True).split())
        link_nodes = [node for node in cells[2].find_all('a', href=True)]
        if not title or not link_nodes:
            continue

        document_links = []
        for link_node in link_nodes:
            href = (link_node.get('href') or '').strip()
            if not href:
                continue
            document_link = urljoin(base_url, href)
            if document_link in document_links:
                continue
            document_links.append(document_link)

        if not document_links or document_links[0] in seen_links:
            continue

        primary_link = document_links[0]
        seen_links.add(primary_link)
        items.append({
            'title': title,
            'link': primary_link,
            'url': primary_link,
            'pub_date': normalize_item_date(raw_date, fallback=f'{title} {primary_link}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': circular_no[:200] if circular_no else title[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
            'attachments': [
                {
                    'url': attachment_link,
                    'filename': os.path.basename(urlsplit(attachment_link).path) or None,
                    'file_type': infer_attachment_file_type(attachment_link),
                }
                for attachment_link in document_links[1:]
            ],
        })

    return items


async def extract_items_from_gst_council_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_gst_council_circulars_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_cdsl_home_cards_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    required_terms = [str(term).lower() for term in site.get('required_keywords', []) if term]
    skip_terms = [str(term).lower() for term in site.get('skip_title_terms', []) if term]

    for card in soup.select('.more-new-box'):
        title_node = card.select_one('.news-small-title') or card.find(['h3', 'h4', 'h5'])
        link_node = None
        for anchor in card.select('a[href]'):
            href = (anchor.get('href') or '').strip()
            if href:
                link_node = anchor
                break

        title = ' '.join(title_node.get_text(' ', strip=True).split()) if title_node else ''
        href = (link_node.get('href') or '').strip() if link_node else ''
        if not title or not href:
            continue

        text_blob = f'{title} {href}'.lower()
        if required_terms and not any(term in text_blob for term in required_terms):
            continue
        if skip_terms and any(term in text_blob for term in skip_terms):
            continue

        link = urljoin(base_url, href)
        if link in seen_links:
            continue

        seen_links.add(link)
        pub_date = extract_candidate_date(f'{title} {href}') or ''
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': title[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped'
        })

    return items


async def extract_items_from_cdsl_home_cards(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_cdsl_home_cards_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_cdsl_communiques_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    base_time = datetime.now(timezone.utc)

    for index, row in enumerate(soup.select('#tblCommuniquDtlBody tr')):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 3:
            continue

        communique_no = ' '.join(cells[0].get_text(' ', strip=True).split())
        link_node = cells[1].find('a', href=True)
        title_text = ' '.join(cells[1].get_text(' ', strip=True).split())
        raw_date = ' '.join(cells[2].get_text(' ', strip=True).split())
        href = (link_node.get('href') or '').strip() if link_node else ''
        if not communique_no or not title_text or not href:
            continue

        link = urljoin(base_url, href)
        if link in seen_links:
            continue

        seen_links.add(link)
        title = f'{communique_no} - {title_text}'
        pub_date = parse_normalized_item_date(raw_date) or extract_candidate_date(f'{title} {href}')
        if not pub_date:
            continue
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': (base_time - timedelta(seconds=index)).isoformat(),
            'content_snippet': communique_no[:200],
            'category': 'circular',
            'type': 'communique',
            'site': site_key,
            'source': 'scraped',
            'candidate_file_url': link,
            'attachments': collect_item_attachments({
                'link': link,
                'base_url': base_url,
            }),
        })

    return sort_items_latest_first(items)


async def extract_items_from_cdsl_communiques_api(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    base_url = site['urls'][0]
    load_url = site.get('cdsl_load_url') or urljoin(base_url, '/eservices/Publications/GetOnLoadCommunique')
    initial_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    ajax_headers = {
        'User-Agent': initial_headers['User-Agent'],
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'https://www.cdslindia.com',
        'Referer': base_url,
        'X-Requested-With': 'XMLHttpRequest',
    }
    payload = {
        'm_arch_status': site.get('cdsl_archive_status', 'A'),
        'type': str(site.get('cdsl_type', '3')),
        'cno': site.get('cdsl_cno', 'DP%'),
        'fromDate': site.get('cdsl_from_date', '01-Jan-1990'),
        'toDate': site.get('cdsl_to_date', ''),
        'Keyword': site.get('cdsl_keyword', '%'),
        'Subject': site.get('cdsl_subject', '%'),
        'GCaptcha': site.get('cdsl_gcaptcha', '%'),
    }

    warmup_response = await client.get(base_url, headers=initial_headers)
    warmup_response.raise_for_status()

    response = await client.post(load_url, data=payload, headers=ajax_headers)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        return []

    items: List[Dict[str, Any]] = []
    seen_links = set()
    base_time = datetime.now(timezone.utc)

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        communique_no = ' '.join(str(row.get('comM_ID') or '').split())
        subject = ' '.join(str(row.get('subject') or row.get('description') or '').split())
        raw_date = ' '.join(str(row.get('comM_DATE') or '').split())
        raw_attachment = str(row.get('attachmenT_URL') or '').strip()

        if not communique_no or not subject:
            continue

        download_url = urljoin(
            base_url,
            f"../Publications/DownloadFile?eventID={quote(communique_no)}&method=communique",
        )
        link = download_url
        if not link or link in seen_links:
            continue

        pub_date = parse_normalized_item_date(raw_date) or extract_candidate_date(f'{subject} {raw_attachment} {communique_no}')
        if not pub_date:
            continue

        title = f'{communique_no} - {subject}'
        seen_links.add(link)
        attachment_filename = os.path.basename(raw_attachment.replace('\\', '/')) or None
        attachment_file_type = infer_attachment_file_type(raw_attachment.replace('\\', '/')) or None
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': (base_time - timedelta(seconds=index)).isoformat(),
            'content_snippet': subject[:200],
            'category': 'circular',
            'type': 'communique',
            'site': site_key,
            'source': 'scraped',
            'candidate_file_url': download_url,
            'attachments': collect_item_attachments({
                'link': download_url,
                'base_url': base_url,
                'attachments': [{
                    'url': download_url,
                    'filename': attachment_filename,
                    'file_type': attachment_file_type,
                }],
            }),
        })

    return sort_items_latest_first(items)


def extract_items_from_icmai_notifications_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    container = soup.find(id='Notification_Updates')
    if not container:
        return []

    for anchor in container.select('a[href]'):
        title = ' '.join(anchor.get_text(' ', strip=True).replace('New', ' ').split())
        href = (anchor.get('href') or '').strip()
        if not title or not href:
            continue

        link = urljoin(base_url, href)
        if link in seen_links:
            continue

        pub_date = extract_candidate_date(f'{title} {link}')
        if not pub_date:
            continue

        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': title[:200],
            'category': 'notification',
            'type': 'notification',
            'site': site_key,
            'source': 'scraped',
        })

    return sort_items_latest_first(items)


async def extract_items_from_icmai_notifications(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_icmai_notifications_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_iba_circulars_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for row in soup.select('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 3:
            continue

        link_node = cells[2].find('a', href=True)
        if not link_node:
            continue

        title = ' '.join(link_node.get_text(' ', strip=True).split())
        raw_date = ' '.join(cells[1].get_text(' ', strip=True).split())
        href = (link_node.get('href') or '').strip()
        if not title or not raw_date or not href:
            continue

        link = urljoin(base_url, href)
        if link in seen_links:
            continue

        seen_links.add(link)
        pub_date = extract_candidate_date(raw_date)
        if not pub_date:
            continue

        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': raw_date[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
        })

    return sort_items_latest_first(items)


async def extract_items_from_iba_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_iba_circulars_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_cestat_circulars_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    table = soup.select_one('table#circular')
    if not table:
        return []
    base_time = datetime.now(timezone.utc)

    for index, row in enumerate(table.select('tbody tr')):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 4:
            continue

        title = ' '.join(cells[1].get_text(' ', strip=True).split())
        raw_date = ' '.join(cells[2].get_text(' ', strip=True).split())
        link_node = cells[3].find('a', href=True)
        href = (link_node.get('href') or '').strip() if link_node else ''
        if not title or not raw_date or not href:
            continue

        link = urljoin(base_url, href)
        if link in seen_links:
            continue

        seen_links.add(link)
        pub_date = normalize_item_date(raw_date, fallback=f'{title} {href}')
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': (base_time - timedelta(seconds=index)).isoformat(),
            'content_snippet': raw_date[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
            'candidate_file_url': link,
            'attachments': collect_item_attachments({
                'link': link,
                'base_url': base_url,
            }),
        })

    return sort_items_latest_first(items)


async def extract_items_from_cestat_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_cestat_circulars_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_mse_circulars_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for row in soup.select('table.t-listview tr'):
        cells = row.find_all('td')
        if len(cells) < 5:
            continue

        raw_date = ' '.join(cells[0].get_text(' ', strip=True).split())
        circular_number = ' '.join(cells[1].get_text(' ', strip=True).split())
        segment = ' '.join(cells[2].get_text(' ', strip=True).split())
        department = ' '.join(cells[3].get_text(' ', strip=True).split())
        link_node = cells[4].find('a', href=True)
        if not link_node:
            continue

        title = ' '.join(link_node.get_text(' ', strip=True).split())
        href = normalize_discovered_url(link_node.get('href') or '', base_url)
        if not raw_date or not title or not href:
            continue
        if title.lower() == 'back to circulars':
            continue
        if '/sx-content/circulars/' not in href.lower():
            continue
        if href in seen_links:
            continue

        seen_links.add(href)
        detail_bits = []
        if circular_number:
            detail_bits.append(f'Circular No. {circular_number}')
        if segment:
            detail_bits.append(segment)
        if department:
            detail_bits.append(department)

        items.append({
            'title': title,
            'link': href,
            'url': href,
            'pub_date': normalize_item_date(raw_date, fallback=f'{title} {href}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': ' | '.join(detail_bits)[:200] if detail_bits else title[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
            'candidate_file_url': href,
            'attachments': collect_item_attachments({
                'link': href,
                'base_url': base_url,
            }),
        })

    return sort_items_latest_first(items)


async def extract_items_from_mse_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_mse_circulars_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_dfs_circulars_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for row in soup.select('table tbody tr'):
        ref_cell = row.select_one('td.views-field-field-location')
        subject_cell = row.select_one('td[headers="view-field-attached-table-column"]')
        date_cell = row.select_one('td.views-field-field-start-date')
        section_cell = row.select_one('td.views-field-field-tags')
        addressed_to_cell = row.select_one('td.views-field-body')
        link_node = subject_cell.find('a', href=True) if subject_cell else None
        if not ref_cell or not subject_cell or not date_cell or not link_node:
            continue

        reference_number = ' '.join(ref_cell.get_text(' ', strip=True).split())
        title = ' '.join(link_node.get_text(' ', strip=True).split())
        raw_date = ' '.join(date_cell.get_text(' ', strip=True).split())
        section = ' '.join(section_cell.get_text(' ', strip=True).split()) if section_cell else ''
        addressed_to = ' '.join(addressed_to_cell.get_text(' ', strip=True).split()) if addressed_to_cell else ''
        href = normalize_discovered_url(link_node.get('href') or '', base_url)
        if not title or not raw_date or not href:
            continue
        if href in seen_links:
            continue

        seen_links.add(href)
        detail_bits = []
        if reference_number:
            detail_bits.append(f'Circular No. {reference_number}')
        if section:
            detail_bits.append(section)
        if addressed_to:
            detail_bits.append(addressed_to)

        items.append({
            'title': title,
            'link': href,
            'url': href,
            'pub_date': normalize_item_date(raw_date, fallback=f'{title} {href}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': ' | '.join(detail_bits)[:200] if detail_bits else title[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
            'reference_number': reference_number,
            'candidate_file_url': href,
            'attachments': collect_item_attachments({
                'link': href,
                'base_url': base_url,
            }),
        })

    return sort_items_latest_first(items)


async def extract_items_from_dfs_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_dfs_circulars_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_fiu_compliance_orders_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    orders_root = soup.select_one('#orders')
    if not orders_root:
        return []

    items: List[Dict[str, Any]] = []
    seen_links = set()

    for table in orders_root.select('table.table-bordered'):
        for row in table.select('tr'):
            cells = row.find_all('td')
            if len(cells) < 5:
                continue

            raw_date = ' '.join(cells[1].get_text(' ', strip=True).split())
            description = ' '.join(cells[2].get_text(' ', strip=True).split())
            link_node = cells[4].find('a', href=True)
            if not raw_date or not description or not link_node:
                continue

            href = normalize_discovered_url(link_node.get('href') or '', base_url)
            if not href or '/pdfs/judgements/' not in href.lower():
                continue
            if href in seen_links:
                continue

            seen_links.add(href)
            items.append({
                'title': description,
                'link': href,
                'url': href,
                'pub_date': normalize_item_date(raw_date, fallback=f'{description} {href}'),
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': raw_date[:200],
                'category': 'order',
                'type': 'order',
                'site': site_key,
                'source': 'scraped',
                'candidate_file_url': href,
                'attachments': collect_item_attachments({
                    'link': href,
                    'base_url': base_url,
                }),
            })

    return sort_items_latest_first(items)


async def extract_items_from_fiu_compliance_orders(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_fiu_compliance_orders_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_sebi_legal_listing_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    required_url_terms = [term.lower() for term in site.get('required_url_terms', [])]
    title_keywords = [term.lower() for term in site.get('sebi_title_keywords', [])]
    skip_title_terms = [term.lower() for term in site.get('skip_title_terms', [])]

    for row in soup.select('table tbody tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 2:
            continue

        raw_date = ' '.join(cells[0].get_text(' ', strip=True).split())
        link_node = cells[1].find('a', href=True)
        title = ' '.join((link_node or cells[1]).get_text(' ', strip=True).split())
        href = normalize_discovered_url((link_node.get('href') if link_node else '') or '', base_url)
        if not raw_date or not title or not href:
            continue
        if required_url_terms and not any(term in href.lower() for term in required_url_terms):
            continue

        title_lower = title.lower()
        if title_keywords and not any(term in title_lower for term in title_keywords):
            continue
        if skip_title_terms and any(term in title_lower for term in skip_title_terms):
            continue
        if href in seen_links:
            continue

        seen_links.add(href)
        item_type = 'master-circular' if 'master circular' in title_lower else 'regulation'
        items.append({
            'title': title,
            'link': href,
            'url': href,
            'pub_date': normalize_item_date(raw_date, fallback=f'{title} {href}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': raw_date[:200],
            'category': item_type,
            'type': item_type,
            'site': site_key,
            'source': 'scraped',
        })

    return sort_items_latest_first(items)


async def extract_items_from_sebi_legal_listing(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = None
    try:
        response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    except Exception:
        response = None
    if response:
        html = response.text
    elif site.get('remote_rss_via_ssh'):
        html = await asyncio.to_thread(fetch_remote_html_text_via_ssh, site['urls'][0], site)
    else:
        return []

    return extract_items_from_sebi_legal_listing_html(html, site['urls'][0], site_key, site)


def extract_items_from_sebi_news_listing_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    required_keywords = [term.lower() for term in site.get('required_keywords', [])]
    skip_keywords = [term.lower() for term in site.get('skip_keywords', [])]
    allowed_types = [term.lower() for term in site.get('sebi_listing_types', ['circulars', 'master circulars'])]

    for row in soup.select('table tr'):
        cells = row.find_all(['th', 'td'], recursive=False)
        if len(cells) < 3:
            continue

        raw_date = ' '.join(cells[0].get_text(' ', strip=True).split())
        item_type = ' '.join(cells[1].get_text(' ', strip=True).split())
        link_node = cells[2].find('a', href=True)
        title = ' '.join((link_node or cells[2]).get_text(' ', strip=True).split())
        href = normalize_discovered_url((link_node.get('href') if link_node else '') or '', base_url)
        if not raw_date or not item_type or not title or not href:
            continue

        item_type_lower = item_type.lower()
        title_lower = title.lower()
        if allowed_types and item_type_lower not in allowed_types:
            continue
        if required_keywords and not any(term in title_lower for term in required_keywords):
            continue
        if skip_keywords and any(term in title_lower for term in skip_keywords):
            continue
        if href in seen_links:
            continue

        seen_links.add(href)
        normalized_type = 'master-circular' if 'master circular' in item_type_lower else 'circular'
        items.append({
            'title': title,
            'link': href,
            'url': href,
            'pub_date': normalize_item_date(raw_date, fallback=f'{title} {href}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': item_type[:200],
            'category': normalized_type,
            'type': normalized_type,
            'site': site_key,
            'source': 'scraped',
        })

    return sort_items_latest_first(items)


async def extract_items_from_sebi_news_listing(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for url in site.get('urls', []):
        response = None
        try:
            response = await fetch_with_retry(url, client, SCRAPER_MAX_RETRIES)
        except Exception:
            response = None
        if response:
            html = response.text
        elif site.get('remote_rss_via_ssh'):
            html = await asyncio.to_thread(fetch_remote_html_text_via_ssh, url, site)
        else:
            continue

        for item in extract_items_from_sebi_news_listing_html(html, url, site_key, site):
            link = item.get('link') or item.get('url')
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            items.append(item)

    return sort_items_latest_first(items)


def extract_items_from_fiu_guidance_downloads_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    required_url_terms = [term.lower() for term in site.get('required_url_terms', [])]
    required_title_keywords = [term.lower() for term in site.get('required_title_keywords', [])]
    skip_title_terms = [term.lower() for term in site.get('skip_title_terms', [])]

    for anchor in soup.select('#Others a[href]'):
        title = ' '.join(anchor.get_text(' ', strip=True).split())
        href = normalize_discovered_url(anchor.get('href') or '', base_url)
        if not title or not href:
            continue
        if required_url_terms and not any(term in href.lower() for term in required_url_terms):
            continue
        if 'fiuindia.gov.in' not in href.lower():
            continue

        title_lower = title.lower()
        if required_title_keywords and not any(term in title_lower for term in required_title_keywords):
            continue
        if skip_title_terms and any(term in title_lower for term in skip_title_terms):
            continue
        if href in seen_links:
            continue

        explicit_date_match = re.search(r'\b\d{1,2}\s*(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}\b', title, re.IGNORECASE)
        parsed_date = None
        if explicit_date_match:
            normalized_explicit_date = re.sub(
                r'\b(\d{1,2})\s+(st|nd|rd|th)\b',
                r'\1\2',
                explicit_date_match.group(0),
                flags=re.IGNORECASE,
            )
            parsed_date = parse_normalized_item_date(normalized_explicit_date)
        if not parsed_date:
            parsed_date = parse_normalized_item_date(f'{title} {href}')
        if not parsed_date:
            continue

        seen_links.add(href)
        item_type = 'guidelines'
        if 'circular' in title_lower or 'revision' in title_lower:
            item_type = 'circular'
        elif 'non-compliant' in title_lower or 'non compliant' in title_lower:
            item_type = 'notification'

        items.append({
            'title': title,
            'link': href,
            'url': href,
            'pub_date': parsed_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': title[:200],
            'category': item_type,
            'type': item_type,
            'site': site_key,
            'source': 'scraped',
            'candidate_file_url': href,
            'attachments': collect_item_attachments({
                'link': href,
                'base_url': base_url,
            }),
        })

    return sort_items_latest_first(items)


async def extract_items_from_fiu_guidance_downloads(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_fiu_guidance_downloads_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_uidai_authentication_docs_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    required_title_keywords = [term.lower() for term in site.get('required_title_keywords', [])]
    skip_title_terms = [term.lower() for term in site.get('skip_title_terms', [])]

    for row in soup.select('ul.list-group li.list-group-item'):
        link_node = row.find('a', href=True)
        if not link_node:
            continue

        title = re.sub(r'^\d+\.\s*', '', ' '.join(link_node.get_text(' ', strip=True).split())).strip()
        href = normalize_discovered_url(link_node.get('href') or '', base_url)
        full_text = ' '.join(row.get_text(' ', strip=True).split())
        if not title or not href or not looks_like_document_url(href):
            continue

        title_lower = title.lower()
        if required_title_keywords and not any(term in title_lower for term in required_title_keywords):
            continue
        if skip_title_terms and any(term in title_lower for term in skip_title_terms):
            continue
        if href in seen_links:
            continue

        explicit_date_match = re.search(r'\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b', full_text)
        parsed_date = None
        if explicit_date_match:
            parsed_date = parse_normalized_item_date(explicit_date_match.group(0))
        if not parsed_date:
            parsed_date = parse_normalized_item_date(full_text) or parse_normalized_item_date(f'{title} {href}')
        if not parsed_date:
            continue

        seen_links.add(href)
        item_type = 'circular' if 'circular' in title_lower else 'guidelines'
        if 'checklist' in title_lower:
            item_type = 'checklist'

        items.append({
            'title': title,
            'link': href,
            'url': href,
            'pub_date': parsed_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': full_text[:200],
            'category': item_type,
            'type': item_type,
            'site': site_key,
            'source': 'scraped',
            'candidate_file_url': href,
            'attachments': collect_item_attachments({
                'link': href,
                'base_url': base_url,
            }),
        })

    return sort_items_latest_first(items)


async def extract_items_from_uidai_authentication_docs(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_uidai_authentication_docs_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_crif_rbi_notifications_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for card in soup.select('ul.listing-type-one div.article-type-one'):
        date_node = card.select_one('.date')
        link_node = card.find('a', href=True)
        title_node = card.select_one('.highlight-text') or link_node
        if not date_node or not link_node or not title_node:
            continue

        title = ' '.join(title_node.get_text(' ', strip=True).split())
        raw_date = ' '.join(date_node.get_text(' ', strip=True).split())
        href = (link_node.get('href') or '').strip()
        if not title or not raw_date or not href:
            continue

        link = urljoin(base_url, href)
        if link in seen_links or '/news-events/rbi-notifications/' not in link.lower():
            continue

        seen_links.add(link)
        normalized_date = re.sub(r'(\d{1,2})(st|nd|rd|th)\b', r'\1', raw_date, flags=re.IGNORECASE)
        summary_node = None
        for paragraph in card.find_all('p'):
            paragraph_text = ' '.join(paragraph.get_text(' ', strip=True).split())
            if paragraph_text and paragraph_text != title:
                summary_node = paragraph
                break

        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': normalize_item_date(normalized_date, fallback=f'{title} {href}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': ' '.join(summary_node.get_text(' ', strip=True).split())[:200] if summary_node else title[:200],
            'category': 'notification',
            'type': 'notification',
            'site': site_key,
            'source': 'scraped',
        })

    return sort_items_latest_first(items)


async def extract_items_from_crif_rbi_notifications(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_crif_rbi_notifications_html(response.text, site['urls'][0], site_key, site)


def infer_fimmda_pub_date(title: str, href: str) -> str:
    text = f'{title} {href}'
    if re.search(r'\b\d{1,2}[-/ ](?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[-/ ,]+\d{2,4}\b', text, re.IGNORECASE):
        return normalize_item_date(text)
    if re.search(r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[, ]+\d{4}\b', text, re.IGNORECASE):
        return normalize_item_date(text)

    fy_match = re.search(r'(20\d{2})\s*[-_/]\s*(\d{2,4})', text)
    month_match = re.search(
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\b',
        title,
        re.IGNORECASE,
    )
    if not fy_match or not month_match:
        return ''

    start_year = int(fy_match.group(1))
    end_year_token = fy_match.group(2)
    end_year = int(end_year_token) if len(end_year_token) == 4 else 2000 + int(end_year_token)
    month_name = month_match.group(1).lower()
    month_num = datetime.strptime(month_name, '%B').month
    year = start_year if month_num >= 4 else end_year
    return f'{year:04d}-{month_num:02d}-01'


def extract_items_from_fimmda_notices_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    base_time = datetime.now(timezone.utc)

    for index, anchor in enumerate(soup.select('marquee a[href]')):
        title = ' '.join(anchor.get_text(' ', strip=True).split())
        href = (anchor.get('href') or '').strip()
        if not title or not href:
            continue
        if not (title.startswith('FIMCIR') or title.startswith('FIMNOT')):
            continue

        link = urljoin(base_url, href)
        if link in seen_links:
            continue

        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': infer_fimmda_pub_date(title, href),
            'isoDate': (base_time - timedelta(seconds=index)).isoformat(),
            'content_snippet': title[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
            'candidate_file_url': link,
            'attachments': collect_item_attachments({
                'link': link,
                'base_url': base_url,
            }),
        })

    return sort_items_latest_first(items)


async def extract_items_from_fimmda_notices(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_fimmda_notices_html(response.text, site['urls'][0], site_key, site)


def extract_items_from_lic_press_releases_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    base_time = datetime.now(timezone.utc)

    for table in soup.select('table.custom-table'):
        for index, row in enumerate(table.select('tr')[1:]):
            cells = row.find_all('td', recursive=False)
            if len(cells) < 4:
                continue

            raw_date = ' '.join(cells[1].get_text(' ', strip=True).split())
            title = ' '.join(cells[2].get_text(' ', strip=True).split())
            english_link = cells[3].find('a', href=True)
            href = (english_link.get('href') or '').strip() if english_link else ''
            if not raw_date or not title or not href:
                continue

            link = urljoin(base_url, href)
            if link in seen_links:
                continue

            seen_links.add(link)
            items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': normalize_item_date(raw_date, fallback=f'{title} {href}'),
                'isoDate': (base_time - timedelta(seconds=len(items))).isoformat(),
                'content_snippet': title[:200],
                'category': 'press-release',
                'type': 'press-release',
                'site': site_key,
                'source': 'scraped',
                'candidate_file_url': link,
                'attachments': collect_item_attachments({
                    'link': link,
                    'base_url': base_url,
                }),
            })

    return sort_items_latest_first(items)


async def extract_items_from_lic_press_releases(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    return extract_items_from_lic_press_releases_html(response.text, site['urls'][0], site_key, site)


async def extract_items_from_sidbi_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['api_url'], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    try:
        payload = response.json()
    except Exception:
        return []

    items: List[Dict[str, Any]] = []
    seen_links = set()
    uploads_base = site.get('sidbi_uploads_base') or 'https://www.sidbi.in/uploads/'

    for row in payload.get('data', []) if isinstance(payload, dict) else []:
        raw_title = row.get('circulars_title_eng') or row.get('circulars_title') or ''
        title_html = html_lib.unescape(str(raw_title))
        title = ' '.join(BeautifulSoup(title_html, 'html.parser').get_text(' ', strip=True).split())
        filename = ' '.join(str(row.get('filename') or '').split())
        if not title or not filename:
            continue

        link = f"{uploads_base.rstrip('/')}/{quote(filename, safe='()/._-')}"
        if link in seen_links:
            continue

        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': normalize_item_date(str(row.get('circulars_date') or ''), fallback=f'{title} {filename}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': title[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
            'candidate_file_url': link,
            'attachments': collect_item_attachments({
                'link': link,
                'base_url': uploads_base,
            }),
        })

    return sort_items_latest_first(items)


def extract_items_from_sbi_notice_addendums_html(
    html: str,
    base_url: str,
    site_key: str,
    site: Dict[str, Any],
) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for row in soup.select('tbody tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 4:
            continue

        link_node = cells[0].find('a', href=True)
        if not link_node:
            continue

        title = ' '.join(link_node.get_text(' ', strip=True).split()) or ' '.join(cells[0].get_text(' ', strip=True).split())
        raw_date = ' '.join(cells[3].get_text(' ', strip=True).split())
        link = normalize_discovered_url(link_node.get('href') or '', base_url)
        if not title or not link or link in seen_links:
            continue

        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': normalize_item_date(raw_date, fallback=f'{title} {link}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': title[:200],
            'category': 'notice',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
            'candidate_file_url': link,
            'attachments': collect_item_attachments({
                'link': link,
                'base_url': base_url,
            }),
        })

    return sort_items_latest_first(items)


async def extract_items_from_sbi_notice_addendums(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    api_url = site.get('api_url')
    if not api_url:
        return []

    end_date = datetime.now()
    days_back = int(site.get('sbi_notice_addendum_days_back') or 550)
    start_date = end_date - timedelta(days=days_back)
    headers = {
        'Content-Type': 'application/json;charset=utf-8',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': site.get('urls', ['https://www.sbimf.com/notice-and-addendums'])[0],
    }

    items: List[Dict[str, Any]] = []
    seen_links = set()
    for addendum_type in site.get('sbi_notice_addendum_types', []):
        payload = {
            'AddendumType': addendum_type,
            'FromDate': start_date.strftime('%m/%d/%Y'),
            'ToDate': end_date.strftime('%m/%d/%Y'),
        }
        try:
            response = await client.post(
                api_url,
                headers=headers,
                content=json.dumps(payload),
                timeout=45,
            )
            response.raise_for_status()
        except Exception:
            continue

        extracted = extract_items_from_sbi_notice_addendums_html(
            response.text,
            site.get('urls', ['https://www.sbimf.com/notice-and-addendums'])[0],
            site_key,
            site,
        )
        for item in extracted:
            link = item.get('link') or item.get('url')
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            items.append(item)

    return sort_items_latest_first(items)


def extract_items_from_ncdex_circulars_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for row in soup.select('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 5:
            continue

        raw_date = ' '.join(cells[0].get_text(' ', strip=True).split())
        circular_no = ' '.join(cells[1].get_text(' ', strip=True).split())
        department = ' '.join(cells[2].get_text(' ', strip=True).split())
        title = ' '.join(cells[3].get_text(' ', strip=True).split())
        link_node = cells[4].find('a', href=True)
        if not raw_date or not circular_no or not title or not link_node:
            continue

        href = (link_node.get('href') or '').strip()
        link = urljoin(base_url, href)
        if not link or link in seen_links:
            continue

        seen_links.add(link)
        pub_date = extract_candidate_date(raw_date)
        if not pub_date:
            continue

        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': ' | '.join(part for part in [circular_no, department] if part)[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
        })

    return sort_items_latest_first(items)


def extract_items_from_mcxccl_circulars_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for row in soup.select('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 4:
            continue

        raw_date = ' '.join(cells[0].get_text(' ', strip=True).split())
        category_text = ' '.join(cells[1].get_text(' ', strip=True).split())
        title_node = cells[2].find('a', href=True)
        circular_no = ' '.join(cells[3].get_text(' ', strip=True).split())
        if not raw_date or not title_node:
            continue

        title = ' '.join(title_node.get_text(' ', strip=True).split())
        href = (title_node.get('href') or '').strip()
        if not title or not href:
            continue

        link = urljoin(base_url, href)
        if link in seen_links:
            continue

        seen_links.add(link)
        pub_date = extract_candidate_date(raw_date)
        if not pub_date:
            continue

        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': ' | '.join(part for part in [category_text, circular_no] if part)[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
        })

    return sort_items_latest_first(items)


def extract_items_from_nsdl_circulars_html(html: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    skip_terms = [str(term).lower() for term in site.get('skip_keywords', []) if term]

    for row in soup.select('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 3:
            continue

        raw_date = ' '.join(cells[0].get_text(' ', strip=True).split())
        status_text = ' '.join(cells[1].get_text(' ', strip=True).split())
        link_node = cells[2].find('a', href=True)
        if not raw_date or not status_text or not link_node:
            continue

        title = ' '.join(link_node.get_text(' ', strip=True).split())
        href = (link_node.get('href') or '').strip()
        if not title or not href:
            continue

        lower_title = title.lower()
        if skip_terms and any(term in lower_title for term in skip_terms):
            continue

        pub_date = extract_candidate_date(raw_date)
        if not pub_date:
            continue

        link = urljoin(base_url, href)
        if link in seen_links:
            continue

        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': status_text[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
        })

    return sort_items_latest_first(items)


def extract_items_from_cbdt_communications_html(html_text: str, base_url: str, site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html_text, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for card in soup.select('div.search_result'):
        number_node = card.select_one('.NotificationNumber')
        date_node = card.select_one('.publishDate')
        number_text = ' '.join(number_node.get_text(' ', strip=True).split()) if number_node else ''
        raw_date = ' '.join(date_node.get_text(' ', strip=True).split()) if date_node else ''

        link = ''
        for node in card.select('[onclick], a[href]'):
            onclick = html_lib.unescape(node.get('onclick') or '')
            match = re.search(r"OpenFormByType\('([^']+)'\)", onclick)
            href = match.group(1) if match else (node.get('href') or '')
            if not href:
                continue
            if href.startswith('javascript:') and not match:
                continue
            link = normalize_discovered_url(href.split('&k=')[0], base_url)
            if link:
                break

        if not link or link in seen_links:
            continue

        card_strings = [' '.join(part.split()) for part in card.stripped_strings]
        subject = ''
        snippet_parts: List[str] = []
        for part in card_strings:
            if not part or part == number_text or part == raw_date:
                continue
            if not subject:
                subject = part
                continue
            if part.lower() == subject.lower():
                continue
            snippet_parts.append(part)

        if not subject:
            continue

        display_number = number_text.rstrip(':').strip()
        title = f'{display_number} | {subject}' if display_number else subject
        category = determine_item_category(title, link, site)
        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': normalize_item_date(raw_date, fallback=f'{title} {link}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': ' '.join(snippet_parts)[:200] if snippet_parts else subject[:200],
            'category': category,
            'type': category,
            'site': site_key,
            'source': 'scraped'
        })

    return items


async def extract_items_from_bse_listing_api(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    api_url = site.get('api_url') or 'https://api.bseindia.com/BseIndiaAPI/api/GetDataCirToListComp/w'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': site.get('referer') or 'https://www.bseindia.com/corporates/CirularToListedComp.html',
    }
    response = await client.get(api_url, headers=headers, timeout=30.0)
    response.raise_for_status()

    payload = response.json()
    rows = payload.get('Table') or []
    items: List[Dict[str, Any]] = []
    for row in rows:
        title = (row.get('mr_heading') or '').strip()
        article_id = (row.get('articleid') or '').strip()
        if not title or not article_id:
            continue

        link = f'https://www.bseindia.com/markets/MarketInfo/DispNewNoticesCirculars.aspx?page={article_id}'
        pub_date = normalize_item_date(row.get('mr_date'))
        category = 'circular'
        snippet = ' | '.join(part for part in [row.get('mr_cat', ''), row.get('Rd_Flag', '')] if part)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': snippet[:200] if snippet else title[:200],
            'category': category,
            'type': category,
            'site': site_key,
            'source': 'scraped'
        })

    return items


async def extract_items_from_iccl_notices(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    items: List[Dict[str, Any]] = []
    for row in soup.select('#GridView2 tr'):
        cells = row.find_all('td')
        if len(cells) < 6:
            continue

        subject_link = cells[2].find('a', href=True)
        if not subject_link:
            continue

        title = subject_link.get_text(' ', strip=True)
        if not title:
            continue

        link = urljoin(site['urls'][0], subject_link['href'])
        notice_no = cells[1].get_text(' ', strip=True)
        pub_date = normalize_item_date(cells[0].get_text(' ', strip=True), fallback=notice_no)
        summary = ' | '.join(
            part for part in [
                notice_no,
                cells[3].get_text(' ', strip=True),
                cells[4].get_text(' ', strip=True),
                cells[5].get_text(' ', strip=True),
            ] if part
        )

        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': summary[:200] if summary else title[:200],
            'category': 'notice',
            'type': 'notice',
            'site': site_key,
            'source': 'scraped'
        })

    return items


async def extract_items_from_ccil_notifications(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    items: List[Dict[str, Any]] = []
    skip_title_terms = [str(term).lower() for term in site.get('skip_title_terms', []) if term]
    skip_url_terms = [str(term).lower() for term in site.get('skip_url_terms', []) if term]
    required_url_terms = [str(term).lower() for term in site.get('required_url_terms', []) if term]
    for row in soup.select('table tr'):
        cells = row.find_all('td')
        if len(cells) < 3:
            continue

        link_node = cells[2].find('a', href=True)
        if not link_node:
            continue

        title = link_node.get_text(' ', strip=True)
        href = link_node.get('href')
        if not title or not href:
            continue

        link = urljoin(site['urls'][0], href)
        lower_title = title.lower()
        lower_link = link.lower()
        if skip_title_terms and any(term in lower_title for term in skip_title_terms):
            continue
        if skip_url_terms and any(term in lower_link for term in skip_url_terms):
            continue
        if required_url_terms and not any(term in lower_link for term in required_url_terms):
            continue

        pub_date = normalize_item_date(cells[1].get_text(' ', strip=True), fallback=title)
        summary_parts = [cell.get_text(' ', strip=True) for cell in cells[3:6]]
        summary = ' | '.join(part for part in summary_parts if part)

        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': summary[:200] if summary else title[:200],
            'category': 'notification',
            'type': 'notification',
            'site': site_key,
            'source': 'scraped'
        })

    return items


async def extract_items_from_ckycr_notifications(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for url in site.get('urls', []):
        response = await fetch_with_retry(url, client, SCRAPER_MAX_RETRIES)
        if not response:
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        for card in soup.select('div.notification'):
            title_node = card.select_one('.nsection1 p') or card.find('p')
            date_node = card.select_one('.nsection1 h5') or card.find('h5')
            link_node = card.find('a', href=True)
            if not title_node or not date_node or not link_node:
                continue

            title = ' '.join(title_node.get_text(' ', strip=True).split())
            raw_date = ' '.join(date_node.get_text(' ', strip=True).split())
            href = (link_node.get('href') or '').strip()
            if not title or not raw_date or not href:
                continue

            link = urljoin(url, href)
            if link in seen_links:
                continue

            seen_links.add(link)
            lower_title = title.lower()
            category = 'communique' if 'communique' in lower_title else 'notification'
            items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': normalize_item_date(raw_date, fallback=title),
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': raw_date[:200],
                'category': category,
                'type': category,
                'site': site_key,
                'source': 'scraped',
                'attachments': collect_item_attachments({'link': link}),
            })

    return items


async def extract_items_from_nse_listing_pages(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for url in site.get('urls', []):
        response = await fetch_with_retry(url, client, SCRAPER_MAX_RETRIES)
        if not response:
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            title = ' '.join(cells[0].get_text(' ', strip=True).split())
            if not title:
                continue

            for cell in cells[1:]:
                link_node = cell.find('a', href=True)
                if not link_node:
                    continue
                href = link_node.get('href')
                if not href:
                    continue
                lower_href = href.lower()
                if 'nsearchives.nseindia.com' not in lower_href:
                    continue
                if lower_href.endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')):
                    continue

                link = urljoin(url, href)
                if link in seen_links:
                    continue

                date_candidate = f"{cell.get_text(' ', strip=True)} {href}"
                if not re.search(r'(\d{2}[./-]\d{2}[./-]\d{2,4}|\d{8}|\d{6})', date_candidate):
                    continue

                pub_date = normalize_item_date(date_candidate, fallback=title)
                summary = ' | '.join(part for part in [title, url] if part)
                seen_links.add(link)
                items.append({
                    'title': title,
                    'link': link,
                    'url': link,
                    'pub_date': pub_date,
                    'isoDate': datetime.now(timezone.utc).isoformat(),
                    'content_snippet': summary[:200],
                    'category': 'circular',
                    'type': 'circular',
                    'site': site_key,
                    'source': 'scraped'
                })

    return items


async def extract_items_from_cbic_tables(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for url in site.get('urls', []):
        response = await fetch_with_retry(url, client, SCRAPER_MAX_RETRIES)
        if not response:
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 6:
                continue

            link_node = row.find('a', href=True)
            if not link_node:
                continue

            href = link_node.get('href')
            if not href:
                continue

            title = ' '.join(cells[4].get_text(' ', strip=True).split())
            ref_no = ' '.join(cells[1].get_text(' ', strip=True).split())
            raw_date = cells[2].get_text(' ', strip=True)
            if not title:
                continue

            link = urljoin(url, href)
            if link in seen_links:
                continue

            pub_date = normalize_item_date(raw_date, fallback=title)
            summary_parts = [ref_no, cells[3].get_text(' ', strip=True)]
            if len(cells) > 6:
                summary_parts.append(cells[5].get_text(' ', strip=True))
            category = 'notification' if 'notification' in url.lower() else 'circular'
            seen_links.add(link)
            items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': pub_date,
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': ' | '.join(part for part in summary_parts if part)[:200] or title[:200],
                'category': category,
                'type': category,
                'site': site_key,
                'source': 'scraped'
            })

    return items


def extract_items_from_cersai_notifications_html(
    html: str,
    base_url: str,
    site_key: str,
    site: Dict[str, Any],
) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    page_text = '\n'.join(
        line.strip()
        for line in soup.get_text('\n').splitlines()
        if line and line.strip()
    )
    if 'Pinned Notifications' not in page_text and 'Regular Notifications' not in page_text:
        return []

    items: List[Dict[str, Any]] = []
    seen_links = set()
    sections = [
        ('Pinned Notifications', 'notification'),
        ('Regular Notifications', 'notification'),
    ]

    for index, (heading, category) in enumerate(sections):
        start = page_text.find(heading)
        if start == -1:
            continue
        end = len(page_text)
        for later_heading, _ in sections[index + 1:]:
            later_pos = page_text.find(later_heading, start + len(heading))
            if later_pos != -1:
                end = min(end, later_pos)
        section_text = page_text[start + len(heading):end]
        for match in re.finditer(
            r'(?P<raw_date>\d{2}-\d{2}-\d{4})\s*-\s*(?P<title>.*?)(?=(?:\n\d{2}-\d{2}-\d{4}\s*-)|\Z)',
            section_text,
            re.DOTALL,
        ):
            raw_date = match.group('raw_date')
            title = ' '.join(match.group('title').split())
            if not title:
                continue

            link = build_fragment_item_link(base_url, f'{raw_date}-{title}')
            if link in seen_links:
                continue

            seen_links.add(link)
            items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': normalize_item_date(raw_date, fallback=title),
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': f'{heading} | {title}'[:200],
                'category': category,
                'type': category,
                'site': site_key,
                'source': 'scraped',
            })

    return items


def extract_dpiit_link_map_from_html(html: str, base_url: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, 'html.parser')
    link_map: Dict[str, str] = {}

    for anchor in soup.find_all('a', href=True):
        href = urljoin(base_url, (anchor.get('href') or '').strip())
        title = ' '.join(anchor.get_text(' ', strip=True).split())
        if not title or not href:
            continue
        lower_href = href.lower()
        if '/static/uploads/' not in lower_href and '/documents/' not in lower_href:
            continue
        if 'view more' in title.lower():
            continue
        link_map[normalize_title_key(title)] = href

    return link_map


def build_dpiit_document_items(
    posts: List[Dict[str, Any]],
    site_key: str,
    site: Dict[str, Any],
    link_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_links = set()
    allowed_categories = {
        normalize_title_key(value)
        for value in site.get('dpiit_allowed_categories', [])
        if value
    }

    for post in posts:
        acf_data = post.get('acf_data') or post.get('acf') or {}
        title = ' '.join(
            html_lib.unescape((acf_data.get('title') or post.get('post_title') or '').replace('\xa0', ' ')).split()
        )
        if not title:
            continue

        categories = [
            ' '.join(html_lib.unescape(str(category.get('name') or '')).replace('\xa0', ' ').split())
            for category in post.get('documents_category', [])
            if category
        ]
        if allowed_categories:
            normalized_categories = {normalize_title_key(value) for value in categories if value}
            if not normalized_categories.intersection(allowed_categories):
                continue

        raw_date = acf_data.get('date') or post.get('post_date') or post.get('date') or ''
        title_key = normalize_title_key(title)
        file_entries = acf_data.get('file') or []
        direct_link = None
        for entry in file_entries:
            if not isinstance(entry, dict):
                continue
            external_link = (entry.get('external_link') or '').strip()
            if external_link:
                direct_link = external_link
                break

        public_link = post.get('link') or ''
        slug = (post.get('post_slug') or post.get('slug') or '').strip()
        if slug:
            public_link = f'https://www.dpiit.gov.in/documents/{slug}'
        elif public_link:
            public_link = public_link.replace('https://cms-dpiit.digifootprint.gov.in', 'https://www.dpiit.gov.in').rstrip('/')
        else:
            public_link = site.get('urls', ['https://www.dpiit.gov.in/'])[0]

        link = (link_map or {}).get(title_key) or direct_link or public_link
        if not link or link in seen_links:
            continue

        seen_links.add(link)
        category = 'document'
        if categories:
            category = normalize_title_key(categories[0]).replace(' ', '-') or category

        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': normalize_item_date(raw_date, fallback=title),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': ' | '.join(part for part in categories if part)[:200] or title[:200],
            'category': category,
            'type': category,
            'site': site_key,
            'source': 'scraped',
            'attachments': collect_item_attachments({'link': link}),
        })

    return items


async def extract_items_from_dpiit_documents(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    api_url = site.get('api_url') or site['urls'][0]
    response = await fetch_with_retry(api_url, client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    payload = response.json()
    posts = payload.get('posts') if isinstance(payload, dict) else None
    if not isinstance(posts, list):
        return []

    link_map: Dict[str, str] = {}
    browser_url = site.get('browser_url')
    if browser_url:
        try:
            rendered_html = await asyncio.to_thread(fetch_openclaw_rendered_html, browser_url, site)
            link_map = extract_dpiit_link_map_from_html(rendered_html, browser_url)
        except Exception:
            link_map = {}

    return build_dpiit_document_items(posts, site_key, site, link_map=link_map)


async def extract_items_from_doe_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for url in site.get('urls', []):
        response = await fetch_with_retry(url, client, SCRAPER_MAX_RETRIES)
        if not response:
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        for row in soup.select('table tr'):
            cells = row.find_all('td')
            if len(cells) < 4:
                continue

            title = ' '.join(cells[1].get_text(' ', strip=True).split())
            raw_date = cells[2].get_text(' ', strip=True)
            link_node = cells[3].find('a', href=True)
            if not title or not link_node:
                continue

            link = urljoin(url, link_node['href'])
            if link in seen_links:
                continue

            seen_links.add(link)
            items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': normalize_item_date(raw_date, fallback=title),
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': cells[0].get_text(' ', strip=True)[:200],
                'category': 'circular',
                'type': 'circular',
                'site': site_key,
                'source': 'scraped'
            })

    return items


async def extract_items_from_doe_orders_hub(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for url in site.get('urls', []):
        response = await fetch_with_retry(url, client, SCRAPER_MAX_RETRIES)
        if not response:
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        category_links: List[Tuple[str, str]] = []
        seen_categories = set()
        for anchor in soup.select('a[href]'):
            href = (anchor.get('href') or '').strip()
            if not re.search(r'/orders-circulars/\d+$', href):
                continue

            category_url = normalize_discovered_url(href, url)
            if not category_url or category_url in seen_categories:
                continue

            category_title = ' '.join(anchor.get_text(' ', strip=True).split())
            if not category_title or category_title.lower() in {'english', 'hindi', 'reset'}:
                continue

            seen_categories.add(category_url)
            category_links.append((category_title, category_url))

        for category_title, category_url in category_links:
            category_response = await fetch_with_retry(category_url, client, SCRAPER_MAX_RETRIES)
            if not category_response:
                continue

            category_soup = BeautifulSoup(category_response.text, 'html.parser')
            for row in category_soup.select('table tr'):
                cells = row.find_all('td')
                if len(cells) < 4:
                    continue

                title_index = 2 if len(cells) >= 5 else 1
                date_index = 3 if len(cells) >= 5 else 2
                document_index = 4 if len(cells) >= 5 else 3

                title = ' '.join(cells[title_index].get_text(' ', strip=True).split())
                raw_date = cells[date_index].get_text(' ', strip=True)
                link_node = cells[document_index].find('a', href=True)
                if not title or not link_node:
                    continue

                link = normalize_discovered_url(link_node.get('href') or '', category_url)
                if not link or link in seen_links:
                    continue

                reference = ' '.join(cells[1].get_text(' ', strip=True).split()) if len(cells) >= 5 else ''
                snippet = ' | '.join(part for part in [category_title, reference] if part)
                pub_date = (
                    extract_candidate_date(raw_date)
                    or extract_candidate_date(f'{title} {link}')
                    or ''
                )

                seen_links.add(link)
                items.append({
                    'title': title,
                    'link': link,
                    'url': link,
                    'pub_date': pub_date,
                    'isoDate': datetime.now(timezone.utc).isoformat(),
                    'content_snippet': (snippet or title)[:200],
                    'category': 'circular',
                    'type': 'circular',
                    'site': site_key,
                    'source': 'scraped',
                    'attachments': collect_item_attachments({'link': link, 'base_url': category_url}),
                })

    return items


def extract_date_from_rbi_notification_detail(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, 'html.parser')
    lines = [
        ' '.join(line.split())
        for line in soup.get_text('\n', strip=True).splitlines()
        if ' '.join(line.split())
    ]
    for line in lines[50:200]:
        lower_line = line.lower()
        if 'website last updated date' in lower_line:
            continue
        if re.search(r'\b20\d{2}-\d{2}/\d+\b', line):
            continue
        candidate_date = extract_candidate_date(line)
        if candidate_date:
            return candidate_date
    for line in lines[:50]:
        lower_line = line.lower()
        if 'website last updated date' in lower_line:
            continue
        candidate_date = extract_candidate_date(line)
        if candidate_date:
            return candidate_date
    return None


async def extract_items_from_rbi_notifications(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    title_terms = [str(term).lower() for term in site.get('rbi_title_keywords', []) if term]
    detail_terms = [str(term).lower() for term in site.get('rbi_detail_keywords', []) if term]
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for row in soup.select('table tr'):
        cells = row.find_all('td')
        if len(cells) < 2:
            continue

        title = ' '.join(cells[0].get_text(' ', strip=True).split())
        if not title or len(title) < 10:
            continue

        normalized_title = title.lower()
        if title_terms and not any(term in normalized_title for term in title_terms):
            continue

        detail_link = None
        document_link = None
        for anchor in row.select('a[href]'):
            normalized_url = normalize_discovered_url(anchor.get('href') or '', str(response.url))
            if not normalized_url:
                continue
            if 'NotificationUser.aspx?Id=' in normalized_url:
                detail_link = normalized_url
            if looks_like_document_url(normalized_url):
                document_link = normalized_url

        if not detail_link and not document_link:
            continue

        raw_date = ''
        detail_text = ''
        if detail_link:
            detail_response = await fetch_with_retry(detail_link, client, SCRAPER_MAX_RETRIES)
            if detail_response:
                detail_text = ' '.join(BeautifulSoup(detail_response.text, 'html.parser').get_text(' ', strip=True).split()).lower()
                if detail_terms and not any(term in detail_text for term in detail_terms):
                    continue
                raw_date = extract_date_from_rbi_notification_detail(detail_response.text) or ''

        primary_link = document_link or detail_link
        if not primary_link or primary_link in seen_links:
            continue

        seen_links.add(primary_link)
        items.append({
            'title': title,
            'link': primary_link,
            'url': primary_link,
            'pub_date': normalize_item_date(raw_date, fallback=f'{title} {detail_link or primary_link}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': title[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
            'attachments': collect_item_attachments({
                'link': primary_link,
                'attachments': [{'url': document_link}] if document_link and document_link != primary_link else [],
                'base_url': str(response.url),
            }),
        })

    return items


async def extract_items_from_nfra_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    for row in soup.select('table.doc-table tr'):
        cells = row.find_all('td')
        if len(cells) < 3:
            continue

        title = ' '.join(cells[0].get_text(' ', strip=True).split())
        raw_date = cells[1].get_text(' ', strip=True)
        link_node = cells[2].find('a', href=True)
        if not title or not link_node:
            continue

        link = urljoin(site['urls'][0], link_node['href'])
        if link in seen_links:
            continue

        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': normalize_item_date(raw_date, fallback=title),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': title[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped'
        })

    return items


def extract_ibbi_pdf_url(cell) -> Optional[str]:
    link_node = cell.find('a', href=True)
    if not link_node:
        return None

    href = (link_node.get('href') or '').strip()
    if href and not href.lower().startswith('javascript:'):
        return href

    onclick = link_node.get('onclick') or ''
    match = re.search(r"newwindow1\('([^']+)'\)", onclick)
    return match.group(1).strip() if match else None


async def extract_items_from_ibbi_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_links = set()
    pending_pages = list(site.get('urls', []))
    seen_pages = set()

    while pending_pages:
        page_url = pending_pages.pop(0)
        if page_url in seen_pages:
            continue
        seen_pages.add(page_url)

        response = await fetch_with_retry(page_url, client, SCRAPER_MAX_RETRIES)
        if not response:
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        for page_link in soup.select('a[href]'):
            href = page_link.get('href') or ''
            if '/legal-framework/circulars?page=' in href:
                next_page = urljoin(page_url, href)
                if next_page not in seen_pages:
                    pending_pages.append(next_page)

        for row in soup.select('table tr'):
            cells = row.find_all('td')
            if len(cells) < 4:
                continue

            title = ' '.join(cells[2].get_text(' ', strip=True).split())
            raw_date = cells[1].get_text(' ', strip=True)
            pdf_url = extract_ibbi_pdf_url(cells[3]) or (extract_ibbi_pdf_url(cells[4]) if len(cells) > 4 else None)
            if not title or not pdf_url:
                continue

            link = urljoin(page_url, pdf_url)
            if link in seen_links:
                continue

            seen_links.add(link)
            items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': normalize_item_date(raw_date, fallback=title),
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': title[:200],
                'category': 'circular',
                'type': 'circular',
                'site': site_key,
                'source': 'scraped'
            })

    return items


async def extract_items_from_pfrda_listing(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_links = set()
    pending_pages = list(site.get('urls', []))
    seen_pages = set()

    while pending_pages:
        page_url = pending_pages.pop(0)
        if page_url in seen_pages:
            continue
        seen_pages.add(page_url)

        response = await fetch_with_retry(page_url, client, SCRAPER_MAX_RETRIES)
        if not response:
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        page_key = site.get('pfrda_page_key') or ''
        for page_link in soup.select('.pagination a[href]'):
            href = page_link.get('href') or ''
            if page_key and page_key not in href:
                continue
            if 'start=' not in href:
                continue
            next_page = urljoin(page_url, href)
            if next_page not in seen_pages:
                pending_pages.append(next_page)

        for card in soup.select('#accordionListing .accordianCard'):
            link_node = card.find('a', href=True)
            title_node = card.select_one('.accordian-title')
            date_block = card.select_one('.accordian-dateReference')
            tag_node = card.select_one('.tag')
            if not link_node or not title_node or not date_block:
                continue

            title = ' '.join(title_node.get_text(' ', strip=True).split())
            link = strip_url_query(urljoin(page_url, link_node['href']))
            if not title or link in seen_links:
                continue

            date_text = ' '.join(date_block.get_text(' ', strip=True).split())
            issue_date_match = re.search(r'Issue Date:\s*([0-9]{2}-[0-9]{2}-[0-9]{4})', date_text)
            if not issue_date_match:
                continue

            ref_match = re.search(r'Reference Number:\s*([^|]+?)(?:Issue Date:|$)', date_text)
            summary_parts = []
            if ref_match:
                summary_parts.append(' '.join(ref_match.group(1).split()).rstrip('|'))
            if tag_node:
                summary_parts.append(' '.join(tag_node.get_text(' ', strip=True).split()))

            category = 'master-circular' if 'master circular' in title.lower() or 'master-circulars' in page_url else 'circular'
            seen_links.add(link)
            items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': normalize_item_date(issue_date_match.group(1), fallback=title),
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': ' | '.join(part for part in summary_parts if part)[:200] or title[:200],
                'category': category,
                'type': category,
                'site': site_key,
                'source': 'scraped'
            })

    return items


async def extract_items_from_nse_circulars_api(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    dept = site.get('nse_circular_department')
    company = (site.get('nse_circular_company') or '').strip().lower()
    companies = {str(value).strip().lower() for value in site.get('nse_circular_companies', []) if str(value).strip()}
    if company:
        companies.add(company)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(site.get('nse_circular_days', 365)))
    api_url = (
        'https://www.nseindia.com/api/circulars'
        f'?fromDate={start_date.strftime("%d-%m-%Y")}'
        f'&toDate={end_date.strftime("%d-%m-%Y")}'
    )
    if dept:
        api_url += f'&dept={dept}'

    response = await fetch_with_retry(api_url, client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    payload = response.json()
    items: List[Dict[str, Any]] = []
    for row in payload.get('data', []):
        row_company = str(row.get('circCompany') or '').strip().lower()
        if companies and row_company not in companies:
            continue

        link = row.get('circFilelink')
        subject = (row.get('sub') or '').strip()
        display_no = (row.get('circDisplayNo') or '').strip()
        if not link or not subject:
            continue

        title = f'{display_no} | {subject}' if display_no else subject
        pub_date = parse_yyyymmdd_date(row.get('cirDate')) or datetime.now().strftime('%Y-%m-%d')
        summary = ' | '.join(
            part for part in [
                row.get('circDepartment', ''),
                row.get('circCategory', ''),
                row.get('circCompany', ''),
                row.get('circFileSize', ''),
            ] if part
        )

        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': summary[:200] if summary else subject[:200],
            'category': row.get('circCategory', 'circular').lower().replace(' ', '-'),
            'type': 'circular',
            'site': site_key,
            'source': 'scraped'
        })

    return items


async def extract_items_from_irdai_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for url in site.get('urls', []):
        response = await fetch_with_retry(url, client, SCRAPER_MAX_RETRIES)
        if not response:
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        for row in soup.select('table tr'):
            cells = row.find_all('td')
            if len(cells) < 6:
                continue

            title = ' '.join(cells[2].get_text(' ', strip=True).split()) or ' '.join(cells[3].get_text(' ', strip=True).split())
            subtitle = ' '.join(cells[3].get_text(' ', strip=True).split()) if len(cells) > 3 else ''
            raw_date = cells[4].get_text(' ', strip=True) if len(cells) > 4 else ''
            document_cell = cells[-1]
            link_node = document_cell.find('a', href=True)
            if not title or not link_node:
                continue

            href = (link_node.get('href') or '').strip()
            if not href:
                continue

            link = urljoin(url, href)
            if link in seen_links:
                continue

            seen_links.add(link)
            items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': normalize_item_date(raw_date, fallback=title),
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': subtitle[:200] if subtitle else title[:200],
                'category': 'circular',
                'type': 'circular',
                'site': site_key,
                'source': 'scraped',
                'attachments': collect_item_attachments({'link': link}),
            })

    return items


async def extract_items_from_nps_trust_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for row in soup.select('table tr'):
        cells = row.find_all('td')
        if len(cells) < 4:
            continue

        title = ' '.join(cells[1].get_text(' ', strip=True).split())
        raw_date = cells[2].get_text(' ', strip=True)
        link_node = cells[3].find('a', href=True)
        if not title or not link_node:
            continue

        href = (link_node.get('href') or '').strip()
        if not href:
            continue

        link = urljoin(site['urls'][0], href)
        if link in seen_links:
            continue

        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': normalize_item_date(raw_date, fallback=f'{title} {link}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': title[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
        })

    return items


async def extract_items_from_niti_notifications(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()

    for row in soup.select('table tr'):
        cells = row.find_all('td')
        if len(cells) < 4:
            continue

        title = ' '.join(cells[1].get_text(' ', strip=True).split())
        raw_date = ' '.join(cells[2].get_text(' ', strip=True).split())
        link_node = cells[3].find('a', href=True)
        if not title or not link_node:
            continue

        href = (link_node.get('href') or '').strip()
        if not href:
            continue

        link = urljoin(site['urls'][0], href)
        if link in seen_links:
            continue

        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': normalize_item_date(raw_date, fallback=f'{title} {link}'),
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': raw_date[:200] if raw_date else title[:200],
            'category': 'notification',
            'type': 'notification',
            'site': site_key,
            'source': 'scraped',
        })

    return items


async def extract_items_from_nabard_circulars(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    response = await fetch_with_retry(site['urls'][0], client, SCRAPER_MAX_RETRIES)
    if not response:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    items: List[Dict[str, Any]] = []
    seen_links = set()
    skip_title_terms = [str(term).lower() for term in site.get('skip_title_terms', []) if term]

    for link_node in soup.select('a[href*="CircularPage.aspx"]'):
        title = ' '.join(link_node.get_text(' ', strip=True).split())
        href = (link_node.get('href') or '').strip()
        if not title or not href:
            continue
        if skip_title_terms and any(term in title.lower() for term in skip_title_terms):
            continue

        link = urljoin(site['urls'][0], href)
        if link in seen_links:
            continue

        detail_response = await fetch_with_retry(link, client, SCRAPER_MAX_RETRIES)
        detail_text = ''
        if detail_response:
            detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
            detail_text = ' '.join(detail_soup.get_text(' ', strip=True).split())

        pub_date = (
            extract_candidate_date(detail_text[:4000])
            or extract_candidate_date(detail_text)
            or extract_candidate_date(title)
            or ''
        )
        if not pub_date:
            continue

        seen_links.add(link)
        items.append({
            'title': title,
            'link': link,
            'url': link,
            'pub_date': pub_date,
            'isoDate': datetime.now(timezone.utc).isoformat(),
            'content_snippet': detail_text[:200] if detail_text else title[:200],
            'category': 'circular',
            'type': 'circular',
            'site': site_key,
            'source': 'scraped',
        })

    return items


async def extract_items_from_npci_circulars_api(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    current_year = datetime.now().year
    years = site.get('npci_years') or [current_year, current_year - 1]
    products = site.get('npci_products') or ['upi', 'imps', 'nach']
    items: List[Dict[str, Any]] = []

    for product in products:
        for year in years:
            api_url = (
                f'https://www.npci.org.in/api/circulars/{product}'
                f'?pageNum=1&year={year}&sort=desc&size=100&locale=en'
            )
            response = await fetch_with_retry(api_url, client, SCRAPER_MAX_RETRIES)
            if not response:
                continue

            payload = response.json()
            files = (payload.get('data') or {}).get('files') or []
            for file_info in files:
                media = file_info.get('media') or {}
                media_url = media.get('url')
                title = (file_info.get('fileName') or '').strip()
                if not title or not media_url:
                    continue

                link = urljoin('https://www.npci.org.in', media_url)
                summary = f'{product.upper()} | {file_info.get("yearLabel", "")}'.strip(' |')
                items.append({
                    'title': title,
                    'link': link,
                    'url': link,
                    'pub_date': datetime.now().strftime('%Y-%m-%d'),
                    'isoDate': datetime.now(timezone.utc).isoformat(),
                    'content_snippet': summary[:200] if summary else title[:200],
                    'category': 'circular',
                    'type': 'circular',
                    'site': site_key,
                    'source': 'scraped'
                })

    return items


async def extract_items_from_special_source(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    api_strategy = site.get('api_strategy')
    html_strategy = site.get('html_strategy')
    browser_strategy = site.get('browser_strategy')

    if api_strategy == 'nse_circulars':
        return await extract_items_from_nse_circulars_api(site_key, site, client)
    if api_strategy == 'bse_listing_api':
        return await extract_items_from_bse_listing_api(site_key, site, client)
    if api_strategy == 'npci_circulars':
        return await extract_items_from_npci_circulars_api(site_key, site, client)
    if api_strategy == 'dpiit_documents':
        return await extract_items_from_dpiit_documents(site_key, site, client)
    if api_strategy == 'mcx_rss':
        return await extract_items_from_mcx_rss(site_key, site)
    if api_strategy == 'sidbi_circulars':
        return await extract_items_from_sidbi_circulars(site_key, site, client)
    if api_strategy == 'sbi_notice_addendums':
        return await extract_items_from_sbi_notice_addendums(site_key, site, client)
    if api_strategy == 'cdsl_communiques':
        return await extract_items_from_cdsl_communiques_api(site_key, site, client)
    if api_strategy == 'cbdt_structured_contents':
        return await extract_items_from_cbdt_structured_contents(site_key, site, client)
    if html_strategy == 'bse_notices':
        return await extract_items_from_bse_notices(site_key, site, client)
    if html_strategy == 'nse_listing_pages':
        return await extract_items_from_nse_listing_pages(site_key, site, client)
    if html_strategy == 'iccl_notices':
        return await extract_items_from_iccl_notices(site_key, site, client)
    if html_strategy == 'ccil_notifications':
        return await extract_items_from_ccil_notifications(site_key, site, client)
    if html_strategy == 'ckycr_notifications':
        return await extract_items_from_ckycr_notifications(site_key, site, client)
    if html_strategy == 'cbic_tables':
        return await extract_items_from_cbic_tables(site_key, site, client)
    if html_strategy == 'dfs_circulars':
        return await extract_items_from_dfs_circulars(site_key, site, client)
    if html_strategy == 'nps_trust_circulars':
        return await extract_items_from_nps_trust_circulars(site_key, site, client)
    if html_strategy == 'niti_notifications':
        return await extract_items_from_niti_notifications(site_key, site, client)
    if html_strategy == 'icmai_notifications':
        return await extract_items_from_icmai_notifications(site_key, site, client)
    if html_strategy == 'iba_circulars':
        return await extract_items_from_iba_circulars(site_key, site, client)
    if html_strategy == 'cestat_circulars':
        return await extract_items_from_cestat_circulars(site_key, site, client)
    if html_strategy == 'mse_circulars':
        return await extract_items_from_mse_circulars(site_key, site, client)
    if html_strategy == 'fiu_compliance_orders':
        return await extract_items_from_fiu_compliance_orders(site_key, site, client)
    if html_strategy == 'sebi_legal_listing':
        return await extract_items_from_sebi_legal_listing(site_key, site, client)
    if html_strategy == 'sebi_news_listing':
        return await extract_items_from_sebi_news_listing(site_key, site, client)
    if html_strategy == 'fiu_guidance_downloads':
        return await extract_items_from_fiu_guidance_downloads(site_key, site, client)
    if html_strategy == 'uidai_authentication_docs':
        return await extract_items_from_uidai_authentication_docs(site_key, site, client)
    if html_strategy == 'crif_rbi_notifications':
        return await extract_items_from_crif_rbi_notifications(site_key, site, client)
    if html_strategy == 'fimmda_notices':
        return await extract_items_from_fimmda_notices(site_key, site, client)
    if html_strategy == 'remote_generic_html':
        html = await asyncio.to_thread(fetch_remote_html_text_via_ssh, site['urls'][0], site)
        soup = BeautifulSoup(html, 'html.parser')
        return extract_items_from_soup(soup, site['urls'][0], site_key, site)
    if html_strategy == 'lic_press_releases':
        return await extract_items_from_lic_press_releases(site_key, site, client)
    if html_strategy == 'nabard_circulars':
        return await extract_items_from_nabard_circulars(site_key, site, client)
    if html_strategy == 'gst_council_circulars':
        return await extract_items_from_gst_council_circulars(site_key, site, client)
    if html_strategy == 'cdsl_home_cards':
        return await extract_items_from_cdsl_home_cards(site_key, site, client)
    if html_strategy == 'irdai_circulars':
        return await extract_items_from_irdai_circulars(site_key, site, client)
    if html_strategy == 'doe_circulars':
        return await extract_items_from_doe_circulars(site_key, site, client)
    if html_strategy == 'doe_orders_hub':
        return await extract_items_from_doe_orders_hub(site_key, site, client)
    if html_strategy == 'rbi_notifications':
        return await extract_items_from_rbi_notifications(site_key, site, client)
    if html_strategy == 'nfra_circulars':
        return await extract_items_from_nfra_circulars(site_key, site, client)
    if html_strategy == 'ibbi_circulars':
        return await extract_items_from_ibbi_circulars(site_key, site, client)
    if html_strategy == 'pfrda_listing':
        return await extract_items_from_pfrda_listing(site_key, site, client)
    if browser_strategy == 'mca_home':
        browser_url = site.get('browser_url') or site['urls'][0]
        items: List[Dict[str, Any]] = []
        for attempt in range(2):
            html = await asyncio.to_thread(fetch_mca_home_html, browser_url)
            items = extract_items_from_mca_home_html(html, browser_url, site_key, site)
            if items or attempt == 1:
                return items
            await asyncio.sleep(2)
    if browser_strategy == 'cbdt_communications':
        items: List[Dict[str, Any]] = []
        browser_urls = site.get('browser_urls') or site.get('urls', [])
        for browser_url in browser_urls:
            html = await asyncio.to_thread(fetch_openclaw_rendered_html, browser_url, site)
            items.extend(extract_items_from_cbdt_communications_html(html, browser_url, site_key, site))
        return items
    if browser_strategy == 'cersai_notifications':
        browser_url = site.get('browser_url') or site['urls'][0]
        html = await asyncio.to_thread(fetch_openclaw_rendered_html, browser_url, site)
        return extract_items_from_cersai_notifications_html(html, browser_url, site_key, site)

    return []


async def extract_items_from_mcx_rss(site_key: str, site: Dict[str, Any]) -> List[Dict[str, Any]]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30, verify=False) as client:
        return await extract_items_from_rss(site_key, site, client)


async def extract_items_from_rss(site_key: str, site: Dict[str, Any], client) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    required_keywords = [str(keyword).lower() for keyword in site.get('required_keywords', []) if keyword]
    skip_keywords = [str(keyword).lower() for keyword in site.get('skip_keywords', []) if keyword]
    last_browser_error: Optional[Exception] = None

    for feed in site.get('rss_feeds', []):
        feed_config = feed if isinstance(feed, dict) else {'url': feed}
        feed_url = feed_config.get('url')
        if not feed_url:
            continue

        response = None
        direct_error: Optional[Exception] = None
        try:
            response = await fetch_with_retry(feed_url, client, SCRAPER_MAX_RETRIES)
        except Exception as exc:
            direct_error = exc
        xml_text = ''
        if response:
            xml_text = response.text.lstrip('\ufeff').strip()
        elif site.get('rss_browser_fallback'):
            try:
                xml_text = await asyncio.to_thread(fetch_openclaw_xml_text, feed_url, site)
            except Exception as exc:
                if direct_error is not None:
                    last_browser_error = RuntimeError(
                        f'Direct RSS fetch failed for {feed_url}: {direct_error}; '
                        f'OpenClaw fallback failed: {exc}'
                    )
                else:
                    last_browser_error = exc
                remote_ssh_target = site.get('remote_rss_via_ssh')
                if remote_ssh_target:
                    try:
                        xml_text = await asyncio.to_thread(fetch_remote_rss_text_via_ssh, feed_url, site)
                    except Exception as remote_exc:
                        if direct_error is not None:
                            last_browser_error = RuntimeError(
                                f'Direct RSS fetch failed for {feed_url}: {direct_error}; '
                                f'OpenClaw fallback failed: {exc}; '
                                f'Remote RSS fallback failed: {remote_exc}'
                            )
                        else:
                            last_browser_error = RuntimeError(
                                f'OpenClaw fallback failed: {exc}; Remote RSS fallback failed: {remote_exc}'
                            )
                        continue
                else:
                    continue
        elif direct_error is not None:
            raise direct_error
        else:
            continue
        root = ET.fromstring(xml_text)

        for entry in root.findall('.//item'):
            title = (entry.findtext('title') or '').strip()
            link = (entry.findtext('link') or '').strip()
            if not title or not link:
                continue

            description = BeautifulSoup(entry.findtext('description') or '', 'html.parser').get_text(' ', strip=True)
            text_blob = f'{title} {link} {description}'.lower()
            if required_keywords and not any(keyword in text_blob for keyword in required_keywords):
                continue
            if skip_keywords and any(keyword in text_blob for keyword in skip_keywords):
                continue
            pub_date = parse_rss_pub_date(entry.findtext('pubDate')) or datetime.now().strftime('%Y-%m-%d')
            category = feed_config.get('category') or (site.get('update_types', ['notice'])[0] if site.get('update_types') else 'notice')
            item_type = feed_config.get('type') or category

            items.append({
                'title': title,
                'link': link,
                'url': link,
                'pub_date': pub_date,
                'isoDate': datetime.now(timezone.utc).isoformat(),
                'content_snippet': description[:200] if description else title[:200],
                'category': category,
                'type': item_type,
                'site': site_key,
                'source': 'scraped'
            })

    if not items and last_browser_error is not None:
        raise last_browser_error

    return items


async def scrape_site(site_key: str, site: Dict):
    if site.get('api_strategy') or site.get('html_strategy') or site.get('browser_strategy'):
        try:
            special_items: List[Dict[str, Any]] = []
            start_time = time.time()
            started_at = datetime.now(timezone.utc).isoformat()
            stats = {
                'status': 'success',
                'items_found': 0,
                'items_added': 0,
                'errors': []
            }

            logger.info(f"[{datetime.now(timezone.utc).isoformat()}] Scraping {site['name']} via special source...")
            async with get_rss_httpx_client(False) as client:
                special_items = await extract_items_from_special_source(site_key, site, client)

            if special_items:
                seen = set()
                unique_items = []
                for item in special_items:
                    link = item.get('link') or item.get('url')
                    if not link or link in seen:
                        continue
                    seen.add(link)
                    unique_items.append(item)
                unique_items = apply_source_downgrade(site, unique_items, stats)
                unique_items = sort_items_latest_first(unique_items)

                stats['items_found'] = len(unique_items)
                stats['errors'].append(
                    f"Used {site.get('api_strategy') or site.get('html_strategy') or site.get('browser_strategy')}"
                )
                result_classification = classify_scrape_result(unique_items, stats)
                stats['result_status'] = result_classification['result_status']
                if result_classification['failure_category']:
                    stats['failure_category'] = result_classification['failure_category']
                if result_classification['failure_reason']:
                    stats['failure_reason'] = result_classification['failure_reason']
                evaluation = evaluate_scrape_quality(site_key, site, unique_items, stats)
                stats['coverage_status'] = evaluation['coverage_status']
                stats['validation'] = evaluation

                async with get_db_async() as conn:
                    conn.execute(
                        """
                        INSERT INTO scraping_logs
                        (site, url, run_id, status, coverage_status, items_found, error_message, validation_details, started_at, completed_at, duration_seconds)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            site_key,
                            site['urls'][0],
                            SCRAPE_RUN_ID.get(),
                            stats['status'],
                            stats['coverage_status'],
                            stats['items_found'],
                            json.dumps(stats['errors']) if stats['errors'] else None,
                            serialize_validation_details(evaluation),
                            started_at,
                            datetime.now(timezone.utc).isoformat(),
                            time.time() - start_time,
                        ),
                    )
                    conn.commit()

                logger.info(f"[{datetime.now(timezone.utc).isoformat()}] {site['name']}: Found {len(unique_items)} special-source items")
                return unique_items, stats
            if site.get('special_source_only'):
                stats['items_found'] = 0
                stats['errors'].append('Special source returned no items')
                result_classification = classify_scrape_result([], stats)
                stats['result_status'] = result_classification['result_status']
                if result_classification['failure_category']:
                    stats['failure_category'] = result_classification['failure_category']
                if result_classification['failure_reason']:
                    stats['failure_reason'] = result_classification['failure_reason']
                evaluation = evaluate_scrape_quality(site_key, site, [], stats)
                stats['coverage_status'] = evaluation['coverage_status']
                stats['validation'] = evaluation
                async with get_db_async() as conn:
                    conn.execute(
                        """
                        INSERT INTO scraping_logs
                        (site, url, run_id, status, coverage_status, items_found, error_message, validation_details, started_at, completed_at, duration_seconds)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            site_key,
                            site['urls'][0],
                            SCRAPE_RUN_ID.get(),
                            stats['status'],
                            stats['coverage_status'],
                            stats['items_found'],
                            json.dumps(stats['errors']) if stats['errors'] else None,
                            serialize_validation_details(evaluation),
                            started_at,
                            datetime.now(timezone.utc).isoformat(),
                            time.time() - start_time,
                        ),
                    )
                    conn.commit()
                logger.info(f"[{datetime.now(timezone.utc).isoformat()}] {site['name']}: Special-source-only scrape yielded no items")
                return [], stats
        except Exception as special_exception:
            if site.get('special_source_only'):
                stats = {
                    'status': 'failed',
                    'items_found': 0,
                    'items_added': 0,
                    'errors': [f'Special-source scraping failed: {special_exception}'],
                }
                result_classification = classify_scrape_result([], stats)
                stats['result_status'] = result_classification['result_status']
                if result_classification['failure_category']:
                    stats['failure_category'] = result_classification['failure_category']
                if result_classification['failure_reason']:
                    stats['failure_reason'] = result_classification['failure_reason']
                evaluation = evaluate_scrape_quality(site_key, site, [], stats)
                stats['coverage_status'] = evaluation['coverage_status']
                stats['validation'] = evaluation
                async with get_db_async() as conn:
                    conn.execute(
                        """
                        INSERT INTO scraping_logs
                        (site, url, run_id, status, coverage_status, items_found, error_message, validation_details, started_at, completed_at, duration_seconds)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            site_key,
                            site['urls'][0],
                            SCRAPE_RUN_ID.get(),
                            stats['status'],
                            stats['coverage_status'],
                            stats['items_found'],
                            json.dumps(stats['errors']),
                            serialize_validation_details(evaluation),
                            started_at,
                            datetime.now(timezone.utc).isoformat(),
                            time.time() - start_time,
                        ),
                    )
                    conn.commit()
                logger.warning(f'Special-source-only scraping failed for {site_key}: {special_exception}')
                return [], stats
            logger.warning(f'Special-source scraping failed for {site_key}, falling back to default flow: {special_exception}')

    if site.get('rss_feeds'):
        try:
            rss_items: List[Dict[str, Any]] = []
            start_time = time.time()
            started_at = datetime.now(timezone.utc).isoformat()
            stats = {
                'status': 'success',
                'items_found': 0,
                'items_added': 0,
                'errors': []
            }

            logger.info(f"[{datetime.now(timezone.utc).isoformat()}] Scraping {site['name']} via RSS...")
            empty_retry_count = max(0, int(site.get('retry_on_empty') or 0))
            empty_retry_delay = max(0.0, float(site.get('retry_on_empty_delay_seconds', 2.0)))
            for empty_attempt in range(empty_retry_count + 1):
                for verify_ssl in [True, False]:
                    try:
                        async with get_rss_httpx_client(verify_ssl) as client:
                            rss_items = await extract_items_from_rss(site_key, site, client)
                        if rss_items:
                            stats['errors'].append('Used RSS feed')
                            break
                    except Exception as rss_error:
                        stats['errors'].append(f'RSS fetch failed: {rss_error}')
                        logger.warning(f'RSS fetch failed for {site_key}: {rss_error}')

                if rss_items:
                    break
                if empty_attempt < empty_retry_count and not site.get('allow_zero_results'):
                    logger.warning(
                        f"RSS scrape for {site_key} returned no items; retrying empty result "
                        f"({empty_attempt + 1}/{empty_retry_count})"
                    )
                    if empty_retry_delay > 0:
                        await asyncio.sleep(empty_retry_delay)

            if rss_items:
                seen = set()
                unique_items = []
                for item in rss_items:
                    link = item.get('link')
                    if not link or link in seen:
                        continue
                    seen.add(link)
                    unique_items.append(item)
                unique_items = apply_source_downgrade(site, unique_items, stats)
                unique_items = sort_items_latest_first(unique_items)

                stats['items_found'] = len(unique_items)
                result_classification = classify_scrape_result(unique_items, stats)
                stats['result_status'] = result_classification['result_status']
                if result_classification['failure_category']:
                    stats['failure_category'] = result_classification['failure_category']
                if result_classification['failure_reason']:
                    stats['failure_reason'] = result_classification['failure_reason']
                evaluation = evaluate_scrape_quality(site_key, site, unique_items, stats)
                stats['coverage_status'] = evaluation['coverage_status']
                stats['validation'] = evaluation

                async with get_db_async() as conn:
                    conn.execute(
                        """
                        INSERT INTO scraping_logs
                        (site, url, run_id, status, coverage_status, items_found, error_message, validation_details, started_at, completed_at, duration_seconds)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            site_key,
                            site['urls'][0],
                            SCRAPE_RUN_ID.get(),
                            stats['status'],
                            stats['coverage_status'],
                            stats['items_found'],
                            json.dumps(stats['errors']) if stats['errors'] else None,
                            serialize_validation_details(evaluation),
                            started_at,
                            datetime.now(timezone.utc).isoformat(),
                            time.time() - start_time,
                        ),
                    )
                    conn.commit()

                logger.info(f"[{datetime.now(timezone.utc).isoformat()}] {site['name']}: Found {len(unique_items)} RSS items")
                return unique_items, stats
            if site.get('rss_only'):
                stats['items_found'] = 0
                stats['errors'].append('RSS only source returned no matching items')
                stats['result_status'] = 'empty'
                evaluation = evaluate_scrape_quality(site_key, site, [], stats)
                stats['coverage_status'] = evaluation['coverage_status']
                stats['validation'] = evaluation

                async with get_db_async() as conn:
                    conn.execute(
                        """
                        INSERT INTO scraping_logs
                        (site, url, run_id, status, coverage_status, items_found, error_message, validation_details, started_at, completed_at, duration_seconds)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            site_key,
                            site['urls'][0],
                            SCRAPE_RUN_ID.get(),
                            stats['status'],
                            stats['coverage_status'],
                            stats['items_found'],
                            json.dumps(stats['errors']) if stats['errors'] else None,
                            serialize_validation_details(evaluation),
                            started_at,
                            datetime.now(timezone.utc).isoformat(),
                            time.time() - start_time,
                        ),
                    )
                    conn.commit()

                logger.info(f"[{datetime.now(timezone.utc).isoformat()}] {site['name']}: RSS-only source yielded no matching items")
                return [], stats
        except Exception as rss_exception:
            logger.warning(f'RSS scraping failed for {site_key}, falling back to HTML: {rss_exception}')

    items, stats = await ORIGINAL_SCRAPE_SITE(site_key, site)

    if should_try_openclaw_browser_fallback(site, items, stats):
        try:
            browser_items = await asyncio.to_thread(extract_items_via_openclaw_browser, site_key, site)
            if browser_items:
                items = browser_items
                stats.setdefault('errors', []).append('Used OpenClaw browser fallback')
            else:
                stats.setdefault('errors', []).append('OpenClaw browser fallback returned no items')
        except Exception as browser_error:
            stats.setdefault('errors', []).append(f'OpenClaw browser fallback failed: {browser_error}')

    items = apply_source_downgrade(site, items, stats)
    items = sort_items_latest_first(items)
    result_classification = classify_scrape_result(items, stats)
    stats['result_status'] = result_classification['result_status']
    if result_classification['failure_category']:
        stats['failure_category'] = result_classification['failure_category']
    if result_classification['failure_reason']:
        stats['failure_reason'] = result_classification['failure_reason']

    try:
        evaluation = evaluate_scrape_quality(site_key, site, items, stats)
        stats['coverage_status'] = evaluation['coverage_status']
        stats['validation'] = evaluation
        conn = get_db()
        try:
            row = conn.execute(
                'SELECT id FROM scraping_logs WHERE site = ? ORDER BY started_at DESC LIMIT 1',
                (site_key,),
            ).fetchone()
            if row:
                row_id = row['id'] if hasattr(row, 'keys') else row[0]
                conn.execute(
                    'UPDATE scraping_logs SET run_id = ?, coverage_status = ?, validation_details = ? WHERE id = ?',
                    (SCRAPE_RUN_ID.get(), evaluation['coverage_status'], serialize_validation_details(evaluation), row_id),
                )
                conn.commit()
        finally:
            conn.close()
    except Exception as coverage_error:
        logger.warning(f'Coverage evaluation failed for {site_key}: {coverage_error}')

    return items, stats


async def process_all_sites():
    token = SCRAPE_RUN_ID.set(str(uuid4()))
    try:
        await ORIGINAL_PROCESS_ALL_SITES()
    finally:
        SCRAPE_RUN_ID.reset(token)


SITES['sebi']['rss_feeds'] = ['https://www.sebi.gov.in/sebirss.xml']
SITES['rbi']['rss_feeds'] = [
    {'url': 'https://rbi.org.in/notifications_rss.xml', 'category': 'notification', 'type': 'notification'},
    {'url': 'https://rbi.org.in/pressreleases_rss.xml', 'category': 'press-release', 'type': 'press-release'},
]

for site_key in [
    'bse_clearing', 'dor', 'gic', 'gstn', 'hpx', 'iex', 'ifsc', 'irdai_grievance',
    'nmcx', 'nps', 'nsccl', 'nse_ifsc', 'pfrda', 'pxil', 'rbi_bsp', 'rbi_ccil', 'rbi_dpss',
    'rpfc', 'sat', 'sebi_ifsc'
]:
    SITES.pop(site_key, None)

SITES.update({
    'amfi': {'name': 'AMFI', 'description': 'Association of Mutual Funds in India', 'category': 'market-infrastructure', 'urls': ['https://www.amfiindia.com/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'notification'], 'new_source': True},
    'bcsbi': {'name': 'BCSBI', 'description': 'Banking Codes and Standards Board of India', 'category': 'market-infrastructure', 'urls': ['https://www.bcsbi.org.in/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'code-update'], 'new_source': True},
    'cestat': {'name': 'CESTAT', 'description': 'Customs, Excise and Service Tax Appellate Tribunal', 'category': 'legal', 'urls': ['https://cestat.gov.in/'], 'rate_limit_delay': 2, 'update_types': ['order', 'judgment'], 'new_source': True},
    'cibil': {'name': 'CIBIL', 'description': 'TransUnion CIBIL', 'category': 'credit-bureau', 'urls': ['https://www.cibil.com/'], 'rate_limit_delay': 2, 'update_types': ['notice', 'press-release'], 'new_source': True},
    'cma_india': {'name': 'ICMAI', 'description': 'Institute of Cost Accountants of India', 'category': 'professional-body', 'urls': ['https://icmai.in/'], 'rate_limit_delay': 2, 'update_types': ['notice', 'circular'], 'new_source': True},
    'crif_highmark': {'name': 'CRIF High Mark', 'description': 'CRIF High Mark Credit Information Services', 'category': 'credit-bureau', 'urls': ['https://www.crifhighmark.com/'], 'rate_limit_delay': 2, 'update_types': ['notice', 'press-release'], 'new_source': True},
    'dicgc': {'name': 'DICGC', 'description': 'Deposit Insurance and Credit Guarantee Corporation', 'category': 'institutional', 'urls': ['https://www.dicgc.org.in/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'notification'], 'new_source': True},
    'epfo': {'name': 'EPFO', "description": "Employees' Provident Fund Organisation", 'category': 'pension', 'urls': ['https://www.epfindia.gov.in/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'notification'], 'new_source': True},
    'equifax': {'name': 'Equifax India', 'description': 'Equifax Credit Information Services', 'category': 'credit-bureau', 'urls': ['https://www.equifax.co.in/'], 'rate_limit_delay': 2, 'update_types': ['notice', 'press-release'], 'new_source': True},
    'experian': {'name': 'Experian India', 'description': 'Experian Credit Bureau', 'category': 'credit-bureau', 'urls': ['https://www.experian.in/'], 'rate_limit_delay': 2, 'update_types': ['notice', 'press-release'], 'new_source': True},
    'gic_re': {'name': 'GIC Re', 'description': 'General Insurance Corporation of India', 'category': 'insurance', 'urls': ['https://www.gicofindia.in/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'press-release'], 'new_source': True},
    'gst_council': {'name': 'GST Council', 'description': 'Goods and Services Tax Council', 'category': 'legal', 'urls': ['https://gstcouncil.gov.in/'], 'rate_limit_delay': 2, 'update_types': ['notification', 'press-release'], 'new_source': True},
    'iba': {'name': 'IBA', "description": "Indian Banks' Association", 'category': 'market-infrastructure', 'urls': ['https://www.iba.org.in/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'notice'], 'new_source': True},
    'icai': {'name': 'ICAI', 'description': 'Institute of Chartered Accountants of India', 'category': 'professional-body', 'urls': ['https://www.icai.org/'], 'rate_limit_delay': 2, 'update_types': ['notification', 'circular'], 'new_source': True},
    'icsi': {'name': 'ICSI', 'description': 'Institute of Company Secretaries of India', 'category': 'professional-body', 'urls': ['https://www.icsi.edu/'], 'rate_limit_delay': 2, 'update_types': ['notification', 'circular'], 'new_source': True},
    'india_inx': {'name': 'India INX', 'description': 'India International Exchange', 'category': 'exchange', 'urls': ['https://www.indiainx.com/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'notice'], 'new_source': True},
    'itat': {'name': 'ITAT', 'description': 'Income Tax Appellate Tribunal', 'category': 'legal', 'urls': ['https://www.itat.gov.in/'], 'rate_limit_delay': 2, 'update_types': ['order', 'judgment'], 'new_source': True},
    'nism': {'name': 'NISM', 'description': 'National Institute of Securities Markets', 'category': 'professional-body', 'urls': ['https://www.nism.ac.in/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'notice'], 'new_source': True},
    'npci': {'name': 'NPCI', 'description': 'National Payments Corporation of India', 'category': 'payments', 'urls': ['https://www.npci.org.in/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'notification'], 'new_source': True},
    'nps_trust': {'name': 'NPS Trust', 'description': 'National Pension System Trust', 'category': 'pension', 'urls': ['https://www.npstrust.org.in/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'notification'], 'new_source': True},
    'pdai': {'name': 'PDAI', 'description': 'Primary Dealers Association of India', 'category': 'market-infrastructure', 'urls': ['https://www.pdai.org.in/'], 'rate_limit_delay': 2, 'update_types': ['circular', 'notice'], 'new_source': True},
})

SITES['amfi']['urls'] = ['https://www.amfiindia.com/distributor/amfi-circulars']
SITES['amfi']['required_keywords'] = ['circular', 'guideline', 'arn', '.pdf']

main_v7_fixed_base.SITES = SITES
main_v7_fixed_base.init_db = init_db
main_v7_fixed_base.extract_items_from_soup = extract_items_from_soup
main_v7_fixed_base.collect_item_attachments = collect_item_attachments
main_v7_fixed_base.persist_item_attachments = persist_item_attachments
main_v7_fixed_base.scrape_site = scrape_site
main_v7_fixed_base.process_all_sites = process_all_sites

app.version = '8.0'
app.title = 'GovUpdate API'

@app.get('/api/source-coverage', tags=['Monitoring'])
@handle_api_errors
async def get_source_coverage(
    api_key_info = Depends(validate_api_key)
):
    async with get_db_async() as conn:
        coverage_report = build_source_coverage_report(conn, SITES)
        return {
            'success': True,
            **coverage_report,
        }
