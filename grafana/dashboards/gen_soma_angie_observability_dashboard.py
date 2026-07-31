#!/usr/bin/env python3
"""Generate SOMA's Angie observability dashboard.

The dashboard separates terminal callback proxies from storage operations. Its
storage tab is also the release console for the shared storage gateway: backend
and Angie keep their existing metric families, while the dashboard normalizes
them into one bounded runtime dimension for direct-v1 versus gateway-v2 review.
"""

import json

PROM = {"type": "prometheus", "uid": "grafanacloud-prom"}
LOKI = {"type": "loki", "uid": "grafanacloud-logs"}
TEMPO = {"type": "tempo", "uid": "grafanacloud-traces"}

UNKNOWN = "Unknown — not measured"
NEUTRAL = [{"color": "text"}]
ERROR_STEPS = [
    {"color": "text"},
    {"color": "green", "value": 0},
    {"color": "orange", "value": 1},
    {"color": "red", "value": 5},
]
COUNT_STEPS = [
    {"color": "text"},
    {"color": "green", "value": 0},
    {"color": "orange", "value": 1},
    {"color": "red", "value": 10},
]
SUCCESS_STEPS = [
    {"color": "text"},
    {"color": "red", "value": 0},
    {"color": "orange", "value": 90},
    {"color": "green", "value": 99},
]

CALLBACK_LOGS = (
    '{service_name=~"soma-.+"} | json '
    '| event="claude_session_callback_processed"'
)
ANGIE_SPANS = 'span_name=~"claude_session\\\\.(job|callback)\\\\.process"'

_panel_id = 0


def next_id():
    global _panel_id
    _panel_id += 1
    return _panel_id


def target(expr=None, *, datasource=PROM, legend=None, instant=False, **extra):
    result = {"datasource": datasource, "refId": "A", **extra}
    if expr is not None:
        result.update({"editorMode": "code", "expr": expr})
    if instant:
        result.update({"instant": True, "format": "table", "range": False})
    elif datasource == PROM:
        result["range"] = True
    if legend:
        result["legendFormat"] = legend
    return result


def panel(kind, title, x, y, width, height, targets=None, *, datasource=PROM, description=""):
    return {
        "id": next_id(),
        "type": kind,
        "title": title,
        "datasource": datasource,
        "gridPos": {"x": x, "y": y, "w": width, "h": height},
        "targets": targets or [],
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {},
        "description": description,
    }


def stat(
    title,
    x,
    expr,
    description,
    *,
    y=0,
    datasource=PROM,
    unit="short",
    decimals=1,
    thresholds=None,
):
    result = panel(
        "stat",
        title,
        x,
        y,
        6,
        5,
        [target(expr, datasource=datasource, instant=True, queryType="instant")],
        datasource=datasource,
        description=description,
    )
    result["options"] = {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "textMode": "auto",
        "colorMode": "background",
        "graphMode": "area",
    }
    result["fieldConfig"]["defaults"] = {
        "unit": unit,
        "decimals": decimals,
        "noValue": UNKNOWN,
        "thresholds": {"mode": "absolute", "steps": thresholds or NEUTRAL},
    }
    return result


def gauge(title, x, expr, description, *, y=5, datasource=PROM, thresholds):
    result = panel(
        "gauge",
        title,
        x,
        y,
        12,
        8,
        [target(expr, datasource=datasource, instant=True, queryType="instant")],
        datasource=datasource,
        description=description,
    )
    result["options"] = {
        "orientation": "auto",
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "showThresholdLabels": False,
        "showThresholdMarkers": True,
    }
    result["fieldConfig"]["defaults"] = {
        "unit": "percent",
        "decimals": 1,
        "min": 0,
        "max": 100,
        "noValue": UNKNOWN,
        "thresholds": {"mode": "absolute", "steps": thresholds},
    }
    return result


