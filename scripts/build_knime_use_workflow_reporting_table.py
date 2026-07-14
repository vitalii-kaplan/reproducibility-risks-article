#!/usr/bin/env python3
"""Build the KNIME-use workflow-reporting table from the audit summary and data.

The source summary contains counts over the complete 100-record audit. This
script verifies those counts, then recalculates every reporting flag within the
subset whose ``uses_knime`` flag is true. Workflow-download outcomes are taken
from the workflow inventory because they are retrieval results, not
article-reporting flags.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ASSESSMENT = Path("data/processed/audit/article_audit_report.json")
DEFAULT_WORKFLOW_REFERENCES = Path("data/processed/audit/knime_downloadable_workflow_references.json")
DEFAULT_TABLE3 = Path("article/tables/top_cited_article_audit_summary.csv")
DEFAULT_ARTICLE = Path("article/article.tex")
DEFAULT_OUTPUT = Path("article/tables/knime_use_workflow_reporting_signals.csv")
DEFAULT_COMPARISON = Path("article/tables/logs/knime_use_workflow_reporting_table_comparison.csv")

TABLE4_LABELS: tuple[tuple[str, str], ...] = (
    ("Uses KNIME", "uses_knime"),
    ("Workflow or nodes described in text", "describes_workflow_or_nodes_in_text"),
    ("Workflow screenshots or figures", "provides_workflow_screenshots_or_figures"),
    ("Reports KNIME version", "reports_knime_version"),
    ("Reports extension/plugin dependencies", "reports_extension_or_plugin_dependencies"),
    ("Reports extension installation source", "reports_extension_installation_source"),
    ("Reports downloadable workflows", "provides_downloadable_knime_workflow_files"),
)


@dataclass(frozen=True)
class TableRow:
    label: str
    count: int
    share: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, default=DEFAULT_ASSESSMENT)
    parser.add_argument("--workflow-references", type=Path, default=DEFAULT_WORKFLOW_REFERENCES)
    parser.add_argument("--table3", type=Path, default=DEFAULT_TABLE3)
    parser.add_argument("--article", type=Path, default=DEFAULT_ARTICLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit with status 1 if generated CSV values differ from JSON or LaTeX.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def flag_fields(article: dict[str, Any]) -> dict[str, Any]:
    if isinstance(article.get("flag_audit_fields"), dict):
        return article["flag_audit_fields"]
    return article.get("article_audit_fields", {}).get("flag_audit_fields", {})


def flag_count(articles: list[dict[str, Any]], flag_name: str) -> int:
    return sum(1 for article in articles if flag_fields(article).get(flag_name) is True)


def pct(count: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((count / denominator) * 100, 1)


def load_table3_counts(path: Path) -> dict[str, int]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return {row["label"]: int(row["count"]) for row in reader}


def workflow_download_count(workflow_references: dict[str, Any]) -> int:
    summary_count = workflow_references.get("summary_counts", {}).get(
        "downloaded_with_workflow_files_or_workflow_directory"
    )
    if isinstance(summary_count, int):
        return summary_count

    return sum(
        1
        for record in workflow_references.get("records", [])
        if record.get("download_result", {}).get("workflow_files_found")
    )


def build_rows(
    table3_counts: dict[str, int],
    articles: list[dict[str, Any]],
    workflow_references: dict[str, Any],
) -> tuple[list[TableRow], list[str]]:
    denominator = table3_counts.get("Uses KNIME")
    if denominator is None:
        raise ValueError("Table 3 CSV does not contain a 'Uses KNIME' row.")

    mismatches: list[str] = []
    knime_use_articles = [
        article for article in articles if flag_fields(article).get("uses_knime") is True
    ]
    if denominator != len(knime_use_articles):
        mismatches.append(
            f"Uses KNIME: source summary count {denominator} differs from "
            f"JSON subset count {len(knime_use_articles)}"
        )

    rows: list[TableRow] = []
    for label, flag_name in TABLE4_LABELS:
        if label not in table3_counts:
            raise ValueError(f"Table 3 CSV does not contain required row {label!r}.")
        table3_count = table3_counts[label]
        all_records_count = flag_count(articles, flag_name)
        if table3_count != all_records_count:
            mismatches.append(
                f"{label}: source summary count {table3_count} differs from "
                f"all-record JSON count {all_records_count}"
            )
        subset_count = flag_count(knime_use_articles, flag_name)
        rows.append(TableRow(label, subset_count, pct(subset_count, denominator)))

        if label == "Reports downloadable workflows":
            downloaded = workflow_download_count(workflow_references)
            rows.append(
                TableRow(
                    "Articles with successfully downloaded workflows",
                    downloaded,
                    pct(downloaded, denominator),
                )
            )
    return rows, mismatches


def write_table(path: Path, rows: list[TableRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["label", "count", "share_percent"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "label": row.label,
                    "count": row.count,
                    "share_percent": f"{row.share:.1f}",
                }
            )


def clean_latex_cell(value: str) -> str:
    value = value.strip().replace(r"\%", "%")
    value = re.sub(r"\\[a-zA-Z]+\{([^{}]*)\}", r"\1", value)
    value = re.sub(r"\\[a-zA-Z]+", "", value)
    return value.replace("{", "").replace("}", "").strip()


def parse_article_table(article_tex: str, label: str) -> dict[str, tuple[int, float]]:
    label_marker = rf"\label{{{label}}}"
    label_index = article_tex.find(label_marker)
    if label_index < 0:
        raise ValueError(f"Could not find LaTeX table label {label!r}")
    end_index = article_tex.find(r"\end{longtable}", label_index)
    if end_index < 0:
        raise ValueError(f"Could not find end of longtable for {label!r}")

    table_text = article_tex[label_index:end_index]
    parsed: dict[str, tuple[int, float]] = {}
    for raw_line in table_text.splitlines():
        line = raw_line.strip()
        if not line or "&" not in line or line.startswith("\\"):
            continue
        if line.startswith("Audit flag"):
            continue
        line = line.removesuffix(r"\\").strip()
        cells = [clean_latex_cell(cell) for cell in line.split("&")]
        if len(cells) < 3:
            continue
        try:
            parsed[cells[0]] = (int(cells[1]), float(cells[2].replace("%", "")))
        except ValueError:
            continue
    return parsed


def write_comparison(path: Path, rows: list[TableRow], article_rows: dict[str, tuple[int, float]]) -> list[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    mismatches: list[str] = []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "label",
                "generated_count",
                "article_count",
                "count_match",
                "generated_share_percent",
                "article_share_percent",
                "share_match",
            ],
        )
        writer.writeheader()
        for row in rows:
            article_count, article_share = article_rows.get(row.label, ("", ""))  # type: ignore[assignment]
            count_match = article_count == row.count
            share_match = article_share == row.share
            if not count_match or not share_match:
                mismatches.append(
                    f"{row.label}: generated {row.count} / {row.share:.1f}%, "
                    f"article has {article_count} / {article_share}%"
                )
            writer.writerow(
                {
                    "label": row.label,
                    "generated_count": row.count,
                    "article_count": article_count,
                    "count_match": count_match,
                    "generated_share_percent": f"{row.share:.1f}",
                    "article_share_percent": "" if article_share == "" else f"{article_share:.1f}",
                    "share_match": share_match,
                }
            )
    return mismatches


def main() -> int:
    args = parse_args()
    data = load_json(args.assessment)
    workflow_references = load_json(args.workflow_references)
    table3_counts = load_table3_counts(args.table3)
    rows, json_mismatches = build_rows(table3_counts, data["articles"], workflow_references)
    write_table(args.output, rows)

    article_tex = args.article.read_text(encoding="utf-8")
    latex_mismatches = write_comparison(
        args.comparison,
        rows,
        parse_article_table(article_tex, "tab:knime-use-assessment"),
    )

    print(f"Wrote {args.output}")
    print(f"Wrote {args.comparison}")
    mismatches = json_mismatches + latex_mismatches
    if mismatches:
        print(f"Found {len(mismatches)} KNIME-use table mismatches.")
        for mismatch in mismatches:
            print(f"- {mismatch}")
        return 1 if args.fail_on_mismatch else 0

    print(
        "Generated KNIME-use table values match the source summary, audit JSON, "
        "the workflow inventory, and the current LaTeX table."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
