#!/usr/bin/env python3
"""Generate the Angie Mac Claude account-pool status dashboard."""

import json

from gen_soma_angie_observability_dashboard import (
    COUNT_STEPS,
    LOKI,
    PROM,
    SUCCESS_STEPS,
    data_query,
    gauge,
    grid_items,
    logs_panel,
    panel,
    panel_element,
    stat,
    target,
    text_panel,
    timeseries,
)

RUNTIME = '{service_name="angie_runtime"} | json'
EVENT = f'{RUNTIME} | body="angie.runtime_event"'
POOL = f'{EVENT} | attributes_area="account_pool"'
SESSION = f'{EVENT} | attributes_area="session"'
API = f'{RUNTIME} | body="angie.api_request"'

POOL_AVAILABILITY_STEPS = [
    {"color": "text"},
    {"color": "red", "value": 0},
    {"color": "orange", "value": 25},
    {"color": "green", "value": 50},
]
UTILIZATION_STEPS = [
    {"color": "text"},
    {"color": "green", "value": 0},
    {"color": "orange", "value": 75},
    {"color": "red", "value": 90},
]
USAGE_STEPS = [
    {"color": "text"},
    {"color": "green", "value": 0},
    {"color": "orange", "value": 75},
    {"color": "red", "value": 95},
]


def field_override(name, properties):
    return {
        "matcher": {"id": "byName", "options": name},
        "properties": properties,
    }


def latest_account_metric(metric):
    """Select the freshest collector instance and remove its restart UUID label."""
    return (
        f"max by (account) ({metric} and on (account, instance) "
        f"topk by (account) (1, timestamp({metric})))"
    )


def account_usage_timeseries(title, x, metric, description):
    result = timeseries(
        title,
        x,
        16,
        latest_account_metric(metric),
        "{{account}}",
        description,
        "percent",
        percent=True,
    )
    result["fieldConfig"]["defaults"]["thresholds"] = {
        "mode": "absolute",
        "steps": USAGE_STEPS,
    }
    return result


