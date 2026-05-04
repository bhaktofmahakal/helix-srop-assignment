---
title: Support Tickets
product_area: support
tags: [support, tickets, escalation, sla, priority]
---

# Support Tickets

## Opening a Ticket

**UI:** Click the **?** icon → Support → New Ticket.

**API:**
```bash
POST /v1/tickets
{
  "title": "Builds stuck in queued state for 2 hours",
  "description": "...",
  "priority": "high",
  "product_area": "ci-cd",
  "attachments": ["screenshot.png"]
}
```

**Priority levels:**

| Priority | Use when | SLA (Pro) | SLA (Enterprise) |
|----------|----------|-----------|-----------------|
| `critical` | Production down, data loss risk | 1 hour | 30 min |
| `high` | Major feature broken, significant impact | 4 hours | 2 hours |
| `normal` | Feature degraded, workaround exists | 24 hours | 8 hours |
| `low` | Question, enhancement request | 48 hours | 24 hours |

## Ticket Lifecycle

```
open → in_progress → pending_customer → resolved → closed
                           ↕
                      reopened (within 14 days of resolution)
```

You receive email notifications on every state change. Reply to the email to add a comment.

## Escalating a Ticket

If a ticket is not progressing:

1. **UI:** Open the ticket → **Escalate** button → select reason.
2. **API:**
```bash
POST /v1/tickets/{ticket_id}/escalate
{ "reason": "production_impacted", "note": "3 engineers blocked" }
```

Escalation bumps priority to `critical` and pages the on-call engineer.

Enterprise customers: your CSM can be @-mentioned in ticket comments for direct escalation.

## Providing Diagnostic Information

Include in your ticket to speed resolution:

- **Build ID** (format: `bld_xxxxxxxx`)
- **Organization ID** (Settings → General → Org ID)
- **Timestamp** of when the issue started (UTC)
- **Error messages** — copy the exact text, not a screenshot
- **What changed** before the issue appeared

## Viewing Ticket History

```bash
GET /v1/tickets?status=open&limit=20
GET /v1/tickets/{ticket_id}/comments
```

## SLA Tracking

SLA clock starts when a ticket is submitted. It pauses when status is `pending_customer` (waiting for your response). If an SLA is breached, the ticket is automatically escalated internally and you are notified.

View SLA status: Ticket detail → **SLA** badge (green = within SLA, yellow = at risk, red = breached).

## Common Ticket Templates

### Build Failure Report
```
Build ID: bld_xxx
Pipeline: [name]
Branch: main
Started: 2026-04-01 12:00 UTC
Error in step: [step name]
Last 20 lines of log:
[paste here]
```

### Secret Scanning False Positive
```
Alert ID: sa_xxx
File: [path]
Line: [number]
Reason this is not a secret: [explanation]
```
