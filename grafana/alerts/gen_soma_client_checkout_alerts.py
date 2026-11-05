#!/usr/bin/env python3
"""Generate the Sign & Pay (client checkout) alert rules.

    python3 grafana/alerts/gen_soma_client_checkout_alerts.py > grafana/alerts/soma_client_checkout_alerts.json

Per-checkout trouble goes to the Ascend payments channel (backend
``settings.ascend_payments_slack_channel``) through the ``soma-ascend-payments``
contact point. Only the canary (Ascend's checkout is broken for everyone) goes to
#engineering-alerts, through ``soma-engineering-all``.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "dashboards"))
from gen_soma_client_checkout_dashboard import events_in  # noqa: E402

DASHBOARD = "https://earnestpuma1431.grafana.net/d/soma-client-checkout"
PAYMENTS = "soma-ascend-payments"
ENGINEERING = "soma-engineering-all"

# US Eastern minute of the day. PromQL clocks are UTC; DST runs from the second
# Sunday of March to the first Sunday of November (day_of_month - day_of_week is
# the date of the latest Sunday).
LAST_SUNDAY = "(day_of_month() - day_of_week())"
DST = (
    "clamp_max((month() >= bool 4) * (month() <= bool 10)"
    f" + (month() == bool 3) * ({LAST_SUNDAY} >= bool 8)"
    f" + (month() == bool 11) * ({LAST_SUNDAY} < bool 1), 1)"
)
ET_MINUTE = f"((hour() * 60 + minute() + 1140 + 60 * {DST}) % 1440)"


def rule(uid, title, expr, receiver, severity, summary, description):
    return {
        "uid": uid,
        "title": title,
        "ruleGroup": "client-checkout",
        "folderUID": "fwtfg9",
        "orgID": 1,
        "condition": "C",
        "data": [
            {"datasourceUid": "grafanacloud-prom", "queryType": "", "refId": "A",
             "relativeTimeRange": {"from": 600, "to": 0},
             "model": {"editorMode": "code", "expr": expr, "instant": True, "intervalMs": 1000,
                       "maxDataPoints": 43200, "refId": "A"}},
            {"datasourceUid": "__expr__", "queryType": "", "refId": "C",
             "relativeTimeRange": {"from": 0, "to": 0},
             "model": {"conditions": [{"evaluator": {"params": [0.5], "type": "gt"}}],
                       "expression": "A", "intervalMs": 1000, "maxDataPoints": 43200,
                       "refId": "C", "type": "threshold"}},
        ],  # fmt: skip
        # Every query returns a value (or vector(0)) except the canary-missing one
        # outside its 6:30-noon window, where an empty result means "not checked".
        "noDataState": "OK",
        "execErrState": "Alerting",
        "for": "0s",
        "isPaused": False,
        "annotations": {"summary": summary, "description": description, "runbook_url": DASHBOARD},
        "labels": {"component": "client_checkout", "paging": "false", "service": "soma-backend",
                   "severity": severity, "team": "soma"},
        "notification_settings": {"receiver": receiver, "group_by": ["grafana_folder", "alertname"],
                                  "group_wait": "30s", "group_interval": "5m",
                                  "repeat_interval": "4h"},  # fmt: skip
    }


rules = [
    rule(
        "soma-client-checkout-submitted-not-paid",
        "Sign & Pay: payment submitted, no Ascend paid webhook within 2 h",
        f'{events_in("pay_submitted", "24h", "2h", "26h")} - {events_in("webhook_paid", "26h")}',
        PAYMENTS,
        "critical",
        "{{ $value }} Sign & Pay payment(s) submitted over 2 h ago without a paid webhook",
        "More pay_submitted events 2-26 h ago than webhook_paid events in the last 26 h: "
        "Ascend accepted a payment form but never told us it was paid. Open the checkout "
        "in the Hub and look the program up in Ascend before doing anything else; never "
        "re-run the payment. Counts are events, not checkouts, so one paid fallback can "
        "hide a missing one.",
    ),
    rule(
        "soma-client-checkout-pay-failed",
        "Sign & Pay: payment failed or unknown",
        events_in("pay_failed|unknown", "15m"),
        PAYMENTS,
        "critical",
        "{{ $value }} Sign & Pay payment(s) failed or went unknown in the last 15 min",
        "The payer failed, Ascend's total did not match the signed terms, or a payment "
        "stuck in paying for 15 min was marked unknown. The client was shown Ascend's own "
        "link. An unknown may already be charged: check Ascend before anything is "
        "retried. The backend also posts each checkout to this channel with its id.",
    ),
    rule(
        "soma-client-checkout-canary-failed",
        "Sign & Pay: daily Ascend canary failed",
        events_in("canary_failed", "1h"),
        ENGINEERING,
        "critical",
        "The Sign & Pay canary could not reach Ascend's card step",
        "The daily dry run on a sandbox Ascend link failed before the card step, so the "
        "payer is likely broken for every client (Ascend's checkout changed or is down). "
        "Clients still get Ascend's own link as the fallback. Check the canary logs.",
    ),
    rule(
        "soma-client-checkout-canary-missing",
        "Sign & Pay: no canary_ok by 6:30 am ET",
        f'({events_in("canary_ok", "6h")} < bool 0.5)'
        f" and on() ({ET_MINUTE} >= 390 < 720)",
        ENGINEERING,
        "warning",
        "No Sign & Pay canary_ok since the 6 am ET run",
        "No canary_ok event in the last 6 h, checked from 6:30 am to noon ET: the daily "
        "canary did not run or did not finish, so nobody has checked that Ascend's "
        "checkout still works today. Check the scheduler that runs policy_book/ascend_daily.",
    ),
]

if __name__ == "__main__":
    print(json.dumps(rules, indent=2))