def account_capacity_table():
    queries = [
        target(latest_account_metric("angie_account_active_sessions"), instant=True, refId="A"),
        target(
            latest_account_metric("angie_account_capacity_sessions"),
            instant=True,
            refId="B",
        ),
        target(
            "clamp_min("
            f"{latest_account_metric('angie_account_capacity_sessions')} - "
            f"{latest_account_metric('angie_account_active_sessions')}, 0)",
            instant=True,
            refId="C",
        ),
        target(
            latest_account_metric("angie_account_usage_five_hour_percent"),
            instant=True,
            refId="D",
        ),
        target(
            "clamp_min("
            f"{latest_account_metric('angie_account_usage_five_hour_reset_unixtime')} "
            "- time(), 0)",
            instant=True,
            refId="E",
        ),
        target(
            latest_account_metric("angie_account_usage_seven_day_percent"),
            instant=True,
            refId="F",
        ),
        target(
            "clamp_min("
            f"{latest_account_metric('angie_account_usage_seven_day_reset_unixtime')} "
            "- time(), 0)",
            instant=True,
            refId="G",
        ),
        target(
            latest_account_metric("angie_account_cooldown_remaining_seconds"),
            instant=True,
            refId="H",
        ),
        target(latest_account_metric("angie_account_eligible"), instant=True, refId="I"),
        target(latest_account_metric("angie_account_disabled"), instant=True, refId="J"),
        target(
            "clamp_min(time() - "
            f"{latest_account_metric('angie_account_usage_updated_unixtime')}, 0)",
            instant=True,
            refId="K",
        ),
    ]
    result = panel(
        "table",
        "Per-account Claude capacity — current state",
        0,
        5,
        24,
        11,
        queries,
        datasource=PROM,
        description="One row per configured Claude account. The 5h and 7d columns come from "
        "Anthropic's unified rate-limit windows; pool cooldown is Angie's current scheduling "
        "hold. Missing usage means the usage monitor has not produced a sample for that account.",
    )
    result["options"] = {"cellHeight": "sm", "showHeader": True}
    result["transformations"] = [
        {"id": "joinByField", "options": {"byField": "account", "mode": "outer"}},
        {
            "id": "organize",
            "options": {
                "excludeByName": {
                    "__name__": True,
                    "Time": True,
                    **{f"Time {index}": True for index in range(1, 12)},
                },
                "indexByName": {
                    "account": 0,
                    "Value #I": 1,
                    "Value #A": 2,
                    "Value #B": 3,
                    "Value #C": 4,
                    "Value #D": 5,
                    "Value #E": 6,
                    "Value #F": 7,
                    "Value #G": 8,
                    "Value #H": 9,
                    "Value #J": 10,
                    "Value #K": 11,
                },
                "renameByName": {
                    "account": "Account",
                    "Value #A": "Active",
                    "Value #B": "Max",
                    "Value #C": "Available",
                    "Value #D": "5h used",
                    "Value #E": "5h resets in",
                    "Value #F": "7d used",
                    "Value #G": "7d resets in",
                    "Value #H": "Pool cooldown",
                    "Value #I": "Eligible",
                    "Value #J": "Disabled",
                    "Value #K": "Usage sample age",
                },
            },
        },
    ]
    boolean_mapping = {
        "id": "mappings",
        "value": [
            {
                "type": "value",
                "options": {
                    "0": {"text": "No", "color": "red", "index": 0},
                    "1": {"text": "Yes", "color": "green", "index": 1},
                },
            }
        ],
    }
    disabled_mapping = {
        "id": "mappings",
        "value": [
            {
                "type": "value",
                "options": {
                    "0": {"text": "No", "color": "green", "index": 0},
                    "1": {"text": "Yes", "color": "red", "index": 1},
                },
            }
        ],
    }
    result["fieldConfig"]["overrides"] = [
        field_override("Active", [{"id": "decimals", "value": 0}]),
        field_override("Max", [{"id": "decimals", "value": 0}]),
        field_override(
            "Available",
            [
                {"id": "decimals", "value": 0},
                {
                    "id": "thresholds",
                    "value": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "red"},
                            {"color": "orange", "value": 1},
                            {"color": "green", "value": 2},
                        ],
                    },
                },
                {"id": "custom.cellOptions", "value": {"type": "color-text"}},
            ],
        ),
        *[
            field_override(
                field,
                [
                    {"id": "unit", "value": "percent"},
                    {"id": "decimals", "value": 0},
                    {
                        "id": "thresholds",
                        "value": {"mode": "absolute", "steps": USAGE_STEPS},
                    },
                    {"id": "custom.cellOptions", "value": {"type": "color-text"}},
                ],
            )
            for field in ("5h used", "7d used")
        ],
        *[
            field_override(
                field,
                [
                    {"id": "unit", "value": "s"},
                    {"id": "decimals", "value": 0},
                    {"id": "noValue", "value": "—"},
                ],
            )
            for field in (
                "5h resets in",
                "7d resets in",
                "Pool cooldown",
                "Usage sample age",
            )
        ],
        field_override("Eligible", [boolean_mapping]),
        field_override("Disabled", [disabled_mapping]),
    ]
    return result


