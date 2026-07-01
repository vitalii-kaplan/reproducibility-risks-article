#!/usr/bin/env python3
"""Collect OpenAlex works matching a KNIME search query."""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ENDPOINT = "https://api.openalex.org/works"
DEFAULT_SEARCH = "KNIME"
DEFAULT_SEARCH_PARAM = "search.title_and_abstract"
DEFAULT_FILTER = "type:article"
DEFAULT_PER_PAGE = 200


CSV_FIELDS = [
    "id",
    "doi",
    "display_name",
    "publication_year",
    "publication_date",
    "type",
    "type_crossref",
    "cited_by_count",
    "is_oa",
    "open_access_status",
    "primary_location_source",
    "primary_location_landing_page_url",
    "primary_location_pdf_url",
    "authorships_count",
    "first_author",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search", default=DEFAULT_SEARCH)
    parser.add_argument("--search-param", default=DEFAULT_SEARCH_PARAM)
    parser.add_argument("--filter", default=DEFAULT_FILTER)
    parser.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE)
    parser.add_argument("--mailto", default="")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--no-clean", action="store_true")
    return parser.parse_args()


def request_json(url: str, retries: int = 3) -> dict[str, Any]:
    headers = {"User-Agent": "knime-reproducibility-study/0.1"}
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def build_url(args: argparse.Namespace, cursor: str) -> str:
    params = {
        args.search_param: args.search,
        "filter": args.filter,
        "per-page": str(args.per_page),
        "cursor": cursor,
    }
    if args.mailto:
        params["mailto"] = args.mailto
    return f"{ENDPOINT}?{urllib.parse.urlencode(params)}"


def default_output_dir(args: argparse.Namespace) -> Path:
    return Path("data/original/openalex")


def clean_output_dir(out_dir: Path) -> None:
    pages_dir = out_dir / "pages"
    for path in pages_dir.glob("page_*.json"):
        path.unlink()
    for name in ["metadata.json", "works.jsonl", "works.csv"]:
        path = out_dir / name
        if path.exists():
            path.unlink()


def source_name(work: dict[str, Any]) -> str:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    return source.get("display_name") or ""


def location_url(work: dict[str, Any], field: str) -> str:
    location = work.get("primary_location") or {}
    return location.get(field) or ""


def first_author(work: dict[str, Any]) -> str:
    authorships = work.get("authorships") or []
    if not authorships:
        return ""
    author = authorships[0].get("author") or {}
    return author.get("display_name") or ""


def csv_row(work: dict[str, Any]) -> dict[str, Any]:
    open_access = work.get("open_access") or {}
    return {
        "id": work.get("id") or "",
        "doi": work.get("doi") or "",
        "display_name": work.get("display_name") or "",
        "publication_year": work.get("publication_year") or "",
        "publication_date": work.get("publication_date") or "",
        "type": work.get("type") or "",
        "type_crossref": work.get("type_crossref") or "",
        "cited_by_count": work.get("cited_by_count") or 0,
        "is_oa": open_access.get("is_oa"),
        "open_access_status": open_access.get("oa_status") or "",
        "primary_location_source": source_name(work),
        "primary_location_landing_page_url": location_url(work, "landing_page_url"),
        "primary_location_pdf_url": location_url(work, "pdf_url"),
        "authorships_count": len(work.get("authorships") or []),
        "first_author": first_author(work),
    }


def write_outputs(
    out_dir: Path,
    metadata: dict[str, Any],
    works: list[dict[str, Any]],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    with (out_dir / "metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
        f.write("\n")

    with (out_dir / "works.jsonl").open("w", encoding="utf-8") as f:
        for work in works:
            json.dump(work, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")

    with (out_dir / "works.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for work in works:
            writer.writerow(csv_row(work))


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir or default_output_dir(args)
    if not args.no_clean:
        clean_output_dir(out_dir)
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    collected_at = datetime.now(UTC).isoformat(timespec="seconds")
    works: list[dict[str, Any]] = []
    page_summaries: list[dict[str, Any]] = []
    first_meta: dict[str, Any] | None = None
    cursor = "*"
    page_number = 0

    while cursor:
        page_number += 1
        url = build_url(args, cursor)
        page = request_json(url)
        if first_meta is None:
            first_meta = page.get("meta") or {}

        page_path = pages_dir / f"page_{page_number:04d}.json"
        with page_path.open("w", encoding="utf-8") as f:
            json.dump(page, f, ensure_ascii=False, indent=2)
            f.write("\n")

        results = page.get("results") or []
        works.extend(results)
        meta = page.get("meta") or {}
        page_summaries.append(
            {
                "page": page_number,
                "url": url,
                "path": str(page_path),
                "results": len(results),
                "count": meta.get("count"),
                "next_cursor_present": bool(meta.get("next_cursor")),
            }
        )

        if not results:
            break
        if args.max_pages and page_number >= args.max_pages:
            break
        cursor = meta.get("next_cursor")
        if cursor:
            time.sleep(args.sleep)

    metadata = {
        "collected_at_utc": collected_at,
        "endpoint": ENDPOINT,
        "query_parameters": {
            "search_parameter": args.search_param,
            "search": args.search,
            "filter": args.filter,
            "per-page": args.per_page,
            "cursor": "cursor pagination from *",
            "mailto": args.mailto,
        },
        "openalex_first_page_meta": first_meta or {},
        "pages_collected": page_number,
        "works_collected": len(works),
        "page_summaries": page_summaries,
        "raw_page_directory": str(pages_dir),
        "derived_files": ["works.jsonl", "works.csv"],
    }
    write_outputs(out_dir, metadata, works)

    print(f"wrote {len(works)} works to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
