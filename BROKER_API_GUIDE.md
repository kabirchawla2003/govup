# Broker Alerts API Guide

This guide describes the public broker alerts API surface.

## Scope

The product is intentionally narrow:

- broker-relevant regulatory and market-infrastructure alerts
- API access to normalized events
- signed webhooks for new events
- source health and delivery observability

It is not a generic "all circulars for everyone" feed.

## Core profile

Profile key: `broker_alerts_v1`

Key endpoints:

- `GET /profiles/broker-alerts-v1`
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
- `GET /api/reliability/latest`
- `POST /api/webhooks/{webhook_id}/test`
- `POST /api/webhooks/{webhook_id}/replay`

## Event shape

The webhook payload looks like:

```json
{
  "delivery_id": "dlv_...",
  "profile_key": "broker_alerts_v1",
  "sent_at": "2026-03-14T10:00:00+00:00",
  "event": {
    "event_id": "evt_...",
    "source_key": "sebi",
    "source_keys": ["sebi", "bse"],
    "mirror_count": 1,
    "mirror_sources": [
      {
        "source_key": "bse",
        "source_name": "BSE"
      }
    ],
    "title": "SEBI order on margin reporting",
    "summary": "SEBI order on margin reporting",
    "published_date": "2026-03-12",
    "published_at": "2026-03-12T00:00:00+00:00",
    "canonical_url": "https://www.sebi.gov.in/legal/orders/...",
    "direct_file_url": null,
    "category": "order",
    "type": "order",
    "group": "regulator",
    "contract": "circulars_orders_notices",
    "confidence": "verified",
    "profile_key": "broker_alerts_v1"
  }
}
```

Important fields:

- `event_id`: stable canonical event id
- `source_key`: preferred primary source after dedupe
- `source_keys`: all merged source keys for the same event
- `mirror_sources`: other mirrored sources kept for traceability
- `canonical_url`: normalized primary link for the event
- `direct_file_url`: direct PDF/ZIP/etc if available
- `confidence`: `verified`, `likely`, or `degraded`

## Webhook headers

Every webhook delivery includes:

- `Content-Type: application/json`
- `X-GovUpdate-Event-Id`
- `X-GovUpdate-Delivery-Id`
- `X-GovUpdate-Webhook-Id`
- `X-GovUpdate-Source`
- `Idempotency-Key`
- `X-GovUpdate-Signature` when a secret is configured

Signature format:

- `sha256=<hex>`

The signature is computed over the raw request body.

## Retry and idempotency

- Delivery retries use the configured `retry_count`
- `Idempotency-Key` is the canonical `event_id`
- Successful deliveries are not replayed again unless forced

## Auto-pause and dead letters

Webhooks now support:

- `pause_on_failure_threshold`
- automatic pause after repeated failed deliveries
- dead-letter persistence for permanently failed events

Relevant fields returned on webhook objects:

- `consecutive_failure_count`
- `dead_letter_count`
- `pause_on_failure_threshold`
- `auto_paused`
- `last_delivery_status`
- `last_delivery_http_status`
- `last_delivery_latency_ms`

Relevant operational endpoints:

- `GET /api/webhooks/{webhook_id}/deliveries`
- `GET /api/webhooks/{webhook_id}/dead-letters`
- `GET /api/webhooks/{webhook_id}/health`
- `GET /api/reliability/latest`

## Webhook create example

```bash
curl -X POST "http://localhost:8000/api/webhooks" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/govupdate/webhook",
    "name": "compliance-prod",
    "profile_name": "broker_alerts_v1",
    "site_keys": ["sebi", "nse", "bse", "nsdl", "cdsl"],
    "confidence_filter": "verified",
    "retry_count": 3,
    "pause_on_failure_threshold": 5,
    "timeout_seconds": 30
  }'
```

## Sample receivers

- Python: [examples/webhook_receiver.py](D:/circular_api/examples/webhook_receiver.py)
- Node: [examples/webhook_receiver_node.js](D:/circular_api/examples/webhook_receiver_node.js)

## Source health semantics

Source health should be interpreted as:

- `working`: current source is healthy
- `degraded`: source is available but confidence is lower
- `network_failed`: transport or DNS problem
- `blocked`: upstream access restriction
- `browser_failed`: browser-control layer failure
- `excluded`: intentionally outside broker product scope

## Pilot checklist

Before onboarding a broker pilot:

- verify webhook endpoint accepts signed JSON
- verify `Idempotency-Key` handling
- subscribe only to the customer's relevant source set
- review `/api/source-health`
- review `/api/reliability/latest`
- run `/api/webhooks/{id}/test`
- monitor `/api/webhooks/{id}/health` and `/dead-letters`
