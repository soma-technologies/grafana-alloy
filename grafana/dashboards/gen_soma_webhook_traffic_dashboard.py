"""Generate the dedicated SOMA webhook traffic and Slack usefulness dashboard."""

from __future__ import annotations

import json


PROM = {"type": "prometheus", "uid": "grafanacloud-prom"}
LOKI = {"type": "loki", "uid": "grafanacloud-logs"}
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


def next_id() -> int:
    global _panel_id
    _panel_id += 1
    return _panel_id


def target(
    expr: str,
    legend: str | None = None,
    ref: str = "A",
    *,
    instant: bool = False,
    datasource: dict = PROM,
) -> dict:
    result = {
        "datasource": datasource,
        "editorMode": "code",
        "expr": expr,
        "refId": ref,
    }
    if instant:
        result.update({"instant": True, "format": "table", "range": False, "queryType": "instant"})
    elif datasource == PROM:
        result["range"] = True
    else:
        result["queryType"] = "range"
    if legend:
        result["legendFormat"] = legend
    return result


def panel(
    kind: str,
    title: str,
    x: int,
    y: int,
    width: int,
    height: int,
    targets: list[dict] | None = None,
    *,
    description: str = "",
    datasource: dict = PROM,
) -> dict:
    return {
        "id": next_id(),
        "type": kind,
        "title": title,
        "datasource": datasource,
        "gridPos": {"x": x, "y": y, "w": width, "h": height},
        "targets": targets or [],
        "description": description,
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {},
    }


def stat(
    title: str,
    x: int,
    y: int,
    expr: str,
    description: str,
    *,
    unit: str = "short",
    decimals: int = 0,
    thresholds: list[dict] | None = None,
    datasource: dict = PROM,
) -> dict:
    result = panel(
        "stat",
        title,
        x,
        y,
        6,
        4,
        [target(expr, instant=True, datasource=datasource)],
        description=description,
        datasource=datasource,
    )
    result["options"] = {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "textMode": "auto",
        "colorMode": "background",
        "graphMode": "none",
    }
    result["fieldConfig"]["defaults"] = {
        "unit": unit,
        "decimals": decimals,
        "noValue": "Not measured",
        "thresholds": {"mode": "absolute", "steps": thresholds or [{"color": "text"}]},
    }
    return result


def timeseries(
    title: str,
    x: int,
    y: int,
    width: int,
    height: int,
    targets: list[dict],
    description: str,
    *,
    unit: str = "reqps",
    datasource: dict = PROM,
) -> dict:
    result = panel(
        "timeseries",
        title,
        x,
        y,
        width,
        height,
        targets,
        description=description,
        datasource=datasource,
    )
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


def table(
    title: str,
    x: int,
    y: int,
    width: int,
    height: int,
    targets: list[dict],
    description: str,
    *,
    datasource: dict = PROM,
) -> dict:
    result = panel(
        "table",
        title,
        x,
        y,
        width,
        height,
        targets,
        description=description,
        datasource=datasource,
    )
    result["options"] = {"showHeader": True, "cellHeight": "sm"}
    return result


def pie(
    title: str,
    x: int,
    y: int,
    width: int,
    height: int,
    expr: str,
    legend: str,
    description: str,
) -> dict:
    result = panel(
        "piechart",
        title,
        x,
        y,
        width,
        height,
        [target(expr, legend, instant=True)],
        description=description,
    )
    result["options"] = {
        "displayLabels": ["name", "percent"],
        "legend": {"displayMode": "table", "placement": "right", "showLegend": True},
        "pieType": "donut",
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
        "tooltip": {"mode": "single", "sort": "none"},
    }
    result["fieldConfig"]["defaults"] = {"unit": "short", "decimals": 0, "noValue": "Not measured"}
    return result


def text_panel(title: str, x: int, y: int, width: int, height: int, markdown: str) -> dict:
    result = panel("text", title, x, y, width, height)
    result["options"] = {"mode": "markdown", "content": markdown}
    return result


def field_override(name: str, properties: list[dict]) -> dict:
    return {"matcher": {"id": "byName", "options": name}, "properties": properties}


SOURCE_FILTER = 'source=~"$source"'
TOTAL_INGRESS = f'sum(increase(soma_webhook_requests_total{{{SOURCE_FILTER}}}[$__range]))'
SLACK_CLASSIFIED = 'sum(increase(soma_slack_events_total[$__range]))'

