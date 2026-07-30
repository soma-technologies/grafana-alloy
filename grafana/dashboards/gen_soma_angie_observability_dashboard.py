#!/usr/bin/env python3
"""Generate SOMA's Angie observability dashboard.

The dashboard separates terminal callback proxies from provider attempts. Angie
storage is intentionally first-class because transcript archival can fail while
the underlying session still completes.
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

ARCHIVE = 'workflow="session_archive",logical_area="session_transcripts"'
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
    datasource=PROM,
    unit="short",
    decimals=1,
    thresholds=None,
):
    result = panel(
        "stat",
        title,
        x,
        0,
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


def gauge(title, x, expr, description, *, datasource=PROM, thresholds):
    result = panel(
        "gauge",
        title,
        x,
        5,
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


def logs_panel(title, y, expr, description, *, width=24):
    result = panel(
        "logs",
        title,
        0,
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

storage = [
    stat(
        "Provider attempt error ratio",
        0,
        f"100 * sum(rate(soma_storage_errors_total{{{ARCHIVE}}}[5m])) / "
        f"clamp_min(sum(rate(soma_storage_operations_total{{{ARCHIVE}}}[5m])), 1e-9)",
        "Failed transcript-storage attempts divided by all attempts. Retries count again; this "
        "is not the percentage of sessions whose transcript was lost.",
        unit="percent",
        thresholds=ERROR_STEPS,
    ),
    stat(
        "Failed archive calls / min",
        6,
        f"sum(rate(soma_storage_errors_total{{{ARCHIVE}}}[5m])) * 60",
        "Failed Supabase transcript archive attempts per minute.",
        unit="opm",
        thresholds=COUNT_STEPS,
    ),
    stat(
        "Archive retries / min",
        12,
        f'sum(rate(soma_storage_events_total{{event="retry",{ARCHIVE}}}[5m])) * 60',
        "Retry events per minute. Compare with failures to identify retry amplification.",
        unit="opm",
        thresholds=COUNT_STEPS,
    ),
    stat(
        "Archive provider p95",
        18,
        "histogram_quantile(0.95, sum by (le) "
        f"(rate(soma_storage_duration_milliseconds_bucket{{{ARCHIVE}}}[5m])))",
        "P95 provider-attempt duration. Fast rejections can make this look artificially good.",
        unit="ms",
        decimals=0,
    ),
    gauge(
        "Successful archive attempts",
        0,
        "100 * sum(rate(soma_storage_operations_total{"
        f'{ARCHIVE},outcome="success"}}[5m])) / clamp_min(sum(rate('
        f"soma_storage_operations_total{{{ARCHIVE}}}[5m])), 1e-9)",
        "Successful provider attempts as a share of attempts. Retries and snapshots count again.",
        thresholds=SUCCESS_STEPS,
    ),
    gauge(
        "Failed archive attempts",
        12,
        "100 * sum(rate(soma_storage_operations_total{"
        f'{ARCHIVE},outcome="error"}}[5m])) / clamp_min(sum(rate('
        f"soma_storage_operations_total{{{ARCHIVE}}}[5m])), 1e-9)",
        "Failed provider attempts as a share of attempts, not unique sessions.",
        thresholds=ERROR_STEPS,
    ),
    timeseries(
        "Archive provider attempts",
        0,
        13,
        f"sum by (operation, outcome) (rate(soma_storage_operations_total{{{ARCHIVE}}}"
        "[$__rate_interval]))",
        "{{operation}} · {{outcome}}",
        "Supabase transcript archive attempts by operation and outcome.",
        "ops",
        stack=True,
    ),
    timeseries(
        "Terminal transcript archive outcomes",
        12,
        13,
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
        "Archive provider p95 by outcome",
        0,
        21,
        "histogram_quantile(0.95, sum by (le, outcome) "
        f"(rate(soma_storage_duration_milliseconds_bucket{{{ARCHIVE}}}"
        "[$__rate_interval])))",
        "{{outcome}}",
        "P95 provider-attempt latency split by success and error.",
        "ms",
    ),
    timeseries(
        "Attempted transcript bytes",
        12,
        21,
        f"sum by (outcome) (rate(soma_storage_transfer_bytes_total{{{ARCHIVE}}}"
        "[$__rate_interval]))",
        "{{outcome}}",
        "Transcript bytes supplied to provider calls. Error bytes were not confirmed stored.",
        "Bps",
        stack=True,
    ),
    timeseries(
        "Archive failures by upstream status",
        0,
        29,
        'sum by (upstream_status, service_name) (count_over_time('
        '{service_name=~"soma-.+"} | json | event="storage_operation_failed" '
        '| workflow="session_archive" | logical_area="session_transcripts" [5m]))',
        "{{upstream_status}} · {{service_name}}",
        "Safe failure diagnostics by upstream status and runtime.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
    timeseries(
        "Archive retry and guard events",
        12,
        29,
        f"sum by (event) (rate(soma_storage_events_total{{{ARCHIVE}}}[$__rate_interval]))",
        "{{event}}",
        "Storage retry events. Circuit-breaker transitions appear in the logs below after the "
        "emergency guard is deployed.",
        "ops",
        stack=True,
    ),
    logs_panel(
        "Recent Angie storage and breaker logs",
        37,
        '{service_name=~"soma-.+"} | json '
        '| event=~"storage_operation_failed|session_transcript_.*|session_archive_breaker_.*|'
        'session_archive_recovery_complete"',
        "Transcript archive failures, terminal outcomes and circuit-breaker transitions. "
        "Expand a line for safe upstream status and request identifiers.",
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
    ("Angie storage", storage),
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
        "description": "Terminal callback health, sessions, storage, summary work, failures, "
        "and traces for SOMA's Angie workflows.",
        "editable": True,
        "elements": elements,
        "layout": {"kind": "TabsLayout", "spec": {"tabs": tabs}},
        "links": [
            {
                "title": "Angie storage — full page",
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
