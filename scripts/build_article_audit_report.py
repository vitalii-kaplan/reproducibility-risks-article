#!/usr/bin/env python3
"""Build compact article audit report from current collected audit JSON files."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_FLAGS = Path("data/processed/audit/article_supplementary_llm_flags.json")
DEFAULT_REFERENCES = Path("data/processed/audit/article_reference_llm_classifications.json")
DEFAULT_OUTPUT = Path("data/processed/audit/article_audit_report.json")

FLAG_NAMES = [
    "uses_knime",
    "reports_knime_version",
    "provides_downloadable_knime_workflow_files",
    "provides_workflow_screenshots_or_figures",
    "describes_workflow_or_nodes_in_text",
    "provides_input_data_direct_url",
    "reports_input_data_availability",
    "provides_code_or_scripts",
    "reports_extension_or_plugin_dependencies",
    "reports_extension_installation_source",
]

WORKFLOW_REFERENCE_TYPES = {
    "knime_workflow_direct_file",
    "knime_hub_workflow",
    "myexperiment_workflow",
    "workflow_repository",
    "possible_workflow_supplement",
}

CONFIRMED_OR_POSSIBLE_WORKFLOW_ACCESS = {
    "direct_workflow_available",
    "workflow_landing_page_available",
    "possible_workflow_requires_inspection",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flags", type=Path, default=DEFAULT_FLAGS)
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def repo_relative_script_path() -> str:
    path = Path(__file__).resolve()
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return Path(__file__).name


def reference_is_workflow_relevant(reference: dict[str, Any]) -> bool:
    reference_type = reference.get("reference_type")
    workflow_access = reference.get("workflow_access")

    if reference_type not in WORKFLOW_REFERENCE_TYPES:
        return False
    return workflow_access in CONFIRMED_OR_POSSIBLE_WORKFLOW_ACCESS or (
        workflow_access == "manual_check_required"
    )


def linked_resource(reference: dict[str, Any]) -> dict[str, Any]:
    workflow_access = reference.get("workflow_access", "")
    if workflow_access == "manual_check_required":
        audit_status = "manual_check_required"
    elif workflow_access == "direct_workflow_available":
        audit_status = "confirmed_direct_workflow"
    elif workflow_access == "workflow_landing_page_available":
        audit_status = "confirmed_workflow_landing_page"
    else:
        audit_status = "possible_workflow_requires_inspection"

    return {
        "url": reference.get("url", ""),
        "reference_type": reference.get("reference_type", ""),
        "workflow_access": workflow_access,
        "workflow_form": reference.get("workflow_form", ""),
        "audit_status": audit_status,
        "evidence_quote": reference.get("evidence_quote", ""),
        "reason": reference.get("reason", ""),
        "confidence": reference.get("confidence", ""),
    }


def report_article(
    article: dict[str, Any], references_by_rank: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    rank = article.get("rank")
    meta = article.get("meta", {})
    seed = meta.get("openalex_seed_fields", {})
    references = references_by_rank.get(rank, {}).get("reference_classifications", [])
    linked_resources = [
        linked_resource(reference)
        for reference in references
        if reference_is_workflow_relevant(reference)
    ]

    flags = {name: bool(article.get("flag_audit_fields", {}).get(name, False)) for name in FLAG_NAMES}
    flags["provides_downloadable_knime_workflow_files"] = bool(linked_resources)
    return {
        "rank": rank,
        "article_identifier": meta.get("article_identifier", ""),
        "pdf_file": meta.get("pdf_file", "undefined"),
        "doi": seed.get("doi", ""),
        "title": seed.get("title", ""),
        "publication_year": seed.get("publication_year", ""),
        "flag_audit_fields": flags,
        "linked_resources": linked_resources,
    }


def main() -> int:
    args = parse_args()
    flags = load_json(args.flags)
    references = load_json(args.references)
    references_by_rank = {
        article.get("rank"): article for article in references.get("articles", [])
    }

    articles = [
        report_article(article, references_by_rank)
        for article in sorted(
            flags.get("articles", []),
            key=lambda item: item.get("rank") if item.get("rank") is not None else 10**9,
        )
    ]

    flag_counts = Counter()
    workflow_resource_counts = Counter()
    for article in articles:
        for name, value in article["flag_audit_fields"].items():
            if value is True:
                flag_counts[name] += 1
        if article["linked_resources"]:
            workflow_resource_counts["articles_with_linked_resources"] += 1
            workflow_resource_counts["linked_resources"] += len(article["linked_resources"])
        for resource in article["linked_resources"]:
            workflow_resource_counts[resource["audit_status"]] += 1

    report = {
        "created_at": date.today().isoformat(),
        "created_by": repo_relative_script_path(),
        "source_files": {
            "article_flags": args.flags.as_posix(),
            "reference_classifications": args.references.as_posix(),
        },
        "scope": "Compact article audit report. Flags come from supplementary article-level LLM classification; linked_resources come from workflow-relevant reference-page classifications.",
        "linked_resource_filter": {
            "confirmed_or_possible_workflow_access": sorted(CONFIRMED_OR_POSSIBLE_WORKFLOW_ACCESS),
            "manual_check_required_included_only_for_reference_types": sorted(WORKFLOW_REFERENCE_TYPES),
        },
        "summary": {
            "articles": len(articles),
            "flag_true_counts": dict(flag_counts),
            "workflow_link_counts": dict(workflow_resource_counts),
        },
        "articles": articles,
    }
    write_json(args.output, report)
    print(f"Wrote {len(articles)} article report records to {args.output}.")
    print(f"Articles with linked workflow resources: {workflow_resource_counts['articles_with_linked_resources']}.")
    print(f"Linked workflow resources: {workflow_resource_counts['linked_resources']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
