---
title: Builds
product_area: ci-cd
tags: [builds, pipelines, failures, logs, artifacts]
---

# Builds

A **build** is a single execution of your pipeline triggered by a git event, a manual dispatch, or a scheduled cron job.

## Build States

| State | Description |
|-------|-------------|
| `queued` | Waiting for an available runner. |
| `running` | Actively executing pipeline steps. |
| `passed` | All steps completed with exit code 0. |
| `failed` | One or more steps exited non-zero. |
| `cancelled` | Stopped by a user or timeout policy. |
| `skipped` | Conditions (branch filters, path filters) prevented execution. |

## Triggering a Build

**Via push:** Any push to a tracked branch triggers the pipeline defined in `.helix-ci.yml`.

**Manual trigger via API:**
```bash
curl -X POST https://api.helix.example/v1/repos/{repo_id}/builds \
  -H "Authorization: Bearer $HELIX_TOKEN" \
  -d '{"ref": "main", "pipeline": "deploy"}'
```

**Via UI:** Repository → Builds → Run Pipeline → select branch and pipeline.

## Viewing Build Logs

Logs stream in real-time. To fetch via API:

```bash
GET /v1/builds/{build_id}/logs?step=test&tail=200
```

Logs are retained for 30 days on the Free plan, 90 days on Pro, and 1 year on Enterprise.

## Artifacts

Build artifacts (binaries, coverage reports, container images) are stored in Helix Artifact Registry.

```bash
# Download artifact
curl -L https://artifacts.helix.example/{build_id}/{artifact_name} \
  -H "Authorization: Bearer $HELIX_TOKEN" -o artifact.tar.gz
```

Artifact retention mirrors log retention per plan.

## Debugging Failed Builds

1. Open the failed build → click the failed step to expand logs.
2. Look for exit code in the final line: `exit status 1`.
3. Check environment variables are set: **Settings → CI/CD Variables**.
4. Reproduce locally: `helix run --local --pipeline test --ref HEAD`.

Common failure patterns:

| Pattern | Cause |
|---------|-------|
| `Cannot connect to Docker daemon` | Runner misconfigured — contact support |
| `No such file or directory: .helix-ci.yml` | Missing config file in repo root |
| `Artifact upload failed: 403` | Artifact Registry permissions not set |
| `Timeout after 3600s` | Build exceeded plan time limit; optimize or upgrade plan |

## Build Limits by Plan

| Plan | Concurrent builds | Max build time | Storage |
|------|-----------------|----------------|---------|
| Free | 1 | 30 min | 1 GB |
| Pro | 5 | 60 min | 10 GB |
| Enterprise | Unlimited | 120 min | Unlimited |
