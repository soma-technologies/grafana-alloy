"""Generate the operator-facing SOMA workflow health dashboard.

One tab per business workflow, driven by span metrics that Alloy derives from
the workflow spans each durable worker emits. A workflow with no observed runs
is reported as unknown, never as a healthy zero.

Fine-grained outcomes (retrying vs failed vs state_update_failed) are span
attributes, not metric labels, so they are reached through the trace drill-down
rather than plotted here.
"""

import json

PROM = {"type": "prometheus", "uid": "grafanacloud-prom"}

WORKFLOWS = [
    {
        "key": "ingestion",
        "title": "Ingestion",
        "span": "ingestion.job.process",
        "blurb": "Tivly, Bold Penguin, Benepath, OpenPhone, Aircall and Gmail leads "
        "landing in Supabase via ingestion_jobs.",
    },
    {
        "key": "claude_session",
        "title": "Claude session",
        "span": "claude_session.job.process",
        "blurb": "Angie Mac/VPS session callbacks processed by the callback worker.",
    },
    {
        "key": "vendor_campaign",
        "title": "Vendor campaign",
        "span": "vendor_campaign.job.process",
        "blurb": "Scheduler-driven campaign syncs and vendor API work.",
    },
    {
        "key": "quote",
        "title": "Quote (Hiscox)",
        "span": "quote.job.process",
        "blurb": "Hiscox GL quote jobs run inside the web service's browser pool.",
    },
    {
        "key": "slack",
        "title": "Slack",
        "span": None,
        "blurb": "Slack events and Closing Desk inbound, handled in-process on web with no "
        "durable job row. The highest-volume workflow in SOMA.",
    },
]

WORKFLOW_KEYS = "|".join(item["key"] for item in WORKFLOWS)

ALL_WORKFLOW_SPANS = f'span_name=~"({WORKFLOW_KEYS})\\\\..*"'

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


def stat(title, x, y, expr, description, *, unit="short", decimals=0, thresholds=None, width=6):
    result = panel(
        "stat", title, x, y, width, 4, [target(expr, instant=True)], description=description
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
        # Absence is unknown, not healthy. Grey, never green.
        "noValue": "Unknown — no runs observed",
        "thresholds": {"mode": "absolute", "steps": thresholds or [{"color": "text"}]},
    }
    return result


def timeseries(title, x, y, width, targets, description, unit, height=8):
    result = panel("timeseries", title, x, y, width, height, targets, description=description)
    result["fieldConfig"]["defaults"] = {
        "unit": unit,
        "custom": {
            "lineWidth": 2,
            "fillOpacity": 12,
            "gradientMode": "opacity",
            "showPoints": "never",
        },
        "noValue": "Unknown — no runs observed",
    }
    result["options"] = {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
        "tooltip": {"mode": "multi", "sort": "desc"},
    }
    return result


def table(title, x, y, width, height, targets, description):
    result = panel("table", title, x, y, width, height, targets, description=description)
    result["options"] = {"showHeader": True, "cellHeight": "sm"}
    result["fieldConfig"]["defaults"] = {"noValue": "No workflow runs observed in this window"}
    return result


def text_panel(title, x, y, width, height, markdown):
    result = panel("text", title, x, y, width, height)
    result["options"] = {"mode": "markdown", "content": markdown}
    return result


def field_override(name, properties):
    return {"matcher": {"id": "byName", "options": name}, "properties": properties}


def by_workflow(inner):
    """Roll a span-name-keyed vector up to one series per workflow."""
    return f'label_replace({inner}, "workflow", "$1", "span_name", "([^.]+)\\\\..*")'


def runs_expr(selector):
    return f"sum(increase(traces_spanmetrics_calls_total{{{selector}}}[$__range]))"


def failures_expr(selector):
    return (
        "sum(increase(traces_spanmetrics_calls_total"
        f'{{{selector}, status_code="STATUS_CODE_ERROR"}}[$__range]))'
    )


def failure_ratio_expr(selector):
    return f"100 * ({failures_expr(selector)} / clamp_min({runs_expr(selector)}, 1))"


def p95_expr(selector):
    return (
        "histogram_quantile(0.95, sum by (le) (rate("
        f"traces_spanmetrics_duration_milliseconds_bucket{{{selector}}}[$__rate_interval])))"
    )


def last_seen_expr(selector):
    return f"time() - max(timestamp(traces_spanmetrics_calls_total{{{selector}}}))"


FAILURE_STEPS = [{"color": "green"}, {"color": "orange", "value": 1}, {"color": "red", "value": 5}]
AGE_STEPS = [{"color": "text"}]


