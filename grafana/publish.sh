#!/usr/bin/env bash
# Generate, validate, push and snapshot SOMA dashboards.
#
#   ./grafana/publish.sh                    # all dashboards
#   ./grafana/publish.sh soma_engineering   # one dashboard
#
# Requires GCX_CONFIG to point at the soma gcx config. Always inspect the PNG it
# writes: every dashboard defect found so far was visible there and invisible in
# the JSON.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

: "${GCX_CONFIG:?set GCX_CONFIG, e.g. ~/.config/gcx/soma-config.yaml}"

# The registry is the only place the dashboard list lives.
mapfile -t dashboards < <(
  python3 -c "
import json, pathlib
registry = json.loads(pathlib.Path('grafana/registry.json').read_text())['dashboards']
for entry in registry:
    if entry['status'] == 'managed':
        print(entry['generator'].removeprefix('gen_').removesuffix('_dashboard.py'))
"
)
if [[ $# -gt 0 ]]; then
  dashboards=("$@")
fi

echo "publishing: ${dashboards[*]}"

snapshots="grafana/dashboards/snapshots"
mkdir -p "$snapshots"

for name in "${dashboards[@]}"; do
  generator="grafana/dashboards/gen_${name}_dashboard.py"
  target="grafana/dashboards/${name}_dashboard.json"
  uid="$(echo "$name" | tr '_' '-')"

  [[ -f "$generator" ]] || { echo "no generator: $generator" >&2; exit 1; }

  echo "==> $name"
  python3 "$generator" > "$target.tmp"
  mv "$target.tmp" "$target"

  gcx resources validate -p "$target" -o json | grep -q '"failures": \[\]' \
    || { echo "validation failed for $name" >&2; gcx resources validate -p "$target"; exit 1; }

  gcx resources push -p "$target"

  GCX_AGENT_MODE=true gcx dashboards snapshot "$uid" \
    --output-dir "$snapshots" --since 24h --width 1920 --theme dark

  echo "    snapshot: $snapshots/$uid.png  <- look at this"
done
