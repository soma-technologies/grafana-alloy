# Grafana as code

Everything in this folder is the source of truth for SOMA's Grafana dashboards and
alert rules. Before this existed, dashboards were generated from scripts on one
laptop and pushed straight to production Grafana — no review, no history, and no
way to tell what was live. That is what this folder fixes.

The generator is authoritative, not the JSON, and never the Grafana UI. If someone
edits a dashboard in the browser, the next publish overwrites it.

## Layout

```
grafana/
  registry.json   the dashboard list — hand-maintained, read by everything else
  dashboards/     generator per dashboard + its generated JSON
  alerts/         alert rule definitions (Grafana provisioning format)
  DASHBOARDS.md   generated: registry joined against live Grafana, plus drift
  METRICS.md      generated: every metric available, by origin, with cardinality
  publish.sh      generate -> validate -> push -> snapshot
```

## Publishing

```bash
export GCX_CONFIG=~/.config/gcx/soma-config.yaml
./grafana/publish.sh                      # all dashboards
./grafana/publish.sh soma_engineering     # one dashboard
```

The script regenerates JSON from the generator, validates it, pushes it, then
renders a PNG. **Always look at the PNG.** Every dashboard bug found while
building these was visible in the snapshot and invisible in the JSON — a green
"Unknown", a `NaN` cell, a percentile pinned flat at the top histogram bucket.

Alert rules are pushed separately:

```bash
for f in grafana/alerts/*.json; do
  python3 -c "import json,sys;[print(json.dumps(r)) for r in json.load(open('$f'))]" |
    while read -r rule; do echo "$rule" > /tmp/rule.json;
      gcx api /api/v1/provisioning/alert-rules -d @/tmp/rule.json; done
done
```

## What is live

`registry.json` is the single source of truth for which dashboards exist and who
owns them. It used to be written out in four places — this README, the publish
script, the inventory generator, and the handoff doc — and they drifted.

Read the generated **[DASHBOARDS.md](DASHBOARDS.md)** for the current list: every
dashboard, its status, panel count, and its panels. It also reports drift in both
directions, so a dashboard created in the UI and never registered shows up as a
finding rather than a surprise.

Statuses: `managed` (generated here), `adopt` (SOMA-specific, should be generated
here), `retire` (safe to delete, decision recorded), `stock` (Grafana Cloud, leave
alone).

Add a dashboard to `registry.json` and nowhere else — `publish.sh` derives what to
publish from it.

## On rebuilding from scratch

Tempting, and mostly wrong. The layout of these dashboards is the cheap part; the
expensive part is a set of corrections that each took evidence to find, and which
a fresh build would reintroduce as false alarms:

- **Absent is not zero.** Null must render grey as unknown, never green. Grafana
  colours a null value using the *base* threshold step, so the base has to be
  neutral and green has to start at 0. Getting this wrong shows "Unknown" on a
  green background, which is worse than no panel.
- **A counter that has never fired is absent, not zero.** Export failures and 5xx
  need `or <denominator> * 0` to render a known zero.
- **A retry is not an error.** Retrying attempts leave span status unset on
  purpose, so they never inflate any span-derived failure ratio.
- **Percentiles saturate.** The top histogram bucket is 10s; a p99 sitting flat at
  10s means the real value is unreadable, not that latency is 10s.
- **Traffic follows the US business day.** SOMA's operators work US Eastern hours
  and volume swings roughly 75x overnight. Absolute freshness thresholds go red
  every night, so freshness is deliberately uncoloured until a per-workflow
  cadence is agreed. Dashboards render in `America/New_York` so the working day
  reads as one block.
- **Replication lag reads 0 when no replica exists.** Every lag panel is paired
  with "Replica attached" for exactly this reason.

Worth doing instead: delete the three proof dashboards, decide `an29kk`'s fate
against `soma-engineering`, and bring `soma-supabase` in here or retire it.

## Adding a dashboard

1. Copy the closest existing generator. They share the same helpers — `stat`,
   `timeseries`, `table`, `text_panel` — and the same Grafana v2 resource envelope.
2. **Use `TabsLayout`. Always** — this is a house rule, not a size threshold. Put
   the answer on the first tab, since that is the one open by default: on
   `soma-operations` that is the action queue. `gen_dashboards.py` reports any
   managed dashboard that is not tabbed as drift, so a `GridLayout` cannot merge
   unnoticed.
3. Give every panel a description that says what it does *not* prove. The
   acknowledgement panels do not prove the business action completed, and saying so
   in the panel is what stops someone reading them as an SLI.
4. Publish, then read the PNG.
