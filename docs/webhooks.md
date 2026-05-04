---
title: Webhooks
product_area: integrations
tags: [webhooks, events, integrations, http]
---

# Webhooks

Webhooks let Helix notify your services when events happen — build completions, secret detections, ticket updates, etc.

## Creating a Webhook

**UI:** Settings → Integrations → Webhooks → New Webhook.

**API:**
```bash
POST /v1/orgs/{org_id}/webhooks
{
  "url": "https://yourservice.example/helix-events",
  "secret": "your-signing-secret",
  "events": ["build.completed", "build.failed", "secret.detected", "ticket.created"]
}
```

## Event Types

| Event | Fires when |
|-------|-----------|
| `build.queued` | A build enters the queue |
| `build.started` | A build begins running |
| `build.completed` | A build finishes (any status) |
| `build.failed` | A build exits non-zero |
| `build.cancelled` | A build is cancelled |
| `secret.detected` | Secret Scanning finds a credential |
| `ticket.created` | A support ticket is opened |
| `ticket.resolved` | A support ticket is resolved |
| `deploy_key.rotated` | A deploy key is replaced |
| `member.added` | User joins the organization |
| `member.removed` | User leaves the organization |

## Payload Format

```json
{
  "event": "build.failed",
  "delivery_id": "d1a2b3c4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2026-04-01T14:32:11Z",
  "org_id": "org_abc123",
  "data": {
    "build_id": "bld_xyz789",
    "pipeline": "test",
    "ref": "main",
    "sha": "a1b2c3d4e5f6",
    "duration_seconds": 142,
    "failed_step": "pytest",
    "exit_code": 1
  }
}
```

## Verifying Signatures

Every delivery includes `X-Helix-Signature-256` — HMAC-SHA256 of the raw payload body using your webhook secret.

```python
import hmac, hashlib

def verify_signature(payload_body: bytes, secret: str, signature_header: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```

Always verify before processing the payload.

## Retry Policy

Helix retries failed deliveries (non-2xx responses or timeouts) with exponential backoff:
- Attempt 1: immediate
- Attempt 2: 5 minutes later
- Attempt 3: 30 minutes later
- Attempt 4: 2 hours later
- After 4 failures: webhook is paused; admin notified

View delivery history: Settings → Integrations → Webhooks → [webhook] → Recent Deliveries.

## Testing Webhooks

Send a test delivery:
```bash
POST /v1/webhooks/{webhook_id}/test
{ "event": "build.completed" }
```

Or use the **Redeliver** button on any past delivery in the UI.

## Common Integrations

- **Slack:** Use `build.failed` + `build.completed` to post to a channel.
- **PagerDuty:** Fire `build.failed` on `main` to create an incident.
- **GitHub/GitLab:** Update commit status from `build.completed`.
- **Custom ITSM:** Create tickets on `secret.detected`.
