#!/usr/bin/env python3
"""Attach fetched-page metadata to article URL collection.

This script joins ``data/processed/audit/pages/index.json`` back into
``article_url_collection.json``. It only records fetch metadata beside each URL:
status code, final URL, redirect count, and paths to the stored sidecar/body.
It does not classify URLs or inspect downloaded page content.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_COLLECTION = Path("data/processed/audit/article_url_collection.json")
DEFAULT_PAGES_INDEX = Path("data/processed/audit/pages/index.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument("--pages-index", type=Path, default=DEFAULT_PAGES_INDEX)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_COLLECTION,
        help="Output path. Defaults to updating the collection in place.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def url_value(entry: str | dict[str, Any]) -> str:
    if isinstance(entry, str):
        return entry
    return str(entry.get("url", ""))


def page_meta(page: dict[str, Any] | None) -> dict[str, Any]:
    if not page:
        return {
            "fetch_status": "not_checked",
            "http_status_code": None,
            "final_url": None,
            "redirect_count": 0,
            "page_record_file": None,
            "page_body_file": None,
        }
    return {
        "fetch_status": page.get("status"),
        "http_status_code": page.get("http_status_code"),
        "final_url": page.get("final_url"),
        "redirect_count": len(page.get("redirects") or []),
        "page_record_file": page.get("record_file"),
        "page_body_file": page.get("body_file"),
        "browser_fetch_status": page.get("browser_fetch_status", "not_attempted"),
        "browser_http_status_code": page.get("browser_http_status_code"),
        "browser_final_url": page.get("browser_final_url"),
        "browser_title": page.get("browser_title"),
        "browser_page_body_file": page.get("browser_body_file"),
    }


def attach_metadata(collection: dict[str, Any], pages_index: dict[str, Any]) -> dict[str, Any]:
    pages_by_url = {page.get("url"): page for page in pages_index.get("pages", [])}
    updated_articles = 0
    updated_url_entries = 0
    missing_fetch_metadata = 0

    for article in collection.get("articles", []):
        new_urls = []
        changed_article = False
        for entry in article.get("urls", []):
            url = url_value(entry)
            page = pages_by_url.get(url)
            if page is None:
                missing_fetch_metadata += 1
            new_entry = {"url": url, **page_meta(page)}
            new_urls.append(new_entry)
            updated_url_entries += 1
            changed_article = True
        if changed_article:
            article["urls"] = new_urls
            updated_articles += 1

    collection["page_fetch_metadata"] = {
        "attached_at": now_iso(),
        "attached_by": Path(__file__).as_posix(),
        "pages_index": DEFAULT_PAGES_INDEX.as_posix(),
        "scope": "URL fetch metadata only. No URL classification, page-content interpretation, or audit-field inference.",
        "fields_added_to_urls": [
            "fetch_status",
            "http_status_code",
            "final_url",
            "redirect_count",
            "page_record_file",
            "page_body_file",
            "browser_fetch_status",
            "browser_http_status_code",
            "browser_final_url",
            "browser_title",
            "browser_page_body_file",
        ],
        "source_summary": pages_index.get("summary", {}),
        "summary": {
            "articles_with_url_entries": updated_articles,
            "url_entries_updated": updated_url_entries,
            "url_entries_without_fetch_metadata": missing_fetch_metadata,
        },
    }
    return collection


def main() -> int:
    args = parse_args()
    collection = read_json(args.collection)
    pages_index = read_json(args.pages_index)
    updated = attach_metadata(collection, pages_index)
    updated["page_fetch_metadata"]["pages_index"] = args.pages_index.as_posix()
    write_json(args.output, updated)
    summary = updated["page_fetch_metadata"]["summary"]
    print(f"Wrote URL fetch metadata to {args.output}.")
    print(f"URL entries updated: {summary['url_entries_updated']}.")
    print(f"Missing fetch metadata: {summary['url_entries_without_fetch_metadata']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
