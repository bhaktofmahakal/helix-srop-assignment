---
title: API Authentication
product_area: security
tags: [auth, tokens, api-key, oauth, jwt]
---

# API Authentication

All Helix API requests require authentication. Three methods are supported depending on your use case.

## 1. Personal Access Tokens (PAT)

Best for: scripts, local development, one-off automation.

**Create a PAT:** Settings → Developer → Personal Access Tokens → New Token.

Scopes available:
- `read:repos` — read repository metadata
- `write:repos` — push, create branches
- `read:builds` — view build status and logs
- `write:builds` — trigger builds, cancel
- `admin:org` — manage organization settings

**Usage:**
```bash
curl -H "Authorization: Bearer $HELIX_TOKEN" \
  https://api.helix.example/v1/repos
```

PATs expire in 90 days by default. Rotation reminders are sent 14 days before expiry.

## 2. OAuth 2.0 (for user-facing applications)

Best for: third-party integrations, IDE plugins, apps acting on behalf of a user.

**Authorization Code Flow:**

```
GET https://auth.helix.example/oauth/authorize
  ?client_id=CLIENT_ID
  &redirect_uri=https://yourapp.example/callback
  &scope=read:repos+read:builds
  &state=RANDOM_STATE
  &response_type=code
```

Exchange code for token:
```bash
POST https://auth.helix.example/oauth/token
{
  "client_id": "CLIENT_ID",
  "client_secret": "CLIENT_SECRET",
  "code": "AUTHORIZATION_CODE",
  "grant_type": "authorization_code",
  "redirect_uri": "https://yourapp.example/callback"
}
```

Access tokens expire in 1 hour. Use the refresh token to get a new access token:
```bash
POST https://auth.helix.example/oauth/token
{
  "grant_type": "refresh_token",
  "refresh_token": "REFRESH_TOKEN",
  "client_id": "CLIENT_ID",
  "client_secret": "CLIENT_SECRET"
}
```

## 3. Service Account Tokens

Best for: machine-to-machine, CI/CD pipelines, long-lived automation.

Service accounts are not tied to a user. Create via:
```bash
POST /v1/orgs/{org_id}/service-accounts
{ "name": "my-deploy-bot", "scopes": ["read:repos", "write:builds"] }
```

Returns a `token` — store it in your secret manager immediately. It is shown only once.

## Token Storage Best Practices

- Store in environment variables or a secret manager (Vault, AWS Secrets Manager).
- Never commit tokens to source code.
- Use Secret Scanning to catch accidental commits.
- Rotate PATs every 90 days; service account tokens every 30 days for high-privilege accounts.

## Rate Limits

| Plan | Requests/minute | Requests/hour |
|------|----------------|--------------|
| Free | 60 | 1,000 |
| Pro | 600 | 10,000 |
| Enterprise | 6,000 | 100,000 |

Rate limit headers are included in every response:
```
X-RateLimit-Limit: 600
X-RateLimit-Remaining: 487
X-RateLimit-Reset: 1711929600
```

On 429, retry after `Retry-After` seconds.