def timeseries(
    title,
    x,
    y,
    expr,
    legend,
    description,
    unit,
    *,
    datasource=PROM,
    draw_style="line",
    stack=False,
    percent=False,
):
    result = panel(
        "timeseries",
        title,
        x,
        y,
        12,
        8,
        [target(expr, datasource=datasource, legend=legend, queryType="range")],
        datasource=datasource,
        description=description,
    )
    defaults = {
        "unit": unit,
        "noValue": UNKNOWN,
        "custom": {
            "drawStyle": draw_style,
            "fillOpacity": 45 if draw_style == "bars" else 12,
            "lineWidth": 2,
            "showPoints": "never",
            "spanNulls": True,
            "stacking": {"group": "A", "mode": "normal" if stack else "none"},
            "thresholdsStyle": {"mode": "line" if percent else "off"},
        },
    }
    if percent:
        defaults.update(
            {
                "min": 0,
                "max": 100,
                "thresholds": {"mode": "absolute", "steps": ERROR_STEPS},
            }
        )
    result["fieldConfig"]["defaults"] = defaults
    result["options"] = {
        "legend": {
            "calcs": ["lastNotNull", "max"],
            "displayMode": "table",
            "placement": "bottom",
            "showLegend": True,
        },
        "tooltip": {"mode": "multi", "sort": "desc"},
    }
    return result


def text_panel(title, y, markdown):
    result = panel("text", title, 0, y, 24, 7)
    result["options"] = {"mode": "markdown", "content": markdown}
    return result


def logs_panel(title, y, expr, description, *, x=0, width=24):
    result = panel(
        "logs",
        title,
        x,
        y,
        width,
        11,
        [target(expr, datasource=LOKI, direction="backward", queryType="range")],
        datasource=LOKI,
        description=description,
    )
    result["options"] = {
        "dedupStrategy": "none",
        "enableInfiniteScrolling": False,
        "enableLogDetails": True,
        "prettifyLogMessage": False,
        "showCommonLabels": False,
        "showLabels": False,
        "showTime": True,
        "sortOrder": "Descending",
        "wrapLogMessage": True,
    }
    return result


def with_runtime(expr, runtime):
    """Add a bounded runtime label without changing the application's schema."""
    return (
        f'label_replace(({expr}), "runtime", "{runtime}", '
        '"runtime", "^$")'
    )


def storage_union(backend_expr, angie_expr):
    """Combine the backend and Angie storage families for dashboard queries."""
    return (
        f"({with_runtime(backend_expr, 'backend')}) or "
        f"({with_runtime(angie_expr, 'angie')})"
    )


def gateway_share(metric):
    observed = f'sum(rate({metric}{{instrumentation=~"direct_v1|gateway_v2"}}[15m]))'
    gateway = f'sum(rate({metric}{{instrumentation="gateway_v2"}}[15m]))'
    return (
        f"100 * (({gateway}) or ({observed}) * 0) "
        f"/ clamp_min(({observed}), 1e-9)"
    )


def traces_panel():
    result = panel(
        "table",
        "Failed Angie workflow traces",
        12,
        0,
        12,
        10,
        [
            target(
                datasource=TEMPO,
                limit=50,
                query='{ name =~ "claude_session\\\\.(job|callback)\\\\.process" '
                '&& status = error }',
                queryType="traceql",
                tableType="traces",
            )
        ],
        datasource=TEMPO,
        description="Failed callback-worker spans. Open a row to inspect the full trace.",
    )
    result["options"] = {"cellHeight": "sm", "showHeader": True}
    return result


