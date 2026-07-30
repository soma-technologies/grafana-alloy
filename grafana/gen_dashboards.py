#!/usr/bin/env python3
"""Regenerate DASHBOARDS.md from registry.json plus what is live in Grafana.

The dashboard list used to live in four places — the README table, the publish
script, the ownership sets in the widget inventory, and the handoff doc — and they
drifted. registry.json is now the only hand-maintained copy; this reads it, joins
it against live Grafana, and reports anything that appears in one and not the
other.

    GCX_CONFIG=~/.config/gcx/soma-config.yaml python3 grafana/gen_dashboards.py \
        > grafana/DASHBOARDS.md
"""

from __future__ import annotations

import collections
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
REGISTRY = HERE / "registry.json"

STATUS_ORDER = ["managed", "adopt", "retire", "stock"]
STATUS_LABEL = {
    "managed": "Managed in this repo",
    "adopt": "SOMA-specific — adopt into this repo",
    "retire": "Safe to delete",
    "stock": "Grafana Cloud stock / integration — leave alone",
}


def live_dashboards() -> dict[str, dict]:
    result = subprocess.run(
        ["gcx", "dashboards", "list", "-o", "json"], capture_output=True, text=True, check=False
    )
    lines = [line for line in result.stdout.splitlines() if '"class"' not in line]
    blob = "\n".join(lines).strip()
    if not blob:
        raise SystemExit(f"gcx dashboards list returned no JSON:\n{result.stderr}")
    data = json.loads(blob)
    items = data.get("items") if isinstance(data, dict) else data
    search = subprocess.run(
        ["gcx", "api", "/api/search?type=dash-db&limit=200", "-o", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    folders: dict[str, str] = {}
    rows = [line for line in search.stdout.splitlines() if '"class"' not in line]
    if rows:
        for row in json.loads("\n".join(rows)):
            folders[row["uid"]] = row.get("folderTitle") or "ROOT (General)"

    for d in items:
        d["_folder"] = folders.get(d["metadata"]["name"], "?")

    return {
        d["metadata"]["name"]: d
        for d in items
        if d.get("metadata", {}).get("annotations", {}).get("grafana.app/managedBy")
        != "classic-file-provisioning"
    }


def panels(spec: dict) -> list[tuple[str, str, str]]:
    """Return (section, title, viz) per panel, following whichever layout is used."""
    elements = spec.get("elements") or {}
    layout = spec.get("layout") or {}
    kind = layout.get("kind")
    refs: list[tuple[str, str]] = []
    if kind == "TabsLayout":
        for tab in layout["spec"]["tabs"]:
            refs += [
                (tab["spec"]["title"], i["spec"]["element"]["name"])
                for i in tab["spec"]["layout"]["spec"].get("items", [])
            ]
    elif kind == "RowsLayout":
        for row in layout["spec"].get("rows", []):
            refs += [
                (row["spec"].get("title") or "", i["spec"]["element"]["name"])
                for i in row["spec"].get("layout", {}).get("spec", {}).get("items", [])
            ]
    else:
        refs += [("", i["spec"]["element"]["name"]) for i in layout.get("spec", {}).get("items", [])]

    out = []
    for section, ref in refs:
        el = elements.get(ref, {}).get("spec", {})
        out.append((section, el.get("title") or "(untitled)", (el.get("vizConfig") or {}).get("group", "?")))
    return out


def main() -> int:
    registry = json.loads(REGISTRY.read_text())["dashboards"]
    live = live_dashboards()

    by_uid = {entry["uid"]: entry for entry in registry}
    panel_map = {uid: panels(board.get("spec", {})) for uid, board in live.items()}

    missing_from_registry = sorted(set(live) - set(by_uid))
    missing_from_grafana = sorted(uid for uid in by_uid if uid not in live)

    # House rule: every dashboard generated here uses the modern tabbed layout.
    not_tabbed = sorted(
        uid
        for uid, entry in by_uid.items()
        if entry["status"] == "managed"
        and uid in live
        and (live[uid].get("spec", {}).get("layout") or {}).get("kind") != "TabsLayout"
    )
    wrong_folder = sorted(
        (uid, entry["folder"], live[uid].get("_folder", "?"))
        for uid, entry in by_uid.items()
        if uid in live and entry.get("folder") and live[uid].get("_folder") != entry["folder"]
    )

    types: collections.Counter = collections.Counter()
    titles: dict[str, list[str]] = collections.defaultdict(list)
    for uid, found in panel_map.items():
        for _, title, viz in found:
            types[viz] += 1
            titles[title.strip().lower()].append(uid)

    total_panels = sum(len(v) for v in panel_map.values())

    print("# SOMA dashboards")
    print()
    print(
        f"{len(by_uid)} dashboards registered, {len(live)} live in Grafana, "
        f"{total_panels} panels in total."
    )
    print()
    print("Single source of truth: `registry.json`. Regenerate this file with")
    print("`python3 grafana/gen_dashboards.py > grafana/DASHBOARDS.md`. Do not hand-edit.")
    print()

    if missing_from_registry or missing_from_grafana or not_tabbed or wrong_folder:
        print("## Drift")
        print()
        for uid in missing_from_registry:
            title = live[uid].get("spec", {}).get("title", "?")
            print(f"- **Live but unregistered:** `{uid}` — {title}. Add it to `registry.json`.")
        for uid in missing_from_grafana:
            print(
                f"- **Registered but not live:** `{uid}` — {by_uid[uid]['title']}. "
                "Already deleted, or never published."
            )
        for uid in not_tabbed:
            print(
                f"- **Not tabbed:** `{uid}` — {by_uid[uid]['title']} is generated here but does "
                "not use `TabsLayout`. Every managed dashboard uses tabs."
            )
        for uid, expected, actual in wrong_folder:
            print(
                f"- **Wrong folder:** `{uid}` is in `{actual}`, registry says `{expected}`."
            )
        print()
    else:
        print("No drift: every live dashboard is registered and every registered dashboard is live.")
        print()

    print("## Registry")
    print()
    print("| Dashboard | UID | Status | Audience | Panels | Generator |")
    print("|---|---|---|---|---|---|")
    for status in STATUS_ORDER:
        for entry in sorted(registry, key=lambda e: e["title"]):
            if entry["status"] != status:
                continue
            uid = entry["uid"]
            count = len(panel_map.get(uid, [])) or "—"
            generator = f"`{entry['generator']}`" if entry["generator"] else "—"
            print(
                f"| {entry['title']} | `{uid}` | {status} | {entry['audience']} "
                f"| {count} | {generator} |"
            )
    print()

    print("## Panel types in use")
    print()
    print("| Type | Count |")
    print("|---|---|")
    for viz, count in types.most_common():
        print(f"| `{viz}` | {count} |")
    print()

    duplicates = {
        title: sorted(set(uids))
        for title, uids in titles.items()
        if len(set(uids)) > 1 and title != "(untitled)"
    }
    if duplicates:
        print("## Same panel title on more than one dashboard")
        print()
        print("Stock integration boards overlap curated ones by design, so this is not")
        print("automatically wrong — but check here before adding a panel.")
        print()
        print("| Panel | Dashboards |")
        print("|---|---|")
        for title, uids in sorted(duplicates.items()):
            print(f"| {title} | {', '.join(f'`{u}`' for u in uids)} |")
        print()

    for status in STATUS_ORDER:
        entries = [e for e in registry if e["status"] == status]
        if not entries:
            continue
        print(f"## {STATUS_LABEL[status]}")
        print()
        for entry in sorted(entries, key=lambda e: e["title"]):
            uid = entry["uid"]
            found = panel_map.get(uid, [])
            print(f"### {entry['title']} — `{uid}` ({len(found)} panels)")
            print()
            print(entry["note"])
            print()
            if status != "stock" and found:
                section = None
                for sec, title, viz in found:
                    if sec != section:
                        if sec:
                            print(f"**{sec}**")
                            print()
                        section = sec
                    print(f"- `{viz}` — {title}")
                print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
