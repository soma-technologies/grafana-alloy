#!/usr/bin/env python3
"""Generate SOMA's storage diagnostics dashboard.

The first tab answers whether storage provider calls are healthy. The remaining
tabs separate traffic/latency from failure logs and traces. Counts are provider
attempts, not unique business workflows; retries therefore increase both the
operation count and the error ratio denominator.
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

SELECTOR = 'workflow=~"$workflow",logical_area=~"$logical_area"'

_panel_id = 0


def next_id():
    global _panel_id
    _panel_id += 1
    return _panel_id


def target(expr=None, *, datasource=PROM, legend=None, instant=False, **extra):
    result = {
        "datasource": datasource,
        "refId": "A",
        **extra,
    }
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


def stat(title, x, expr, description, *, unit="short", decimals=1, thresholds=None):
    result = panel(
        "stat",
        title,
        x,
        0,
        6,
        5,
        [target(expr, instant=True)],
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


def gauge(title, x, expr, description, *, thresholds):
    result = panel(
        "gauge",
        title,
        x,
        5,
        12,
        8,
        [target(expr, instant=True)],
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


def logs_panel():
    result = panel(
        "logs",
        "Storage failure logs",
        0,
        0,
        12,
        10,
        [
            target(
                '{service_name=~"soma-.+"} | json '
                '| event="storage_operation_failed" '
                '| workflow=~"$workflow" | logical_area=~"$logical_area"',
                datasource=LOKI,
                direction="backward",
                queryType="range",
            )
        ],
        datasource=LOKI,
        description="Payload-blind provider failures with safe upstream diagnostics. Expand a "
        "line and follow its trace ID when one is present.",
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
        "Failed storage traces",
        12,
        0,
        12,
        10,
        [
            target(
                datasource=TEMPO,
                limit=50,
                query='{ name =~ "storage\\\\..+" '
                '&& span.storage.provider = "supabase" '
                '&& span.storage.workflow =~ "$workflow" '
                '&& span.storage.logical_area =~ "$logical_area" '
                '&& status = error }',
                queryType="traceql",
                tableType="traces",
            )
        ],
        datasource=TEMPO,
        description="Failed storage client spans. Open a row to inspect the complete request "
        "trace and surrounding workflow.",
    )
    result["options"] = {"cellHeight": "sm", "showHeader": True}
    return result


health = [
    stat(
        "Provider attempt error ratio",
        0,
        f"100 * sum(rate(soma_storage_errors_total{{{SELECTOR}}}[5m])) "
        f"/ clamp_min(sum(rate(soma_storage_operations_total{{{SELECTOR}}}[5m])), 1e-9)",
        "Failed provider attempts as a share of all observed provider attempts over 5 minutes. "
        "Retries count again; this is not a unique-session or business-failure rate.",
        unit="percent",
        thresholds=ERROR_STEPS,
    ),
    stat(
        "Failed provider calls / min",
        6,
        f"sum(rate(soma_storage_errors_total{{{SELECTOR}}}[5m])) * 60",
        "Failed storage provider attempts per minute. Repeated retries of one object are "
        "counted separately.",
        unit="opm",
        thresholds=COUNT_STEPS,
    ),
    stat(
        "Retries / min",
        12,
        f'sum(rate(soma_storage_events_total{{event="retry",{SELECTOR}}}[5m])) * 60',
        "Storage retry events per minute. Compare with failed calls to see retry amplification.",
        unit="opm",
        thresholds=COUNT_STEPS,
    ),
    stat(
        "P95 provider-call latency",
        18,
        "histogram_quantile(0.95, sum by (le) "
        f"(rate(soma_storage_duration_milliseconds_bucket{{{SELECTOR}}}[5m])))",
        "P95 duration of provider attempts. Fast failures can lower this value, so it is not a "
        "success-latency SLI.",
        unit="ms",
        decimals=0,
    ),
    gauge(
        "Successful provider attempts",
        0,
        "100 * sum(rate(soma_storage_operations_total{"
        f'{SELECTOR},outcome="success"}}[5m])) '
        f"/ clamp_min(sum(rate(soma_storage_operations_total{{{SELECTOR}}}[5m])), 1e-9)",
        "Successful provider attempts as a share of all attempts over five minutes. Retries "
        "count as additional attempts; this does not prove unique workflows completed.",
        thresholds=SUCCESS_STEPS,
    ),
    gauge(
        "Failed provider attempts",
        12,
        "100 * sum(rate(soma_storage_operations_total{"
        f'{SELECTOR},outcome="error"}}[5m])) '
        f"/ clamp_min(sum(rate(soma_storage_operations_total{{{SELECTOR}}}[5m])), 1e-9)",
        "Failed provider attempts as a share of all attempts over five minutes. Repeated "
        "retries of one object are counted separately.",
        thresholds=ERROR_STEPS,
    ),
    text_panel(
        "How to read storage health",
        13,
        "**These are provider-attempt diagnostics, not business outcomes.** A retry is another "
        "provider attempt, so a single session can produce many failures. Use the failure logs "
        "and traces to identify the upstream response, then use workflow-level telemetry to "
        "decide customer impact.\n\n"
        "`soma_storage_transfer_bytes_total` records bytes attempted by the application. Bytes "
        "on an error series were not confirmed stored. Missing telemetry renders as **Unknown**, "
        "never as a healthy zero.",
    ),
]

traffic = [
    timeseries(
        "Storage provider attempt rate",
        0,
        0,
        "sum by (workflow, operation, outcome) "
        f"(rate(soma_storage_operations_total{{{SELECTOR}}}[$__rate_interval]))",
        "{{workflow}} · {{operation}} · {{outcome}}",
        "Provider attempts per second split by workflow, operation, and outcome.",
        "ops",
        stack=True,
    ),
    timeseries(
        "Provider attempt error ratio by workflow",
        12,
        0,
        "100 * sum by (workflow) "
        f"(rate(soma_storage_errors_total{{{SELECTOR}}}[$__rate_interval])) "
        "/ clamp_min(sum by (workflow) "
        f"(rate(soma_storage_operations_total{{{SELECTOR}}}[$__rate_interval])), 1e-9)",
        "{{workflow}}",
        "Failed provider attempts as a percentage of attempts, split by workflow. Retries count "
        "again and can dominate this ratio.",
        "percent",
        percent=True,
    ),
    timeseries(
        "P95 latency by operation",
        0,
        8,
        "histogram_quantile(0.95, sum by (le, workflow, operation) "
        f"(rate(soma_storage_duration_milliseconds_bucket{{{SELECTOR}}}[$__rate_interval])))",
        "{{workflow}} · {{operation}}",
        "P95 provider-attempt latency by workflow and operation. Failure and success attempts "
        "are combined.",
        "ms",
    ),
    timeseries(
        "Attempted payload throughput",
        12,
        8,
        "sum by (workflow, operation, outcome) "
        f"(rate(soma_storage_transfer_bytes_total{{{SELECTOR}}}[$__rate_interval]))",
        "{{workflow}} · {{operation}} · {{outcome}}",
        "Application payload bytes supplied to provider calls per second. Error series are "
        "attempted bytes, not confirmed storage.",
        "Bps",
        stack=True,
    ),
]

failures = [
    logs_panel(),
    traces_panel(),
    timeseries(
        "5m failures by upstream status and service",
        0,
        10,
        "sum by (upstream_status, service_name) "
        "(count_over_time({service_name=~\"soma-.+\"} | json "
        "| event=\"storage_operation_failed\" "
        "| workflow=~\"$workflow\" | logical_area=~\"$logical_area\" [5m]))",
        "{{upstream_status}} · {{service_name}}",
        "Failure events in each rolling five-minute window by upstream status and runtime. A "
        "missing series means no matching failure logs.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
    timeseries(
        "Retries, fallbacks and conflicts",
        12,
        10,
        "sum by (event, workflow, operation) "
        f"(rate(soma_storage_events_total{{{SELECTOR}}}[$__rate_interval]))",
        "{{event}} · {{workflow}} · {{operation}}",
        "Retry, fallback, and conflict events emitted by the storage boundary.",
        "ops",
        stack=True,
    ),
]


def data_query(raw_target, default_datasource):
    datasource = raw_target.get("datasource", default_datasource)
    query_spec = {
        key: value
        for key, value in raw_target.items()
        if key not in {"datasource", "refId"}
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
                    "transformations": [],
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
    ("Traffic & latency", traffic),
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


def custom_variable(name, label, query):
    return {
        "kind": "CustomVariable",
        "spec": {
            "allValue": ".*",
            "allowCustomValue": False,
            "current": {"text": "All", "value": "$__all"},
            "hide": "dontHide",
            "includeAll": True,
            "label": label,
            "multi": True,
            "name": name,
            "options": [],
            "query": query,
            "skipUrlSync": False,
        },
    }


dashboard = {
    "apiVersion": "dashboard.grafana.app/v2",
    "kind": "Dashboard",
    "metadata": {
        "annotations": {
            "grafana.app/folder": "eftnndsaxtvy8a",
            "grafana.app/message": "Manage SOMA storage observability dashboard as code",
        },
        "name": "soma-storage-observability",
    },
    "spec": {
        "annotations": [],
        "cursorSync": "Off",
        "description": "Production health, traffic, latency, retries, safe failure logs, and "
        "traces for Soma's Supabase Storage boundaries.",
        "editable": True,
        "elements": elements,
        "layout": {"kind": "TabsLayout", "spec": {"tabs": tabs}},
        "links": [
            {
                "title": "SOMA Engineering",
                "type": "link",
                "url": "/d/soma-engineering/soma-engineering",
                "targetBlank": False,
                "includeVars": False,
                "keepTime": True,
                "asDropdown": False,
                "icon": "external link",
                "tags": [],
                "tooltip": "Open the main engineering dashboard",
            },
            {
                "title": "Supabase infrastructure",
                "type": "link",
                "url": "/d/soma-supabase/soma-supabase",
                "targetBlank": False,
                "includeVars": False,
                "keepTime": True,
                "asDropdown": False,
                "icon": "external link",
                "tags": [],
                "tooltip": "Open Supabase infrastructure health",
            },
        ],
        "liveNow": False,
        "preload": False,
        "tags": ["soma", "engineering", "storage", "supabase", "observability"],
        "timeSettings": {
            "autoRefresh": "1m",
            "autoRefreshIntervals": ["30s", "1m", "5m", "15m", "30m", "1h"],
            "fiscalYearStartMonth": 0,
            "from": "now-3h",
            "hideTimepicker": False,
            "timezone": "America/New_York",
            "to": "now",
        },
        "title": "SOMA Storage Observability",
        "variables": [
            custom_variable("workflow", "Workflow", "session_archive,object_store"),
            custom_variable(
                "logical_area",
                "Logical area",
                "session_transcripts,generic_objects,lead_artifacts,persisted_reference",
            ),
        ],
    },
}

print(json.dumps(dashboard, indent=2))
