# AGENTS.md

This repository is the single source of truth for SOMA's shared observability
infrastructure: the Alloy collector, Grafana dashboard generators, generated
dashboard resources, alert rules, dashboard registry, and operator-facing
observability documentation. Application instrumentation remains beside the
application code, but shared Grafana assets must not be created in the backend
repository or only in the Grafana UI.

## Dashboard layout is non-negotiable: use tabs

- Every managed dashboard MUST use Grafana v2 with `TabsLayout` as its top-level
  layout, even when the dashboard currently needs only one tab.
- NEVER publish a managed dashboard whose top-level layout is `GridLayout`,
  `RowsLayout`, or `AutoGridLayout`.
- Put the primary answer or action queue on the first tab. Diagnostics and
  supporting detail belong on later, clearly named tabs.
- A grid is allowed only inside a `TabsLayoutTab` to place that tab's panels.
- Before publishing, generate the JSON and prove that `.spec.layout.kind` is
  exactly `TabsLayout`. Treat any other value as a release-blocking failure.
- Browser-only edits are temporary. Update the generator here, regenerate the
  JSON, validate it, publish it, and inspect the rendered snapshot.

## Source-of-truth boundaries

- `config.alloy` owns telemetry collection, processing, and export.
- `grafana/dashboards/gen_*.py` owns managed dashboard definitions.
- Generated `grafana/dashboards/*_dashboard.json` files are review artifacts;
  their generators are authoritative.
- `grafana/alerts/` owns provisioned alert definitions.
- `grafana/registry.json` is the only hand-maintained dashboard registry.
- `grafana/DASHBOARDS.md` and `grafana/METRICS.md` are generated inventories;
  never hand-edit them.

Preserve unrelated working-tree changes. In particular, do not overwrite the
observability roadmap while consolidating dashboard assets.