traffic_panels = [
    stat(
        "Ingress events",
        0,
        0,
        f"{TOTAL_INGRESS} or vector(0)",
        "All webhook requests in the selected range. Receipt is not proof of business completion.",
    ),
    stat(
        "Largest source share",
        6,
        0,
        f'100 * max(sum by (source) (increase(soma_webhook_requests_total{{{SOURCE_FILTER}}}[$__range]))) / scalar(clamp_min({TOTAL_INGRESS}, 1))',
        "Share of selected traffic generated by the largest source.",
        unit="percent",
        decimals=1,
    ),
    stat(
        "Slack share",
        12,
        0,
        '100 * sum(increase(soma_webhook_requests_total{source="slack"}[$__range])) / scalar(clamp_min(sum(increase(soma_webhook_requests_total[$__range])), 1))',
        "Slack requests as a percentage of all webhook ingress, independent of the source filter.",
        unit="percent",
        decimals=1,
    ),
    stat(
        "Ingress exception rate",
        18,
        0,
        f'100 * (sum(increase(soma_webhook_requests_total{{{SOURCE_FILTER}, outcome=~"rejected|failed"}}[$__range])) or vector(0)) / scalar(clamp_min({TOTAL_INGRESS}, 1))',
        "Rejected or failed receipts divided by all selected webhook requests.",
        unit="percent",
        decimals=2,
        thresholds=[{"color": "green"}, {"color": "yellow", "value": 1}, {"color": "red", "value": 5}],
    ),
    pie(
        "Traffic percentage by source",
        0,
        4,
        10,
        10,
        f'sum by (source) (increase(soma_webhook_requests_total{{{SOURCE_FILTER}}}[$__range]))',
        "{{source}}",
        "Exact share of selected ingress by source. Choose a representative business window.",
    ),
]

source_table = table(
    "Source traffic — exact counts and percentages",
    10,
    4,
    14,
    10,
    [
        target(
            f'sum by (source) (increase(soma_webhook_requests_total{{{SOURCE_FILTER}}}[$__range]))',
            ref="A",
            instant=True,
        ),
        target(
            f'100 * sum by (source) (increase(soma_webhook_requests_total{{{SOURCE_FILTER}}}[$__range])) / scalar(clamp_min({TOTAL_INGRESS}, 1))',
            ref="B",
            instant=True,
        ),
        target(
            f'86400 * sum by (source) (increase(soma_webhook_requests_total{{{SOURCE_FILTER}}}[$__range])) / $__range_s',
            ref="C",
            instant=True,
        ),
        target(
            f'30 * 86400 * sum by (source) (increase(soma_webhook_requests_total{{{SOURCE_FILTER}}}[$__range])) / $__range_s',
            ref="D",
            instant=True,
        ),
    ],
    "Observed volume, selected-traffic share, normalized daily rate, and linear 30-day projection.",
)
source_table["transformations"] = [
    {"id": "joinByField", "options": {"byField": "source", "mode": "outer"}},
    {
        "id": "organize",
        "options": {
            "excludeByName": {f"Time {i}": True for i in range(1, 5)},
            "renameByName": {
                "source": "Source",
                "Value #A": "Events",
                "Value #B": "Share",
                "Value #C": "Events/day",
                "Value #D": "30-day projection",
            },
        },
    },
]
source_table["fieldConfig"]["overrides"] = [
    field_override("Events", [{"id": "decimals", "value": 0}]),
    field_override("Share", [{"id": "unit", "value": "percent"}, {"id": "decimals", "value": 1}]),
    field_override("Events/day", [{"id": "decimals", "value": 0}]),
    field_override("30-day projection", [{"id": "decimals", "value": 0}]),
]
source_table["options"]["sortBy"] = [{"displayName": "Events", "desc": True}]
traffic_panels.append(source_table)
traffic_panels.append(
    timeseries(
        "Ingress rate by source",
        0,
        14,
        24,
        8,
        [
            target(
                f'sum by (source) (rate(soma_webhook_requests_total{{{SOURCE_FILTER}}}[$__rate_interval]))',
                "{{source}}",
            )
        ],
        "Source request rate. Spikes here explain changes in traffic percentage and delivery cost.",
    )
)


STORED_SLACK_LOGS = (
    '{service_name="soma-backend-web"} | json '
    '| event="Slack interaction stored"'
)

