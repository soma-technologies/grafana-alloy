# Grafana Alloy Collector for Soma

OpenTelemetry collector using Grafana Alloy to receive OTLP data from Soma services and forward to Grafana Cloud.

This repository is also the consolidated source of truth for SOMA's shared
observability assets:

- `config.alloy` — telemetry collection, processing, and export
- `grafana/dashboards/` — authoritative generators and generated dashboard JSON
- `grafana/alerts/` — Grafana alert definitions
- `grafana/registry.json` — the complete dashboard registry
- `grafana/DASHBOARDS.md` and `grafana/METRICS.md` — generated live inventories

Keep application metric/log/span emission next to the application code. Keep
collector configuration, dashboards, alerts, and shared observability runbooks
here—not in an application repository and not only in the Grafana UI.

The active stabilization baseline and consulting backlog live in
[`OBSERVABILITY_ROADMAP.md`](OBSERVABILITY_ROADMAP.md).

## Configuration

- `Dockerfile`: Extends `grafana/alloy:latest` with custom config.
- `config.alloy`: Alloy configuration to receive OTLP on ports 4317/4318 and forward to Grafana Cloud.

## Environment Variables

- `GC_OTLP_AUTH`: Grafana Cloud OTLP token (Basic auth).

## Railway Deployment

1. Connect this repo to Railway as a new service.
2. Set `GC_OTLP_AUTH` environment variable.
3. Railway will build and deploy using the Dockerfile.
