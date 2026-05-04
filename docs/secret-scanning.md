---
title: Secret Scanning
product_area: security
tags: [secrets, scanning, tokens, alerts, remediation]
---

# Secret Scanning

Secret Scanning automatically detects credentials, API keys, and tokens committed to your repositories — before they reach production or are exposed publicly.

## How It Works

Every push triggers a scan of the diff. Helix compares content against 200+ patterns including:

- AWS IAM keys (`AKIA...`)
- GitHub/GitLab personal access tokens
- Stripe, Twilio, SendGrid, and other SaaS API keys
- Private SSH keys (`-----BEGIN RSA PRIVATE KEY-----`)
- Generic high-entropy strings (configurable threshold)
- Database connection strings with embedded passwords

## Enabling Secret Scanning

**Repository level:** Settings → Security → Secret Scanning → Enable.

**Organization level:** Organization Settings → Security → Enforce Secret Scanning (applies to all repos).

Once enabled, historical commits are scanned within 24 hours on Pro/Enterprise. Free plan scans new pushes only.

## Alert Workflow

When a secret is detected:

1. The push is **blocked** (on Pro/Enterprise with push protection enabled).
2. An alert appears in **Security → Secret Alerts**.
3. Email notifications sent to: repo admins + the committer.
4. Webhook fired to configured endpoints: `POST /webhook` with `event: secret_detected`.

## Responding to an Alert

**Step 1: Revoke the secret immediately.** Treat the secret as fully compromised regardless of repo visibility.

**Step 2: Remove from history:**
```bash
# Using git-filter-repo (recommended over BFG)
pip install git-filter-repo
git filter-repo --path-glob '*.env' --invert-paths
git push --force-with-lease origin main
```

**Step 3: Resolve the alert in UI:** Security → Secret Alerts → [alert] → Mark Resolved → select reason.

**Step 4: Rotate the credential.** Do not reuse revoked secrets.

## Allowlisting False Positives

If a detected string is not a real secret (e.g. a test fixture):

```yaml
# .helix/secret-scanning.yml
ignored_paths:
  - tests/fixtures/
ignored_patterns:
  - AKIAIOSFODNN7EXAMPLE  # test key from AWS docs
```

## Custom Patterns

Add organization-specific patterns:

```yaml
# .helix/secret-scanning.yml
custom_patterns:
  - name: internal-service-token
    regex: 'hsvc_[a-zA-Z0-9]{32}'
    severity: high
```

## Audit Log

All secret detection events are in the audit log:

```
GET /v1/audit-logs?event_type=secret_detected&repo_id={id}
```
