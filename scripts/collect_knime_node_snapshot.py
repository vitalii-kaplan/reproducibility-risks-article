#!/usr/bin/env python3
"""Collect full KNIME node-registration metadata for one source snapshot."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path


NODE_EXTENSION_POINT = "org.knime.workbench.repository.nodes"
NODESET_EXTENSION_POINT = "org.knime.workbench.repository.nodesets"
CLASS_MAPPER_EXTENSION_POINT = "org.knime.core.NodeFactoryClassMapper"
MIGRATION_RULE_EXTENSION_POINT = "org.knime.workflow.migration.NodeMigrationRule"


@dataclass(frozen=True)
class PluginNode:
    snapshot_id: str
    snapshot_date: str
    repo: str
    plugin_xml: str
    extension_point: str
    element: str
    factory_class: str
    category_path: str
    deprecated: bool
    hidden: bool


@dataclass(frozen=True)
class NodeDescription:
    snapshot_id: str
    snapshot_date: str
    repo: str
    xml_path: str
    factory_class_guess: str
    name: str
    node_type: str
    deprecated: bool


@dataclass(frozen=True)
class FactoryClassMapper:
    snapshot_id: str
    snapshot_date: str
    repo: str
    plugin_xml: str
    class_mapper: str


@dataclass(frozen=True)
class MigrationRule:
    snapshot_id: str
    snapshot_date: str
    repo: str
    plugin_xml: str
    rule_class: str


def bool_attr(value: str | None) -> bool:
    return value is not None and value.lower() == "true"


def repo_name(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).parts[0]
    except (ValueError, IndexError):
        return ""


def iter_files(root: Path, filename: str | None = None, suffix: str | None = None):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in {".git", "target", "bin", ".metadata"}
        ]
        for fname in filenames:
            if filename and fname != filename:
                continue
            if suffix and not fname.endswith(suffix):
                continue
            yield Path(dirpath) / fname


def parse_xml(path: Path):
    try:
        return ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def factory_class_from_description_path(path: Path) -> str:
    stem = path.name.removesuffix(".xml")
    if not stem.endswith("NodeFactory"):
        return ""
    parts = list(path.with_suffix("").parts)
    try:
        src_index = max(i for i, part in enumerate(parts) if part.startswith("src"))
    except ValueError:
        return stem
    package_parts = parts[src_index + 1 :]
    return ".".join(package_parts)


def collect_plugin_metadata(root: Path, snapshot_id: str, snapshot_date: str):
    nodes: list[PluginNode] = []
    mappers: list[FactoryClassMapper] = []
    rules: list[MigrationRule] = []

    for plugin_xml in iter_files(root, filename="plugin.xml"):
        xml_root = parse_xml(plugin_xml)
        if xml_root is None:
            continue

        repo = repo_name(root, plugin_xml)
        rel_plugin = str(plugin_xml.relative_to(root))

        for extension in xml_root.findall("extension"):
            point = extension.get("point", "")
            for child in list(extension):
                element = local_name(child.tag)

                if point == NODE_EXTENSION_POINT and element == "node":
                    nodes.append(
                        PluginNode(
                            snapshot_id=snapshot_id,
                            snapshot_date=snapshot_date,
                            repo=repo,
                            plugin_xml=rel_plugin,
                            extension_point=point,
                            element=element,
                            factory_class=child.get("factory-class", ""),
                            category_path=child.get("category-path", ""),
                            deprecated=bool_attr(child.get("deprecated")),
                            hidden=bool_attr(child.get("hidden")),
                        )
                    )
                elif point == NODESET_EXTENSION_POINT and element == "nodeset":
                    nodes.append(
                        PluginNode(
                            snapshot_id=snapshot_id,
                            snapshot_date=snapshot_date,
                            repo=repo,
                            plugin_xml=rel_plugin,
                            extension_point=point,
                            element=element,
                            factory_class=child.get("factory-class", ""),
                            category_path=child.get("category-path", ""),
                            deprecated=bool_attr(child.get("deprecated")),
                            hidden=bool_attr(child.get("hidden")),
                        )
                    )
                elif (
                    point == CLASS_MAPPER_EXTENSION_POINT
                    and element == "NodeFactoryClassMapper"
                ):
                    mappers.append(
                        FactoryClassMapper(
                            snapshot_id=snapshot_id,
                            snapshot_date=snapshot_date,
                            repo=repo,
                            plugin_xml=rel_plugin,
                            class_mapper=child.get("classMapper", ""),
                        )
                    )
                elif point == MIGRATION_RULE_EXTENSION_POINT and element == "Rule":
                    rules.append(
                        MigrationRule(
                            snapshot_id=snapshot_id,
                            snapshot_date=snapshot_date,
                            repo=repo,
                            plugin_xml=rel_plugin,
                            rule_class=child.get("class", ""),
                        )
                    )

    return nodes, mappers, rules


def collect_node_descriptions(
    root: Path, snapshot_id: str, snapshot_date: str
) -> list[NodeDescription]:
    descriptions: list[NodeDescription] = []
    for xml_path in iter_files(root, suffix=".xml"):
        if not xml_path.name.endswith("NodeFactory.xml"):
            continue
        xml_root = parse_xml(xml_path)
        if xml_root is None or local_name(xml_root.tag) != "knimeNode":
            continue

        name = ""
        for child in list(xml_root):
            if local_name(child.tag) == "name" and child.text:
                name = child.text.strip()
                break

        descriptions.append(
            NodeDescription(
                snapshot_id=snapshot_id,
                snapshot_date=snapshot_date,
                repo=repo_name(root, xml_path),
                xml_path=str(xml_path.relative_to(root)),
                factory_class_guess=factory_class_from_description_path(xml_path),
                name=name,
                node_type=xml_root.get("type", ""),
                deprecated=bool_attr(xml_root.get("deprecated")),
            )
        )
    return descriptions


def write_csv(path: Path, rows, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_summary(path: Path, snapshot_id: str, snapshot_date: str, rows: dict[str, int]):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["snapshot_id", "snapshot_date", *rows.keys()]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {"snapshot_id": snapshot_id, "snapshot_date": snapshot_date, **rows}
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect KNIME node metadata for one checked-out source snapshot. "
            "By default, output goes to "
            "data/original/knime_snapshots/<snapshot-date>/."
        )
    )
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. Default: "
            "data/original/knime_snapshots/<snapshot-date>"
        ),
    )
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    if not source_root.is_dir():
        print(f"error: source root is not a directory: {source_root}", file=sys.stderr)
        return 2

    plugin_nodes, mappers, rules = collect_plugin_metadata(
        source_root, args.snapshot_id, args.snapshot_date
    )
    descriptions = collect_node_descriptions(
        source_root, args.snapshot_id, args.snapshot_date
    )

    registered_nodes = [n for n in plugin_nodes if n.element == "node"]
    registered_nodesets = [n for n in plugin_nodes if n.element == "nodeset"]
    deprecated_nodes = [n for n in registered_nodes if n.deprecated]
    hidden_nodes = [n for n in registered_nodes if n.hidden]
    deprecated_nodesets = [n for n in registered_nodesets if n.deprecated]
    deprecated_descriptions = [d for d in descriptions if d.deprecated]
    unique_deprecated_factories = {n.factory_class for n in deprecated_nodes if n.factory_class}

    out_dir = args.out_dir or Path(
        "data/original/knime_snapshots"
    ) / args.snapshot_date
    write_csv(
        out_dir / "plugin_nodes.csv",
        plugin_nodes,
        [
            "snapshot_id",
            "snapshot_date",
            "repo",
            "plugin_xml",
            "extension_point",
            "element",
            "factory_class",
            "category_path",
            "deprecated",
            "hidden",
        ],
    )
    write_csv(
        out_dir / "node_descriptions.csv",
        descriptions,
        [
            "snapshot_id",
            "snapshot_date",
            "repo",
            "xml_path",
            "factory_class_guess",
            "name",
            "node_type",
            "deprecated",
        ],
    )
    write_csv(
        out_dir / "factory_class_mappers.csv",
        mappers,
        ["snapshot_id", "snapshot_date", "repo", "plugin_xml", "class_mapper"],
    )
    write_csv(
        out_dir / "migration_rules.csv",
        rules,
        ["snapshot_id", "snapshot_date", "repo", "plugin_xml", "rule_class"],
    )

    summary = {
        "plugin_xml_registered_nodes": len(registered_nodes),
        "plugin_xml_deprecated_nodes": len(deprecated_nodes),
        "plugin_xml_unique_deprecated_factory_classes": len(unique_deprecated_factories),
        "plugin_xml_hidden_nodes": len(hidden_nodes),
        "plugin_xml_registered_nodesets": len(registered_nodesets),
        "plugin_xml_deprecated_nodesets": len(deprecated_nodesets),
        "node_description_files": len(descriptions),
        "node_description_deprecated_files": len(deprecated_descriptions),
        "factory_class_mappers": len(mappers),
        "migration_rules": len(rules),
    }
    write_summary(out_dir / "summary.csv", args.snapshot_id, args.snapshot_date, summary)

    print(f"snapshot_id\t{args.snapshot_id}")
    print(f"snapshot_date\t{args.snapshot_date}")
    for key, value in summary.items():
        print(f"{key}\t{value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
