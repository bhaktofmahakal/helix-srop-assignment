---
title: Observability Overview
product_area: observability
tags: [observability, metrics, logs, traces, alerts, dashboards]
---

# Observability

Helix Observability provides unified metrics, logs, and distributed traces for services running in your CI/CD pipelines and production environments.

## Core Pillars

### Metrics

Helix collects Prometheus-compatible metrics. Instrument your service:

```python
from helix_sdk import metrics

counter = metrics.Counter("requests_total", labels=["status", "route"])
counter.inc(status="200", route="/api/users")
```

Metrics are queryable in Helix Dashboards using PromQL.

### Logs

Structured logs ship via the Helix Agent or direct API ingestion. Minimum required fields:

```json
{
  "timestamp": "2026-04-01T12:00:00Z",
  "level": "error",
  "message": "database connection failed",
  "service": "api-gateway",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Log retention: 30 days (Free), 90 days (Pro), 1 year (Enterprise).

### Traces

Helix supports OpenTelemetry distributed tracing. Configure your exporter:

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

exporter = OTLPSpanExporter(
    endpoint="https://otel.helix.example:4317",
    headers={"Authorization": f"Bearer {HELIX_TOKEN}"},
)
```

## Alerts

Create alerts from any metric query:

```yaml
# .helix/alerts.yml
alerts:
  - name: high-error-rate
    expr: rate(requests_total{status=~"5.."}[5m]) > 0.05
    for: 2m
    severity: critical
    notify:
      - slack: "#incidents"
      - email: oncall@yourorg.example
```

## Dashboards

Dashboards are defined as JSON (Grafana-compatible) or via the drag-and-drop UI. Import a dashboard:

```bash
POST /v1/dashboards
Content-Type: application/json

{ "title": "API Health", "panels": [...] }
```

## Agent Installation

Install the Helix Agent to ship host metrics and logs:

```bash
# Linux
curl -sSL https://install.helix.example/agent | bash -s -- --token $HELIX_TOKEN

# Docker
docker run -d --name helix-agent \
  -e HELIX_TOKEN=$HELIX_TOKEN \
  -v /var/log:/var/log:ro \
  helix/agent:latest
```

## Retention and Pricing

| Tier | Metrics retention | Log retention | Trace retention |
|------|------------------|---------------|----------------|
| Free | 7 days | 30 days | 3 days |
| Pro | 13 months | 90 days | 30 days |
| Enterprise | Custom | 1 year | 1 year |

Ingestion pricing beyond the free tier: $0.10/GB for logs, $0.30/million samples for metrics.
