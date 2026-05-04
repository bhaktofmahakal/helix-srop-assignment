---
title: Billing and Plans
product_area: billing
tags: [billing, plans, upgrade, invoice, limits]
---

# Billing and Plans

## Plan Overview

| Feature | Free | Pro ($49/seat/mo) | Enterprise (custom) |
|---------|------|-------------------|---------------------|
| Concurrent builds | 1 | 5 | Unlimited |
| Build time limit | 30 min | 60 min | 120 min |
| Log retention | 30 days | 90 days | 1 year |
| Secret scanning | New pushes only | Full history + push protection | Full + custom patterns |
| Audit logs | 7 days | 90 days | Unlimited |
| Observability seats | 1 | 10 | Unlimited |
| SLA | None | 99.5% | 99.9% |
| Support | Community | Email (48h) | Dedicated CSM |

## Upgrading Your Plan

**Via UI:** Settings → Billing → Change Plan → select Pro or Enterprise → enter payment method.

**Via API:**
```bash
POST /v1/orgs/{org_id}/subscription
{
  "plan": "pro",
  "seats": 5,
  "billing_cycle": "annual"  # or "monthly"
}
```

Annual billing saves 20% versus monthly.

## Invoices

Invoices are generated on the 1st of each billing month. To download:

**UI:** Settings → Billing → Invoices → [month] → Download PDF.

**API:**
```bash
GET /v1/orgs/{org_id}/invoices?limit=12
```

Each invoice includes a breakdown by product area (CI/CD, Observability, Secret Scanning).

## Usage Limits and Overages

Free plan: builds are queued and will not run if you exceed the concurrent limit. No overages — upgrade to unblock.

Pro plan: overages for build minutes are charged at $0.01/minute beyond the 2,000 included minutes/seat/month.

## Cancellation

Settings → Billing → Cancel Plan → confirm. Your account downgrades to Free at the end of the current billing period. Data is retained for 60 days post-cancellation.

## Payment Methods

Accepted: Visa, Mastercard, Amex, ACH (Enterprise only). To update: Settings → Billing → Payment Method.

## Tax and VAT

VAT is applied for EU customers. Provide your VAT ID at Settings → Billing → Tax Information to get invoices without VAT (reverse charge).

## Troubleshooting

| Issue | Action |
|-------|--------|
| Build queue stuck on Free plan | You've hit concurrent limit; upgrade or wait |
| Invoice not received | Check spam; re-send via Settings → Billing → Invoices |
| Upgrade not taking effect | Allow up to 5 minutes; contact support if persists |
| Incorrect charge | Open a billing ticket via Settings → Support → New Ticket → type: Billing |