evidence_panels = [
    stat(
        "Stored interactions",
        0,
        0,
        f"sum(count_over_time({STORED_SLACK_LOGS} [$__range]))",
        "Slack messages that survived filtering and were persisted. Derived from current structured logs.",
        datasource=LOKI,
    ),
    stat(
        "Outside sales route",
        6,
        0,
        'sum(count_over_time({service_name="soma-backend-web"} | json '
        '| event="Skipping Slack lead routing outside sales channel" [$__range]))',
        "Persisted Slack messages for which the matcher deliberately performs no lead routing.",
        datasource=LOKI,
    ),
    stat(
        "Sales-thread matches",
        12,
        0,
        'sum(count_over_time({service_name="soma-backend-web"} | json '
        '| event="Matched Slack interaction via thread mapping" [$__range]))',
        "Slack interactions deterministically associated with a lead through its sales thread.",
        datasource=LOKI,
    ),
    stat(
        "Angie mentions",
        18,
        0,
        'sum(count_over_time({service_name="soma-backend-web"} | json '
        '| event="slack_app_mention_received" [$__range]))',
        "Accepted app mentions that reached the Angie mention handler.",
        datasource=LOKI,
    ),
    text_panel(
        "What current logs prove",
        0,
        4,
        24,
        4,
        "This is the best historical evidence available before the new classifier is deployed. It proves how many messages were stored, routed outside sales, matched to sales threads, and accepted as Angie mentions. It cannot explain every filtered Slack event, so do not treat the remainder as a specific filter category.",
    ),
]

stored_channel_table = table(
    "Stored Slack interactions by channel — current logs",
    0,
    8,
    12,
    11,
    [
        target(
            f"sum by (channel) (count_over_time({STORED_SLACK_LOGS} [$__range]))",
            instant=True,
            datasource=LOKI,
        )
    ],
    "Exact stored-message count per channel in retained logs. Channel IDs without configured aliases remain raw.",
    datasource=LOKI,
)
stored_channel_table["transformations"] = [
    {
        "id": "organize",
        "options": {
            "excludeByName": {"Time": True},
            "renameByName": {
                "channel": "Channel ID",
                "Value #A": "Stored interactions",
            },
        },
    }
]
stored_channel_table["fieldConfig"]["overrides"] = [
    field_override("Stored interactions", [{"id": "decimals", "value": 0}])
]
stored_channel_table["options"]["sortBy"] = [
    {"displayName": "Stored interactions", "desc": True}
]
evidence_panels.append(stored_channel_table)
evidence_panels.append(
    timeseries(
        "Stored Slack message rate by channel — current logs",
        12,
        8,
        12,
        11,
        [
            target(
                f"sum by (channel) (count_over_time({STORED_SLACK_LOGS} [5m]))",
                "{{channel}}",
                datasource=LOKI,
            )
        ],
        "Five-minute stored-message counts by channel. This excludes events filtered before persistence.",
        unit="short",
        datasource=LOKI,
    )
)


slack_panels = [
    stat(
        "Classified Slack events",
        0,
        0,
        SLACK_CLASSIFIED,
        "Valid Slack envelopes classified by the new channel/disposition metric. Not measured before deployment.",
    ),
    stat(
        "Directly useful",
        6,
        0,
        f'100 * sum(increase(soma_slack_events_total{{utility="direct"}}[$__range])) / scalar(clamp_min({SLACK_CLASSIFIED}, 1))',
        "Traffic reaching Angie, sales-thread matching, or an interactive action.",
        unit="percent",
        decimals=1,
        thresholds=[{"color": "red"}, {"color": "yellow", "value": 25}, {"color": "green", "value": 60}],
    ),
    stat(
        "Stored without matcher route",
        12,
        0,
        f'100 * sum(increase(soma_slack_events_total{{utility="passive"}}[$__range])) / scalar(clamp_min({SLACK_CLASSIFIED}, 1))',
        "Messages currently persisted even though the matcher deliberately has no route for their channel.",
        unit="percent",
        decimals=1,
        thresholds=[{"color": "green"}, {"color": "yellow", "value": 10}, {"color": "red", "value": 30}],
    ),
    stat(
        "Classification coverage",
        18,
        0,
        f'100 * {SLACK_CLASSIFIED} / scalar(clamp_min(sum(increase(soma_webhook_requests_total{{source="slack", outcome="accepted"}}[$__range])), 1))',
        "Classified valid Slack envelopes divided by accepted Slack HTTP requests. Treat breakdowns below 95% as incomplete.",
        unit="percent",
        decimals=1,
        thresholds=[{"color": "red"}, {"color": "yellow", "value": 90}, {"color": "green", "value": 95}],
    ),
    text_panel(
        "Coverage and meaning",
        0,
        4,
        24,
        4,
        "**Direct** reaches a current business path. **Stored without matcher route** is real storage work but has no current matching path. **Filtered** is acknowledged and ignored. Channel telemetry begins only after the backend release; use **Classification coverage** before trusting percentages.",
    ),
    pie(
        "Slack traffic by current utility",
        0,
        8,
        8,
        10,
        'sum by (utility) (increase(soma_slack_events_total[$__range]))',
        "{{utility}}",
        "Direct, passive, filtered, and Slack protocol/control traffic.",
    ),
]

