"""Generate the operator-facing SOMA workflow dashboard.

This dashboard intentionally uses only existing telemetry. It does not write to
application databases or imply that an absent metric is a successful workflow.
"""

import json


PROM = {"type": "prometheus", "uid": "grafanacloud-prom"}
TEMPO = {"type": "tempo", "uid": "grafanacloud-traces"}
SOURCES = [
    "slack",
    "closing_desk",
    "gmail",
    "claude",
    "openphone",
    "llamaparse",
    "tivly",
    "aircall",
    "isc_extension",
    "bold_penguin",
    "benepath",
    "railway",
]


_panel_id = 0


def next_id():
    global _panel_id
    _panel_id += 1
    return _panel_id


def target(expr, legend=None, ref="A", instant=False):
    result = {
        "datasource": PROM,
        "editorMode": "code",
        "expr": expr,
        "refId": ref,
        "range": not instant,
    }
    if instant:
        result.update({"instant": True, "format": "table"})
    if legend:
        result["legendFormat"] = legend
    return result


def panel(kind, title, x, y, width, height, targets=None, *, description=None):
    result = {
        "id": next_id(),
        "type": kind,
        "title": title,
        "datasource": PROM,
        "gridPos": {"x": x, "y": y, "w": width, "h": height},
        "targets": targets or [],
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {},
    }
    if description:
        result["description"] = description
    return result


def stat(title, x, expr, description, *, unit="short", decimals=0, thresholds=None):
    result = panel("stat", title, x, 0, 6, 4, [target(expr, instant=True)], description=description)
    result["options"] = {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "textMode": "auto",
        "colorMode": "background",
        "graphMode": "none",
    }
    defaults = {
        "unit": unit,
        "decimals": decimals,
        "noValue": "No telemetry",
        "thresholds": {"mode": "absolute", "steps": thresholds or [{"color": "green"}]},
    }
    result["fieldConfig"]["defaults"] = defaults
    return result


def timeseries(title, x, y, width, targets, description, unit):
    result = panel("timeseries", title, x, y, width, 8, targets, description=description)
    result["fieldConfig"]["defaults"] = {
        "unit": unit,
        "custom": {
            "lineWidth": 2,
            "fillOpacity": 12,
            "gradientMode": "opacity",
            "showPoints": "never",
        },
    }
    result["options"] = {
        "legend": {"displayMode": "table", "placement": "bottom", "showLegend": True},
        "tooltip": {"mode": "multi", "sort": "desc"},
    }
    return result


def table(title, x, y, width, height, targets, description):
    result = panel("table", title, x, y, width, height, targets, description=description)
    result["options"] = {"showHeader": True, "cellHeight": "sm"}
    return result


def field_override(name, properties):
    return {"matcher": {"id": "byName", "options": name}, "properties": properties}


def text_panel(title, x, y, width, height, markdown):
    result = panel("text", title, x, y, width, height)
    result["options"] = {"mode": "markdown", "content": markdown}
    return result


source_filter = 'source=~"$source"'
expected_sources = " or ".join(
    f'label_replace(vector(1), "source", "{source}", "", "")'
    for source in SOURCES
)
panels = [
    stat(
        "Acknowledged",
        0,
        f'sum(increase(soma_webhook_requests_total{{{source_filter}, outcome="accepted"}}[$__range])) or vector(0)',
        "Webhook requests acknowledged in the selected range. This is receipt, not proof of terminal business completion.",
    ),
    stat(
        "Ingress exception rate",
        6,
        f'100 * (sum(increase(soma_webhook_requests_total{{{source_filter}, outcome=~"rejected|failed"}}[$__range])) or vector(0)) / clamp_min(sum(increase(soma_webhook_requests_total{{{source_filter}}}[$__range])), 1)',
        "Rejected or failed receipts divided by all webhook requests. Review at 1%; investigate immediately at 5%.",
        unit="percent",
        decimals=2,
        thresholds=[{"color": "green"}, {"color": "yellow", "value": 1}, {"color": "red", "value": 5}],
    ),
    stat(
        "Processing failures",
        12,
        f'sum(increase(soma_webhook_processing_total{{{source_filter}, outcome="failed"}}[$__range])) or vector(0)',
        "Recorded terminal processing failures after acknowledgement. Any value requires investigation.",
        thresholds=[{"color": "green"}, {"color": "red", "value": 1}],
    ),
    stat(
        "Processing retries",
        18,
        f'sum(increase(soma_webhook_processing_total{{{source_filter}, outcome="retrying"}}[$__range])) or vector(0)',
        "Retry events in the selected range. Review when non-zero; confirm whether each retry later succeeded.",
        thresholds=[{"color": "green"}, {"color": "yellow", "value": 1}, {"color": "red", "value": 10}],
    ),
]