status = [
    stat(
        "Latest worker heartbeat",
        0,
        f'1000 * max(last_over_time({EVENT} | attributes_area="worker" '
        '| attributes_event="heartbeat" | unwrap attributes_last_heartbeat_unixtime [5m]))',
        "Latest worker heartbeat from the Angie Mac. Unknown means no heartbeat was observed "
        "within five minutes.",
        datasource=LOKI,
        unit="dateTimeFromNow",
        decimals=0,
    ),
    stat(
        "Pool snapshots / 15m",
        6,
        f'sum(count_over_time({POOL} | attributes_event="snapshot" [15m]))',
        "Pool status snapshots observed in the last 15 minutes. A blank value means status is "
        "not being emitted.",
        datasource=LOKI,
        decimals=0,
    ),
    stat(
        "Minimum eligible accounts",
        12,
        f'min(min_over_time({POOL} | attributes_event="snapshot" '
        '| unwrap attributes_eligible_accounts [5m]))',
        "Lowest eligible-account count observed over five minutes; deliberately conservative.",
        datasource=LOKI,
        decimals=0,
        thresholds=[
            {"color": "text"},
            {"color": "red", "value": 0},
            {"color": "orange", "value": 1},
            {"color": "green", "value": 2},
        ],
    ),
    stat(
        "At-capacity accounts",
        18,
        f'max(max_over_time({POOL} | attributes_event="snapshot" '
        '| unwrap attributes_at_capacity_accounts [5m]))',
        "Highest number of accounts reporting at capacity over five minutes.",
        datasource=LOKI,
        decimals=0,
        thresholds=COUNT_STEPS,
    ),
    account_capacity_table(),
    account_usage_timeseries(
        "5-hour usage by account",
        0,
        "angie_account_usage_five_hour_percent",
        "Anthropic five-hour usage percentage for each Claude account. The 95% line is Angie's "
        "default usage-hold threshold.",
    ),
    account_usage_timeseries(
        "7-day usage by account",
        12,
        "angie_account_usage_seven_day_percent",
        "Anthropic seven-day usage percentage for each Claude account. This is independent of "
        "the rolling five-hour window.",
    ),
    timeseries(
        "Available session slots by account",
        0,
        24,
        "clamp_min("
        f"{latest_account_metric('angie_account_capacity_sessions')} - "
        f"{latest_account_metric('angie_account_active_sessions')}, 0)",
        "{{account}}",
        "Configured per-account concurrency minus active sessions. An account can still be "
        "ineligible because of a usage hold even when this value is above zero.",
        "short",
    ),
    timeseries(
        "Pool cooldown remaining by account",
        12,
        24,
        latest_account_metric("angie_account_cooldown_remaining_seconds"),
        "{{account}}",
        "Seconds until Angie will schedule the account again. The table above shows the 5h and "
        "7d reset windows alongside this effective pool hold.",
        "s",
    ),
    text_panel(
        "Reading pool status",
        32,
        "**Read the table first.** `5h used` is the rolling session window and `7d used` is the "
        "weekly window. `Available` is concurrency headroom; `Eligible` is the scheduling "
        "answer after disabled, cooldown, and concurrency checks. Usage at or above **95%** "
        "normally creates a pool hold until the relevant reset.",
    ),
]