channel_table = table(
    "Slack traffic by channel",
    8,
    8,
    16,
    10,
    [
        target('sum by (channel) (increase(soma_slack_events_total[$__range]))', ref="A", instant=True),
        target(
            f'100 * sum by (channel) (increase(soma_slack_events_total[$__range])) / scalar(clamp_min({SLACK_CLASSIFIED}, 1))',
            ref="B",
            instant=True,
        ),
        target('sum by (channel) (increase(soma_slack_events_total{utility="direct"}[$__range]))', ref="C", instant=True),
        target('sum by (channel) (increase(soma_slack_events_total{utility="passive"}[$__range]))', ref="D", instant=True),
        target('sum by (channel) (increase(soma_slack_events_total{utility="filtered"}[$__range]))', ref="E", instant=True),
        target(
            '100 * sum by (channel) (increase(soma_slack_events_total{utility="direct"}[$__range])) / clamp_min(sum by (channel) (increase(soma_slack_events_total[$__range])), 1)',
            ref="F",
            instant=True,
        ),
    ],
    "Per-channel volume and current utility. Unknown channels remain visible by Slack channel ID.",
)
channel_table["transformations"] = [
    {"id": "joinByField", "options": {"byField": "channel", "mode": "outer"}},
    {
        "id": "organize",
        "options": {
            "excludeByName": {f"Time {i}": True for i in range(1, 7)},
            "renameByName": {
                "channel": "Channel",
                "Value #A": "Events",
                "Value #B": "Slack share",
                "Value #C": "Direct",
                "Value #D": "No matcher route",
                "Value #E": "Filtered",
                "Value #F": "Direct %",
            },
        },
    },
]
channel_table["fieldConfig"]["overrides"] = [
    field_override("Events", [{"id": "decimals", "value": 0}]),
    field_override("Slack share", [{"id": "unit", "value": "percent"}, {"id": "decimals", "value": 1}]),
    field_override("Direct", [{"id": "decimals", "value": 0}]),
    field_override("No matcher route", [{"id": "decimals", "value": 0}]),
    field_override("Filtered", [{"id": "decimals", "value": 0}]),
    field_override("Direct %", [{"id": "unit", "value": "percent"}, {"id": "decimals", "value": 1}]),
]
channel_table["options"]["sortBy"] = [{"displayName": "Events", "desc": True}]
slack_panels.append(channel_table)
slack_panels.append(
    timeseries(
        "Slack event rate by channel",
        0,
        18,
        24,
        8,
        [target('sum by (channel) (rate(soma_slack_events_total[$__rate_interval]))', "{{channel}}")],
        "Classified Slack event rate. Use this to find which channel causes a traffic spike.",
    )
)


disposition_panels = [
    pie(
        "Slack disposition percentage",
        0,
        0,
        10,
        11,
        'sum by (disposition) (increase(soma_slack_events_total[$__range]))',
        "{{disposition}}",
        "What the current handler does with valid Slack envelopes.",
    )
]