def overview_tab():
    panels = []
    everything = ALL_WORKFLOW_SPANS

    panels.append(
        stat(
            "Workflow runs",
            0,
            0,
            runs_expr(everything),
            "Durable job attempts that reported a terminal outcome in this window.",
        )
    )
    panels.append(
        stat(
            "Terminal failures",
            6,
            0,
            failures_expr(everything),
            "Attempts that ended failed or lost their bookkeeping. Retries are not counted "
            "here: a retry has not ended yet.",
            thresholds=[{"color": "green"}, {"color": "red", "value": 1}],
        )
    )
    panels.append(
        stat(
            "Failure rate",
            12,
            0,
            failure_ratio_expr(everything),
            "Terminal failures over all workflow runs.",
            unit="percent",
            decimals=2,
            thresholds=FAILURE_STEPS,
        )
    )
    panels.append(
        stat(
            "Workflows reporting",
            18,
            0,
            f"count(count by (span_name) (traces_spanmetrics_calls_total{{{everything}}}))",
            f"How many of the {len(WORKFLOWS)} expected workflows produced any run. "
            "Fewer means the rest are unknown, not idle.",
        )
    )

    runs = by_workflow(
        f"increase(traces_spanmetrics_calls_total{{{everything}}}[$__range])"
    )
    errors = by_workflow(
        "increase(traces_spanmetrics_calls_total"
        f'{{{everything}, status_code="STATUS_CODE_ERROR"}}[$__range])'
    )
    seen = by_workflow(f"timestamp(traces_spanmetrics_calls_total{{{everything}}})")
    per_workflow = [
        target(f"sum by (workflow) ({runs})", ref="A", instant=True),
        target(
            f"sum by (workflow) ({errors}) or sum by (workflow) ({runs}) * 0",
            ref="B",
            instant=True,
        ),
        target(f"time() - max by (workflow) ({seen})", ref="C", instant=True),
    ]
    overview = table(
        "Workflow health — observed workflows only",
        0,
        4,
        24,
        9,
        per_workflow,
        "One row per workflow that reported at least one run. A workflow missing from this "
        "table is unknown: either it had no work, or it stopped telling us.",
    )
    overview["transformations"] = [
        {"id": "joinByField", "options": {"byField": "workflow", "mode": "outer"}},
        {
            "id": "organize",
            "options": {
                "excludeByName": {"Time 1": True, "Time 2": True, "Time 3": True},
                "renameByName": {
                    "workflow": "Workflow",
                    "Value #A": "Runs",
                    "Value #B": "Terminal failures",
                    "Value #C": "Last run age",
                },
            },
        },
    ]
    workflow_names = {
        "id": "mappings",
        "value": [
            {
                "type": "value",
                "options": {
                    item["key"]: {"text": item["title"], "index": index}
                    for index, item in enumerate(WORKFLOWS)
                },
            }
        ],
    }
    overview["fieldConfig"]["overrides"] = [
        field_override("Workflow", [workflow_names]),
        field_override("Runs", [{"id": "decimals", "value": 0}]),
        field_override(
            "Terminal failures",
            [
                {"id": "decimals", "value": 0},
                {
                    "id": "thresholds",
                    "value": {
                        "mode": "absolute",
                        "steps": [{"color": "green"}, {"color": "red", "value": 1}],
                    },
                },
                {"id": "custom.cellOptions", "value": {"type": "color-text"}},
            ],
        ),
        field_override(
            "Last run age",
            [
                {"id": "unit", "value": "s"},
                {"id": "decimals", "value": 0},
                {"id": "noValue", "value": "—"},
            ],
        ),
    ]
    panels.append(overview)

    panels.append(
        timeseries(
            "Workflow throughput",
            0,
            13,
            24,
            [
                target(
                    "sum by (workflow) ("
                    + by_workflow(
                        "rate(traces_spanmetrics_calls_total"
                        f"{{{everything}}}[$__rate_interval])"
                    )
                    + ") * 60",
                    legend="{{workflow}}",
                )
            ],
            "Terminal job outcomes per minute, by workflow.",
            "opm",
        )
    )

    expected = "\n".join(f"- **{item['title']}** — {item['blurb']}" for item in WORKFLOWS)
    panels.append(
        text_panel(
            "How to read this dashboard",
            0,
            21,
            24,
            8,
            "### What a workflow run means\n\n"
            "One row of durable work claimed by a worker, from claim to terminal outcome. "
            "It proves the job reached an end state — not that the business result was correct.\n\n"
            "### Expected workflows\n\n"
            f"{expected}\n\n"
            "A workflow absent from the table above is **unknown**, never healthy. Compare this "
            "list against what is reporting.\n\n"
            "### Retries are not failures\n\n"
            "A retrying attempt leaves the span status unset on purpose, so retries never inflate "
            "the failure rate. To separate retrying from failed, open the traces and filter on "
            "`span.result`.\n\n"
            "### Traffic follows the US business day\n\n"
            "SOMA's operators work US Eastern hours. Measured over 24h, hourly processing runs "
            "roughly 800-6,100 operations between 09:00 and 23:00 ET, falling to 50-200 "
            "overnight — about a 75x swing. A quiet workflow at 04:00 ET is expected, not an "
            "incident. Dashboard times are shown in US Eastern so the business day reads as one "
            "block.\n\n"
            "### Known gaps\n\n"
            "Ingress is not joined to processing: a webhook trace ends when the job row is "
            "written, and the worker's trace starts fresh. Slack, document parsing, and Railway "
            "alerts run in-process and have no durable job, so they are not on this dashboard.",
        )
    )
    return panels