ingress_actions = table(
    "Action queue — ingress",
    0,
    4,
    8,
    8,
    [
        target(
            f'sum by (source) (increase(soma_webhook_requests_total{{{source_filter}, outcome=~"rejected|failed"}}[$__range])) > 0',
            ref="A",
            instant=True,
        ),
        target(
            f'100 * sum by (source) (increase(soma_webhook_requests_total{{{source_filter}, outcome=~"rejected|failed"}}[$__range])) / clamp_min(sum by (source) (increase(soma_webhook_requests_total{{{source_filter}}}[$__range])), 1) > 0',
            ref="B",
            instant=True,
        ),
    ],
    "Action: inspect source validation/signature failures and correlated traces; confirm business impact before replaying anything.",
)
ingress_actions["transformations"] = [
    {"id": "joinByField", "options": {"byField": "source", "mode": "outer"}},
    {
        "id": "organize",
        "options": {
            "excludeByName": {"Time 1": True, "Time 2": True},
            "renameByName": {"source": "Source", "Value #A": "Exceptions", "Value #B": "Exception rate"},
        },
    },
]
ingress_actions["fieldConfig"]["overrides"] = [
    field_override("Exceptions", [{"id": "decimals", "value": 0}]),
    field_override(
        "Exception rate",
        [
            {"id": "unit", "value": "percent"},
            {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
            {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "green"}, {"color": "yellow", "value": 1}, {"color": "red", "value": 5}]}},
        ],
    ),
]
ingress_actions["options"]["sortBy"] = [{"displayName": "Exception rate", "desc": True}]
panels.append(ingress_actions)


processing_actions = table(
    "Action queue — processing",
    8,
    4,
    8,
    8,
    [
        target(
            f'sum by (source, operation, outcome) (increase(soma_webhook_processing_total{{{source_filter}, outcome=~"retrying|failed"}}[$__range])) > 0',
            instant=True,
        )
    ],
    "Action: inspect the named operation; confirm retry recovery or terminal state before manually intervening.",
)
processing_actions["transformations"] = [
    {
        "id": "organize",
        "options": {
            "excludeByName": {"Time": True},
            "renameByName": {"source": "Source", "operation": "Operation", "outcome": "State", "Value": "Events"},
        },
    }
]
processing_actions["fieldConfig"]["overrides"] = [
    field_override("Events", [{"id": "decimals", "value": 0}])
]
panels.append(processing_actions)


missing_sources = table(
    "Action queue — no observed traffic",
    16,
    4,
    8,
    8,
    [
        target(
            f'({expected_sources}) unless on (source) (sum by (source) (increase(soma_webhook_requests_total[$__range])) > 0)',
            instant=True,
        )
    ],
    "Action: verify whether traffic was expected during this range, then check sender configuration and endpoint health. Absence is unknown, not failure.",
)
missing_sources["transformations"] = [
    {
        "id": "organize",
        "options": {
            "excludeByName": {"Time": True, "Value": True},
            "renameByName": {"source": "Expected source without traffic"},
        },
    }
]
panels.append(missing_sources)