sessions = [
    stat(
        "Sessions started",
        0,
        f'sum(count_over_time({SESSION} | attributes_event="started" [$__range]))',
        "Claude pool sessions started in the selected range.",
        datasource=LOKI,
        decimals=0,
    ),
    stat(
        "Sessions completed",
        6,
        f'sum(count_over_time({SESSION} | attributes_event="completed" [$__range]))',
        "Claude pool sessions completed successfully in the selected range.",
        datasource=LOKI,
        decimals=0,
    ),
    stat(
        "Sessions failed",
        12,
        f'sum(count_over_time({SESSION} | attributes_event="failed" [$__range]))',
        "Claude pool sessions that emitted a failed runtime event.",
        datasource=LOKI,
        decimals=0,
        thresholds=COUNT_STEPS,
    ),
    stat(
        "Pool rotations",
        18,
        f'sum(count_over_time({POOL} | attributes_event="rotated" [$__range]))',
        "Account rotations in the selected range.",
        datasource=LOKI,
        decimals=0,
    ),
    gauge(
        "Completed-session ratio",
        0,
        f'100 * sum(count_over_time({SESSION} | attributes_event="completed" [$__range])) '
        f'/ sum(count_over_time({SESSION} | attributes_event=~"completed|failed" '
        '[$__range]))',
        "Completed divided by completed plus failed session runtime events. In-flight sessions "
        "are excluded.",
        datasource=LOKI,
        thresholds=SUCCESS_STEPS,
    ),
    gauge(
        "Pool API success ratio",
        12,
        f'100 * sum(count_over_time({API} | attributes_status_class="2xx" [$__range])) '
        f'/ sum(count_over_time({API} [$__range]))',
        "2xx Angie pool API requests divided by all observed pool API requests.",
        datasource=LOKI,
        thresholds=SUCCESS_STEPS,
    ),
    timeseries(
        "Session lifecycle",
        0,
        13,
        f'sum by (attributes_event, attributes_outcome) (count_over_time({SESSION} [5m]))',
        "{{attributes_event}} · {{attributes_outcome}}",
        "Session lifecycle events in rolling five-minute windows.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
    timeseries(
        "Completed-session p95 duration",
        12,
        13,
        f'quantile_over_time(0.95, {SESSION} | attributes_event="completed" '
        '| unwrap attributes_duration_ms [15m])',
        "p95",
        "P95 duration of sessions completed in each rolling 15-minute window.",
        "ms",
        datasource=LOKI,
    ),
    timeseries(
        "Pool API requests by area and status",
        0,
        21,
        f'sum by (attributes_area, attributes_status_class) (count_over_time({API} [5m]))',
        "{{attributes_area}} · {{attributes_status_class}}",
        "Session creation, status polling, and other pool API requests by status class.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
    timeseries(
        "Pool API p95 latency",
        12,
        21,
        f'quantile_over_time(0.95, {API} | unwrap attributes_duration_ms [5m])',
        "p95",
        "P95 Angie pool API latency in rolling five-minute windows.",
        "ms",
        datasource=LOKI,
    ),
]


runtime = [
    timeseries(
        "Worker heartbeats",
        0,
        0,
        f'sum(count_over_time({EVENT} | attributes_area="worker" '
        '| attributes_event="heartbeat" [5m]))',
        "heartbeats",
        "Worker heartbeats in each rolling five-minute window.",
        "short",
        datasource=LOKI,
        draw_style="bars",
    ),
    timeseries(
        "Process lifecycle",
        12,
        0,
        f'sum by (attributes_event, attributes_outcome) (count_over_time({EVENT} '
        '| attributes_area="process" [5m]))',
        "{{attributes_event}} · {{attributes_outcome}}",
        "Claude process starts and exits.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
    timeseries(
        "Callback delivery outcomes",
        0,
        8,
        f'sum by (attributes_outcome, attributes_reason) (count_over_time({EVENT} '
        '| attributes_area="callback" | attributes_event="delivery" [5m]))',
        "{{attributes_outcome}} · {{attributes_reason}}",
        "Callbacks sent from the Angie Mac to SOMA.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
    timeseries(
        "Account rotations",
        12,
        8,
        f'sum by (attributes_outcome, attributes_reason) (count_over_time({POOL} '
        '| attributes_event="rotated" [5m]))',
        "{{attributes_outcome}} · {{attributes_reason}}",
        "Claude account rotation activity.",
        "short",
        datasource=LOKI,
        draw_style="bars",
        stack=True,
    ),
    logs_panel(
        "Recent pool warnings and errors",
        16,
        '{service_name="angie_runtime"} | json | severity=~"WARN|ERROR"',
        "Warnings and errors emitted by the Angie Mac pool runtime.",
    ),
]


tabs_spec = [
    ("Pool status", status),
    ("Sessions & API", sessions),
    ("Runtime & callbacks", runtime),
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
            "grafana.app/message": "Manage Angie Claude pool status as code",
        },
        "name": "soma-angie-claude-pool",
    },
    "spec": {
        "annotations": [],
        "cursorSync": "Off",
        "description": "Claude account eligibility, cooldown, capacity, sessions, API health, "
        "heartbeats, callbacks, and runtime events from the Angie Mac.",
        "editable": True,
        "elements": elements,
        "layout": {"kind": "TabsLayout", "spec": {"tabs": tabs}},
        "links": [
            {
                "title": "Angie observability",
                "type": "link",
                "url": "/d/soma-angie-observability/soma-angie-observability",
                "targetBlank": False,
                "includeVars": False,
                "keepTime": True,
                "asDropdown": False,
                "icon": "external link",
                "tags": [],
                "tooltip": "Open the complete Angie dashboard",
            },
            {
                "title": "Angie storage",
                "type": "link",
                "url": "/d/soma-storage-observability/soma-storage-observability?"
                "var-workflow=session_archive&var-logical_area=session_transcripts",
                "targetBlank": False,
                "includeVars": False,
                "keepTime": True,
                "asDropdown": False,
                "icon": "external link",
                "tags": [],
                "tooltip": "Open Angie transcript storage diagnostics",
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
                "tooltip": "Open host resource health",
            },
        ],
        "liveNow": False,
        "preload": False,
        "tags": ["soma", "engineering", "angie", "claude", "pool", "observability"],
        "timeSettings": {
            "autoRefresh": "30s",
            "autoRefreshIntervals": ["10s", "30s", "1m", "5m", "15m"],
            "fiscalYearStartMonth": 0,
            "from": "now-6h",
            "hideTimepicker": False,
            "timezone": "America/New_York",
            "to": "now",
        },
        "title": "SOMA Angie — Claude Pool Status",
        "variables": [],
    },
}

print(json.dumps(dashboard, indent=2))
