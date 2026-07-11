#!/usr/bin/env python3
"""Collect article metadata and normalized URLs from processed article HTML.

This is intentionally narrower than the article-audit scripts. It does not
classify URLs, infer article-audit fields, read the curated audit, or use an
LLM. It only joins the OpenAlex seed table to the local article registry,
matches processed GROBID HTML by registry key, and collects normalized URLs
from HTML/TEI text.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from old_audit_assessments_deterministic import (
    UNDEFINED,
    linked_resources_from_sources,
    load_seed_articles,
    parse_registry_bbl,
    text_match_for_article,
    text_metadata,
)


DEFAULT_SEED_CSV = Path("data/processed/openalex/openalex_knime_most_cited.csv")
DEFAULT_REGISTRY = Path("data/original/articles/registry.bbl")
DEFAULT_TEXT_DIR = Path("data/processed/articles")
DEFAULT_OUTPUT = Path("data/processed/audit/article_url_collection.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-csv", type=Path, default=DEFAULT_SEED_CSV)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--text-dir", type=Path, default=DEFAULT_TEXT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=0, help="Maximum records to write. 0 means all.")
    parser.add_argument("--rank", type=int, action="append", help="Write only this citation rank.")
    return parser.parse_args()


def selected_articles(
    articles: list[dict[str, Any]], ranks: list[int] | None, limit: int
) -> list[dict[str, Any]]:
    selected = [article for article in articles if not ranks or article["rank"] in ranks]
    return selected[:limit] if limit > 0 else selected


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def collect_article(article: dict[str, Any], text_dir: Path) -> dict[str, Any]:
    text_path, _text_match = text_match_for_article(article, text_dir)
    metadata = text_metadata(text_path)
    tei_file = metadata.get("tei_file") or ""
    tei_path = Path(tei_file) if tei_file else None
    lines = text_path.read_text(encoding="utf-8", errors="replace").splitlines() if text_path else []

    resources = linked_resources_from_sources(lines, tei_path, None) if text_path else []
    urls = [resource["url"] for resource in resources]

    meta = {
        "article_identifier": article.get("article_identifier", ""),
        "pdf_file": metadata.get("source_pdf") or UNDEFINED,
        "tei_file": tei_file or UNDEFINED,
        "processed_text_file": text_path.as_posix() if text_path else UNDEFINED,
        "openalex_seed_fields": article.get("openalex_seed_fields", {}),
    }

    return {
        "rank": article["rank"],
        "meta": meta,
        "urls": urls,
    }


def main() -> int:
    args = parse_args()
    registry = parse_registry_bbl(args.registry)
    seed_articles = selected_articles(
        load_seed_articles(args.seed_csv, registry), args.rank, args.limit
    )
    articles = [collect_article(article, args.text_dir) for article in seed_articles]

    result = {
        "created_at": date.today().isoformat(),
        "created_by": Path(__file__).as_posix(),
        "scope": "Metadata and URL collection only. No URL classification, article-audit inference, curated-audit reads, network calls, or LLM calls.",
        "source_files": {
            "top_cited_seed": args.seed_csv.as_posix(),
            "article_registry": args.registry.as_posix(),
            "article_directory": args.text_dir.as_posix(),
        },
        "method": {
            "article_matching": "Processed HTML is matched by full registry key/full DOI-derived registry key only.",
            "url_collection": "URLs are collected from processed GROBID HTML text and TEI URL targets, then normalized and syntactically checked by the shared deterministic URL normalizer.",
        },
        "summary": {
            "records_written": len(articles),
            "records_with_processed_text": sum(
                1
                for article in articles
                if article["meta"].get("processed_text_file") != UNDEFINED
            ),
            "records_with_urls": sum(
                1 for article in articles if article.get("urls")
            ),
            "total_urls": sum(
                len(article.get("urls", [])) for article in articles
            ),
        },
        "articles": articles,
    }
    write_json(args.output, result)
    print(f"Wrote {len(articles)} article URL records to {args.output}.")
    print(f"Records with processed text: {result['summary']['records_with_processed_text']}.")
    print(f"Collected URLs: {result['summary']['total_urls']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