# Acknowledgements and processing events are deliberately shown as independent
# stages. They are not divided into a completion ratio because some inputs fan
# out into multiple operations and therefore are not one-to-one.
workflow = table(
    "Workflow health — observed sources",
    0,
    12,
    24,
    10,
    [
        target(
            f'sum by (source) (increase(soma_webhook_requests_total{{{source_filter}, outcome="accepted"}}[$__range]))',
            ref="A",
            instant=True,
        ),
        target(
            f'(sum by (source) (increase(soma_webhook_requests_total{{{source_filter}, outcome=~"rejected|failed"}}[$__range]))) or (sum by (source) (increase(soma_webhook_requests_total{{{source_filter}, outcome="accepted"}}[$__range])) * 0)',
            ref="B",
            instant=True,
        ),
        target(
            f'sum by (source) (increase(soma_webhook_processing_total{{{source_filter}, outcome="succeeded"}}[$__range]))',
            ref="C",
            instant=True,
        ),
        target(
            f'(sum by (source) (increase(soma_webhook_processing_total{{{source_filter}, outcome=~"retrying|failed"}}[$__range]))) or (sum by (source) (increase(soma_webhook_processing_total{{{source_filter}, outcome="succeeded"}}[$__range])) * 0)',
            ref="D",
            instant=True,
        ),
        target(
            f'time() - max by (source) (soma_webhook_last_seen_seconds{{{source_filter}}})',
            ref="E",
            instant=True,
        ),
        target(
            f'100 * ((sum by (source) (increase(soma_webhook_requests_total{{{source_filter}, outcome=~"rejected|failed"}}[$__range]))) or (sum by (source) (increase(soma_webhook_requests_total{{{source_filter}}}[$__range])) * 0)) / clamp_min(sum by (source) (increase(soma_webhook_requests_total{{{source_filter}}}[$__range])), 1)',
            ref="F",
            instant=True,
        ),
    ],
    "Stage counts for sources with telemetry. Processing events may fan out, so acknowledgement and success counts are not expected to match one-for-one.",
)
workflow["transformations"] = [
    {"id": "joinByField", "options": {"byField": "source", "mode": "outer"}},
    {
        "id": "organize",
        "options": {
            "excludeByName": {f"Time {index}": True for index in range(1, 7)},
            "renameByName": {
                "source": "Source",
                "Value #A": "Acknowledged",
                "Value #B": "Ingress problems",
                "Value #C": "Processing successes",
                "Value #D": "Processing problems",
                "Value #E": "Last seen age",
                "Value #F": "Ingress exception %",
            },
        },
    },
]
workflow["fieldConfig"]["overrides"] = [
    field_override("Source", [{"id": "custom.width", "value": 190}]),
    field_override("Last seen age", [{"id": "unit", "value": "s"}]),
    field_override("Acknowledged", [{"id": "decimals", "value": 0}]),
    field_override("Processing successes", [{"id": "decimals", "value": 0}]),
    field_override(
        "Ingress exception %",
        [
            {"id": "unit", "value": "percent"},
            {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
            {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "green"}, {"color": "yellow", "value": 1}, {"color": "red", "value": 5}]}},
        ],
    ),
    field_override(
        "Ingress problems",
        [
            {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
            {"id": "decimals", "value": 0},
            {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "green"}, {"color": "red", "value": 1}]}},
        ],
    ),
    field_override(
        "Processing problems",
        [
            {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
            {"id": "decimals", "value": 0},
            {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "green"}, {"color": "red", "value": 1}]}},
        ],
    ),
]
panels.append(workflow)


panels.extend(
    [
        timeseries(
            "Webhook acknowledgements by source",
            0,
            22,
            12,
            [target(f'sum by (source) (rate(soma_webhook_requests_total{{{source_filter}, outcome="accepted"}}[$__rate_interval]))', "{{source}}")],
            "Rate of successfully acknowledged inbound webhook requests.",
            "reqps",
        ),
        timeseries(
            "Processing outcomes by source",
            12,
            22,
            12,
            [target(f'sum by (source, outcome) (rate(soma_webhook_processing_total{{{source_filter}}}[$__rate_interval]))', "{{source}} · {{outcome}}")],
            "Recorded post-receipt processing events. Retry and failed series should trigger investigation.",
            "ops",
        ),
        timeseries(
            "Webhook acknowledgement p95",
            0,
            30,
            8,
            [
                target(
                    f'histogram_quantile(0.95, sum by (le, source) (rate(soma_webhook_duration_milliseconds_bucket{{{source_filter}}}[$__rate_interval])))',
                    "{{source}}",
                )
            ],
            "P95 time to return the webhook acknowledgement. This is not end-to-end business completion latency.",
            "ms",
        ),
        timeseries(
            "Processing p95",
            8,
            30,
            8,
            [
                target(
                    f'histogram_quantile(0.95, sum by (le, source) (rate(soma_webhook_processing_duration_milliseconds_bucket{{{source_filter}}}[$__rate_interval])))',
                    "{{source}}",
                )
            ],
            "P95 duration of instrumented post-receipt processing operations.",
            "ms",
        ),
        timeseries(
            "Acknowledgement data out",
            16,
            30,
            8,
            [target(f'sum by (source) (rate(soma_webhook_response_bytes_total{{{source_filter}}}[$__rate_interval]))', "{{source}}")],
            "Bytes per second returned in webhook acknowledgements. Request-body/data-in bytes are not instrumented yet.",
            "Bps",
        ),
    ]
)