health = [
    stat(
        "Completed terminal callbacks",
        0,
        f'sum(count_over_time({CALLBACK_LOGS} | status="completed" [$__range]))',
        "Completed Angie callback records in the selected range. This is the closest existing "
        "execution-outcome proxy, but it does not prove every downstream business side effect.",
        datasource=LOKI,
        decimals=0,
    ),
    stat(
        "Failed terminal callbacks",
        6,
        f'sum(count_over_time({CALLBACK_LOGS} | status="failed" [$__range]))',
        "Callbacks whose Angie session status was failed in the selected range.",
        datasource=LOKI,
        decimals=0,
        thresholds=COUNT_STEPS,
    ),
    stat(
        "Rate-limited callbacks",
        12,
        f'sum(count_over_time({CALLBACK_LOGS} | status="rate_limited" [$__range]))',
        "Terminal callbacks reporting rate_limited. This is session status, not HTTP 429 count.",
        datasource=LOKI,
        decimals=0,
        thresholds=COUNT_STEPS,
    ),
    stat(
        "Master session failures",
        18,
        'sum(count_over_time({service_name=~"soma-.+"} | json '
        '| event="master_session_failed" [$__range]))',
        "Master-workflow failures observed in the selected range.",
        datasource=LOKI,
        decimals=0,
        thresholds=COUNT_STEPS,
    ),
    gauge(
        "Terminal callback completion ratio",
        0,
        f'100 * sum(count_over_time({CALLBACK_LOGS} | status="completed" [$__range])) '
        f'/ sum(count_over_time({CALLBACK_LOGS} [$__range]))',
        "Completed terminal callbacks divided by completed, failed and rate-limited callbacks. "
        "This is an execution proxy, not an end-to-end business SLI.",
        datasource=LOKI,
        thresholds=SUCCESS_STEPS,
    ),
    gauge(
        "Non-completed terminal callback ratio",
        12,
        f'100 * sum(count_over_time({CALLBACK_LOGS} | status=~"failed|rate_limited" '
        f'[$__range])) / sum(count_over_time({CALLBACK_LOGS} [$__range]))',
        "Failed plus rate-limited terminal callbacks as a share of observed terminal callbacks.",
        datasource=LOKI,
        thresholds=ERROR_STEPS,
    ),
    text_panel(
        "How to read Angie health",
        13,
        "**Callback status is the best existing terminal execution proxy, not a formal business "
        "SLI.** Callback processing can succeed even when a later orchestrator side effect logs "
        "an error. Storage attempts and transcript outcomes are deliberately separated on the "
        "Angie storage tab. Missing telemetry renders as **Unknown**, never healthy green.",
    ),
]

