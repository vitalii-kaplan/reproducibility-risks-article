#!/usr/bin/env python3
"""Update article_audit_report.json from downloaded workflow inventory evidence."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORT = Path("data/processed/audit/article_audit_report.json")
DEFAULT_INVENTORY = Path("data/processed/audit/knime_downloadable_workflow_references.json")
DEFAULT_OUTPUT = Path("data/processed/audit/article_audit_report.json")
DEFAULT_WORKFLOW_ROOT = Path("data/original/workflows")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--workflow-root", type=Path, default=DEFAULT_WORKFLOW_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def workflow_files_in_zip(path: Path) -> list[str]:
    found: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                lower = name.lower()
                if lower.endswith("/workflow.knime") or lower.endswith(".knwf"):
                    found.append(f"{path.name}::{name}")
    except zipfile.BadZipFile:
        return []
    return found


def scan_workflow_files(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    found: list[str] = []
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower == "workflow.knime" or lower.endswith(".knwf"):
            found.append(path.relative_to(directory).as_posix())
        elif lower.endswith(".zip"):
            found.extend(workflow_files_in_zip(path))
    return sorted(set(found))


def rank_from_dir(path: Path) -> int | None:
    match = re.match(r"(\d+)_", path.name)
    return int(match.group(1)) if match else None


def local_workflow_files_by_rank(root: Path) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    if not root.exists():
        return result
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        rank = rank_from_dir(directory)
        if rank is None:
            continue
        files = scan_workflow_files(directory)
        if files:
            result[rank] = files
    return result


def inventory_by_rank(inventory: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        int(record["rank"]): record
        for record in inventory.get("records", [])
        if isinstance(record.get("rank"), int)
    }


def inventory_workflow_files(record: dict[str, Any] | None) -> list[str]:
    files = (record or {}).get("download_result", {}).get("workflow_files_found", [])
    return files if isinstance(files, list) else []


def linked_resource_from_inventory(record: dict[str, Any]) -> list[dict[str, Any]]:
    resources = []
    for reference in record.get("workflow_references", []):
        url = reference.get("url", "")
        if not url:
            continue
        resources.append(
            {
                "url": url,
                "reference_type": reference.get("type", ""),
                "workflow_access": reference.get("workflow_access", "direct_workflow_available"),
                "workflow_form": reference.get("workflow_form", ""),
                "audit_status": "downloaded_workflow_artifact",
                "evidence_quote": "",
                "reason": "Workflow artifact evidence is present in data/processed/audit/knime_downloadable_workflow_references.json or data/original/workflows.",
                "confidence": "high",
            }
        )
    return resources


def merge_linked_resources(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url = {item.get("url"): item for item in existing if item.get("url")}
    for item in additions:
        url = item.get("url")
        if not url:
            continue
        if url in by_url:
            by_url[url]["audit_status"] = "downloaded_workflow_artifact"
            by_url[url]["confidence"] = "high"
        else:
            by_url[url] = item
    return list(by_url.values())


def recompute_summary(report: dict[str, Any]) -> None:
    flag_counts = Counter()
    workflow_counts = Counter()
    for article in report.get("articles", []):
        for name, value in article.get("flag_audit_fields", {}).items():
            if value is True:
                flag_counts[name] += 1
        linked = article.get("linked_resources", [])
        if linked:
            workflow_counts["articles_with_linked_resources"] += 1
            workflow_counts["linked_resources"] += len(linked)
        for resource in linked:
            workflow_counts[resource.get("audit_status", "unknown")] += 1
    report.setdefault("summary", {})["articles"] = len(report.get("articles", []))
    report["summary"]["flag_true_counts"] = dict(flag_counts)
    report["summary"]["workflow_link_counts"] = dict(workflow_counts)


def main() -> int:
    args = parse_args()
    report = load_json(args.report)
    inventory = load_json(args.inventory)
    inv_by_rank = inventory_by_rank(inventory)
    local_by_rank = local_workflow_files_by_rank(args.workflow_root)
    downloaded_ranks = {
        rank
        for rank, record in inv_by_rank.items()
        if inventory_workflow_files(record) or local_by_rank.get(rank)
    } | set(local_by_rank)

    updated = 0
    for article in report.get("articles", []):
        rank = article.get("rank")
        if rank not in downloaded_ranks:
            continue
        flags = article.setdefault("flag_audit_fields", {})
        if flags.get("provides_downloadable_knime_workflow_files") is not True:
            updated += 1
        flags["provides_downloadable_knime_workflow_files"] = True
        record = inv_by_rank.get(rank)
        if record:
            article["linked_resources"] = merge_linked_resources(
                article.get("linked_resources", []),
                linked_resource_from_inventory(record),
            )
        article["workflow_artifact_evidence"] = {
            "source": args.inventory.as_posix(),
            "local_workflow_files_found": local_by_rank.get(rank, inventory_workflow_files(record)),
        }

    report["workflow_inventory_backpropagation"] = {
        "updated_at": now_iso(),
        "source_inventory": args.inventory.as_posix(),
        "workflow_root": args.workflow_root.as_posix(),
        "downloaded_ranks": sorted(downloaded_ranks),
        "articles_updated": updated,
    }
    recompute_summary(report)
    write_json(args.output, report)
    print(f"Backpropagated workflow evidence for {len(downloaded_ranks)} ranks.")
    print(f"Articles changed from false to true: {updated}.")
    print(f"Wrote {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