def workflow_tab(workflow):
    selector = f'span_name=~"{workflow["key"]}\\\\..*"'
    panels = [
        stat(
            "Runs",
            0,
            0,
            runs_expr(selector),
            f"{workflow['title']} job attempts that reached a terminal outcome.",
        ),
        stat(
            "Terminal failures",
            6,
            0,
            failures_expr(selector),
            "Attempts that ended failed or lost their bookkeeping.",
            thresholds=[{"color": "green"}, {"color": "red", "value": 1}],
        ),
        stat(
            "Failure rate",
            12,
            0,
            failure_ratio_expr(selector),
            "Terminal failures over runs for this workflow.",
            unit="percent",
            decimals=2,
            thresholds=FAILURE_STEPS,
        ),
        stat(
            "Last run age",
            18,
            0,
            last_seen_expr(selector),
            "Time since this workflow last reported a run. Deliberately uncoloured: SOMA's "
            "operators work US Eastern hours, so overnight silence is normal, and no expected "
            "cadence has been agreed per workflow yet. Judge it against the business day, not "
            "against zero.",
            unit="s",
            thresholds=AGE_STEPS,
        ),
        timeseries(
            "Throughput",
            0,
            4,
            12,
            [
                target(
                    f"sum(rate(traces_spanmetrics_calls_total{{{selector}}}[$__rate_interval])) * 60",
                    legend="runs/min",
                )
            ],
            "Terminal outcomes per minute.",
            "opm",
        ),
        timeseries(
            "Latency",
            12,
            4,
            12,
            [
                target(p95_expr(selector), legend="p95"),
                target(
                    "histogram_quantile(0.50, sum by (le) (rate("
                    f"traces_spanmetrics_duration_milliseconds_bucket{{{selector}}}"
                    "[$__rate_interval])))",
                    legend="p50",
                    ref="B",
                ),
            ],
            "How long one attempt takes, claim to terminal outcome.",
            "ms",
        ),
        timeseries(
            "Runs by service instance",
            0,
            12,
            24,
            [
                target(
                    "sum by (service_name) (rate(traces_spanmetrics_calls_total"
                    f"{{{selector}}}[$__rate_interval])) * 60",
                    legend="{{service_name}}",
                )
            ],
            "Which worker service is doing this work. A service dropping to zero while others "
            "continue points at one bad replica rather than the workflow.",
            "opm",
        ),
        text_panel(
            "Drill down",
            0,
            20,
            24,
            6,
            f"### {workflow['title']}\n\n{workflow['blurb']}\n\n"
            "**Separate retrying from failed** — this panel's failure count deliberately excludes "
            "retries. Open Explore against the traces datasource and run:\n\n"
            f"```\n{{ span.workflow.name = \"{workflow['key']}\" && span.result = \"retrying\" }}\n```\n\n"
            "Swap `retrying` for `failed`, `cancelled`, or `state_update_failed`. Every span also "
            "carries `job.id`, `job.type`, and `job.attempt`, so a single job can be followed "
            "across its attempts.\n\n"
            "**Follow one job from its webhook to its worker** — the webhook span records the "
            "job it created, the worker span records the job it ran, so match either side:\n\n"
            "```\n{ .enqueued.job.id = \"<id>\" || .job.id = \"<id>\" }\n```",
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


tabs_spec = [("All workflows", overview_tab())]
for item in WORKFLOWS:
    tabs_spec.append((item["title"], workflow_tab(item)))

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
            "grafana.app/message": "Create SOMA workflow health dashboard",
        },
        "name": "soma-workflow-health",
    },
    "spec": {
        "annotations": [],
        "cursorSync": "Off",
        "description": "Per-workflow health for SOMA's durable job workflows, derived from "
        "workflow spans. Absence of telemetry is reported as unknown, never as success.",
        "editable": True,
        "elements": elements,
        "layout": {"kind": "TabsLayout", "spec": {"tabs": tabs}},
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
                "tooltip": "Webhook receipt and processing overview",
            }
        ],
        "liveNow": False,
        "preload": False,
        "tags": ["soma", "operations", "workflows"],
        "timeSettings": {
            "autoRefresh": "1m",
            "autoRefreshIntervals": ["30s", "1m", "5m", "15m", "30m", "1h"],
            "fiscalYearStartMonth": 0,
            "from": "now-6h",
            "hideTimepicker": False,
            "timezone": "America/New_York",
            "to": "now",
        },
        "title": "SOMA Workflow Health",
        "variables": [],
    },
}


if __name__ == "__main__":
    print(json.dumps(dashboard, indent=2))
