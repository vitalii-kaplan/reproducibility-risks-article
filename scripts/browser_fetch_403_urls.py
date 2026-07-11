#!/usr/bin/env python3
"""Browser-fetch URLs that returned HTTP 403 in article_url_collection.json.

This is a second-stage retrievability check for URLs that simple HTTP fetching
could not access. It uses Playwright with Chrome, saves rendered HTML, and
updates only browser-fetch metadata in article_url_collection.json.

It does not solve or bypass captchas. If the rendered page is a Cloudflare or
captcha challenge, the URL is marked as ``blocked_by_challenge``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_COLLECTION = Path("data/processed/audit/article_url_collection.json")
DEFAULT_OUTPUT_DIR = Path("data/processed/audit/browser_pages")
DEFAULT_TIMEOUT_SECONDS = 45
CAPTCHA_PROTECTED_DOMAINS = {"myexperiment.org", "www.myexperiment.org"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--limit", type=int, default=0, help="Maximum unique 403 URLs to process. 0 means all.")
    parser.add_argument("--rank", type=int, action="append", help="Process 403 URLs only from this article rank.")
    parser.add_argument("--url", action="append", help="Process only this exact URL.")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless.")
    parser.add_argument(
        "--keep-profile",
        type=Path,
        default=None,
        help="Use this persistent Chrome profile directory instead of a temporary profile.",
    )
    parser.add_argument("--delay", type=float, default=0.5)
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


def safe_slug(url: str, max_len: int = 80) -> str:
    chars = []
    for char in url.lower():
        if char.isalnum() or char in {".", "-", "_"}:
            chars.append(char)
        else:
            chars.append("_")
    slug = "".join(chars).strip("._")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug[:max_len] or "url"


def short_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def iter_url_entries(collection: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    entries = []
    for article in collection.get("articles", []):
        for entry in article.get("urls", []):
            if isinstance(entry, dict):
                entries.append((article, entry))
    return entries


def select_unique_403_urls(collection: dict[str, Any], args: argparse.Namespace) -> list[str]:
    selected = []
    seen = set()
    allowed_urls = set(args.url or [])
    allowed_ranks = set(args.rank or [])
    for article, entry in iter_url_entries(collection):
        rank = article.get("rank")
        url = entry.get("url")
        if allowed_ranks and rank not in allowed_ranks:
            continue
        if allowed_urls and url not in allowed_urls:
            continue
        if entry.get("http_status_code") != 403:
            continue
        if url in seen:
            continue
        seen.add(url)
        selected.append(url)
        if args.limit > 0 and len(selected) >= args.limit:
            break
    return selected


def captcha_protected_domain(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in CAPTCHA_PROTECTED_DOMAINS


def captcha_protected_record(url: str, ordinal: int, args: argparse.Namespace) -> dict[str, Any]:
    final_url = url
    if final_url.startswith("http://"):
        final_url = "https://" + final_url.removeprefix("http://")
    record = {
        "ordinal": ordinal,
        "url": url,
        "started_at": now_iso(),
        "finished_at": now_iso(),
        "elapsed_seconds": 0,
        "browser_fetch_status": "blocked_by_challenge",
        "browser_http_status_code": 403,
        "browser_final_url": final_url,
        "browser_title": "captcha-protected domain; browser visit skipped",
        "browser_body_file": None,
        "browser_body_sha256": None,
        "browser_body_bytes_stored": 0,
        "browser_error": {
            "type": "SkippedCaptchaProtectedDomain",
            "message": "Domain is known to present an interactive captcha/Cloudflare challenge; automated revisit skipped.",
        },
    }
    record_path = args.output_dir / f"{ordinal:04d}_{short_hash(url)}_{safe_slug(url)}.json"
    write_json(record_path, record)
    record["browser_record_file"] = record_path.as_posix()
    return record


def is_challenge_page(title: str, body_text: str, final_url: str) -> bool:
    evidence = f"{title}\n{body_text}\n{final_url}".lower()
    markers = [
        "just a moment",
        "performing security verification",
        "verify you are not a bot",
        "cf-ray",
        "cloudflare",
        "captcha",
        "turnstile",
    ]
    return any(marker in evidence for marker in markers)


def browser_fetch_url(context: Any, url: str, ordinal: int, args: argparse.Namespace) -> dict[str, Any]:
    page = context.new_page()
    started = time.monotonic()
    record: dict[str, Any] = {
        "ordinal": ordinal,
        "url": url,
        "started_at": now_iso(),
        "finished_at": None,
        "elapsed_seconds": None,
        "browser_fetch_status": "not_started",
        "browser_http_status_code": None,
        "browser_final_url": None,
        "browser_title": None,
        "browser_body_file": None,
        "browser_body_sha256": None,
        "browser_body_bytes_stored": 0,
        "browser_error": None,
    }
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        title = page.title()
        try:
            body_text = page.locator("body").inner_text(timeout=5_000)
        except Exception:
            body_text = ""
        html = page.content().encode("utf-8", errors="replace")
        body_path = args.output_dir / "files" / f"{ordinal:04d}_{short_hash(url)}_{safe_slug(url)}.html"
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(html)
        status = "blocked_by_challenge" if is_challenge_page(title, body_text, page.url) else "fetched"
        record.update(
            {
                "browser_fetch_status": status,
                "browser_http_status_code": response.status if response else None,
                "browser_final_url": page.url,
                "browser_title": title,
                "browser_body_file": body_path.as_posix(),
                "browser_body_sha256": hashlib.sha256(html).hexdigest(),
                "browser_body_bytes_stored": len(html),
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
        record["finished_at"] = now_iso()
        record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    record_path = args.output_dir / f"{ordinal:04d}_{short_hash(url)}_{safe_slug(url)}.json"
    write_json(record_path, record)
    record["browser_record_file"] = record_path.as_posix()
    return record


def apply_browser_results(collection: dict[str, Any], by_url: dict[str, dict[str, Any]]) -> int:
    updated = 0
    fields = [
        "browser_fetch_status",
        "browser_http_status_code",
        "browser_final_url",
        "browser_title",
        "browser_body_file",
        "browser_record_file",
    ]
    for _article, entry in iter_url_entries(collection):
        result = by_url.get(entry.get("url"))
        if not result:
            continue
        for field in fields:
            entry[field] = result.get(field)
        updated += 1
    return updated


def launch_context(playwright: Any, args: argparse.Namespace, profile_dir: str | Path) -> Any:
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel="chrome",
        headless=args.headless,
        viewport={"width": 1366, "height": 900},
        locale="en-US",
        args=["--disable-blink-features=AutomationControlled"],
    )


def run_browser_pass(collection: dict[str, Any], urls: list[str], args: argparse.Namespace) -> list[dict[str, Any]]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    captcha_skipped = [
        captcha_protected_record(url, ordinal, args)
        for ordinal, url in enumerate(urls, start=1)
        if captcha_protected_domain(url)
    ]
    browser_urls = [url for url in urls if not captcha_protected_domain(url)]
    if not browser_urls:
        return captcha_skipped

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Playwright is not installed. Use the project Playwright venv, for example: "
            ".venv-playwright/bin/python scripts/browser_fetch_403_urls.py"
        ) from exc

    records = []
    if args.keep_profile:
        args.keep_profile.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = launch_context(playwright, args, args.keep_profile)
            try:
                records = fetch_all(context, browser_urls, args, start_ordinal=len(captcha_skipped) + 1)
            finally:
                context.close()
        return captcha_skipped + records

    with tempfile.TemporaryDirectory(prefix="article-url-browser-profile-") as profile_dir:
        with sync_playwright() as playwright:
            context = launch_context(playwright, args, profile_dir)
            try:
                records = fetch_all(context, browser_urls, args, start_ordinal=len(captcha_skipped) + 1)
            finally:
                context.close()
    return captcha_skipped + records


def fetch_all(
    context: Any, urls: list[str], args: argparse.Namespace, start_ordinal: int = 1
) -> list[dict[str, Any]]:
    records = []
    total = len(urls)
    for offset, url in enumerate(urls, start=0):
        ordinal = start_ordinal + offset
        print(f"[browser {offset + 1}/{total}] {url}")
        records.append(browser_fetch_url(context, url, ordinal, args))
        if args.delay > 0 and offset + 1 < total:
            time.sleep(args.delay)
    return records


def main() -> int:
    args = parse_args()
    collection = read_json(args.collection)
    urls = select_unique_403_urls(collection, args)
    records = run_browser_pass(collection, urls, args)
    by_url = {record["url"]: record for record in records}
    updated_entries = apply_browser_results(collection, by_url)
    index = {
        "created_at": now_iso(),
        "created_by": repo_relative_script_path(),
        "source_collection": args.collection.as_posix(),
        "output_dir": args.output_dir.as_posix(),
        "scope": "Browser fallback for URLs whose first-stage HTTP status code is 403. Captchas are detected and recorded, not bypassed.",
        "parameters": {
            "headless": args.headless,
            "timeout_seconds": args.timeout,
            "limit": args.limit,
            "ranks": args.rank or [],
            "urls": args.url or [],
        },
        "summary": {
            "unique_403_urls_selected": len(urls),
            "url_entries_updated": updated_entries,
            "browser_fetched": sum(1 for record in records if record["browser_fetch_status"] == "fetched"),
            "blocked_by_challenge": sum(
                1 for record in records if record["browser_fetch_status"] == "blocked_by_challenge"
            ),
            "fetch_errors": sum(1 for record in records if record["browser_fetch_status"] == "fetch_error"),
            "skipped_captcha_protected_domain": sum(
                1
                for record in records
                if (record.get("browser_error") or {}).get("type") == "SkippedCaptchaProtectedDomain"
            ),
            "browser_http_200": sum(1 for record in records if record.get("browser_http_status_code") == 200),
            "browser_http_403": sum(1 for record in records if record.get("browser_http_status_code") == 403),
        },
        "pages": records,
    }
    write_json(args.output_dir / "index.json", index)
    collection["browser_403_fetch_metadata"] = {
        "attached_at": now_iso(),
        "attached_by": repo_relative_script_path(),
        "browser_index": (args.output_dir / "index.json").as_posix(),
        "summary": index["summary"],
    }
    write_json(args.output, collection)
    print(f"Wrote browser 403 index to {args.output_dir / 'index.json'}.")
    print(f"Updated URL entries in {args.output}: {updated_entries}.")
    print(index["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
