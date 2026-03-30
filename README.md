# GovUpdate Broker Alerts API

Open-source FastAPI service for broker-focused regulatory alerts across Indian market infrastructure sources.

GovUpdate aggregates and normalizes updates from broker-relevant sources such as SEBI, NSE, BSE, NSDL, CDSL, RBI, FEMA, CBDT, CBIC, CKYCR, CERSAI, SCORES, FIU-IND, and related entities, then exposes the result through an API and signed webhooks.

It is built for people who want a broker-only regulatory alert pipeline instead of manually tracking circulars across many regulator and market-infrastructure sites.

## Why this exists

- Indian broker-relevant updates are fragmented across many websites and formats.
- Raw circular feeds are noisy and not broker-specific.
- Internal tools often want structured events and webhook delivery, not another dashboard.

## Who this is for

- developers building internal compliance or monitoring tooling
- compliance and ops teams that want a self-hosted reference implementation
- niche regtech builders who need a starting point for broker-focused alerting

## What you get

- normalized broker-alert event feed
- source profile and source health visibility
- signed webhooks with replay support
- retry handling, dead letters, and auto-pause on repeated failure
- tests covering the current broker-alert and verification flows

## 60-second demo

```powershell
.\install.ps1
.\.venv\Scripts\Activate.ps1
uvicorn src.main:app --reload
```

Then open:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/profiles/broker-alerts-v1`
- `http://127.0.0.1:8000/api/events`

Example:

```bash
curl "http://127.0.0.1:8000/api/events?limit=5"
```

Typical event shape:

```json
{
  "event_id": "evt_...",
  "source_key": "sebi",
  "source_keys": ["sebi", "bse"],
  "title": "SEBI order on margin reporting",
  "published_date": "2026-03-12",
  "canonical_url": "https://www.sebi.gov.in/legal/orders/...",
  "type": "order",
  "confidence": "verified",
  "profile_key": "broker_alerts_v1"
}
```

## Project status

- experimental and maintained as a reference implementation
- suitable for self-hosting, internal tooling, and further extension
- not legal, regulatory, or compliance advice

Read [DISCLAIMER.md](DISCLAIMER.md) before using this project in a production compliance workflow.

## Supported entrypoints

The current public app entrypoint is:

- `uvicorn src.main:app --reload`

The main modules are:

- `src/main.py`
- `src/api.py`
- `src/broker_alerts.py`
- `init_db.py`
- `init_api_db.py`

Historical `main-v*` files are retained as development history and parser reference material. They are not the supported public runtime surface.

## Install

```powershell
.\install.ps1
.\.venv\Scripts\Activate.ps1
```

For POSIX shells:

```bash
chmod +x install.sh
./install.sh
source .venv/bin/activate
```

## Run

```powershell
uvicorn src.main:app --reload
```

Open the API docs at `http://127.0.0.1:8000/docs`.

## External prerequisites

- Python 3.13 is the version used by the published CI workflow.
- OpenClaw is optional and is not installed by `pip install -r requirements.txt`.
- Install and run OpenClaw separately only if you need browser-backed live scraping for JS-rendered or anti-bot-sensitive sources.

## Configuration

Example environment variables live in [.env.example](.env.example).

Important notes:

- do not commit a real `.env`
- configure OpenClaw only if you need browser-backed live scraping for JS-rendered or anti-bot-sensitive sources
- local scraped data and generated verification artifacts are intentionally ignored from the public repo

## OpenClaw browser support

Some source fetches in the scraper stack use an OpenClaw-managed browser. This is mainly for sites that do not expose a stable RSS/API path or require rendered DOM access.

OpenClaw is not required for every endpoint or parser, but it is part of the live scraping path for selected sources and fallbacks.

The relevant environment variables are:

- `OPENCLAW_BROWSER_CONTROL_URL`
- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_BROWSER_PROFILE`

If these are not set, the code may also fall back to a local OpenClaw config at `~/.openclaw/openclaw.json`.

The repo also ignores local OpenClaw runtime logs under `.openclaw-run/`.

If you are only consuming an existing local database or using the API/webhook layer, you can skip OpenClaw entirely.

## Main API surface

- `GET /`
- `GET /health`
- `GET /sources`
- `GET /profiles/broker-alerts-v1`
- `GET /api/circulars`
- `GET /api/circulars/{circular_id}`
- `GET /api/sites`
- `GET /api/source-health`
- `GET /api/source-subscriptions`
- `PUT /api/source-subscriptions`
- `GET /api/events`
- `GET /api/events/{event_id}`
- `GET /api/webhooks`
- `POST /api/webhooks`
- `PATCH /api/webhooks/{webhook_id}`
- `DELETE /api/webhooks/{webhook_id}`
- `GET /api/webhooks/{webhook_id}/deliveries`
- `GET /api/webhooks/{webhook_id}/dead-letters`
- `GET /api/webhooks/{webhook_id}/health`
- `POST /api/webhooks/{webhook_id}/test`
- `POST /api/webhooks/{webhook_id}/replay`

For a fuller API contract and webhook payload example, see [BROKER_API_GUIDE.md](BROKER_API_GUIDE.md).

## Tests

The repository includes targeted backend CI in [.github/workflows/backend-ci.yml](.github/workflows/backend-ci.yml).

Run the main public test slices locally with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_broker_alerts_api.py tests/test_run_full_latest_verification.py tests/test_special_source_parsers.py -q
```

`pytest` is included in `requirements-dev.txt` and is installed by default by `install.ps1` and `install.sh`.

## Deployment

Production deployment notes are in [DEPLOYMENT.md](DEPLOYMENT.md).

The repo includes:

- a production `Dockerfile`
- `.dockerignore`
- example `systemd` unit
- example `nginx` config

## Sample webhook receiver

A minimal signed receiver example is in [examples/webhook_receiver.py](examples/webhook_receiver.py).
A Node version is in [examples/webhook_receiver_node.js](examples/webhook_receiver_node.js).

Run it with:

```powershell
$env:GOVUPDATE_WEBHOOK_SECRET="change-me"
uvicorn examples.webhook_receiver:app --port 8010
```

Then point a GovUpdate webhook at:

```text
http://localhost:8010/govupdate/webhook
```

## License

This project is available under the [MIT License](LICENSE).
