---
title: Runners
product_area: ci-cd
tags: [runners, self-hosted, agents, executor]
---

# Runners

Runners are the compute environments that execute your pipeline steps. Helix provides cloud-hosted runners and supports self-hosted runners for custom requirements.

## Cloud-Hosted Runners

Available pools:

| Pool | CPU | RAM | Storage | Use case |
|------|-----|-----|---------|----------|
| `standard` | 2 vCPU | 7 GB | 14 GB SSD | Default — most workloads |
| `large` | 8 vCPU | 32 GB | 100 GB SSD | Heavy builds, parallel testing |
| `gpu` | 4 vCPU + T4 GPU | 15 GB | 50 GB SSD | ML training, inference benchmarks |
| `macos` | M1 4-core | 8 GB | 100 GB | iOS/macOS builds |

Cloud runners are ephemeral — a fresh VM is provisioned per build. No state persists between builds unless you use caching or artifacts.

## Self-Hosted Runners

Run pipelines on your own infrastructure (on-prem, VPC, air-gapped).

### Installation

```bash
# Linux x86_64
curl -sSL https://dl.helix.example/runner/install.sh | bash

# Configure
helix-runner configure \
  --url https://helix.example \
  --token $RUNNER_REGISTRATION_TOKEN \
  --name my-runner-01 \
  --labels linux,docker,fast-storage

# Start as a service
sudo systemctl enable --now helix-runner
```

### Runner Labels

Label runners to target specific pipelines:

```yaml
# .helix-ci.yml
pipelines:
  build:
    runner:
      labels: [self-hosted, linux, fast-storage]
```

### Autoscaling Self-Hosted Runners

Use the Helix Runner Autoscaler to scale based on queue depth:

```yaml
# runner-autoscaler.yml
provider: aws  # or gcp, azure, kubernetes
min_runners: 1
max_runners: 20
idle_timeout: 300  # seconds before idle runner terminates
scale_up_threshold: 3  # jobs waiting → add runner
```

## Runner Security

- Cloud runners run in isolated VMs — no cross-build data leakage.
- Self-hosted runners should run with a dedicated non-root user: `helix-runner`.
- Network egress: runners need outbound HTTPS to `api.helix.example` and your artifact registries.
- For highly sensitive builds, use `runner.network: isolated` to disable all outbound except Helix.

## Troubleshooting Runner Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Build stuck in `queued` state | No matching runner available | Check runner labels match; verify runner is online |
| `runner disconnected` error | Network interruption | Check runner logs: `journalctl -u helix-runner -n 100` |
| Docker-in-Docker not working | DinD requires privileged mode | Add `runner.privileged: true` in config (self-hosted only) |
| Build slower than expected | Runner pool overloaded | Upgrade to `large` pool or add self-hosted runners |

## Monitoring Runners

Runner health is visible at Organization → Runners. Metrics available:
- Queue depth per label
- Active builds per runner
- Runner CPU/memory utilization (self-hosted only, requires agent)
