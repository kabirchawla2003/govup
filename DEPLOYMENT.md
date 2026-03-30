# Deployment

This project is designed to be self-hosted as a small FastAPI service backed by SQLite or a copied scraper database.

## Environment

Minimum useful configuration:

```env
DB_PATH=./data/govupdate.db
LOG_LEVEL=info
OPENCLAW_BROWSER_CONTROL_URL=http://127.0.0.1:18791
OPENCLAW_GATEWAY_TOKEN=replace-me
OPENCLAW_BROWSER_PROFILE=openclaw
```

OpenClaw is only required for browser-backed live scraping paths. If you are serving an already-populated local database, the API can run without it.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## Docker

The repository includes a production `Dockerfile`.

Build and run:

```powershell
docker build -t govupdate-broker-alerts .
docker run --rm -p 8000:8000 --env-file .env govupdate-broker-alerts
```

## Reverse proxy

Any standard reverse proxy setup is fine. The app is plain HTTP behind Uvicorn.

Typical production concerns:

- protect the host and database file
- keep generated scrape artifacts and logs out of the public web root
- terminate TLS at the proxy
- monitor webhook failures and dead letters
- back up the SQLite database if webhook configuration matters

## Data model

The API reads circular/update data from:

- `circulars` view if present
- otherwise the `updates` table

Webhook configuration and delivery history live in the local database created by `init_db.py`.
