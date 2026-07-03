#!/usr/bin/env python3
"""Refresh article-audit provenance from extracted article text files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_ASSESSMENT = Path("data/processed/audit/knime_most_cited_article_assessments.json")
DEFAULT_QUESTIONS = Path("data/processed/audit/knime_article_audit_questions.json")
DEFAULT_TEXT_DIR = Path("data/processed/articles")


FLAG_PATTERNS: dict[str, list[str]] = {
    "uses_knime": [
        r"\bKNIME\b",
        r"Konstanz Information Miner",
    ],
    "reports_knime_version": [
        r"\bKNIME\b.{0,120}\b(version|Desktop|Analytics Platform|v[0-9])\b",
        r"\b(version|Desktop|Analytics Platform|v[0-9])\b.{0,120}\bKNIME\b",
        r"\bKNIME\s+[0-9]+(?:\.[0-9]+)+\b",
    ],
    "provides_downloadable_knime_workflow_files": [
        r"workflow.{0,160}(available|download|Supporting Information)",
        r"(available|download|Supporting Information).{0,160}workflow",
        r"myexperiment\.org/workflows",
    ],
    "provides_workflow_screenshots_or_figures": [
        r"(Fig\.|Figure|Supplementary Fig).{0,160}(workflow|KNIME)",
        r"(workflow|KNIME).{0,160}(Fig\.|Figure|Supplementary Fig)",
    ],
    "describes_workflow_or_nodes_in_text": [
        r"\bKNIME\b.{0,160}(workflow|node|nodes|module|modules|pipeline)",
        r"(workflow|node|nodes|module|modules|pipeline).{0,160}\bKNIME\b",
        r"\b(GroupBy|RDKit|Indigo|CDK|Learner|Predictor|X-Partitioner|Normalizer)\b",
    ],
    "provides_input_data_direct_url": [
        r"(training and test data|data|dataset).{0,160}https?://",
        r"https?://[^ ]*(data|dataset|publications-sites|uci)[^ ]*",
    ],
    "reports_input_data_availability": [
        r"(data|dataset|training and test data|Supplementary data).{0,160}(available|repository|download|UCI)",
        r"(available|repository|download|UCI).{0,160}(data|dataset|training and test data|Supplementary data)",
    ],
    "provides_code_or_scripts": [
        r"(source code|code|scripts|public repository).{0,160}(available|github|http)",
        r"(github|http).{0,160}(source code|code|scripts|repository)",
    ],
    "reports_extension_or_plugin_dependencies": [
        r"\b(RDKit|Indigo|CDK|ChemAxon)\b.{0,120}\b(nodes|plug-in|plugin|extension|version|v[0-9])\b",
        r"\b(nodes|plug-in|plugin|extension|version|v[0-9])\b.{0,120}\b(RDKit|Indigo|CDK|ChemAxon)\b",
    ],
    "reports_extension_installation_source": [
        r"(update mechanism|community contributions|Project URL|available via|tech\.knime\.org/community|knime\.org/community)",
    ],
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("._")
    return slug or "article"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, default=DEFAULT_ASSESSMENT)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--text-dir", type=Path, default=DEFAULT_TEXT_DIR)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def rename_line_keys(value: Any) -> None:
    if isinstance(value, dict):
        if "pdf_text_lines" in value and "extracted_text_lines" not in value:
            value["extracted_text_lines"] = value.pop("pdf_text_lines")
        elif "pdf_text_lines" in value:
            value.pop("pdf_text_lines")
        for child in value.values():
            rename_line_keys(child)
    elif isinstance(value, list):
        for child in value:
            rename_line_keys(child)


def text_path_for_article(article: dict[str, Any], text_dir: Path) -> Path | None:
    pdf_file = article.get("pdf_file")
    if not pdf_file:
        return None
    stem = Path(pdf_file).stem
    candidate = text_dir / f"{slugify(stem)}.txt"
    if candidate.exists():
        return candidate
    return None


def normalize_line(line: str) -> str:
    line = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", line)
    return re.sub(r"\s+", " ", line).strip()


def line_window(lines: list[str], index: int, radius: int = 1) -> tuple[str, str]:
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    label = str(start + 1) if start == end - 1 else f"{start + 1}-{end}"
    snippet = " ".join(normalize_line(line) for line in lines[start:end])
    return label, snippet[:500]


def find_support(lines: list[str], flag: str, limit: int = 2) -> list[dict[str, str]]:
    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in FLAG_PATTERNS.get(flag, [])]
    support: list[dict[str, str]] = []
    seen_ranges: set[str] = set()
    for index, line in enumerate(lines):
        if flag in {
            "provides_workflow_screenshots_or_figures",
            "describes_workflow_or_nodes_in_text",
            "reports_extension_or_plugin_dependencies",
        } and index < 10:
            continue
        haystack = normalize_line(line)
        if not haystack:
            continue
        if not any(pattern.search(haystack) for pattern in patterns):
            continue
        label, snippet = line_window(lines, index)
        if label in seen_ranges:
            continue
        seen_ranges.add(label)
        support.append(
            {
                "extracted_text_lines": label,
                "note": f"Extracted text evidence: {snippet}",
            }
        )
        if len(support) >= limit:
            break
    return support


def find_linked_resource_support(
    lines: list[str], urls: list[str], limit: int = 2
) -> list[dict[str, str]]:
    support: list[dict[str, str]] = []
    compact_lines = [normalize_line(line).replace(" ", "") for line in lines]
    for url in urls:
        compact_url = normalize_line(url).replace(" ", "")
        if not compact_url:
            continue
        for index, compact_line in enumerate(compact_lines):
            if compact_url not in compact_line:
                continue
            label, snippet = line_window(lines, index)
            support.append(
                {
                    "extracted_text_lines": label,
                    "note": f"Extracted text evidence for linked resource {url}: {snippet}",
                }
            )
            break
        if len(support) >= limit:
            break
    return support


def has_numeric_line_ref(item: dict[str, str]) -> bool:
    line_ref = item.get("extracted_text_lines", item.get("pdf_text_lines", ""))
    return bool(re.fullmatch(r"\d+(?:-\d+)?", line_ref))


def is_generated_text_support(item: dict[str, str]) -> bool:
    return item.get("note", "").startswith("Extracted text evidence")


def dedupe_support(items: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        line_ref = item.get("extracted_text_lines", item.get("pdf_text_lines", ""))
        key = (line_ref, item.get("note", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def summary_counts(articles: list[dict[str, Any]], flag_names: list[str]) -> dict[str, int]:
    counts = {flag: 0 for flag in flag_names}
    for article in articles:
        audit = article.get("article_audit_fields", {})
        relation = (
            audit.get("description_audit_fields", {}).get("knime_article_relation", "")
        )
        if relation == "about_knime":
            continue
        flags = audit.get("flag_audit_fields", {})
        for flag in flag_names:
            if flags.get(flag) is True:
                counts[flag] += 1
    return counts


def main() -> int:
    args = parse_args()
    assessment = load_json(args.assessment)
    questions = load_json(args.questions)
    rename_line_keys(assessment)
    flag_names = list(questions["flag_questions"].keys())

    updated_articles = 0
    text_backed_flags = 0

    for article in assessment["articles"]:
        audit = article.setdefault("article_audit_fields", {})
        relation = (
            audit.get("description_audit_fields", {}).get("knime_article_relation", "")
        )
        text_path = text_path_for_article(article, args.text_dir)
        if text_path is None:
            article["processed_text_file"] = None
        else:
            updated_articles += 1
            article["processed_text_file"] = text_path.as_posix()

        if relation == "about_knime":
            audit["flag_audit_fields"] = {}
            audit["flag_audit_support"] = {}
            continue

        if text_path is None:
            continue

        lines = text_path.read_text(encoding="utf-8", errors="replace").splitlines()

        flags = audit.setdefault("flag_audit_fields", {})
        support = audit.setdefault("flag_audit_support", {})

        if flags.get("full_text_accessible") is True:
            support["full_text_accessible"] = [
                {
                    "extracted_text_lines": "processed_text_file",
                    "note": f"Extracted article text available: {text_path.as_posix()}",
                }
            ]

        for flag in flag_names:
            if flag == "full_text_accessible" or flags.get(flag) is not True:
                continue
            if flag == "linked_workflow_artifacts_retrievable":
                continue

            existing = [
                item for item in support.get(flag, []) if not is_generated_text_support(item)
            ]
            line_backed = [item for item in existing if has_numeric_line_ref(item)]

            if flag == "provides_input_data_direct_url":
                candidates = find_linked_resource_support(
                    lines, article.get("linked_resources", {}).get("data_urls", [])
                )
            elif flag == "provides_code_or_scripts":
                candidates = find_linked_resource_support(
                    lines, article.get("linked_resources", {}).get("code_urls", [])
                )
                if not candidates:
                    candidates = find_support(lines, flag)
            else:
                candidates = find_support(lines, flag)
            if candidates:
                text_backed_flags += 1

            support[flag] = dedupe_support(
                [
                    *line_backed,
                    *candidates,
                    *[
                        item
                        for item in existing
                        if not has_numeric_line_ref(item)
                        and not str(
                            item.get("extracted_text_lines", item.get("pdf_text_lines", ""))
                        ).startswith("manual_assessment")
                        and item.get("extracted_text_lines", item.get("pdf_text_lines"))
                        != "article_audit_fields"
                    ],
                ]
            )

    assessment["article_text_source"] = {
        "directory": args.text_dir.as_posix(),
        "method": "Generated from local PDFs with scripts/extract_article_texts.py using pdftotext -layout.",
        "articles_with_extracted_text": updated_articles,
    }
    assessment["article_audit_summary_counts"] = summary_counts(
        assessment["articles"], flag_names
    )

    write_json(args.assessment, assessment)
    print(
        f"Updated {updated_articles} articles with extracted text provenance; "
        f"found text-backed support for {text_backed_flags} positive flags."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
