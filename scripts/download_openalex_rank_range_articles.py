#!/usr/bin/env python3
"""Download article PDFs for a citation-rank range from local OpenAlex data."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def slug(text: str, fallback: str) -> str:
    text = re.sub(r"^https?://doi\.org/", "", text.strip(), flags=re.I)
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return (text[:90] or fallback).strip("_")


def load_ranked_works(path: Path) -> list[dict]:
    works = []
    with path.open() as f:
        for line in f:
            if line.strip():
                works.append(json.loads(line))
    works.sort(key=lambda w: int(w.get("cited_by_count") or 0), reverse=True)
    return works


def candidate_urls(work: dict) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, url: str | None) -> None:
        if url and url not in seen:
            seen.add(url)
            candidates.append((label, url))

    best = work.get("best_oa_location") or {}
    primary = work.get("primary_location") or {}
    open_access = work.get("open_access") or {}
    content_urls = work.get("content_urls") or {}
    add("best_oa_location.pdf_url", best.get("pdf_url"))
    add("primary_location.pdf_url", primary.get("pdf_url"))
    add("open_access.oa_url", open_access.get("oa_url"))
    add("content_urls.pdf", content_urls.get("pdf"))
    for i, loc in enumerate(work.get("locations") or [], start=1):
        add(f"locations[{i}].pdf_url", loc.get("pdf_url"))
    return candidates


def extension_from_response(url: str, content_type: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".pdf") or "pdf" in content_type.lower():
        return ".pdf"
    return ".bin"


def is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def download(url: str, path_prefix: Path, timeout: int) -> tuple[str, Path | None, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 reproducibility-risks article audit",
            "Accept": "application/pdf,text/html,application/octet-stream;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            status = getattr(response, "status", "")
            ext = extension_from_response(response.geturl(), content_type)
            target = path_prefix.with_suffix(ext)
            data = response.read()
            target.write_bytes(data)
            if is_pdf(target):
                return "downloaded_pdf", target, f"HTTP {status}; {content_type}; {url}"
            return "downloaded_non_pdf", target, f"HTTP {status}; {content_type}; {url}"
    except urllib.error.HTTPError as exc:
        return "http_error", None, f"HTTP {exc.code}; {url}"
    except urllib.error.URLError as exc:
        return "url_error", None, f"{exc.reason}; {url}"
    except TimeoutError:
        return "timeout", None, url


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True, help="1-based rank start")
    parser.add_argument("--end", type=int, required=True, help="1-based rank end")
    parser.add_argument("--works", default="data/original/openalex/works.jsonl")
    parser.add_argument("--out-dir", default="data/original/articles")
    parser.add_argument("--manifest-dir", default="data/processed/audit")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    works = load_ranked_works(Path(args.works))
    out_dir = Path(args.out_dir)
    manifest_dir = Path(args.manifest_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"article_download_attempts_{args.start}-{args.end}.csv"

    rows = []
    for rank, work in enumerate(works[args.start - 1 : args.end], start=args.start):
        title = work.get("display_name") or work.get("title") or ""
        doi = work.get("doi") or ""
        candidates = candidate_urls(work)
        status = "not_downloaded"
        output_path = ""
        note = "No candidate PDF URL in OpenAlex metadata"
        used_url = ""
        for idx, (label, url) in enumerate(candidates, start=1):
            path_prefix = out_dir / f"{rank:02d}_{slug(doi or title, 'article')}_{idx}"
            result, path, detail = download(url, path_prefix, args.timeout)
            used_url = url
            if result == "downloaded_pdf" and path is not None:
                status = "downloaded_pdf"
                output_path = str(path)
                note = f"{label}; {detail}"
                break
            if result == "downloaded_non_pdf" and path is not None:
                path.unlink(missing_ok=True)
            note = f"{label}; {detail}"
            time.sleep(1)
        rows.append(
            {
                "rank": rank,
                "title": title,
                "doi": doi,
                "status": status,
                "output_path": output_path,
                "used_url": used_url,
                "note": note,
            }
        )
        print(f"{rank}\t{status}\t{doi}\t{title}", file=sys.stderr)

    with manifest_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["rank", "title", "doi", "status", "output_path", "used_url", "note"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
