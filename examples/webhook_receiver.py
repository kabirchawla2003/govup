import hashlib
import hmac
import json
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request


WEBHOOK_SECRET = os.getenv("GOVUPDATE_WEBHOOK_SECRET", "change-me")

app = FastAPI(title="GovUpdate Sample Webhook Receiver")


def verify_signature(body: bytes, signature_header: str | None) -> None:
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing signature header")

    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header.removeprefix("sha256=")

    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid signature")


@app.post("/govupdate/webhook")
async def receive_webhook(
    request: Request,
    x_govupdate_signature: str | None = Header(default=None),
    x_govupdate_event_id: str | None = Header(default=None),
    x_govupdate_delivery_id: str | None = Header(default=None),
    x_govupdate_source: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await request.body()
    verify_signature(body, x_govupdate_signature)

    payload = json.loads(body)
    event = payload.get("event", {})

    print(
        json.dumps(
            {
                "received": True,
                "delivery_id": x_govupdate_delivery_id,
                "event_id": x_govupdate_event_id or event.get("event_id"),
                "source_key": x_govupdate_source or event.get("source_key"),
                "title": event.get("title"),
                "published_date": event.get("published_date"),
            }
        )
    )

    return {
        "ok": True,
        "delivery_id": x_govupdate_delivery_id,
        "event_id": x_govupdate_event_id or event.get("event_id"),
    }
