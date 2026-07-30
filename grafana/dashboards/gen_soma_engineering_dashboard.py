"""Generate the engineering-facing SOMA diagnostics dashboard.

Five tabs: service health, HTTP routes, dependencies, workflow spans, and the
telemetry pipeline itself.

Two honesty rules run through it. Absent telemetry renders as unknown in grey,
never as a healthy green zero. And any panel whose value can saturate or divide
by nothing says so in its description rather than showing a confident number.
"""

import json

PROM = {"type": "prometheus", "uid": "grafanacloud-prom"}

SERVER_LATENCY = "http_server_duration_milliseconds"
SPAN_CALLS = "traces_spanmetrics_calls_total"
SPAN_LATENCY = "traces_spanmetrics_duration_milliseconds"
TOP_BUCKET_MS = 10000

WORKFLOW_KEYS = "ingestion|claude_session|vendor_campaign|quote|slack"
WORKFLOW_SPANS = f'span_name=~"({WORKFLOW_KEYS})\\\\..*"'

UNKNOWN = "Unknown — not measured"
NEUTRAL = [{"color": "text"}]
ERROR_STEPS = [
    {"color": "text"},
    {"color": "green", "value": 0},
    {"color": "orange", "value": 1},
    {"color": "red", "value": 5},
]
COUNT_STEPS = [{"color": "text"}, {"color": "green", "value": 0}, {"color": "red", "value": 1}]

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
    return {
        "id": next_id(),
        "type": kind,
        "title": title,
        "datasource": PROM,
        "gridPos": {"x": x, "y": y, "w": width, "h": height},
        "targets": targets or [],
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {},
        "description": description or "",
    }


def stat(
    title,
    x,
    y,
    expr,
    description,
    *,
    unit="short",
    decimals=0,
    thresholds=None,
    width=6,
    mappings=None,
):
    result = panel("stat", title, x, y, width, 4, [target(expr, instant=True)], description=description)
    result["options"] = {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "textMode": "auto",
        "colorMode": "background",
        "graphMode": "none",
    }
    result["fieldConfig"]["defaults"] = {
        "unit": unit,
        "decimals": decimals,
        "noValue": UNKNOWN,
        "thresholds": {"mode": "absolute", "steps": thresholds or NEUTRAL},
    }
    if mappings:
        result["fieldConfig"]["defaults"]["mappings"] = mappings
    return result


def timeseries(title, x, y, width, targets, description, unit, *, height=8, legend="list"):
    result = panel("timeseries", title, x, y, width, height, targets, description=description)
    result["fieldConfig"]["defaults"] = {
        "unit": unit,
        "noValue": UNKNOWN,
        "custom": {
            "lineWidth": 2,
            "fillOpacity": 10,
            "gradientMode": "opacity",
            "showPoints": "never",
        },
    }
    result["options"] = {
        "legend": {"displayMode": legend, "placement": "bottom", "showLegend": True},
        "tooltip": {"mode": "multi", "sort": "desc"},
    }
    return result


def table(title, x, y, width, height, targets, description):
    result = panel("table", title, x, y, width, height, targets, description=description)
    result["options"] = {"showHeader": True, "cellHeight": "sm"}
    result["fieldConfig"]["defaults"] = {"noValue": UNKNOWN}
    return result


def text_panel(title, x, y, width, height, markdown):
    result = panel("text", title, x, y, width, height)
    result["options"] = {"mode": "markdown", "content": markdown}
    return result


def field_override(name, properties):
    return {"matcher": {"id": "byName", "options": name}, "properties": properties}


def quantile(fraction, metric, selector="", group=""):
    by = f"le, {group}" if group else "le"
    inner = f"{metric}_bucket{{{selector}}}" if selector else f"{metric}_bucket"
    return f"histogram_quantile({fraction}, sum by ({by}) (rate({inner}[$__rate_interval])))"


