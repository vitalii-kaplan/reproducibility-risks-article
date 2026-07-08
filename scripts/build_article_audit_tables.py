#!/usr/bin/env python3
"""Build the top-cited article audit summary table from structured audit flags.

The manuscript keeps the rendered table in LaTeX, but the counts should come
from the audit JSON. This script computes the Table 3 rows from per-article
``flag_audit_fields`` and description-level classification fields, writes the
CSV source under ``article/tables/``, and compares the generated values with
the current LaTeX table.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ASSESSMENT = Path("data/processed/audit/article_assessments.json")
DEFAULT_ARTICLE = Path("article/article.tex")
DEFAULT_OUTPUT_DIR = Path("article/tables")


@dataclass(frozen=True)
class TableRow:
    label: str
    count: int
    share: float
    interpretation: str = ""


TOP_FLAG_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "Uses KNIME",
        "uses_knime",
        "KNIME used as a workflow, tool, interface, or implementation context",
    ),
    (
        "Workflow or nodes described in text",
        "describes_workflow_or_nodes_in_text",
        "Named workflow steps, nodes, modules, or components recorded",
    ),
    (
        "Workflow screenshots or figures",
        "provides_workflow_screenshots_or_figures",
        "Workflow shown visually in article or supplement",
    ),
    ("Reports KNIME version", "reports_knime_version", "Specific KNIME version value found"),
    (
        "Reports downloadable workflows",
        "provides_downloadable_knime_workflow_files",
        "Executable workflow files provided or linked",
    ),
    (
        "Reports extension/plugin dependencies",
        "reports_extension_or_plugin_dependencies",
        "KNIME extension or node-library dependency reported",
    ),
    (
        "Reports extension installation source",
        "reports_extension_installation_source",
        "Update site, project URL, or installation source reported",
    ),
    (
        "Provides code or scripts",
        "provides_code_or_scripts",
        "Code repository, scripts, or software code reported",
    ),
    (
        "Reports input-data availability",
        "reports_input_data_availability",
        "Data availability stated, with or without direct URL",
    ),
    (
        "Direct input-data resource",
        "provides_input_data_direct_url",
        "Direct data URL or resource pointer recorded",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, default=DEFAULT_ASSESSMENT)
    parser.add_argument("--article", type=Path, default=DEFAULT_ARTICLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit with status 1 if generated CSV values differ from article tables.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def description_fields(article: dict[str, Any]) -> dict[str, Any]:
    return article.get("article_audit_fields", {}).get("description_audit_fields", {})


def flag_fields(article: dict[str, Any]) -> dict[str, Any]:
    return article.get("article_audit_fields", {}).get("flag_audit_fields", {})


def relation(article: dict[str, Any]) -> str:
    return str(description_fields(article).get("knime_article_relation", ""))


def flag_count(articles: list[dict[str, Any]], flag_name: str) -> int:
    return sum(1 for article in articles if flag_fields(article).get(flag_name) is True)


def pct(count: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((count / denominator) * 100, 1)


def build_top_table(articles: list[dict[str, Any]]) -> list[TableRow]:
    total = len(articles)
    assessed = sum(1 for article in articles if relation(article) != "not_assessed")
    not_assessed = sum(1 for article in articles if relation(article) == "not_assessed")
    about_knime = sum(1 for article in articles if relation(article) == "about_knime")
    not_use_case = sum(1 for article in articles if relation(article) == "not_a_knime_use_case")

    rows = [
        TableRow(
            "Audit records",
            total,
            pct(total, total),
            "Most-cited KNIME-matching article records selected from OpenAlex",
        ),
        TableRow(
            "Assessed from full text",
            assessed,
            pct(assessed, total),
            "Article text available for manual assessment",
        ),
        TableRow(
            "Not assessed from full text",
            not_assessed,
            pct(not_assessed, total),
            "Full text unavailable at assessment time",
        ),
        TableRow(
            "About KNIME",
            about_knime,
            pct(about_knime, total),
            "Background/platform or extension papers, not deeper workflow-reporting cases",
        ),
        TableRow(
            "Not a KNIME use case",
            not_use_case,
            pct(not_use_case, total),
            "KNIME appears in the record but is not a KNIME-based study",
        ),
    ]

    for label, flag_name, interpretation in TOP_FLAG_ROWS:
        count = flag_count(articles, flag_name)
        rows.append(TableRow(label, count, pct(count, total), interpretation))

    return rows


def write_table(path: Path, rows: list[TableRow], include_interpretation: bool) -> None:
    fieldnames = ["label", "count", "share_percent"]
    if include_interpretation:
        fieldnames.append("interpretation")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            record: dict[str, str | int] = {
                "label": row.label,
                "count": row.count,
                "share_percent": f"{row.share:.1f}",
            }
            if include_interpretation:
                record["interpretation"] = row.interpretation
            writer.writerow(record)


def clean_latex_cell(value: str) -> str:
    value = value.strip()
    value = value.replace(r"\%", "%")
    value = value.replace("--", "--")
    value = re.sub(r"\\[a-zA-Z]+\{([^{}]*)\}", r"\1", value)
    value = re.sub(r"\\[a-zA-Z]+", "", value)
    value = value.replace("{", "").replace("}", "")
    return value.strip()


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
        if line.startswith("Audit category") or line.startswith("Audit flag"):
            continue
        line = line.removesuffix(r"\\").strip()
        cells = [clean_latex_cell(cell) for cell in line.split("&")]
        if len(cells) < 3:
            continue
        try:
            count = int(cells[1])
            share = float(cells[2].replace("%", ""))
        except ValueError:
            continue
        parsed[cells[0]] = (count, share)
    return parsed


def compare_rows(
    table_name: str, generated: list[TableRow], article_rows: dict[str, tuple[int, float]]
) -> list[dict[str, str]]:
    comparison: list[dict[str, str]] = []
    for row in generated:
        article_count, article_share = article_rows.get(row.label, ("", ""))  # type: ignore[assignment]
        count_match = article_count == row.count
        share_match = article_share == row.share
        comparison.append(
            {
                "table": table_name,
                "label": row.label,
                "generated_count": str(row.count),
                "article_count": str(article_count),
                "count_match": str(count_match),
                "generated_share_percent": f"{row.share:.1f}",
                "article_share_percent": "" if article_share == "" else f"{article_share:.1f}",
                "share_match": str(share_match),
            }
        )
    return comparison


def write_comparison(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "table",
        "label",
        "generated_count",
        "article_count",
        "count_match",
        "generated_share_percent",
        "article_share_percent",
        "share_match",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary_count_check(path: Path, data: dict[str, Any], articles: list[dict[str, Any]]) -> None:
    summary_counts = data.get("article_audit_summary_counts", {})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["flag", "generated_true_count", "json_summary_count", "match"],
        )
        writer.writeheader()
        for _, flag_name, _ in TOP_FLAG_ROWS:
            generated = flag_count(articles, flag_name)
            expected = summary_counts.get(flag_name, "")
            writer.writerow(
                {
                    "flag": flag_name,
                    "generated_true_count": generated,
                    "json_summary_count": expected,
                    "match": generated == expected,
                }
            )
        full_text_generated = flag_count(articles, "full_text_accessible")
        writer.writerow(
            {
                "flag": "full_text_accessible",
                "generated_true_count": full_text_generated,
                "json_summary_count": summary_counts.get("full_text_accessible", ""),
                "match": full_text_generated == summary_counts.get("full_text_accessible", ""),
            }
        )


def main() -> int:
    args = parse_args()
    data = load_json(args.assessment)
    articles = data["articles"]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    top_rows = build_top_table(articles)

    top_csv = args.output_dir / "top_cited_article_audit_summary.csv"
    logs_dir = args.output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    comparison_csv = logs_dir / "article_audit_table_comparison.csv"
    summary_check_csv = logs_dir / "article_audit_summary_count_check.csv"

    write_table(top_csv, top_rows, include_interpretation=True)
    write_summary_count_check(summary_check_csv, data, articles)

    article_tex = args.article.read_text(encoding="utf-8")
    comparison_rows = []
    comparison_rows.extend(
        compare_rows(
            "top_cited_article_audit_summary",
            top_rows,
            parse_article_table(article_tex, "tab:top-cited-assessment"),
        )
    )
    write_comparison(comparison_csv, comparison_rows)

    mismatches = [
        row
        for row in comparison_rows
        if row["count_match"] != "True" or row["share_match"] != "True"
    ]
    print(f"Wrote {top_csv}")
    print(f"Wrote {comparison_csv}")
    print(f"Wrote {summary_check_csv}")
    if mismatches:
        print(f"Found {len(mismatches)} table mismatches.")
        for row in mismatches:
            print(
                f"- {row['table']}: {row['label']} generated "
                f"{row['generated_count']} / {row['generated_share_percent']}%, "
                f"article has {row['article_count']} / {row['article_share_percent']}%"
            )
        return 1 if args.fail_on_mismatch else 0

    print("Generated CSV values match the current LaTeX tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