sessions = [
    timeseries(
        "Claude callback requests",
        0,
        0,
        'sum by (outcome, status_class) (rate(soma_webhook_requests_total{source="claude",'
        'route="/claude/session/callback"}[$__rate_interval]))',
        "{{outcome}} · {{status_class}}",
        "Callback HTTP acknowledgements by outcome and status class.",
        "reqps",
        stack=True,
    ),
    timeseries(
        "Callback worker outcomes",
        12,
        0,
        'sum by (outcome) (rate(soma_webhook_processing_total{source="claude",'
        'operation="session_callback"}[$__rate_interval]))',
        "{{outcome}}",
        "Callback-job processing outcomes. These are worker attempts, not Angie business results.",
        "ops",
        stack=True,
    ),
    timeseries(
        "Angie workflow span rate",
        0,
        8,
        f"sum by (span_name, status_code) (rate(traces_spanmetrics_calls_total{{{ANGIE_SPANS}}}"
        "[$__rate_interval]))",
        "{{span_name}} · {{status_code}}",
        "Callback and job processing span rate. Job retries are additional attempts.",
        "ops",
        stack=True,
    ),
    timeseries(
        "Angie workflow p95 latency",
        12,
        8,
        "histogram_quantile(0.95, sum by (le, span_name) "
        f"(rate(traces_spanmetrics_duration_milliseconds_bucket{{{ANGIE_SPANS}}}"
        "[$__rate_interval])))",
        "{{span_name}}",
        "P95 callback and job processing-span duration.",
        "ms",
    ),
    timeseries(
        "Terminal callback outcomes",
        0,
        16,
        f"sum by (status) (count_over_time({CALLBACK_LOGS} [5m]))",
        "{{status}}",
        "Terminal callback records in each rolling five-minute window.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
    timeseries(
        "Master workflow activity",
        12,
        16,
        'sum by (event) (count_over_time({service_name=~"soma-.+"} | json '
        '| event=~"master_(callback_observed|session_failed|slack_dispatched|'
        'slack_dispatch_queued_after_failure)" [5m]))',
        "{{event}}",
        "Master dispatch, completion-proxy and failure events.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
]

storage_attempt_rate = storage_union(
    "rate(soma_storage_operations_total[$__rate_interval])",
    "rate(angie_storage_operations_total[$__rate_interval])",
)
storage_error_rate = storage_union(
    'rate(soma_storage_operations_total{outcome="error"}[$__rate_interval])',
    'rate(angie_storage_operations_total{outcome="error"}[$__rate_interval])',
)
gateway_error_rate_5m = storage_union(
    'rate(soma_storage_operations_total{instrumentation="gateway_v2",outcome="error"}[5m])',
    'rate(angie_storage_operations_total{instrumentation="gateway_v2",outcome="error"}[5m])',
)
gateway_attempt_rate_5m = storage_union(
    'rate(soma_storage_operations_total{instrumentation="gateway_v2"}[5m])',
    'rate(angie_storage_operations_total{instrumentation="gateway_v2"}[5m])',
)
blocked_error_rate_5m = storage_union(
    'rate(soma_storage_operations_total{instrumentation="gateway_v2",outcome="error",'
    'error_class=~"forbidden|protocol"}[5m])',
    'rate(angie_storage_operations_total{instrumentation="gateway_v2",outcome="error",'
    'error_class=~"forbidden|protocol"}[5m])',
)
gateway_retry_rate_5m = storage_union(
    'rate(soma_storage_events_total{instrumentation="gateway_v2",event="retry"}[5m])',
    'rate(angie_storage_semantic_events_total{instrumentation="gateway_v2",event="retry"}[5m])',
)
storage_latency_p95 = storage_union(
    "histogram_quantile(0.95, sum by (le, provider, instrumentation) "
    "(rate(soma_storage_duration_milliseconds_bucket[$__rate_interval])))",
    "1000 * histogram_quantile(0.95, sum by (le, provider, instrumentation) "
    "(rate(angie_storage_operation_duration_seconds_bucket[$__rate_interval])))",
)
storage_semantic_rate = storage_union(
    "rate(soma_storage_events_total[$__rate_interval])",
    "rate(angie_storage_semantic_events_total[$__rate_interval])",
)
storage_bytes_rate = storage_union(
    "rate(soma_storage_transfer_bytes_total[$__rate_interval])",
    "rate(angie_storage_bytes_total[$__rate_interval])",
)

storage = [
    text_panel(
        "Storage gateway rollout guide",
        0,
        "**`direct_v1` and `gateway_v2` identify instrumentation paths, not different metric "
        "families.** Compare the same runtime, provider, workflow, and operation. Every observed "
        "backend provider call or Angie logical action must appear under exactly one "
        "instrumentation path; do not compare absolute volume across runtimes. Backend rollout "
        "is `off` → `object_store` → `all`; enable "
        "Angie only after backend is stable. Roll back the relevant flag if forbidden/protocol "
        "failures appear, the gateway error ratio exceeds the larger of baseline +0.5 pp or "
        "1.5× baseline, or P95 exceeds the larger of baseline +20% or +100 ms. Soak the first "
        "backend slice for 2 hours and 100 operations, then each full rollout for 24 hours.",
    ),
    stat(
        "Gateway failures / min",
        0,
        f"(sum({gateway_error_rate_5m}) or sum({gateway_attempt_rate_5m}) * 0) * 60",
        "Failed gateway-v2 operations. Backend counts provider calls; Angie counts logical "
        "actions and does not expand curl's internal retries. This is not a unique-workflow "
        "failure count.",
        y=7,
        unit="opm",
        thresholds=COUNT_STEPS,
    ),
    stat(
        "Blocked classes / min",
        6,
        f"(sum({blocked_error_rate_5m}) or sum({gateway_attempt_rate_5m}) * 0) * 60",
        "Gateway-v2 forbidden and protocol failures. Any nonzero value blocks the rollout.",
        y=7,
        unit="opm",
        thresholds=COUNT_STEPS,
    ),
    stat(
        "Gateway retries / min",
        12,
        f"(sum({gateway_retry_rate_5m}) or sum({gateway_attempt_rate_5m}) * 0) * 60",
        "Gateway-v2 retry events across both runtimes. Compare with failures to detect retry "
        "amplification.",
        y=7,
        unit="opm",
        thresholds=COUNT_STEPS,
    ),
    stat(
        "Angie observer drops / min",
        18,
        "(sum(rate(angie_storage_observability_dropped_events_total[5m])) or "
        "sum(rate(angie_storage_operations_total[5m])) * 0) * 60",
        "Storage observations the fail-open Angie datagram producer could not deliver. Missing "
        "telemetry is a rollout blocker, not a healthy zero.",
        y=7,
        unit="opm",
        thresholds=COUNT_STEPS,
    ),
    gauge(
        "Backend gateway-v2 traffic share",
        0,
        gateway_share("soma_storage_operations_total"),
        "Share of recently observed backend provider calls emitted through gateway-v2. This is "
        "rollout progress, not a health score, so it is deliberately uncoloured.",
        y=12,
        thresholds=NEUTRAL,
    ),
    gauge(
        "Angie gateway-v2 traffic share",
        12,
        gateway_share("angie_storage_operations_total"),
        "Share of recently observed Angie logical actions emitted through gateway-v2. This is "
        "rollout progress, not a health score, so it is deliberately uncoloured.",
        y=12,
        thresholds=NEUTRAL,
    ),
    timeseries(
        "Storage operations by runtime and instrumentation",
        0,
        20,
        "sum by (runtime, provider, instrumentation, workflow, operation, outcome) "
        f"({storage_attempt_rate})",
        "{{runtime}} · {{provider}} · {{instrumentation}} · {{workflow}} · {{operation}} · "
        "{{outcome}}",
        "Backend series count provider calls; Angie series count logical actions. Each observed "
        "operation must appear under exactly one instrumentation path. Native-shell curl retries "
        "remain inside one Angie action.",
        "ops",
        stack=True,
    ),
    timeseries(
        "Attempt error ratio: direct-v1 vs gateway-v2",
        12,
        20,
        "100 * ((sum by (runtime, provider, instrumentation) "
        f"({storage_error_rate})) or (sum by (runtime, provider, instrumentation) "
        f"({storage_attempt_rate}) * 0)) / clamp_min(sum by (runtime, provider, instrumentation) "
        f"({storage_attempt_rate}), 1e-9)",
        "{{runtime}} · {{provider}} · {{instrumentation}}",
        "Within-runtime operation error ratio: backend provider calls and Angie logical actions. "
        "Compare gateway with direct for the same runtime, provider, workflow, and operation; do "
        "not compare the two runtimes as if they have identical counting semantics.",
        "percent",
        percent=True,
    ),
    timeseries(
        "P95 latency: direct-v1 vs gateway-v2",
        0,
        28,
        storage_latency_p95,
        "{{runtime}} · {{provider}} · {{instrumentation}}",
        "Backend provider-call and Angie logical-action P95 normalized to milliseconds. Fast "
        "failures can improve this value, so review it beside the error ratio.",
        "ms",
    ),
    timeseries(
        "Storage failures by error class",
        12,
        28,
        "sum by (runtime, provider, instrumentation, error_class) "
        f"({storage_error_rate})",
        "{{runtime}} · {{provider}} · {{instrumentation}} · {{error_class}}",
        "Failed operations grouped only by bounded error class. Forbidden and protocol are rollout "
        "blockers; use the logs below for safe request-level diagnostics.",
        "ops",
        draw_style="bars",
        stack=True,
    ),
    timeseries(
        "Retries, fallbacks and conflicts",
        0,
        36,
        "sum by (runtime, provider, instrumentation, event) "
        f"({storage_semantic_rate})",
        "{{runtime}} · {{provider}} · {{instrumentation}} · {{event}}",
        "Explicit bounded semantic events from each storage boundary. Angie native-shell curl "
        "retries are not expanded into individual events. Compare explicit retry rate with "
        "failure rate to identify amplification.",
        "ops",
        stack=True,
    ),
    timeseries(
        "Attempted storage bytes",
        12,
        36,
        "sum by (runtime, provider, instrumentation, outcome) "
        f"({storage_bytes_rate})",
        "{{runtime}} · {{provider}} · {{instrumentation}} · {{outcome}}",
        "Application bytes supplied to storage calls per second. Error bytes were attempted, not "
        "confirmed stored.",
        "Bps",
        stack=True,
    ),
    logs_panel(
        "Recent backend storage failures",
        44,
        '{service_name=~"soma-.+"} | json | event="storage_operation_failed"',
        "Backend failures with provider, instrumentation, workflow, operation, error class, "
        "bounded upstream diagnostics, and trace context. No paths or payloads are recorded.",
        width=12,
    ),
    logs_panel(
        "Recent Angie storage failures",
        44,
        '{job="angie_storage"} | json | body="angie.storage_operation" | outcome="error"',
        "Angie failures with provider, instrumentation, workflow, operation, error class, and "
        "opaque correlation references. Expand a line for safe diagnostics.",
        x=12,
        width=12,
    ),
    timeseries(
        "Terminal transcript archive outcomes",
        0,
        55,
        'sum by (event) (count_over_time({service_name=~"soma-.+"} | json '
        '| event=~"session_transcript_(archived|archive_timeout|archive_upload_failed|archive_shed)" '
        '[5m]))',
        "{{event}}",
        "Session-level archive outcomes and terminal failures. Unlike provider metrics, one log "
        "event represents one recorder outcome.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
    timeseries(
        "Backend storage failures by upstream status",
        12,
        55,
        'sum by (upstream_status, instrumentation) (count_over_time('
        '{service_name=~"soma-.+"} | json | event="storage_operation_failed" [5m]))',
        "{{upstream_status}} · {{instrumentation}}",
        "Backend failure logs by safe upstream status and instrumentation path. Empty status means "
        "the failure did not include an HTTP response.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
]

summary_pipeline = [
    stat(
        "Summary status lookups",
        0,
        "sum(increase(soma_angie_status_lookup_operations_total[$__range]))",
        "Automatic summary status lookups in the selected range.",
        decimals=0,
    ),
    stat(
        "Failed status lookups",
        6,
        'sum(increase(soma_angie_status_lookup_operations_total{outcome="failed"}'
        '[$__range])) or vector(0)',
        "Automatic status lookup failures. A known zero is derived from the reporting metric.",
        decimals=0,
        thresholds=COUNT_STEPS,
    ),
    stat(
        "Rows read / lookup",
        12,
        "sum(rate(soma_angie_status_lookup_rows_total[15m])) / clamp_min("
        "sum(rate(soma_angie_status_lookup_operations_total[15m])), 1e-9)",
        "Average database rows read per automatic lookup over 15 minutes.",
        decimals=1,
    ),
    stat(
        "Lookup p95",
        18,
        "histogram_quantile(0.95, sum by (le) "
        "(rate(soma_angie_status_lookup_duration_milliseconds_bucket[15m])))",
        "P95 automatic summary-status lookup latency.",
        unit="ms",
        decimals=0,
    ),
    timeseries(
        "Status lookup outcomes",
        0,
        5,
        "sum by (strategy, outcome) "
        "(rate(soma_angie_status_lookup_operations_total[$__rate_interval]))",
        "{{strategy}} · {{outcome}}",
        "Automatic summary status lookup attempts by bounded strategy and outcome.",
        "ops",
        stack=True,
    ),
    timeseries(
        "Summary rows read rate",
        12,
        5,
        "sum by (strategy, outcome) "
        "(rate(soma_angie_status_lookup_rows_total[$__rate_interval]))",
        "{{strategy}} · {{outcome}}",
        "Database rows read by automatic summary lookups per second.",
        "ops",
    ),
    timeseries(
        "Summary lookup p95 by outcome",
        0,
        13,
        "histogram_quantile(0.95, sum by (le, strategy, outcome) "
        "(rate(soma_angie_status_lookup_duration_milliseconds_bucket"
        "[$__rate_interval])))",
        "{{strategy}} · {{outcome}}",
        "P95 summary-status lookup latency split by strategy and outcome.",
        "ms",
    ),
    text_panel(
        "What summary metrics prove",
        21,
        "These metrics describe the database lookup used during automatic summary extraction. "
        "They do **not** prove that the Angie session completed, that its transcript archived, "
        "or that a summary was ultimately delivered.",
    ),
]

failures = [
    logs_panel(
        "Recent Angie warnings and errors",
        0,
        '{service_name=~"soma-.+"} | json '
        '| event=~"(claude_session|master|angie|session_).*" '
        '| level=~"warning|error"',
        "Structured Angie warnings and errors across web and worker runtimes.",
        width=12,
    ),
    traces_panel(),
    timeseries(
        "Angie workflow span errors",
        0,
        11,
        "sum by (span_name, service_name) (rate(traces_spanmetrics_calls_total{"
        f'{ANGIE_SPANS},status_code="STATUS_CODE_ERROR"}}[$__rate_interval]))',
        "{{span_name}} · {{service_name}}",
        "Failed callback/job processing spans. This is diagnostic and attempt-level.",
        "ops",
        stack=True,
    ),
    timeseries(
        "High-value Angie failure events",
        12,
        11,
        'sum by (event) (count_over_time({service_name=~"soma-.+"} | json '
        '| event=~"master_session_failed|interaction_match_session_failed|'
        'appetite_run_summary_failed|angie_orchestrator_error|session_transcript_archive_upload_failed" '
        '[5m]))',
        "{{event}}",
        "Workflow and archival failures in rolling five-minute windows.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
]


def data_query(raw_target, default_datasource):
    datasource = raw_target.get("datasource", default_datasource)
    query_spec = {
        key: value for key, value in raw_target.items() if key not in {"datasource", "refId"}
    }
    return {
        "kind": "PanelQuery",
        "spec": {
            "hidden": False,
            "query": {
                "datasource": {"name": datasource["uid"]},
                "group": datasource["type"],
                "kind": "DataQuery",
                "spec": query_spec,
                "version": "v0",
            },
            "refId": raw_target.get("refId", "A"),
        },
    }


def transformation(raw_transformation):
    return {
        "group": raw_transformation["id"],
        "kind": "Transformation",
        "spec": {"options": raw_transformation.get("options", {})},
    }


def panel_element(raw_panel):
    datasource = raw_panel.get("datasource", PROM)
    return {
        "kind": "Panel",
        "spec": {
            "data": {
                "kind": "QueryGroup",
                "spec": {
                    "queries": [
                        data_query(item, datasource) for item in raw_panel.get("targets", [])
                    ],
                    "queryOptions": {},
                    "transformations": [
                        transformation(item)
                        for item in raw_panel.get("transformations", [])
                    ],
                },
            },
            "description": raw_panel.get("description", ""),
            "id": raw_panel["id"],
            "links": [],
            "title": raw_panel["title"],
            "vizConfig": {
                "group": raw_panel["type"],
                "kind": "VizConfig",
                "spec": {
                    "fieldConfig": raw_panel.get(
                        "fieldConfig", {"defaults": {}, "overrides": []}
                    ),
                    "options": raw_panel.get("options", {}),
                },
                "version": "",
            },
        },
    }


def grid_items(group):
    return [
        {
            "kind": "GridLayoutItem",
            "spec": {
                "element": {"kind": "ElementReference", "name": f"panel-{item['id']}"},
                "height": item["gridPos"]["h"],
                "width": item["gridPos"]["w"],
                "x": item["gridPos"]["x"],
                "y": item["gridPos"]["y"],
            },
        }
        for item in group
    ]


tabs_spec = [
    ("Health", health),
    ("Sessions & callbacks", sessions),
    ("Storage rollout", storage),
    ("Summary pipeline", summary_pipeline),
    ("Failures & traces", failures),
]

all_panels = [item for _, group in tabs_spec for item in group]
elements = {f"panel-{item['id']}": panel_element(item) for item in all_panels}
tabs = [
    {
        "kind": "TabsLayoutTab",
        "spec": {
            "title": title,
            "layout": {"kind": "GridLayout", "spec": {"items": grid_items(group)}},
        },
    }
    for title, group in tabs_spec
]


dashboard = {
    "apiVersion": "dashboard.grafana.app/v2",
    "kind": "Dashboard",
    "metadata": {
        "annotations": {
            "grafana.app/folder": "eftnndsaxtvy8a",
            "grafana.app/message": "Manage SOMA Angie observability dashboard as code",
        },
        "name": "soma-angie-observability",
    },
    "spec": {
        "annotations": [],
        "cursorSync": "Off",
        "description": "Terminal callback health, sessions, storage-gateway rollout, summary "
        "work, failures, and traces for SOMA's Angie workflows.",
        "editable": True,
        "elements": elements,
        "layout": {"kind": "TabsLayout", "spec": {"tabs": tabs}},
        "links": [
            {
                "title": "Storage diagnostics — full page",
                "type": "link",
                "url": "/d/soma-storage-observability/soma-storage-observability?"
                "var-workflow=session_archive&var-logical_area=session_transcripts",
                "targetBlank": False,
                "includeVars": False,
                "keepTime": True,
                "asDropdown": False,
                "icon": "external link",
                "tags": [],
                "tooltip": "Open the full storage diagnostics dashboard",
            },
            {
                "title": "Workflow health",
                "type": "link",
                "url": "/d/soma-workflow-health/soma-workflow-health",
                "targetBlank": False,
                "includeVars": False,
                "keepTime": True,
                "asDropdown": False,
                "icon": "external link",
                "tags": [],
                "tooltip": "Open all SOMA workflow health",
            },
            {
                "title": "Angie Mac host",
                "type": "link",
                "url": "/d/darwin-overview",
                "targetBlank": False,
                "includeVars": False,
                "keepTime": True,
                "asDropdown": False,
                "icon": "external link",
                "tags": [],
                "tooltip": "Open Angie Mac host resource health",
            },
        ],
        "liveNow": False,
        "preload": False,
        "tags": ["soma", "engineering", "angie", "storage", "observability"],
        "timeSettings": {
            "autoRefresh": "1m",
            "autoRefreshIntervals": ["30s", "1m", "5m", "15m", "30m", "1h"],
            "fiscalYearStartMonth": 0,
            "from": "now-24h",
            "hideTimepicker": False,
            "timezone": "America/New_York",
            "to": "now",
        },
        "title": "SOMA Angie Observability",
        "variables": [],
    },
}

if __name__ == "__main__":
    print(json.dumps(dashboard, indent=2))