disposition_table = table(
    "Slack disposition evidence — begins after backend deployment",
    10,
    0,
    14,
    11,
    [
        target(
            'sum by (disposition, utility) (increase(soma_slack_events_total[$__range]))',
            ref="A",
            instant=True,
        ),
        target(
            f'100 * sum by (disposition, utility) (increase(soma_slack_events_total[$__range])) / scalar(clamp_min({SLACK_CLASSIFIED}, 1))',
            ref="B",
            instant=True,
        ),
    ],
    "Exact volume and share for each current Slack decision. This is the evidence for subscription changes.",
)
disposition_table["transformations"] = [
    {"id": "joinByField", "options": {"byField": "disposition", "mode": "outer"}},
    {
        "id": "organize",
        "options": {
            "excludeByName": {"Time 1": True, "Time 2": True},
            "renameByName": {
                "disposition": "Disposition",
                "utility": "Current utility",
                "Value #A": "Events",
                "Value #B": "Share",
            },
        },
    },
]
disposition_table["fieldConfig"]["overrides"] = [
    field_override("Events", [{"id": "decimals", "value": 0}]),
    field_override("Share", [{"id": "unit", "value": "percent"}, {"id": "decimals", "value": 1}]),
]
disposition_table["options"]["sortBy"] = [{"displayName": "Events", "desc": True}]
disposition_panels.append(disposition_table)
disposition_panels.extend(
    [
        timeseries(
            "Slack dispositions over time",
            0,
            11,
            16,
            9,
            [
                target(
                    'sum by (disposition) (rate(soma_slack_events_total[$__rate_interval]))',
                    "{{disposition}}",
                )
            ],
            "Rate by current handler decision. A sudden filtered or passive spike is a subscription/configuration signal.",
        ),
        text_panel(
            "What to change",
            16,
            11,
            8,
            9,
            "**High `stored_without_match_route`:** remove the Slack app from irrelevant channels or route those channels to a cheap archive-only adapter.\n\n**High edits/deletes or unsupported events:** remove those event subscriptions.\n\n**High known bot traffic:** filter before durable delivery.\n\n**Keep:** app mentions, interactive actions, sales-thread messages, and explicitly approved Closing Desk channels.",
        ),
    ]
)


health_panels = [
    stat(
        "Acknowledged",
        0,
        0,
        f'sum(increase(soma_webhook_requests_total{{{SOURCE_FILTER}, outcome="accepted"}}[$__range])) or vector(0)',
        "Successfully acknowledged webhook requests.",
    ),
    stat(
        "Rejected or failed",
        6,
        0,
        f'sum(increase(soma_webhook_requests_total{{{SOURCE_FILTER}, outcome=~"rejected|failed"}}[$__range])) or vector(0)',
        "Ingress exceptions requiring source/signature or server investigation.",
        thresholds=[{"color": "green"}, {"color": "red", "value": 1}],
    ),
    stat(
        "Processing failures",
        12,
        0,
        f'sum(increase(soma_webhook_processing_total{{{SOURCE_FILTER}, outcome="failed"}}[$__range])) or vector(0)',
        "Recorded failures after acknowledgement.",
        thresholds=[{"color": "green"}, {"color": "red", "value": 1}],
    ),
    stat(
        "Peak events/min",
        18,
        0,
        f'max_over_time((sum(rate(soma_webhook_requests_total{{{SOURCE_FILTER}}}[5m])) * 60)[$__range:5m]) or vector(0)',
        "Highest five-minute rolling ingress rate.",
        unit="reqpm",
        decimals=1,
    ),
    timeseries(
        "Webhook acknowledgement p95",
        0,
        4,
        12,
        9,
        [
            target(
                f'histogram_quantile(0.95, sum by (le, source) (rate(soma_webhook_duration_milliseconds_bucket{{{SOURCE_FILTER}}}[$__rate_interval])))',
                "{{source}}",
            )
        ],
        "P95 acknowledgement latency, not end-to-end workflow completion.",
        unit="ms",
    ),
    timeseries(
        "Post-receipt processing outcomes",
        12,
        4,
        12,
        9,
        [
            target(
                f'sum by (source, outcome) (rate(soma_webhook_processing_total{{{SOURCE_FILTER}}}[$__rate_interval]))',
                "{{source}} · {{outcome}}",
            )
        ],
        "Instrumented processing operations can fan out, so this is not a completion ratio against receipts.",
        unit="ops",
    ),
]


reading_panels = [
    text_panel(
        "How to use this dashboard",
        0,
        0,
        24,
        14,
        "### Questions this view answers\n\n1. **Traffic:** Which webhook source owns what percentage of ingress?\n2. **Slack channels:** Which channels create Slack volume?\n3. **Utility:** What reaches a current business path, what is persisted without a matcher route, and what is filtered?\n4. **Action:** Which Slack subscriptions or channel memberships can be removed safely?\n\n### Trust boundary\n\n`Webhook requests` measure HTTP receipts. `Slack events` measure valid payloads classified after signature verification. Channel/disposition data did not exist before this instrumentation release, so historical source totals and Slack breakdowns have different coverage. Trust Slack percentages only when **Classification coverage** is at least 95%.\n\n### Payload privacy\n\nThe Slack metric contains only channel alias/ID, event type, bounded disposition, and utility. It never records message text, user identity, thread ID, event ID, or files.",
    )
]