def service_health_tab():
    panels = [
        stat(
            "Request rate",
            0,
            0,
            f"sum(rate({SERVER_LATENCY}_count[$__rate_interval]))",
            "Inbound HTTP requests per second across all SOMA services.",
            unit="reqps",
            decimals=2,
        ),
        stat(
            "5xx rate",
            6,
            0,
            f'100 * sum(rate({SERVER_LATENCY}_count{{http_status_code=~"5.."}}[$__rate_interval]))'
            f" / clamp_min(sum(rate({SERVER_LATENCY}_count[$__rate_interval])), 0.0001)"
            f" or sum(rate({SERVER_LATENCY}_count[$__rate_interval])) * 0",
            "Share of inbound requests answered with a 5xx. This is SOMA's own failure to "
            "acknowledge, not a business outcome.",
            unit="percent",
            decimals=2,
            thresholds=ERROR_STEPS,
        ),
        stat(
            "In-flight requests",
            12,
            0,
            "sum(http_server_active_requests)",
            "Requests currently being served. A rising floor means work is backing up.",
        ),
        stat(
            "Services reporting",
            18,
            0,
            f"count(count by (service_name) ({SERVER_LATENCY}_count))",
            "How many services are emitting HTTP telemetry. Fewer than expected means the rest "
            "are unknown, not idle.",
        ),
        timeseries(
            "Request rate by service",
            0,
            4,
            12,
            [
                target(
                    f"sum by (service_name) (rate({SERVER_LATENCY}_count[$__rate_interval]))",
                    legend="{{service_name}}",
                )
            ],
            "Inbound HTTP by service.",
            "reqps",
        ),
        timeseries(
            "5xx rate by service",
            12,
            4,
            12,
            [
                target(
                    "100 * sum by (service_name) (rate("
                    f'{SERVER_LATENCY}_count{{http_status_code=~"5.."}}[$__rate_interval]))'
                    f" / clamp_min(sum by (service_name) (rate({SERVER_LATENCY}_count"
                    "[$__rate_interval])), 0.0001)"
                    f" or sum by (service_name) (rate({SERVER_LATENCY}_count"
                    "[$__rate_interval])) * 0",
                    legend="{{service_name}}",
                )
            ],
            "Per-service 5xx share. A service with no traffic shows no line rather than 0%.",
            "percent",
        ),
        timeseries(
            "Inbound latency percentiles",
            0,
            12,
            24,
            [
                target(quantile(0.5, SERVER_LATENCY), legend="p50"),
                target(quantile(0.95, SERVER_LATENCY), legend="p95", ref="B"),
                target(quantile(0.99, SERVER_LATENCY), legend="p99", ref="C"),
            ],
            f"Estimated from histogram buckets whose top edge is {TOP_BUCKET_MS} ms. A percentile "
            f"sitting flat at {TOP_BUCKET_MS} ms means the bucket is saturated — the real value is "
            "somewhere above it and cannot be read from this panel. Use traces for those.",
            "ms",
        ),
    ]
    return panels


