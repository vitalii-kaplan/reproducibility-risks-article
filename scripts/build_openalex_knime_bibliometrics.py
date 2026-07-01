#!/usr/bin/env python3
"""Build processed bibliometric tables from the OpenAlex KNIME dataset."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/original/openalex/works.jsonl")
DEFAULT_OUTPUT = Path("data/processed/openalex")


ABOUT_PATTERNS = [
    r"\bknime\s*[-:]",
    r"\bkonstanz information miner\b",
    r"\bknime\b.*\b(platform|extension|node|nodes|tutorial|workflow system)\b",
    r"\b(knime-cdk|knime4bio|knime analytics platform)\b",
]

USAGE_PATTERNS = [
    r"\busing knime\b",
    r"\bused knime\b",
    r"\bknime was used\b",
    r"\bperformed (using|with|in) knime\b",
    r"\bimplemented (using|with|in) knime\b",
    r"\bdeveloped (using|with|in) knime\b",
    r"\bbuilt (using|with|in) knime\b",
    r"\bknime workflow\b",
    r"\bworkflow[s]?\b.{0,80}\bknime\b",
    r"\bknime\b.{0,80}\bworkflow[s]?\b",
    r"\bknime analytics platform\b",
]


CSV_DIALECT = "unix"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def read_works(path: Path) -> list[dict[str, Any]]:
    works = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                works.append(json.loads(line))
    return works


def abstract_text(work: dict[str, Any]) -> str:
    inverted = work.get("abstract_inverted_index") or {}
    tokens: list[tuple[int, str]] = []
    for token, positions in inverted.items():
        for position in positions:
            tokens.append((position, token))
    tokens.sort(key=lambda item: item[0])
    return " ".join(token for _, token in tokens)


def norm_text(work: dict[str, Any]) -> str:
    parts = [
        work.get("display_name") or "",
        work.get("title") or "",
        abstract_text(work),
        " ".join(k.get("display_name", "") for k in work.get("keywords") or []),
    ]
    return re.sub(r"\s+", " ", " ".join(parts)).lower()


def match_any(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return pattern
    return ""


def classify_knime_role(work: dict[str, Any]) -> tuple[str, bool, str]:
    text = norm_text(work)
    title = (work.get("display_name") or work.get("title") or "").lower()
    about_match = match_any(ABOUT_PATTERNS, text)
    usage_match = match_any(USAGE_PATTERNS, text)

    if about_match and "knime" in title:
        return "about_knime_or_extension", bool(usage_match), about_match
    if usage_match:
        return "uses_knime_as_tool", True, usage_match
    if "knime" in title:
        return "about_or_mentions_knime", False, "knime in title"
    return "ambiguous_match", False, "knime appears in OpenAlex title/abstract search"


def primary_source(work: dict[str, Any]) -> str:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    return source.get("display_name") or location.get("raw_source_name") or ""


def primary_topic_part(work: dict[str, Any], part: str) -> str:
    topic = work.get("primary_topic") or {}
    value = topic.get(part) or {}
    return value.get("display_name") or ""


def top_topic_counts(works: list[dict[str, Any]], part: str, limit: int):
    counter: Counter[str] = Counter()
    for work in works:
        name = primary_topic_part(work, part)
        if name:
            counter[name] += 1
    return counter.most_common(limit)


def has_pdf(work: dict[str, Any]) -> bool:
    if ((work.get("has_content") or {}).get("pdf")):
        return True
    if (work.get("primary_location") or {}).get("pdf_url"):
        return True
    if (work.get("best_oa_location") or {}).get("pdf_url"):
        return True
    return any(bool(loc.get("pdf_url")) for loc in work.get("locations") or [])


def has_fulltext(work: dict[str, Any]) -> bool:
    open_access = work.get("open_access") or {}
    return bool(
        work.get("has_fulltext")
        or open_access.get("any_repository_has_fulltext")
        or open_access.get("oa_url")
        or has_pdf(work)
    )


def is_oa(work: dict[str, Any]) -> bool:
    return bool((work.get("open_access") or {}).get("is_oa"))


def oa_status(work: dict[str, Any]) -> str:
    return (work.get("open_access") or {}).get("oa_status") or "unknown"


def compact_work_row(work: dict[str, Any]) -> dict[str, Any]:
    role, likely_workflow, reason = classify_knime_role(work)
    return {
        "openalex_id": work.get("id") or "",
        "doi": work.get("doi") or "",
        "title": work.get("display_name") or work.get("title") or "",
        "publication_year": work.get("publication_year") or "",
        "publication_date": work.get("publication_date") or "",
        "cited_by_count": work.get("cited_by_count") or 0,
        "source": primary_source(work),
        "domain": primary_topic_part(work, "domain"),
        "field": primary_topic_part(work, "field"),
        "subfield": primary_topic_part(work, "subfield"),
        "primary_topic": (work.get("primary_topic") or {}).get("display_name") or "",
        "is_open_access": is_oa(work),
        "open_access_status": oa_status(work),
        "has_fulltext": has_fulltext(work),
        "has_pdf": has_pdf(work),
        "knime_role": role,
        "likely_uses_knime_workflow_platform": likely_workflow,
        "classification_reason": reason,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, dialect=CSV_DIALECT)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def counter_rows(counter: Counter[str], name_field: str) -> list[dict[str, Any]]:
    total = sum(counter.values())
    return [
        {
            name_field: name,
            "article_count": count,
            "share_percent": round(count / total * 100, 2) if total else 0,
        }
        for name, count in counter.most_common()
    ]


def write_most_cited_md(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Most Cited OpenAlex Articles Matching `KNIME`",
        "",
        "Source: `data/original/openalex/works.jsonl`.",
        "Query: OpenAlex `/works`, `search.title_and_abstract=KNIME`, "
        "`filter=type:article`.",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        title = row["title"]
        year = row["publication_year"]
        citations = row["cited_by_count"]
        source = row["source"] or "Unknown source"
        doi = row["doi"] or row["openalex_id"]
        role = row["knime_role"]
        lines.extend(
            [
                f"## {index}. {title}",
                "",
                f"- Year: {year}",
                f"- Citations: {citations}",
                f"- Source: {source}",
                f"- Link: {doi}",
                f"- Heuristic role: `{role}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    works = read_works(args.input)
    out_dir = args.out_dir

    compact_rows = [compact_work_row(work) for work in works]
    compact_fields = list(compact_rows[0].keys()) if compact_rows else []

    years = Counter(str(row["publication_year"]) for row in compact_rows if row["publication_year"])
    venues = Counter(row["source"] for row in compact_rows if row["source"])
    domains = Counter(row["domain"] for row in compact_rows if row["domain"])
    fields = Counter(row["field"] for row in compact_rows if row["field"])
    oa_statuses = Counter(row["open_access_status"] for row in compact_rows)
    roles = Counter(row["knime_role"] for row in compact_rows)

    top_cited = sorted(
        compact_rows,
        key=lambda row: (int(row["cited_by_count"]), str(row["publication_year"])),
        reverse=True,
    )[:20]
    likely_workflow = [
        row for row in compact_rows if row["likely_uses_knime_workflow_platform"]
    ]

    write_csv(out_dir / "openalex_knime_articles.csv", compact_rows, compact_fields)
    write_csv(
        out_dir / "openalex_knime_articles_by_year.csv",
        [
            {"publication_year": year, "article_count": years[year]}
            for year in sorted(years)
        ],
        ["publication_year", "article_count"],
    )
    write_csv(
        out_dir / "openalex_knime_top_venues.csv",
        counter_rows(venues, "venue"),
        ["venue", "article_count", "share_percent"],
    )
    write_csv(
        out_dir / "openalex_knime_top_domains.csv",
        counter_rows(domains, "domain")[:10],
        ["domain", "article_count", "share_percent"],
    )
    write_csv(
        out_dir / "openalex_knime_top_fields.csv",
        counter_rows(fields, "field")[:10],
        ["field", "article_count", "share_percent"],
    )
    write_csv(
        out_dir / "openalex_knime_most_cited.csv",
        top_cited,
        compact_fields,
    )
    write_csv(
        out_dir / "openalex_knime_likely_workflow_platform.csv",
        likely_workflow,
        compact_fields,
    )

    availability = {
        "total_articles": len(compact_rows),
        "open_access_articles": sum(1 for row in compact_rows if row["is_open_access"]),
        "fulltext_available_articles": sum(1 for row in compact_rows if row["has_fulltext"]),
        "pdf_available_articles": sum(1 for row in compact_rows if row["has_pdf"]),
        "open_access_status_counts": dict(oa_statuses.most_common()),
    }
    classification = {
        "role_counts": dict(roles.most_common()),
        "likely_workflow_platform_articles": len(likely_workflow),
        "method": {
            "about_patterns": ABOUT_PATTERNS,
            "usage_patterns": USAGE_PATTERNS,
            "note": (
                "This is a metadata heuristic over titles, abstracts, and "
                "OpenAlex keywords. It is suitable for triage, not final "
                "manual coding."
            ),
        },
    }
    summary = {
        "source_file": str(args.input),
        "total_articles": len(compact_rows),
        "year_min": min(years) if years else "",
        "year_max": max(years) if years else "",
        "top_venues": counter_rows(venues, "venue")[:10],
        "top_domains": counter_rows(domains, "domain")[:10],
        "top_fields": counter_rows(fields, "field")[:10],
        "availability": availability,
        "classification": classification,
    }
    write_json(out_dir / "openalex_knime_bibliometric_summary.json", summary)
    write_json(out_dir / "openalex_knime_open_access_availability.json", availability)
    write_json(out_dir / "openalex_knime_role_classification_summary.json", classification)
    write_most_cited_md(out_dir / "most_cited.md", top_cited)

    print(f"articles\t{len(compact_rows)}")
    print(f"likely_workflow_platform\t{len(likely_workflow)}")
    print(f"out_dir\t{out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
