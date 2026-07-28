# Grafana Alloy Collector for Soma

OpenTelemetry collector using Grafana Alloy to receive OTLP data from Soma services and forward to Grafana Cloud.

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
