---
title: Deploy Keys
product_area: security
tags: [keys, secrets, ci-cd, rotation]
---

# Deploy Keys

Deploy keys give your CI/CD pipeline read-only (or read-write) access to a specific repository without requiring a personal access token tied to a user account.

## Creating a Deploy Key

1. Navigate to **Settings → Security → Deploy Keys**.
2. Click **New Deploy Key**.
3. Paste your public SSH key (Ed25519 recommended: `ssh-keygen -t ed25519 -C "ci@yourorg"`).
4. Choose **Read-only** unless your pipeline needs to push tags or commits back.
5. Click **Save**.

The key is scoped to one repository. To grant access to multiple repos, create a key per repo or use a service account.

## Rotating a Deploy Key

Rotation should happen every 90 days or immediately after a suspected compromise.

```bash
# Step 1: Generate new key pair (do NOT reuse old passphrase)
ssh-keygen -t ed25519 -f ~/.ssh/helix_deploy_new -C "ci-rotated-$(date +%Y%m%d)"

# Step 2: Add the new public key in the Helix UI (Settings → Deploy Keys → New)
# Keep the old key active during this step.

# Step 3: Update your CI/CD secret store with the new private key.
#   GitHub Actions: Settings → Secrets → HELIX_DEPLOY_KEY
#   GitLab CI:      Settings → CI/CD → Variables → HELIX_DEPLOY_KEY

# Step 4: Trigger a test pipeline run to confirm the new key works.

# Step 5: Delete the old key from Helix UI.
```

Never rotate in place by overwriting the key without first verifying the replacement works. A failed rotation can break all CI pipelines.

## Auditing Key Usage

Every deploy key access is logged. To view:

```
GET /v1/audit-logs?resource_type=deploy_key&limit=100
```

Response includes `key_id`, `accessed_at`, `pipeline_id`, `repo`, and `ip_address`.

## Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `Permission denied (publickey)` | Wrong key in CI secret | Re-paste private key; check for trailing newline |
| Key listed but not working | Key added to wrong repo | Check key scope in Settings |
| Pipeline breaks after rotation | Old key deleted before new one verified | Restore old key from backup; re-verify new key |