dependency = table(
    "Raw dependency span errors — diagnostic only",
    0,
    38,
    24,
    9,
    [
        target(
            'label_join(60 * sum by (client, server) (rate(traces_service_graph_request_total{client=~"soma-.*"}[$__rate_interval])) > 0, "path", " → ", "client", "server")',
            ref="A",
            instant=True,
        ),
        target(
            'label_join((100 * ((sum by (client, server) (rate(traces_service_graph_request_failed_total{client=~"soma-.*"}[$__rate_interval]))) or (sum by (client, server) (rate(traces_service_graph_request_total{client=~"soma-.*"}[$__rate_interval])) * 0)) / clamp_min(sum by (client, server) (rate(traces_service_graph_request_total{client=~"soma-.*"}[$__rate_interval])), 0.0001)) and on (client, server) (sum by (client, server) (rate(traces_service_graph_request_total{client=~"soma-.*"}[$__rate_interval])) > 0), "path", " → ", "client", "server")',
            ref="B",
            instant=True,
        ),
        target(
            'label_join((1000 * sum by (client, server) (rate(traces_service_graph_request_client_seconds_sum{client=~"soma-.*"}[$__rate_interval])) / clamp_min(sum by (client, server) (rate(traces_service_graph_request_client_seconds_count{client=~"soma-.*"}[$__rate_interval])), 0.0001)) and on (client, server) (sum by (client, server) (rate(traces_service_graph_request_total{client=~"soma-.*"}[$__rate_interval])) > 0), "path", " → ", "client", "server")',
            ref="C",
            instant=True,
        ),
    ],
    "Raw OTel span-error percentage. This is not a business SLI: expected Angie transcript-not-ready 404 polling is currently counted as failure. Use traces before escalating.",
)
dependency["transformations"] = [
    {"id": "joinByField", "options": {"byField": "path", "mode": "outer"}},
    {
        "id": "organize",
        "options": {
            "excludeByName": {
                "Time 1": True,
                "Time 2": True,
                "Time 3": True,
                "client 1": True,
                "client 2": True,
                "client 3": True,
                "server 1": True,
                "server 2": True,
                "server 3": True,
            },
            "renameByName": {"path": "Path", "Value #A": "Requests/min", "Value #B": "Failures %", "Value #C": "Average latency"},
        },
    },
]
dependency["fieldConfig"]["overrides"] = [
    field_override("Path", [{"id": "custom.width", "value": 480}]),
    field_override("Requests/min", [{"id": "unit", "value": "rpm"}, {"id": "decimals", "value": 1}]),
    field_override(
        "Failures %",
        [
            {"id": "unit", "value": "percent"},
        ],
    ),
    field_override("Average latency", [{"id": "unit", "value": "ms"}]),
]
dependency["options"]["sortBy"] = [{"displayName": "Failures %", "desc": True}]
panels.append(dependency)


node_graph = panel(
    "nodeGraph",
    "Production service graph",
    0,
    47,
    24,
    12,
    description="Observed production service-to-dependency paths. Queue handoffs are not connected across workers yet, so missing internal edges are a known tracing gap.",
)
node_graph["datasource"] = TEMPO
node_graph["targets"] = [
    {
        "datasource": TEMPO,
        "queryType": "serviceMap",
        "refId": "A",
        "serviceMapQuery": ['{server=~"soma-.*"}', '{client=~"soma-.*"}'],
    }
]
panels.append(node_graph)


