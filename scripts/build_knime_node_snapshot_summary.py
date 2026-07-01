#!/usr/bin/env python3
"""Build cross-snapshot KNIME node summary from extracted snapshot tables."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


FIELDNAMES = [
    "snapshot_id",
    "snapshot_kind",
    "snapshot_date",
    "knime_version",
    "source_basis",
    "repos_processed",
    "repos_skipped",
    "plugin_xml_files",
    "repos_with_plugin_xml",
    "registered_nodes",
    "registered_nodesets",
    "registered_total",
    "unique_factory_classes",
    "deprecated_nodes",
    "deprecated_nodesets",
    "deprecated_total",
    "unique_deprecated_factory_classes",
    "deprecated_node_percent",
    "hidden_nodes",
    "hidden_node_percent",
    "deprecated_and_hidden_nodes",
    "node_description_files",
    "description_deprecated_files",
    "description_deprecated_percent",
    "factory_class_mapper_count",
    "migration_rule_count",
    "nodes_added_since_previous",
    "nodes_removed_since_previous",
    "nodes_newly_deprecated_since_previous",
    "nodes_no_longer_deprecated_since_previous",
    "nodes_newly_hidden_since_previous",
    "nodes_no_longer_hidden_since_previous",
    "nodes_category_changed_since_previous",
]

DATE_VERSION_LABELS = {
    "2018-04-03": "KNIME Analytics Platform 3.5.3 source-date anchor",
    "2019-12-05": "KNIME Analytics Platform 4.1.0 source-date anchor",
    "2023-02-22": "KNIME Analytics Platform 5.0.0 source-date anchor",
    "2026-03-03": "KNIME Analytics Platform 5.11.0 source-date anchor",
    "2026-06-28": "current local source-date snapshot",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def bool_value(value: str) -> bool:
    return value.lower() == "true"


def pct(part: int, whole: int) -> str:
    if whole == 0:
        return "0.00"
    return f"{part / whole * 100:.2f}"


def snapshot_kind(snapshot_id: str) -> str:
    if snapshot_id.startswith("date-"):
        return "date"
    if snapshot_id.startswith("tag-"):
        return "tag"
    return ""


def source_basis(kind: str) -> str:
    if kind == "date":
        return "git-date-checkout"
    if kind == "tag":
        return "git-tag-checkout"
    return ""


def knime_version_label(kind: str, snapshot_date: str) -> str:
    if kind == "date":
        return DATE_VERSION_LABELS.get(snapshot_date, "date-based source snapshot")
    return ""


def node_key(row: dict[str, str]) -> str:
    factory = row["factory_class"].strip()
    if factory:
        return factory
    return f'{row["plugin_xml"]}:{row["element"]}:{row["category_path"]}'


def node_state(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    state: dict[str, dict[str, object]] = {}
    for row in rows:
        if row["element"] != "node":
            continue
        key = node_key(row)
        entry = state.setdefault(
            key,
            {
                "deprecated": False,
                "hidden": False,
                "categories": set(),
            },
        )
        entry["deprecated"] = bool(entry["deprecated"]) or bool_value(row["deprecated"])
        entry["hidden"] = bool(entry["hidden"]) or bool_value(row["hidden"])
        categories = entry["categories"]
        assert isinstance(categories, set)
        if row["category_path"]:
            categories.add(row["category_path"])
    return state


def count_checkout_manifest(snapshot_dir: Path) -> tuple[int, int]:
    manifests = sorted(snapshot_dir.glob("checkout*.csv"))
    if not manifests:
        return 0, 0
    rows = read_csv(manifests[0])
    processed = sum(1 for row in rows if row.get("status") == "checked_out")
    skipped = sum(1 for row in rows if row.get("status") != "checked_out")
    return processed, skipped


def build_row(snapshot_dir: Path, previous_nodes: dict[str, dict[str, object]] | None):
    plugin_nodes = read_csv(snapshot_dir / "plugin_nodes.csv")
    descriptions = read_csv(snapshot_dir / "node_descriptions.csv")
    mappers = read_csv(snapshot_dir / "factory_class_mappers.csv")
    rules = read_csv(snapshot_dir / "migration_rules.csv")

    snapshot_id = plugin_nodes[0]["snapshot_id"] if plugin_nodes else snapshot_dir.name
    snapshot_date = plugin_nodes[0]["snapshot_date"] if plugin_nodes else snapshot_dir.name
    kind = snapshot_kind(snapshot_id)

    nodes = [row for row in plugin_nodes if row["element"] == "node"]
    nodesets = [row for row in plugin_nodes if row["element"] == "nodeset"]
    deprecated_nodes = [row for row in nodes if bool_value(row["deprecated"])]
    deprecated_nodesets = [row for row in nodesets if bool_value(row["deprecated"])]
    hidden_nodes = [row for row in nodes if bool_value(row["hidden"])]
    deprecated_and_hidden = [
        row for row in nodes if bool_value(row["deprecated"]) and bool_value(row["hidden"])
    ]
    description_deprecated = [
        row for row in descriptions if bool_value(row["deprecated"])
    ]

    current_nodes = node_state(plugin_nodes)
    current_keys = set(current_nodes)
    previous_keys = set(previous_nodes or {})

    transitions = {
        "nodes_added_since_previous": "",
        "nodes_removed_since_previous": "",
        "nodes_newly_deprecated_since_previous": "",
        "nodes_no_longer_deprecated_since_previous": "",
        "nodes_newly_hidden_since_previous": "",
        "nodes_no_longer_hidden_since_previous": "",
        "nodes_category_changed_since_previous": "",
    }
    if previous_nodes is not None:
        common = current_keys & previous_keys
        transitions = {
            "nodes_added_since_previous": len(current_keys - previous_keys),
            "nodes_removed_since_previous": len(previous_keys - current_keys),
            "nodes_newly_deprecated_since_previous": sum(
                1
                for key in common
                if current_nodes[key]["deprecated"]
                and not previous_nodes[key]["deprecated"]
            ),
            "nodes_no_longer_deprecated_since_previous": sum(
                1
                for key in common
                if previous_nodes[key]["deprecated"]
                and not current_nodes[key]["deprecated"]
            ),
            "nodes_newly_hidden_since_previous": sum(
                1
                for key in common
                if current_nodes[key]["hidden"] and not previous_nodes[key]["hidden"]
            ),
            "nodes_no_longer_hidden_since_previous": sum(
                1
                for key in common
                if previous_nodes[key]["hidden"] and not current_nodes[key]["hidden"]
            ),
            "nodes_category_changed_since_previous": sum(
                1
                for key in common
                if current_nodes[key]["categories"] != previous_nodes[key]["categories"]
            ),
        }

    repos_processed, repos_skipped = count_checkout_manifest(snapshot_dir)

    unique_factory_classes = {row["factory_class"] for row in nodes if row["factory_class"]}
    unique_deprecated_factory_classes = {
        row["factory_class"] for row in deprecated_nodes if row["factory_class"]
    }

    row = {
        "snapshot_id": snapshot_id,
        "snapshot_kind": kind,
        "snapshot_date": snapshot_date,
        "knime_version": knime_version_label(kind, snapshot_date),
        "source_basis": source_basis(kind),
        "repos_processed": repos_processed,
        "repos_skipped": repos_skipped,
        "plugin_xml_files": len({row["plugin_xml"] for row in plugin_nodes}),
        "repos_with_plugin_xml": len({row["repo"] for row in plugin_nodes}),
        "registered_nodes": len(nodes),
        "registered_nodesets": len(nodesets),
        "registered_total": len(nodes) + len(nodesets),
        "unique_factory_classes": len(unique_factory_classes),
        "deprecated_nodes": len(deprecated_nodes),
        "deprecated_nodesets": len(deprecated_nodesets),
        "deprecated_total": len(deprecated_nodes) + len(deprecated_nodesets),
        "unique_deprecated_factory_classes": len(unique_deprecated_factory_classes),
        "deprecated_node_percent": pct(len(deprecated_nodes), len(nodes)),
        "hidden_nodes": len(hidden_nodes),
        "hidden_node_percent": pct(len(hidden_nodes), len(nodes)),
        "deprecated_and_hidden_nodes": len(deprecated_and_hidden),
        "node_description_files": len(descriptions),
        "description_deprecated_files": len(description_deprecated),
        "description_deprecated_percent": pct(
            len(description_deprecated), len(descriptions)
        ),
        "factory_class_mapper_count": len(mappers),
        "migration_rule_count": len(rules),
        **transitions,
    }
    return row, current_nodes


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the processed cross-snapshot KNIME node summary from "
            "data/original/knime_snapshots by default."
        )
    )
    parser.add_argument(
        "snapshots_root",
        nargs="?",
        type=Path,
        default=Path("data/original/knime_snapshots"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/processed/knime_snapshots/knime_node_snapshot_summary.csv"),
    )
    args = parser.parse_args()

    snapshot_dirs = [
        path
        for path in args.snapshots_root.iterdir()
        if path.is_dir() and (path / "plugin_nodes.csv").is_file()
    ]
    snapshot_dirs.sort(key=lambda path: path.name)

    rows = []
    previous_nodes = None
    for snapshot_dir in snapshot_dirs:
        row, previous_nodes = build_row(snapshot_dir, previous_nodes)
        rows.append(row)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote\t{args.out}")
    print(f"snapshots\t{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
