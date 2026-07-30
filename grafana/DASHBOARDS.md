# SOMA dashboards

14 dashboards registered, 14 live in Grafana, 352 panels in total.

Single source of truth: `registry.json`. Regenerate this file with
`python3 grafana/gen_dashboards.py > grafana/DASHBOARDS.md`. Do not hand-edit.

No drift: every live dashboard is registered and every registered dashboard is live.

## Registry

| Dashboard | UID | Status | Audience | Panels | Generator |
|---|---|---|---|---|---|
| SOMA Engineering | `soma-engineering` | managed | engineers | 35 | `gen_soma_engineering_dashboard.py` |
| SOMA Operations | `soma-operations` | managed | operators | 16 | `gen_soma_operations_dashboard.py` |
| SOMA Workflow Health | `soma-workflow-health` | managed | operators | 47 | `gen_soma_workflow_health_dashboard.py` |
| Supabase — Soma (corrected) | `soma-supabase` | keep | engineers | 29 | — |
| Soma APM | `a5b6pg` | archive | none | 5 | — |
| Soma Metrics | `an29kk` | archive | engineers | 22 | — |
| Soma OTel - Local Test Proof | `as5l5v` | archive | none | 1 | — |
| Soma OTel Local Test Proof | `acn297` | archive | none | 2 | — |
| Alert Groups Insights | `63093493-af68-4fdd-89e9-511c24d8352d` | stock | none | 17 | — |
| Incident Insights | `6e19ccfc-2e2e-40d2-9d40-6890618ba164` | stock | none | 20 | — |
| MacOS / logs | `darwin-logs` | stock | engineers | 5 | — |
| MacOS / overview | `darwin-overview` | stock | engineers | 20 | — |
| Metrics endpoint scrape overview | `metricsendpoint-scrape-overview` | stock | engineers | 6 | — |
| Supabase Project | `d402d94e-da48-48e4-ac52-53026b96a000` | stock | engineers | 127 | — |

## Panel types in use

| Type | Count |
|---|---|
| `timeseries` | 181 |
| `stat` | 101 |
| `table` | 24 |
| `text` | 22 |
| `gauge` | 16 |
| `logs` | 3 |
| `nodeGraph` | 2 |
| `bargauge` | 1 |
| `barchart` | 1 |
| `state-timeline` | 1 |

## Same panel title on more than one dashboard

Stock integration boards overlap curated ones by design, so this is not
automatically wrong — but check here before adding a panel.

| Panel | Dashboards |
|---|---|
| 5xx rate | `an29kk`, `soma-engineering` |
| cpu busy | `d402d94e-da48-48e4-ac52-53026b96a000`, `soma-supabase` |
| database size | `d402d94e-da48-48e4-ac52-53026b96a000`, `soma-engineering` |
| how to read this dashboard | `soma-operations`, `soma-workflow-health` |
| integration version | `darwin-logs`, `darwin-overview` |
| load average | `darwin-overview`, `soma-supabase` |
| logs | `acn297`, `darwin-logs` |
| mean time to resolve (mttr) | `63093493-af68-4fdd-89e9-511c24d8352d`, `6e19ccfc-2e2e-40d2-9d40-6890618ba164` |
| network traffic | `d402d94e-da48-48e4-ac52-53026b96a000`, `darwin-overview` |
| request rate | `an29kk`, `soma-engineering` |
| uptime | `d402d94e-da48-48e4-ac52-53026b96a000`, `darwin-overview` |

## Managed in this repo

### SOMA Engineering — `soma-engineering` (35 panels)

HTTP, routes, dependencies, workflow spans, database load, telemetry pipeline.

**Service health**

- `stat` — Request rate
- `stat` — 5xx rate
- `stat` — In-flight requests
- `stat` — Services reporting
- `timeseries` — Request rate by service
- `timeseries` — 5xx rate by service
- `timeseries` — Inbound latency percentiles
**HTTP routes**

- `table` — Routes — volume, latency, 5xx
- `timeseries` — Requests by status class
**Dependencies**

- `table` — Outbound dependency paths — raw span errors, diagnostic only
- `timeseries` — Outbound call latency
- `timeseries` — Outbound calls by status
**Workflow spans**

- `stat` — Workflow spans/min
- `stat` — Span-error outcomes
- `stat` — Distinct stages
- `stat` — Workflow p95
- `timeseries` — Stage throughput
- `timeseries` — Stage latency p95
- `text` — Reading workflow spans
**Database load**

- `stat` — Database size
- `stat` — Growth per day
- `stat` — Replica attached
- `stat` — Replica lag
- `timeseries` — Database size over time
- `timeseries` — Angie summary status lookup — queries and rows per lookup
- `timeseries` — Angie lookup outcomes by strategy
- `timeseries` — Angie lookup latency p95
- `text` — Reading database load
**Telemetry pipeline**

- `stat` — Spans exported
- `stat` — Export failures
- `stat` — Refused spans
- `stat` — Export queue used
- `timeseries` — Collector span pipeline
- `timeseries` — Telemetry freshness by service
- `text` — Why this tab exists

### SOMA Operations — `soma-operations` (16 panels)

Webhook receipt and processing. Single page on purpose: an operator dashboard should hide nothing behind a tab.

**Action queue**

- `stat` — Acknowledged
- `stat` — Ingress exception rate
- `stat` — Processing failures
- `stat` — Processing retries
- `table` — Action queue — ingress
- `table` — Action queue — processing
- `table` — Action queue — no observed traffic
**Sources**

- `table` — Workflow health — observed sources
- `timeseries` — Webhook acknowledgements by source
- `timeseries` — Processing outcomes by source
**Latency and volume**