ALL_TABS = [
    ("Traffic", traffic_panels),
    ("Current Slack evidence", evidence_panels),
    ("Slack channels", slack_panels),
    ("Slack usefulness", disposition_panels),
    ("Delivery health", health_panels),
    ("How to read", reading_panels),
]
PANELS = [item for _, group in ALL_TABS for item in group]


def data_query(raw: dict, default_datasource: dict) -> dict:
    datasource = raw.get("datasource", default_datasource)
    query = {key: value for key, value in raw.items() if key not in {"datasource", "refId"}}
    return {
        "kind": "PanelQuery",
        "spec": {
            "query": {
                "datasource": {"name": datasource["uid"]},
                "group": datasource["type"],
                "kind": "DataQuery",
                "spec": query,
                "version": "v0",
            },
            "refId": raw["refId"],
            "hidden": False,
        },
    }


def transformation(raw: dict) -> dict:
    return {
        "group": raw["id"],
        "kind": "Transformation",
        "spec": {"options": raw.get("options", {})},
    }


def panel_element(raw: dict) -> dict:
    datasource = raw.get("datasource", PROM)
    return {
        "kind": "Panel",
        "spec": {
            "data": {
                "kind": "QueryGroup",
                "spec": {
                    "queries": [data_query(item, datasource) for item in raw.get("targets", [])],
                    "queryOptions": {},
                    "transformations": [
                        transformation(item) for item in raw.get("transformations", [])
                    ],
                },
            },
            "description": raw.get("description", ""),
            "id": raw["id"],
            "links": [],
            "title": raw["title"],
            "vizConfig": {
                "group": raw["type"],
                "kind": "VizConfig",
                "spec": {
                    "fieldConfig": raw.get("fieldConfig", {"defaults": {}, "overrides": []}),
                    "options": raw.get("options", {}),
                },
                "version": "",
            },
        },
    }


def grid_items(group: list[dict]) -> list[dict]:
    top = min(item["gridPos"]["y"] for item in group)
    return [
        {
            "kind": "GridLayoutItem",
            "spec": {
                "element": {"kind": "ElementReference", "name": f"panel-{item['id']}"},
                "height": item["gridPos"]["h"],
                "width": item["gridPos"]["w"],
                "x": item["gridPos"]["x"],
                "y": item["gridPos"]["y"] - top,
            },
        }
        for item in group
    ]


ELEMENTS = {f"panel-{item['id']}": panel_element(item) for item in PANELS}
TABS = [
    {
        "kind": "TabsLayoutTab",
        "spec": {
            "title": title,
            "layout": {"kind": "GridLayout", "spec": {"items": grid_items(group)}},
        },
    }
    for title, group in ALL_TABS
]


dashboard = {
    "apiVersion": "dashboard.grafana.app/v2",
    "kind": "Dashboard",
    "metadata": {
        "annotations": {
            "grafana.app/folder": "fwtfg9",
            "grafana.app/message": "Add dedicated webhook traffic and Slack usefulness view",
        },
        "name": "soma-webhook-traffic",
    },
    "spec": {
        "annotations": [],
        "cursorSync": "Off",
        "description": "Webhook source percentages, Slack per-channel traffic, current utility, filtering opportunities, and delivery health.",
        "editable": True,
        "elements": ELEMENTS,
        "layout": {"kind": "TabsLayout", "spec": {"tabs": TABS}},
        "links": [
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
                "tooltip": "Broader workflow and dependency operations view",
            }
        ],
        "liveNow": False,
        "preload": False,
        "tags": ["soma", "operations", "webhooks", "slack"],
        "timeSettings": {
            "autoRefresh": "30s",
            "autoRefreshIntervals": ["30s", "1m", "5m", "15m", "30m", "1h"],
            "fiscalYearStartMonth": 0,
            "from": "now-24h",
            "hideTimepicker": False,
            "timezone": "browser",
            "to": "now",
        },
        "title": "SOMA Webhook Traffic",
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
