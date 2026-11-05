#!/usr/bin/env python3
"""Generate the Sign & Pay (client checkout) dashboard.

The backend counts every step on one counter, ``soma.client_checkout.events{event}``
(``backend/app/metrics.py``), exported as ``soma_client_checkout_events_total``.
``grafana/alerts/gen_soma_client_checkout_alerts.py`` reuses ``events_in`` below.
"""

import json

from gen_soma_angie_observability_dashboard import (
    COUNT_STEPS,
    ERROR_STEPS,
    grid_items,
    panel_element,
    stat,
    text_panel,
    timeseries,
)

METRIC = "soma_client_checkout_events_total"
EVENTS = [
    # (event, what one count means, does a count mean trouble)
    ("page_view", "a client opened a Sign & Pay link", False),
    ("signed", "a client signed (name, consent, card sealed)", False),
    ("pay_started", "the payer started on Ascend's checkout", False),
    ("pay_submitted", "Ascend accepted the payment form", False),
    ("pay_failed", "the payer failed, total mismatched, or a stuck payment went unknown", True),
    ("fallback_shown", "the client was shown Ascend's own link instead", True),
    ("webhook_received", "a signed Ascend webhook reached Sign & Pay", False),
    ("webhook_paid", "a checkout was marked paid (webhook or Ascend already paid)", False),
    ("webhook_unmatched", "an Ascend webhook matched no checkout", True),
    ("team_emailed", "the team got the result email", False),
    ("canary_ok", "the 6 am canary reached Ascend's card step", False),
    ("canary_failed", "the 6 am canary could not reach Ascend's card step", True),
]


def events_in(event_re, window, offset="", start=None):
    """Count events in ``window`` (ending ``offset`` ago) for ``event=~event_re``.

    ``start`` is ``offset + window`` written as one duration (PromQL offsets
    take no arithmetic); it defaults to ``window`` when there is no offset.

    ``increase()`` drops a new series' first count, so one checkout or canary a day
    would read 0: a series born in the window adds its ``last_over_time`` value (a
    process that died in the window still counts). "Born" looks back 1 h, so a
    telemetry gap at the window start does not re-count an old series' total.
    """
    sel = f'{METRIC}{{event=~"{event_re}"}}'
    at = f" offset {offset}" if offset else ""
    before = start or window
    assert start or not offset, "an offset needs its start"
    existed = f"last_over_time({sel}[1h] offset {before})"
    return (
        f"((sum(increase({sel}[{window}]{at}) and {existed}) or vector(0))"
        f" + (sum(last_over_time({sel}[{window}]{at}) unless {existed})"
        " or vector(0)))"
    )


def known(expr):
    """Absent is not zero: render Unknown until the backend has exported the counter."""
    return f"({expr}) and on() (count(last_over_time({METRIC}[$__range])) > 0)"


def placed(item, x, y, w=4, h=4):
    item["gridPos"] = {"x": x, "y": y, "w": w, "h": h}
    return item


def bars(title, y, expr, description):
    chart = timeseries(title, 0, y, expr, "{{event}}", description, "short", draw_style="bars")
    return placed(chart, 0, y, w=24, h=8)


COUNTED = "A count of events, not of distinct checkouts; it does not prove the money moved."
counts = [
    placed(
        stat(name, 0, known(events_in(name, "$__range")), f"Over the range: {meaning}. {COUNTED}",
             decimals=0, thresholds=ERROR_STEPS if bad else COUNT_STEPS[:2]),  # fmt: skip
        (i % 6) * 4,
        (i // 6) * 4,
    )
    for i, (name, meaning, bad) in enumerate(EVENTS)
]
trend = bars(
    "Events per hour", 8, f"sum by (event) (increase({METRIC}[1h]))",
    "Hourly increase per event. A new series' first count is not drawn (increase() needs "
    "two samples); the tiles above include it.",
)  # fmt: skip

RUNBOOK = """\
**Alerts** (`grafana/alerts/soma_client_checkout_alerts.json`):

| Alert | Fires when | Goes to |
|---|---|---|
| Payment submitted, not paid | more `pay_submitted` 2–26 h ago than `webhook_paid` in 26 h | Ascend payments channel |
| Payment failed or unknown | any `pay_failed` / `unknown` in 15 min | Ascend payments channel |
| Canary failed | any `canary_failed` in 1 h | #engineering-alerts |
| Canary missing | no `canary_ok` in 6 h, checked 6:30 am–noon ET | #engineering-alerts |

A `pay_failed` may be a crash mid-payment (`unknown`): **check Ascend before anything is
retried**; the payer never retries a payment itself. Counts are events, not checkouts:
open the lead's checkout in the Hub for the per-checkout state.
"""

payer = [
    bars(
        "Payer and canary outcomes per hour", 0,
        f'sum by (event) (increase({METRIC}{{event=~"pay_.*|canary_.*"}}[1h]))',
        "Payer outcomes and the daily canary. A quiet chart is no traffic, not health.",
    ),  # fmt: skip
    text_panel("Alerts and what to do", 8, RUNBOOK),
]

tabs_spec = [("Checkouts", [*counts, trend]), ("Payer & alerts", payer)]
elements = {
    f"panel-{item['id']}": panel_element(item) for _, group in tabs_spec for item in group
}
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
            "grafana.app/message": "Manage Sign & Pay (client checkout) as code",
        },
        "name": "soma-client-checkout",
    },
    "spec": {
        "annotations": [],
        "cursorSync": "Off",
        "description": "Sign & Pay for Ascend: page views, signatures, payer outcomes, "
        "Ascend webhooks, team emails and the daily canary.",
        "editable": True,
        "elements": elements,
        "layout": {"kind": "TabsLayout", "spec": {"tabs": tabs}},
        "links": [],
        "liveNow": False,
        "preload": False,
        "tags": ["soma", "operations", "payments", "ascend"],
        "timeSettings": {"autoRefresh": "1m", "autoRefreshIntervals": ["30s", "1m", "5m", "15m"],
                         "fiscalYearStartMonth": 0, "from": "now-7d", "hideTimepicker": False,
                         "timezone": "America/New_York", "to": "now"},  # fmt: skip
        "title": "SOMA Sign & Pay",
        "variables": [],
    },
}

if __name__ == "__main__":
    print(json.dumps(dashboard, indent=2))
