# Soma observability stabilization plan

Status: active consulting workstream  
Started: 2026-07-29  
Goal: reach a stable, measurable operating point quickly, then improve from evidence instead of intuition.

## Current production baseline

This is the first 24-hour snapshot captured on 2026-07-29. Prometheus `increase()` values are approximate because counters began partway through the window.

| Signal | Observation |
|---|---:|
| Web requests | ~145k / 24h |
| HTTP 200 | ~140,762 |
| HTTP 202 | ~3,884 |
| HTTP 400 | ~134 |
| HTTP 404 | ~119 |
| HTTP 500 | 0 observed |
| Overall HTTP p95 | ~748 ms |
| Highest-volume route | `/slack/events`, ~46k / 24h |
| HTTP metric coverage | `soma-backend-web` only |
| Span-metric coverage | web + callback, ingestion, scheduler, and vendor workers |
| Missing recent service signal | `soma-cron` |
| Dependency graph | active; dependency hostnames resolved |
| Alloy self-monitoring | being added |
| Watchdog alert | not configured |

Zero observed 5xx is not yet an availability SLO. Several endpoints acknowledge work with 200/202 before background processing completes, so business failures can be silent at the HTTP layer.

## Stability milestones

### P0 — make the telemetry trustworthy

- [x] Disable staging telemetry.
- [x] Enable production traces, logs, and metrics for Soma services.
- [x] Generate service-graph and span metrics in Alloy.
- [x] Resolve outbound dependency hostnames from HTTP client spans.
- [x] Point the Soma Metrics dashboard at production services.
- [x] Remove URL query strings from exported spans after extracting the dependency hostname.
- [x] Exclude ASGI `http send`/`http receive` spans from generated span metrics while retaining them in Tempo.
- [x] Bound span-metric cardinality and stop per-replica resource attributes from creating series churn.
- [x] Export Alloy self-metrics.
- [ ] Alert on telemetry/export failures.
- [ ] Confirm `soma-cron` emits telemetry when its next scheduled run executes.

### P0 — webhook and callback flow accounting

Measure ingress by a bounded `source` and route template. Never use raw URLs, record IDs, customer identifiers, or payload values as metric labels.

Initial sources:

- Slack: `/slack/events`, `/slack/interactivity`
- Railway: `/webhooks/railway`
- Bold Penguin: `/webhooks/bold-penguin`
- Benepath: `/webhooks/benepath`
- OpenPhone: `/webhooks/openphone`
- Aircall: `/webhooks/aircall`
- Gmail: `/webhooks/gmail`
- LlamaParse: `/webhooks/llamaparse`
- Tivly: `/webhooks/tivly/leads`, `/webhooks/tivly/leads/test`
- Claude callback: `/claude/session/callback`
- Closing Desk transcript events: `/closing-desk/transcript/event`
- ISC extension events: `/api/isc/quote-event`

Metrics:

- [ ] `soma_webhook_requests_total{source,route,method,status_class}`
- [ ] `soma_webhook_request_bytes_total{source,route,...}` — exact bytes received at the ASGI boundary.
- [ ] `soma_webhook_response_bytes_total{source,route,...}` — exact response bytes returned to the caller.
- [ ] `soma_webhook_duration_milliseconds` — request acknowledgement latency.
- [ ] Dashboard: event rate, data-in rate/total, response-out rate/total, average payload size, status classes, and latency by source.

`response_bytes` means the HTTP acknowledgement returned by Soma. Service-to-dependency traffic is a separate flow and needs HTTP-client request/response byte instrumentation.

### P1 — seven-day operating baseline

- [ ] Preserve seven uninterrupted days of production data before selecting SLO targets.
- [ ] Track daily traffic, 4xx/5xx, p50/p95/p99, dependency failures, and telemetry freshness.
- [ ] Separate ordinary requests, webhooks, callbacks, streaming endpoints, and long-running operations.
- [ ] Exclude `/health` and known idempotent retries from valid-request denominators.
- [ ] Add deployment/version annotations to the dashboard.
- [ ] Treat values at the highest histogram bucket as “at least this slow,” not as exact latency.

### P1 — critical user journeys and outcome metrics

Define an SLI as `good valid events / valid events` for each journey:

1. Slack event received → processed successfully.
2. Lead received → persisted and available.
3. Quote submitted → vendor result recorded.
4. Callback received → state updated.
5. Worker or scheduled job → completed before its freshness deadline.

Add bounded outcome metrics:

- [ ] `soma_events_processed_total{source,outcome}`
- [ ] `soma_jobs_completed_total{worker,outcome}`
- [ ] `soma_job_queue_age_seconds{worker}`
- [ ] `soma_quotes_total{vendor,outcome}`
- [ ] `soma_leads_total{source,outcome}`
- [ ] `soma_callback_processing_seconds{source,outcome}`

Business decisions still required:

- [ ] Value/cost per successful or failed journey.
- [ ] SLO target and measurement window per journey, selected from measured performance.
- [ ] Owner and escalation destination for each journey.
- [ ] Definition of silent/stuck failure for each asynchronous flow.

### P1 — resource saturation and worker health

- [ ] Queue depth and oldest-job age.
- [ ] DB pool used/idle/pending and wait time.
- [ ] Worker concurrency and in-flight jobs.
- [ ] Event-loop lag.
- [ ] Process CPU and memory.
- [ ] External API retries, timeouts, and request/response bytes.

### P2 — alerting and operating process

Start non-paging, then promote only proven alerts:

- [ ] Any sustained 5xx or a bounded absolute failure count for low-volume journeys.
- [ ] Dependency failure ratio and latency regression.
- [ ] No service telemetry for 10–15 minutes.
- [ ] Queue age/freshness breach.
- [ ] Alloy exporter failures or dropped telemetry.
- [ ] Always-firing Watchdog proving the alert pipeline is alive.
- [ ] Multi-window burn-rate alerts after the seven-day baseline and SLO interview.
- [ ] Monthly telemetry cardinality/cost review.
- [ ] Quarterly SLO and ownership review.

## Operating rules

- Page on user-visible symptoms or error-budget burn, not infrastructure causes alone.
- Keep complete diagnostic traces in Tempo; generate low-cardinality metrics from a filtered branch.
- Never put payload content, raw URLs, query strings, customer identifiers, or record IDs in metric labels.
- Validate every dashboard query against live data before publishing it.
- An empty panel must say why it is empty; it must not look like a healthy zero.
- Use RED for services and USE for resources.