def http_routes_tab():
    selector = ""
    routes = table(
        "Routes — volume, latency, 5xx",
        0,
        0,
        24,
        11,
        [
            target(
                f"sum by (http_target) (increase({SERVER_LATENCY}_count[$__range]))",
                ref="A",
                instant=True,
            ),
            target(
                quantile(0.95, SERVER_LATENCY, selector, "http_target"),
                ref="B",
                instant=True,
            ),
            target(
                "100 * sum by (http_target) (increase("
                f'{SERVER_LATENCY}_count{{http_status_code=~"5.."}}[$__range]))'
                f" / clamp_min(sum by (http_target) (increase({SERVER_LATENCY}_count"
                "[$__range])), 1)",
                ref="C",
                instant=True,
            ),
        ],
        "Only routes with observed traffic appear. A route absent here was not called in this "
        "window — that is unknown, not healthy.",
    )
    routes["transformations"] = [
        {"id": "joinByField", "options": {"byField": "http_target", "mode": "outer"}},
        {
            "id": "organize",
            "options": {
                "excludeByName": {"Time 1": True, "Time 2": True, "Time 3": True},
                "renameByName": {
                    "http_target": "Route",
                    "Value #A": "Requests",
                    "Value #B": "p95",
                    "Value #C": "5xx %",
                },
            },
        },
        {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "Requests", "desc": True}]}},
    ]
    routes["fieldConfig"]["overrides"] = [
        field_override("Requests", [{"id": "decimals", "value": 0}]),
        field_override(
            "p95", [{"id": "unit", "value": "ms"}, {"id": "decimals", "value": 0}, {"id": "noValue", "value": "—"}]
        ),
        field_override(
            "5xx %",
            [
                {"id": "unit", "value": "percent"},
                {"id": "decimals", "value": 2},
                {"id": "noValue", "value": "—"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": ERROR_STEPS}},
                {"id": "custom.cellOptions", "value": {"type": "color-text"}},
            ],
        ),
    ]
    return [
        routes,
        timeseries(
            "Requests by status class",
            0,
            11,
            24,
            [
                target(
                    "sum by (http_status_code) (rate("
                    f"{SERVER_LATENCY}_count[$__rate_interval]))",
                    legend="{{http_status_code}}",
                )
            ],
            "Inbound status codes over time.",
            "reqps",
        ),
    ]


def dependencies_tab():
    graph = table(
        "Outbound dependency paths — raw span errors, diagnostic only",
        0,
        0,
        24,
        11,
        [
            target(
                "sum by (client, server) (rate(traces_service_graph_request_total"
                "[$__rate_interval])) * 60",
                ref="A",
                instant=True,
            ),
            target(
                "100 * sum by (client, server) (rate(traces_service_graph_request_failed_total"
                "[$__rate_interval])) / clamp_min(sum by (client, server) (rate("
                "traces_service_graph_request_total[$__rate_interval])), 0.0001)",
                ref="B",
                instant=True,
            ),
        ],
        "Raw OTel span-error share per dependency path. Not a business SLI: expected outcomes "
        "such as Angie's transcript-not-ready 404 polling are counted as failures here. Confirm "
        "in traces before escalating.",
    )
    graph["transformations"] = [
        {"id": "joinByField", "options": {"byField": "server", "mode": "outer"}},
        {
            "id": "organize",
            "options": {
                "excludeByName": {"Time 1": True, "Time 2": True, "client 2": True},
                "renameByName": {
                    "client 1": "From",
                    "server": "To",
                    "Value #A": "Requests/min",
                    "Value #B": "Span errors %",
                },
            },
        },
        {
            "id": "sortBy",
            "options": {"fields": {}, "sort": [{"field": "Requests/min", "desc": True}]},
        },
    ]
    graph["fieldConfig"]["overrides"] = [
        field_override("Requests/min", [{"id": "unit", "value": "rpm"}, {"id": "decimals", "value": 1}]),
        field_override("Span errors %", [{"id": "unit", "value": "percent"}, {"id": "decimals", "value": 2}]),
    ]
    return [
        graph,
        timeseries(
            "Outbound call latency",
            0,
            11,
            12,
            [
                target(quantile(0.95, "http_client_duration_milliseconds"), legend="p95"),
                target(
                    quantile(0.5, "http_client_duration_milliseconds"), legend="p50", ref="B"
                ),
            ],
            "Latency of calls SOMA makes to external APIs. Peer hostname is not on this metric — "
            "use the dependency table or traces to attribute it.",
            "ms",
        ),
        timeseries(
            "Outbound calls by status",
            12,
            11,
            12,
            [
                target(
                    "sum by (http_status_code) (rate(http_client_duration_milliseconds_count"
                    "[$__rate_interval]))",
                    legend="{{http_status_code}}",
                )
            ],
            "Status codes SOMA receives from external APIs.",
            "reqps",
        ),
    ]


def workflows_tab():
    return [
        stat(
            "Workflow spans/min",
            0,
            0,
            f"sum(rate({SPAN_CALLS}{{{WORKFLOW_SPANS}}}[$__rate_interval])) * 60",
            "Rate of terminal workflow outcomes across every traced workflow.",
            unit="opm",
            decimals=1,
        ),
        stat(
            "Span-error outcomes",
            6,
            0,
            f'sum(increase({SPAN_CALLS}{{{WORKFLOW_SPANS}, status_code="STATUS_CODE_ERROR"}}'
            "[$__range]))"
            f" or sum(increase({SPAN_CALLS}{{{WORKFLOW_SPANS}}}[$__range])) * 0",
            "Workflow attempts that ended in a terminal failure. Retries are deliberately not "
            "errors here.",
            thresholds=COUNT_STEPS,
        ),
        stat(
            "Distinct stages",
            12,
            0,
            f"count(count by (span_name) ({SPAN_CALLS}{{{WORKFLOW_SPANS}}}))",
            "How many workflow stages are reporting. Compare against what you expect to be "
            "deployed.",
        ),
        stat(
            "Workflow p95",
            18,
            0,
            quantile(0.95, SPAN_LATENCY, WORKFLOW_SPANS),
            "Slowest-decile duration of one workflow attempt, claim to terminal outcome.",
            unit="ms",
        ),
        timeseries(
            "Stage throughput",
            0,
            4,
            12,
            [
                target(
                    f"sum by (span_name) (rate({SPAN_CALLS}{{{WORKFLOW_SPANS}}}"
                    "[$__rate_interval])) * 60",
                    legend="{{span_name}}",
                )
            ],
            "Terminal outcomes per minute for each workflow stage.",
            "opm",
        ),
        timeseries(
            "Stage latency p95",
            12,
            4,
            12,
            [
                target(
                    quantile(0.95, SPAN_LATENCY, WORKFLOW_SPANS, "span_name"),
                    legend="{{span_name}}",
                )
            ],
            "Per-stage p95 duration.",
            "ms",
        ),
        text_panel(
            "Reading workflow spans",
            0,
            12,
            24,
            6,
            "These are span metrics Alloy derives from the workflow spans each worker and handler "
            "emits. They carry `span_name` and `status_code` only — the richer dimensions "
            "(`result`, `job.id`, `job.type`, `job.attempt`, `enqueued.job.id`) live on the spans "
            "themselves.\n\n"
            "For operator-facing per-workflow health, use **SOMA Workflow Health**. This tab is "
            "for engineering: comparing stage cost and spotting a stage that stopped reporting.\n\n"
            "Retries leave span status unset on purpose, so they never inflate the error count "
            "here. Filter `span.result` in traces to separate `retrying` from `failed`.",
        ),
    ]


def telemetry_tab():
    panels = [
        stat(
            "Spans exported",
            0,
            0,
            "sum(increase(otelcol_exporter_sent_spans_total[$__range]))",
            "Spans the collector successfully shipped to Grafana Cloud in this window.",
        ),
        stat(
            "Export failures",
            6,
            0,
            "sum(increase(otelcol_exporter_send_failed_spans_total[$__range]))"
            " or sum(increase(otelcol_exporter_sent_spans_total[$__range])) * 0",
            "Spans the collector could not ship. The counter is absent until it first fires, so "
            "this panel forces it to 0 when exports are working — an absent series here would "
            "otherwise read as unknown.",
            thresholds=COUNT_STEPS,
        ),
        stat(
            "Refused spans",
            12,
            0,
            "sum(increase(otelcol_receiver_refused_spans_total[$__range]))"
            " or sum(increase(otelcol_receiver_accepted_spans_total[$__range])) * 0",
            "Spans the collector rejected at ingest, usually backpressure. Non-zero means "
            "telemetry is being dropped before it leaves the network.",
            thresholds=COUNT_STEPS,
        ),
        stat(
            "Export queue used",
            18,
            0,
            "100 * sum(otelcol_exporter_queue_size) / clamp_min(sum(otelcol_exporter_queue_capacity), 1)",
            "How full the collector's export queue is. Sustained growth means the collector "
            "cannot drain to Grafana Cloud as fast as SOMA produces telemetry.",
            unit="percent",
            decimals=2,
            thresholds=[
                {"color": "text"},
                {"color": "green", "value": 0},
                {"color": "orange", "value": 50},
                {"color": "red", "value": 80},
            ],
        ),
        timeseries(
            "Collector span pipeline",
            0,
            4,
            12,
            [
                target(
                    "sum(rate(otelcol_receiver_accepted_spans_total[$__rate_interval]))",
                    legend="accepted",
                ),
                target(
                    "sum(rate(otelcol_exporter_sent_spans_total[$__rate_interval]))",
                    legend="exported",
                    ref="B",
                ),
                target(
                    "sum(rate(otelcol_receiver_refused_spans_total[$__rate_interval]))",
                    legend="refused",
                    ref="C",
                ),
            ],
            "Accepted should track exported. A widening gap means spans are being buffered or "
            "dropped.",
            "cps",
        ),
        timeseries(
            "Telemetry freshness by service",
            12,
            4,
            12,
            [
                target(
                    f"time() - max by (service_name) (timestamp({SERVER_LATENCY}_count))",
                    legend="{{service_name}}",
                )
            ],
            "Seconds since each service last reported HTTP telemetry. This metric only "
            "advances when requests arrive, so it climbs overnight on US Eastern hours for "
            "legitimate reasons. A service climbing while its siblings stay flat is the real "
            "signal; everything climbing together is just the quiet hours.",
            "s",
        ),
        text_panel(
            "Why this tab exists",
            0,
            12,
            24,
            6,
            "Every other panel in SOMA's dashboards is only as trustworthy as this pipeline. If "
            "the collector stops exporting, every chart flattens to zero and nothing looks "
            "wrong.\n\n"
            "**Export failures** and **Refused spans** are the two signals worth alerting on "
            "before any business SLO exists, because they invalidate all the others. "
            "**Telemetry freshness** catches the other failure shape: a service that died rather "
            "than a collector that broke.\n\n"
            "Staging telemetry is intentionally disabled and its collector is scaled to zero, so "
            "staging is expected to be absent here.\n\n"
            "Times are shown in US Eastern, matching the hours SOMA's operators work. Volume "
            "swings roughly 75x between the business day and overnight, so read every rate "
            "against the time of day before calling it a regression.",
        ),
    ]
    return panels


def database_load_tab():
    angie = "soma_angie_status_lookup"
    connected = "physical_replication_lag_is_connected_to_primary"
    panels = [
        stat(
            "Database size",
            0,
            0,
            "max(pg_database_size_bytes)",
            "Current Supabase database size.",
            unit="bytes",
            decimals=2,
        ),
        stat(
            "Growth per day",
            6,
            0,
            "deriv(pg_database_size_bytes[24h]) * 86400",
            "Linear fit over the last 24h. Writes concentrate in the US business day, so this "
            "figure swings with the time of day — read it as a trend across days, not a "
            "reading of the last hour.",
            unit="bytes",
            decimals=2,
        ),
        stat(
            "Replica attached",
            12,
            0,
            f"max({connected})",
            "Whether a read replica is currently streaming from the primary. Every replication "
            "lag metric reads a healthy-looking 0 when no replica exists, so this panel is what "
            "makes those numbers safe to interpret.",
            mappings=[
                {
                    "type": "value",
                    "options": {
                        "0": {"text": "No replica attached", "color": "text", "index": 0},
                        "1": {"text": "Attached", "color": "green", "index": 1},
                    },
                }
            ],
        ),
        stat(
            "Replica lag",
            18,
            0,
            f"max(physical_replication_lag_physical_replication_lag_seconds and {connected} == 1)",
            "Seconds the replica trails the primary. Shows unknown when no replica is attached, "
            "rather than 0.",
            unit="s",
            decimals=1,
            thresholds=[
                {"color": "text"},
                {"color": "green", "value": 0},
                {"color": "orange", "value": 30},
                {"color": "red", "value": 60},
            ],
        ),
        timeseries(
            "Database size over time",
            0,
            4,
            12,
            [target("max(pg_database_size_bytes)", legend="size")],
            "Absolute size. The slope is the thing to watch, not the value.",
            "bytes",
        ),
        timeseries(
            "Angie summary status lookup — queries and rows per lookup",
            12,
            4,
            12,
            [
                target(
                    f"sum(rate({angie}_pages_total[$__rate_interval]))"
                    f" / clamp_min(sum(rate({angie}_operations_total[$__rate_interval])), 0.0001)",
                    legend="queries per lookup",
                ),
                target(
                    f"sum(rate({angie}_rows_total[$__rate_interval]))"
                    f" / clamp_min(sum(rate({angie}_operations_total[$__rate_interval])), 0.0001)",
                    legend="rows per lookup",
                    ref="B",
                ),
            ],
            "Database work per automatic summary lookup. The scoped strategy should hold this at "
            "one query and one row; the bulk strategy pages the whole session table. Absent "
            "until a session summary is saved.",
            "short",
        ),
        timeseries(
            "Angie lookup outcomes by strategy",
            0,
            12,
            12,
            [
                target(
                    f"sum by (strategy, outcome) (rate({angie}_operations_total"
                    "[$__rate_interval])) * 60",
                    legend="{{strategy}} · {{outcome}}",
                )
            ],
            "Lookup rate split by strategy and outcome. Only the strategy the feature flag "
            "selects will appear.",
            "opm",
        ),
        timeseries(
            "Angie lookup latency p95",
            12,
            12,
            12,
            [target(quantile(0.95, f"{angie}_duration_milliseconds"), legend="p95")],
            "How long one automatic summary status lookup takes.",
            "ms",
        ),
        text_panel(
            "Reading database load",
            0,
            20,
            24,
            7,
            "**Replication.** No replica is attached today — the read replica is a "
            "recommendation, not yet provisioned. That is why *Replica attached* sits next to "
            "*Replica lag*: with nothing streaming, every lag metric reads 0, which is absence "
            "masquerading as health. Three non-paging alerts cover this and stay silent until a "
            "replica exists: lag above 60s, WAL replay paused, and a replica that was attached "
            "within 6h disappearing.\n\n"
            "**Growth.** Writes follow the US business day, so a 12-hour window straddling the "
            "quiet hours will understate the rate and one covering the working day will "
            "overstate it. Judge growth across whole days.\n\n"
            "**Angie lookups.** These panels answer whether scoping the summary status lookup "
            "actually reduced database reads. They are absent until an Angie session saves a "
            "summary, and only the strategy currently selected by "
            "`ANGIE_SCOPED_SUMMARY_STATUS_ENABLED` will report — so the scoped-versus-bulk "
            "comparison needs the flag flipped to be visible.",
        ),
    ]
    return panels


def data_query(raw_target, datasource):
    return {
        "kind": "PanelQuery",
        "spec": {
            "query": {
                "kind": "DataQuery",
                "group": datasource["type"],
                "datasource": {"name": datasource["uid"]},
                "spec": {
                    key: value
                    for key, value in raw_target.items()
                    if key not in {"datasource", "refId"}
                },
                "version": "v0",
            },
            "refId": raw_target.get("refId", "A"),
            "hidden": False,
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


def grid_items(panels):
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
        for item in panels
    ]


tabs_spec = [
    ("Service health", service_health_tab()),
    ("HTTP routes", http_routes_tab()),
    ("Dependencies", dependencies_tab()),
    ("Workflow spans", workflows_tab()),
    ("Database load", database_load_tab()),
    ("Telemetry pipeline", telemetry_tab()),
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
            "grafana.app/folder": "fwtfg9",
            "grafana.app/message": "Create SOMA engineering diagnostics dashboard",
        },
        "name": "soma-engineering",
    },
    "spec": {
        "annotations": [],
        "cursorSync": "Off",
        "description": "Engineering diagnostics for SOMA: HTTP RED, routes, dependencies, "
        "workflow spans, and the health of the telemetry pipeline itself.",
        "editable": True,
        "elements": elements,
        "layout": {"kind": "TabsLayout", "spec": {"tabs": tabs}},
        "links": [
            {
                "title": "SOMA Workflow Health",
                "type": "link",
                "url": "/d/soma-workflow-health/soma-workflow-health",
                "targetBlank": False,
                "includeVars": False,
                "keepTime": True,
                "asDropdown": False,
                "icon": "external link",
                "tags": [],
                "tooltip": "Per-workflow operator view",
            },
            {
                "title": "SOMA Operations",
                "type": "link",
                "url": "/d/soma-operations/soma-operations",
                "targetBlank": False,
                "includeVars": False,
                "keepTime": True,
                "asDropdown": False,
                "icon": "external link",
                "tags": [],
                "tooltip": "Webhook receipt and processing overview",
            },
        ],
        "liveNow": False,
        "preload": False,
        "tags": ["soma", "engineering", "diagnostics"],
        "timeSettings": {
            "autoRefresh": "1m",
            "autoRefreshIntervals": ["30s", "1m", "5m", "15m", "30m", "1h"],
            "fiscalYearStartMonth": 0,
            "from": "now-6h",
            "hideTimepicker": False,
            "timezone": "America/New_York",
            "to": "now",
        },
        "title": "SOMA Engineering",
        "variables": [],
    },
}


if __name__ == "__main__":
    print(json.dumps(dashboard, indent=2))