panels.append(
    text_panel(
        "How to read this dashboard",
        0,
        59,
        24,
        8,
        """### Operator interpretation

- **Acknowledged** means SOMA received and answered a webhook. It does not prove the final business action completed.
- **Processing success/retry/failure** covers only instrumented operations after receipt. Counts may fan out and are not one-to-one with requests.
- A source missing from **Workflow health** is **Unknown / no observed telemetry**, never automatically healthy.
- Expected sources currently selectable: Slack, Closing Desk, Gmail, Claude, OpenPhone, LlamaParse, Tivly, Aircall, ISC Extension, Bold Penguin, Benepath, and Railway.
- The dependency table is a raw span-error diagnostic. Angie transcript polling returns an expected 404 while a transcript is not ready, so that table must not be used as a business-failure alert yet.

### Known safe coverage gaps

Request-body **data in**, queue depth/oldest-job age, exact cross-queue trace continuity, and terminal business outcomes are not measured yet. This dashboard performs no table mutations and uses telemetry only. Use **Soma Metrics** for engineering HTTP/collector diagnostics.""",
    )
)


def data_query(raw_target, default_datasource):
    datasource = raw_target.get("datasource", default_datasource)
    query_spec = {
        key: value
        for key, value in raw_target.items()
        if key not in {"datasource", "refId"}
    }
    group = "tempo" if datasource["type"] == "tempo" else "prometheus"
    return {
        "kind": "PanelQuery",
        "spec": {
            "hidden": False,
            "query": {
                "datasource": {"name": datasource["uid"]},
                "group": group,
                "kind": "DataQuery",
                "spec": query_spec,
                "version": "v0",
            },
            "refId": raw_target["refId"],
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
                    "queries": [data_query(item, datasource) for item in raw_panel.get("targets", [])],
                    "queryOptions": {},
                    "transformations": [
                        transformation(item) for item in raw_panel.get("transformations", [])
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
                    "fieldConfig": raw_panel.get("fieldConfig", {"defaults": {}, "overrides": []}),
                    "options": raw_panel.get("options", {}),
                },
                "version": "",
            },
        },
    }


elements = {f"panel-{item['id']}": panel_element(item) for item in panels}
layout_items = [
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
    for item in panels
]


dashboard = {
    "apiVersion": "dashboard.grafana.app/v2",
    "kind": "Dashboard",
    "metadata": {
        "annotations": {
            "grafana.app/folder": "fwtfg9",
            "grafana.app/message": "Create SOMA product and operations workflow dashboard",
        },
        "name": "soma-operations",
    },
    "spec": {
        "annotations": [
            {
                "kind": "AnnotationQuery",
                "spec": {
                    "builtIn": True,
                    "enable": True,
                    "hide": True,
                    "iconColor": "rgba(0, 211, 255, 1)",
                    "legacyOptions": {"type": "dashboard"},
                    "name": "Annotations & Alerts",
                    "query": {
                        "datasource": {"name": "-- Grafana --"},
                        "group": "grafana",
                        "kind": "DataQuery",
                        "spec": {},
                        "version": "v0",
                    },
                },
            }
        ],
        "cursorSync": "Off",
        "description": "Product and operations view of webhook receipt, processing, dependencies, and observability gaps.",
        "editable": True,
        "elements": elements,
        "layout": {"kind": "GridLayout", "spec": {"items": layout_items}},
        "links": [
            {
                "title": "Engineering diagnostics — Soma Metrics",
                "type": "link",
                "url": "/d/an29kk/soma-metrics",
                "targetBlank": False,
                "includeVars": False,
                "keepTime": True,
                "asDropdown": False,
                "icon": "external link",
                "tags": [],
                "tooltip": "Open the engineering HTTP and collector dashboard",
            }
        ],
        "liveNow": False,
        "preload": False,
        "tags": ["soma", "operations", "product", "webhooks"],
        "timeSettings": {
            "autoRefresh": "30s",
            "autoRefreshIntervals": ["30s", "1m", "5m", "15m", "30m", "1h"],
            "fiscalYearStartMonth": 0,
            "from": "now-6h",
            "hideTimepicker": False,
            "timezone": "browser",
            "to": "now",
        },
        "title": "SOMA Operations",
        "variables": [
            {
                "kind": "CustomVariable",
                "spec": {
                    "allValue": ".*",
                    "allowCustomValue": False,
                    "current": {"text": "All", "value": "$__all"},
                    "hide": "dontHide",
                    "includeAll": True,
                    "label": "Webhook source",
                    "multi": True,
                    "name": "source",
                    "options": [],
                    "query": ",".join(SOURCES),
                    "skipUrlSync": False,
                },
            }
        ],
    },
}


if __name__ == "__main__":
    print(json.dumps(dashboard, indent=2))
