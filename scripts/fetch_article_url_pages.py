#!/usr/bin/env python3
"""Fetch collected article URLs and store page responses with redirects.

Input is the URL-only collection produced by ``scripts/collect_article_urls.py``.
This script does not classify URLs and does not inspect article-audit fields.
It visits each collected URL, records HTTP status, headers, final URL,
redirect chain, and stores the response body under the output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/processed/audit/article_url_collection.json")
DEFAULT_OUTPUT_DIR = Path("data/processed/audit/pages")
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_DELAY_SECONDS = 0.25
DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_WORKERS = 12
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; KNIME-reproducibility-audit/1.0; "
    "+https://github.com/vitaly-kaplan)"
)


@dataclass
class UrlRecord:
    url: str
    articles: list[dict[str, Any]] = field(default_factory=list)


class RecordingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """urllib redirect handler that records every redirect hop."""

    def __init__(self) -> None:
        super().__init__()
        self.redirects: list[dict[str, Any]] = []

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        self.redirects.append(
            {
                "from_url": req.full_url,
                "to_url": newurl,
                "status_code": code,
                "reason": msg,
            }
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help="Maximum response-body bytes to store per URL. 0 means unlimited.",
    )
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--limit", type=int, default=0, help="Maximum URLs to fetch. 0 means all.")
    parser.add_argument("--rank", type=int, action="append", help="Fetch URLs only from this rank.")
    parser.add_argument("--url", action="append", help="Fetch only this exact URL.")
    parser.add_argument(
        "--browser-fallback",
        choices=["never", "failed", "all"],
        default="never",
        help="Use Playwright/Chrome after urllib. 'failed' tries only http_error/fetch_error records.",
    )
    parser.add_argument(
        "--browser-headless",
        action="store_true",
        help="Run Playwright fallback headless. Headed Chrome can pass some bot checks that headless cannot.",
    )
    parser.add_argument("--browser-timeout", type=float, default=45)
    parser.add_argument(
        "--include-duplicates",
        action="store_true",
        help="Fetch each article URL occurrence instead of each unique URL.",
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


def repo_relative_script_path() -> str:
    path = Path(__file__).resolve()
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return Path(__file__).name


def url_value(entry: str | dict[str, Any]) -> str:
    if isinstance(entry, str):
        return entry
    return str(entry.get("url", ""))


def safe_slug(url: str, max_len: int = 72) -> str:
    cleaned = []
    for char in url.lower():
        if char.isalnum():
            cleaned.append(char)
        elif char in {".", "-", "_"}:
            cleaned.append(char)
        else:
            cleaned.append("_")
    slug = "".join(cleaned).strip("._")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug[:max_len] or "url"


def url_digest(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def body_extension(content_type: str) -> str:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return {
        "text/html": ".html",
        "text/plain": ".txt",
        "application/json": ".json",
        "application/xml": ".xml",
        "text/xml": ".xml",
        "application/pdf": ".pdf",
        "application/zip": ".zip",
        "application/x-zip-compressed": ".zip",
    }.get(media_type, ".bin")


def collect_url_records(
    collection: dict[str, Any],
    ranks: list[int] | None,
    include_duplicates: bool,
    urls: list[str] | None = None,
) -> list[UrlRecord]:
    records: list[UrlRecord] = []
    by_url: dict[str, UrlRecord] = {}

    for article in collection.get("articles", []):
        rank = article.get("rank")
        if ranks and rank not in ranks:
            continue
        article_ref = {
            "rank": rank,
            "article_identifier": article.get("meta", {}).get("article_identifier"),
            "doi": article.get("meta", {}).get("openalex_seed_fields", {}).get("doi"),
            "title": article.get("meta", {}).get("openalex_seed_fields", {}).get("title"),
        }
        for url in article.get("urls", []):
            if urls and url_value(url) not in urls:
                continue
            url = url_value(url)
            if include_duplicates:
                records.append(UrlRecord(url=url, articles=[article_ref]))
                continue
            if url not in by_url:
                by_url[url] = UrlRecord(url=url)
                records.append(by_url[url])
            by_url[url].articles.append(article_ref)

    return records


def read_limited(response: Any, max_bytes: int) -> tuple[bytes, bool]:
    if max_bytes <= 0:
        return response.read(), False
    body = response.read(max_bytes + 1)
    if len(body) <= max_bytes:
        return body, False
    return body[:max_bytes], True


def fetch_url(record: UrlRecord, args: argparse.Namespace, ordinal: int) -> dict[str, Any]:
    url = record.url
    digest = url_digest(url)
    base_name = f"{ordinal:04d}_{digest}_{safe_slug(url)}"
    redirect_handler = RecordingRedirectHandler()
    opener = urllib.request.build_opener(redirect_handler)
    request = urllib.request.Request(url, headers={"User-Agent": args.user_agent})

    started_at = now_iso()
    started_monotonic = time.monotonic()
    page_record: dict[str, Any] = {
        "ordinal": ordinal,
        "url": url,
        "url_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "articles": record.articles,
        "started_at": started_at,
        "finished_at": None,
        "elapsed_seconds": None,
        "status": "not_started",
        "http_status_code": None,
        "reason": None,
        "final_url": None,
        "redirects": [],
        "headers": {},
        "body_file": None,
        "body_sha256": None,
        "body_bytes_stored": 0,
        "body_truncated": False,
        "error": None,
        "browser_fetch_status": "not_attempted",
        "browser_http_status_code": None,
        "browser_final_url": None,
        "browser_title": None,
        "browser_body_file": None,
        "browser_body_sha256": None,
        "browser_body_bytes_stored": 0,
        "browser_error": None,
    }

    try:
        with opener.open(request, timeout=args.timeout) as response:
            body, truncated = read_limited(response, args.max_bytes)
            headers = dict(response.headers.items())
            content_type = headers.get("Content-Type", "")
            body_path = args.output_dir / "files" / f"{base_name}{body_extension(content_type)}"
            body_path.parent.mkdir(parents=True, exist_ok=True)
            body_path.write_bytes(body)

            page_record.update(
                {
                    "status": "fetched",
                    "http_status_code": response.getcode(),
                    "reason": getattr(response, "reason", None),
                    "final_url": response.geturl(),
                    "redirects": redirect_handler.redirects,
                    "headers": headers,
                    "body_file": body_path.as_posix(),
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "body_bytes_stored": len(body),
                    "body_truncated": truncated,
                }
            )
    except urllib.error.HTTPError as exc:
        body, truncated = read_limited(exc, args.max_bytes)
        headers = dict(exc.headers.items()) if exc.headers else {}
        content_type = headers.get("Content-Type", "")
        body_path = args.output_dir / "files" / f"{base_name}{body_extension(content_type)}"
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(body)
        page_record.update(
            {
                "status": "http_error",
                "http_status_code": exc.code,
                "reason": exc.reason,
                "final_url": exc.geturl(),
                "redirects": redirect_handler.redirects,
                "headers": headers,
                "body_file": body_path.as_posix(),
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "body_bytes_stored": len(body),
                "body_truncated": truncated,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        page_record.update(
            {
                "status": "fetch_error",
                "redirects": redirect_handler.redirects,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
    finally:
        page_record["finished_at"] = now_iso()
        page_record["elapsed_seconds"] = round(time.monotonic() - started_monotonic, 3)

    record_path = args.output_dir / f"{base_name}.json"
    write_json(record_path, page_record)
    page_record["record_file"] = record_path.as_posix()
    return page_record


def should_browser_fetch(page_record: dict[str, Any], mode: str) -> bool:
    if mode == "never":
        return False
    if mode == "all":
        return True
    return page_record.get("status") in {"http_error", "fetch_error"}


def browser_fetch_records(records: list[dict[str, Any]], args: argparse.Namespace) -> None:
    targets = [record for record in records if should_browser_fetch(record, args.browser_fallback)]
    if not targets:
        return

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        for record in targets:
            record["browser_fetch_status"] = "not_available"
            record["browser_error"] = {
                "type": type(exc).__name__,
                "message": "Playwright is not installed in this Python environment.",
            }
        return

    with tempfile.TemporaryDirectory(prefix="article-url-browser-profile-") as profile_dir:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="chrome",
                headless=args.browser_headless,
                viewport={"width": 1366, "height": 900},
                locale="en-US",
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                for current, record in enumerate(targets, start=1):
                    print(
                        f"[browser {current}/{len(targets)}] "
                        f"{record.get('status')} {record.get('http_status_code') or ''} {record['url']}"
                    )
                    browser_fetch_one(record, args, context)
                    record_path = Path(record["record_file"])
                    write_json(record_path, {k: v for k, v in record.items() if k != "record_file"})
            finally:
                context.close()


def browser_fetch_one(record: dict[str, Any], args: argparse.Namespace, context: Any) -> None:
    page = context.new_page()
    try:
        response = page.goto(
            record["url"],
            wait_until="domcontentloaded",
            timeout=args.browser_timeout * 1000,
        )
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        title = page.title()
        body_text = ""
        try:
            body_text = page.locator("body").inner_text(timeout=5_000)
        except Exception:
            body_text = ""
        html = page.content().encode("utf-8", errors="replace")
        body_path = (
            args.output_dir
            / "files"
            / f"{record['ordinal']:04d}_{url_digest(record['url'])}_{safe_slug(record['url'])}_browser.html"
        )
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(html)
        challenge_detected = is_browser_challenge_page(title, body_text, page.url)
        record.update(
            {
                "browser_fetch_status": "blocked_by_challenge" if challenge_detected else "fetched",
                "browser_http_status_code": response.status if response else None,
                "browser_final_url": page.url,
                "browser_title": title,
                "browser_body_file": body_path.as_posix(),
                "browser_body_sha256": hashlib.sha256(html).hexdigest(),
                "browser_body_bytes_stored": len(html),
                "browser_error": None,
            }
        )
    except Exception as exc:
        record.update(
            {
                "browser_fetch_status": "fetch_error",
                "browser_final_url": page.url,
                "browser_error": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
    finally:
        page.close()


def is_browser_challenge_page(title: str, body_text: str, final_url: str) -> bool:
    evidence = f"{title}\n{body_text}\n{final_url}".lower()
    challenge_markers = [
        "just a moment",
        "performing security verification",
        "verify you are not a bot",
        "cf-ray",
        "cloudflare",
        "captcha",
        "turnstile",
    ]
    return any(marker in evidence for marker in challenge_markers)


def record_quality(record: dict[str, Any]) -> int:
    score = 0
    if record.get("browser_fetch_status") not in {None, "not_attempted"}:
        score += 100
    if record.get("browser_fetch_status") == "fetched":
        score += 80
    if record.get("browser_fetch_status") == "blocked_by_challenge":
        score += 60
    if record.get("status") == "fetched":
        score += 40
    if record.get("http_status_code") == 200:
        score += 20
    if record.get("body_file"):
        score += 10
    return score


def rebuild_pages_from_sidecars(records: list[UrlRecord], output_dir: Path) -> list[dict[str, Any]]:
    by_url: dict[str, list[tuple[float, dict[str, Any]]]] = {}
    for path in output_dir.glob("*.json"):
        if path.name == "index.json":
            continue
        try:
            record = read_json(path)
        except json.JSONDecodeError:
            continue
        url = record.get("url")
        if not url:
            continue
        record["record_file"] = path.as_posix()
        by_url.setdefault(url, []).append((path.stat().st_mtime, record))

    rebuilt = []
    for ordinal, source_record in enumerate(records, start=1):
        candidates = by_url.get(source_record.url, [])
        if not candidates:
            continue
        _mtime, chosen = max(candidates, key=lambda item: (record_quality(item[1]), item[0]))
        chosen["articles"] = source_record.articles
        chosen["ordinal"] = ordinal
        rebuilt.append(chosen)
    return rebuilt


def main() -> int:
    args = parse_args()
    collection = read_json(args.input)
    records = collect_url_records(collection, args.rank, args.include_duplicates, args.url)
    if args.limit > 0:
        records = records[: args.limit]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    fetched_records: list[dict[str, Any]] = []
    workers = max(1, args.workers)
    if workers == 1:
        for ordinal, record in enumerate(records, start=1):
            print(f"[{ordinal}/{len(records)}] {record.url}")
            fetched_records.append(fetch_url(record, args, ordinal))
            if args.delay > 0 and ordinal < len(records):
                time.sleep(args.delay)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for ordinal, record in enumerate(records, start=1):
                futures.append(executor.submit(fetch_url, record, args, ordinal))
                if args.delay > 0 and ordinal < len(records):
                    time.sleep(args.delay)
            for completed, future in enumerate(as_completed(futures), start=1):
                page_record = future.result()
                fetched_records.append(page_record)
                print(
                    f"[{completed}/{len(records)}] {page_record['status']} "
                    f"{page_record['http_status_code'] or ''} {page_record['url']}"
                )
    fetched_records.sort(key=lambda record: record.get("ordinal", 0))
    browser_fetch_records(fetched_records, args)
    index_records = collect_url_records(collection, None, args.include_duplicates, None)
    fetched_records = rebuild_pages_from_sidecars(index_records, args.output_dir)
    fetched_records.sort(key=lambda record: record.get("ordinal", 0))

    index = {
        "created_at": now_iso(),
        "created_by": repo_relative_script_path(),
        "source_file": args.input.as_posix(),
        "output_dir": args.output_dir.as_posix(),
        "method": {
            "scope": "Network fetch of URLs from article_url_collection.json only. No URL classification or audit inference.",
            "redirects": "HTTP redirects are followed and recorded in each page JSON sidecar.",
            "body_storage": "Response bodies are stored under pages/files with SHA-256 hashes recorded in sidecar JSON files.",
        },
        "parameters": {
            "timeout_seconds": args.timeout,
            "delay_seconds": args.delay,
            "max_bytes": args.max_bytes,
            "workers": workers,
            "browser_fallback": args.browser_fallback,
            "browser_headless": args.browser_headless,
            "browser_timeout_seconds": args.browser_timeout,
            "include_duplicates": args.include_duplicates,
            "ranks": args.rank or [],
            "limit": args.limit,
        },
        "summary": {
            "url_records": len(records),
            "fetched": sum(1 for record in fetched_records if record["status"] == "fetched"),
            "http_errors": sum(1 for record in fetched_records if record["status"] == "http_error"),
            "fetch_errors": sum(1 for record in fetched_records if record["status"] == "fetch_error"),
            "redirected": sum(1 for record in fetched_records if record.get("redirects")),
            "browser_attempted": sum(
                1 for record in fetched_records if record.get("browser_fetch_status") != "not_attempted"
            ),
            "browser_fetched": sum(
                1 for record in fetched_records if record.get("browser_fetch_status") == "fetched"
            ),
            "browser_blocked_by_challenge": sum(
                1
                for record in fetched_records
                if record.get("browser_fetch_status") == "blocked_by_challenge"
            ),
            "browser_http_200": sum(
                1 for record in fetched_records if record.get("browser_http_status_code") == 200
            ),
        },
        "pages": fetched_records,
    }
    write_json(args.output_dir / "index.json", index)
    print(f"Wrote page fetch index to {args.output_dir / 'index.json'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