- `timeseries` — Webhook acknowledgement p95
- `timeseries` — Processing p95
- `timeseries` — Acknowledgement data out
**Dependencies**

- `table` — Raw dependency span errors — diagnostic only
- `nodeGraph` — Production service graph
**How to read**

- `text` — How to read this dashboard

### SOMA Workflow Health — `soma-workflow-health` (47 panels)

One tab per business workflow, overview first. Adding a workflow adds 8 panels automatically.

**All workflows**

- `stat` — Workflow runs
- `stat` — Terminal failures
- `stat` — Failure rate
- `stat` — Workflows reporting
- `table` — Workflow health — observed workflows only
- `timeseries` — Workflow throughput
- `text` — How to read this dashboard
**Ingestion**

- `stat` — Runs
- `stat` — Terminal failures
- `stat` — Failure rate
- `stat` — Last run age
- `timeseries` — Throughput
- `timeseries` — Latency
- `timeseries` — Runs by service instance
- `text` — Drill down
**Claude session**

- `stat` — Runs
- `stat` — Terminal failures
- `stat` — Failure rate
- `stat` — Last run age
- `timeseries` — Throughput
- `timeseries` — Latency
- `timeseries` — Runs by service instance
- `text` — Drill down
**Vendor campaign**

- `stat` — Runs
- `stat` — Terminal failures
- `stat` — Failure rate
- `stat` — Last run age
- `timeseries` — Throughput
- `timeseries` — Latency
- `timeseries` — Runs by service instance
- `text` — Drill down
**Quote (Hiscox)**

- `stat` — Runs
- `stat` — Terminal failures
- `stat` — Failure rate
- `stat` — Last run age
- `timeseries` — Throughput
- `timeseries` — Latency
- `timeseries` — Runs by service instance
- `text` — Drill down
**Slack**

- `stat` — Runs
- `stat` — Terminal failures
- `stat` — Failure rate
- `stat` — Last run age
- `timeseries` — Throughput
- `timeseries` — Latency
- `timeseries` — Runs by service instance
- `text` — Drill down

## Kept as is — live, useful, deliberately not generated here

### Supabase — Soma (corrected) — `soma-supabase` (29 panels)

Curated USE coverage of Postgres and poolers, far better than the 127-panel stock integration board. Decision 2026-07-30: keep as is for now, not generated from this repo. Bring it in only when it next needs changing.

**Overview — real health at a glance**

- `gauge` — RAM pressure (real)
- `gauge` — CPU busy
- `gauge` — Disk used
- `gauge` — Cache hit ratio
- `stat` — Connections
- `stat` — OOM kills (1h)
- `stat` — DB size
- `stat` — Load (1m)
- `stat` — Txn rate
- `stat` — Deadlocks (1h)
- `stat` — Replication lag
- `stat` — WAL size
**Compute — utilisation, saturation, errors**

- `timeseries` — Memory breakdown
- `timeseries` — CPU by mode
- `timeseries` — Disk usage %
- `timeseries` — Disk IO throughput
- `timeseries` — Load average
- `timeseries` — Network throughput
- `timeseries` — Swap used
- `timeseries` — Page faults & swap activity
**Database — Postgres internals**

- `timeseries` — Connections
- `timeseries` — Cache hit ratio %
- `timeseries` — Transactions
- `timeseries` — Tuple activity
- `timeseries` — Deadlocks & temp files
**Connection pooling — Supavisor / PgBouncer**

- `timeseries` — Supavisor connections
- `timeseries` — PgBouncer pools
- `timeseries` — PgBouncer client wait time
- `timeseries` — PostgREST pool

## Archived — kept for reference, not maintained

### Soma APM — `a5b6pg` (5 panels)

Proof of concept, 5 panels. Decision 2026-07-30: keep, archived.

### Soma Metrics — `an29kk` (22 panels)

Superseded by soma-engineering. Its business tiles (Tivly leads, Quotes submitted, Submission flows) render 0 in green, which reads as healthy when the truth is not-measured — so do not use it for business questions. Decision 2026-07-30: keep, archived rather than deleted.

### Soma OTel - Local Test Proof — `as5l5v` (1 panels)

Proof of concept, 1 panel. Decision 2026-07-30: keep, archived.

### Soma OTel Local Test Proof — `acn297` (2 panels)

Proof of concept, 2 panels. Decision 2026-07-30: keep, archived.

## Grafana Cloud stock / integration — leave alone

### Alert Groups Insights — `63093493-af68-4fdd-89e9-511c24d8352d` (17 panels)

Grafana IRM. Renders empty until alerts fire and an incident process exists. Cannot be moved out of the root: Grafana rejects the write with "Cannot save provisioned dashboard".

### Incident Insights — `6e19ccfc-2e2e-40d2-9d40-6890618ba164` (20 panels)

Grafana IRM. Renders empty until alerts fire and an incident process exists. Cannot be moved out of the root: Grafana rejects the write with "Cannot save provisioned dashboard".

### MacOS / logs — `darwin-logs` (5 panels)

Logs from the Angie Mac host.

### MacOS / overview — `darwin-overview` (20 panels)

The Angie Mac host. Its node_* series are macOS volumes, so they do not describe Supabase's disk.

### Metrics endpoint scrape overview — `metricsendpoint-scrape-overview` (6 panels)

Scrape health for the Supabase metrics endpoint.

### Supabase Project — `d402d94e-da48-48e4-ac52-53026b96a000` (127 panels)

Grafana Cloud Supabase integration, 127 panels, mostly generic node_exporter series. soma-supabase covers the same ground with 29 curated panels.

