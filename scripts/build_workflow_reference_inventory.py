#!/usr/bin/env python3
"""Build workflow-reference inventory skeleton from the article audit report.

This script does not retrieve workflows and does not test KNIME import or
execution. It creates or refreshes the workflow-reference inventory from
``article_audit_report.json`` and preserves existing manual retrieval/opening
results for matching article ranks.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_REPORT = Path("data/processed/audit/article_audit_report.json")
DEFAULT_EXISTING = Path("data/processed/audit/knime_downloadable_workflow_references.json")
DEFAULT_OUTPUT = Path("data/processed/audit/knime_downloadable_workflow_references.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--existing", type=Path, default=DEFAULT_EXISTING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--drop-extra-existing-records",
        action="store_true",
        help="Discard existing manual records whose rank is no longer present in article_audit_report linked_resources.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_existing(path: Path) -> dict[str, Any]:
    return load_json(path) if path.exists() else {"records": []}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def doi_safe(doi: str) -> str:
    doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    doi = doi.strip().lower()
    if not doi:
        return "no_doi"
    return re.sub(r"[^a-z0-9._-]+", "_", doi).strip("_") or "no_doi"


def article_directory(article: dict[str, Any], existing: dict[str, Any] | None) -> str:
    existing_directory = (
        (existing or {}).get("download_result", {}).get("directory")
    )
    if existing_directory:
        return str(existing_directory)
    return f"data/original/workflows/{article.get('rank')}_{doi_safe(str(article.get('doi', '')))}"


def workflow_reference(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": resource.get("reference_type", ""),
        "url": resource.get("url", ""),
        "workflow_access": resource.get("workflow_access", ""),
        "workflow_form": resource.get("workflow_form", ""),
        "audit_status": resource.get("audit_status", ""),
        "confidence": resource.get("confidence", ""),
        "reason": resource.get("reason", ""),
    }


def default_download_result(article: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    existing_result = (existing or {}).get("download_result")
    if isinstance(existing_result, dict) and existing_result:
        return existing_result
    return {
        "directory": article_directory(article, existing),
        "status": "not_attempted_in_current_workflow_download_pass",
        "downloaded_files": [],
        "workflow_files_found": [],
        "notes": "Initialized from data/processed/audit/article_audit_report.json; manual retrieval has not been recorded yet.",
    }


def inventory_record(article: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    existing = existing or {}
    record = {
        "rank": article.get("rank"),
        "title": article.get("title", ""),
        "doi": article.get("doi", ""),
        "workflow_artifact_status": "workflow_reference_in_article_audit_report",
        "workflow_references": [
            workflow_reference(resource)
            for resource in article.get("linked_resources", [])
        ],
        "download_result": default_download_result(article, existing),
        "manual_knime_opening_tests": existing.get("manual_knime_opening_tests", []),
    }
    for optional_field in (
        "knime_version",
        "processed_text_file",
        "evidence_extracted_text_lines",
        "notes",
    ):
        if optional_field in existing:
            record[optional_field] = existing[optional_field]
    return record


def has_workflow_files(record: dict[str, Any]) -> bool:
    result = record.get("download_result", {})
    files = result.get("workflow_files_found", [])
    return isinstance(files, list) and bool(files)


def status(record: dict[str, Any]) -> str:
    return str(record.get("download_result", {}).get("status", ""))


def summary_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "article_records_with_downloadable_workflow_references": len(records),
        "downloaded_with_workflow_files_or_workflow_directory": sum(
            1 for record in records if has_workflow_files(record)
        ),
        "repository_downloaded_but_no_workflow_file_found": sum(
            1 for record in records if status(record) == "repository_downloaded_but_no_workflow_file_found"
        ),
        "failed_or_not_obtained": sum(
            1
            for record in records
            if any(token in status(record) for token in ("failed", "not_obtained", "unavailable"))
        ),
        "not_attempted_in_current_workflow_download_pass": sum(
            1
            for record in records
            if status(record) == "not_attempted_in_current_workflow_download_pass"
        ),
        "reported_supplement_or_repository_but_no_knime_workflow_file_confirmed": sum(
            1
            for record in records
            if status(record) == "reported_supplement_or_repository_but_no_knime_workflow_file_confirmed"
        ),
    }


def main() -> int:
    args = parse_args()
    report = load_json(args.report)
    existing = load_existing(args.existing)
    existing_by_rank = {
        record.get("rank"): record
        for record in existing.get("records", [])
        if record.get("rank") is not None
    }

    records = [
        inventory_record(article, existing_by_rank.get(article.get("rank")))
        for article in report.get("articles", [])
        if article.get("linked_resources")
    ]

    extra_existing_records = []
    if not args.drop_extra_existing_records:
        current_ranks = {record.get("rank") for record in records}
        extra_existing_records = [
            record
            for record in existing.get("records", [])
            if record.get("rank") not in current_ranks
        ]
        records.extend(extra_existing_records)

    records.sort(key=lambda record: record.get("rank") if record.get("rank") is not None else 10**9)
    inventory = {
        "created_at": date.today().isoformat(),
        "source_assessment": args.report.as_posix(),
        "selection_rule": "One record per article in article_audit_report.json with non-empty linked_resources; existing manual records outside the current report are retained unless --drop-extra-existing-records is used.",
        "url_status_note": "This inventory is initialized from workflow-relevant report links. Download and KNIME-opening fields require manual update.",
        "retained_extra_existing_records": len(extra_existing_records),
        "records": records,
        "summary_counts": summary_counts(records),
    }
    write_json(args.output, inventory)
    print(f"Wrote {len(records)} workflow-reference records to {args.output}.")
    print(
        "Records with workflow files found: "
        f"{inventory['summary_counts']['downloaded_with_workflow_files_or_workflow_directory']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
