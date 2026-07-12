#!/usr/bin/env python3
"""Attempt workflow artifact downloads from article_audit_report references.

The input report already contains LLM-selected workflow-relevant references.
This script acts on those references deterministically: it skips articles that
already have a workflow directory, tries direct HTTP downloads, optionally uses
Playwright/Chrome to discover download links on landing pages, scans local
files for KNIME workflow evidence, and writes the workflow-reference inventory.

It does not solve captchas or bypass access controls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORT = Path("data/processed/audit/article_audit_report.json")
DEFAULT_EXISTING = Path("data/processed/audit/knime_downloadable_workflow_references.json")
DEFAULT_OUTPUT = Path("data/processed/audit/knime_downloadable_workflow_references.json")
DEFAULT_WORKFLOW_ROOT = Path("data/original/workflows")
DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_MAX_BYTES = 250_000_000
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; KNIME-reproducibility-audit/1.0; "
    "+https://github.com/vitaly-kaplan)"
)

DOWNLOAD_EXTENSIONS = {".knwf", ".zip"}
CAPTCHA_PROTECTED_DOMAINS = {"myexperiment.org", "www.myexperiment.org"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--existing", type=Path, default=DEFAULT_EXISTING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workflow-root", type=Path, default=DEFAULT_WORKFLOW_ROOT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rank", type=int, action="append")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Only try direct HTTP downloads; do not open landing pages with Playwright.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"records": []}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def doi_safe(doi: str) -> str:
    doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    doi = doi.strip().lower()
    return re.sub(r"[^a-z0-9._-]+", "_", doi).strip("_") or "no_doi"


def article_dir(article: dict[str, Any], root: Path) -> Path:
    return root / f"{article.get('rank')}_{doi_safe(str(article.get('doi', '')))}"


def workflow_reference(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": resource.get("reference_type", ""),
        "url": resource.get("url", ""),
        "workflow_access": resource.get("workflow_access", ""),
        "workflow_form": resource.get("workflow_form", ""),
        "audit_status": resource.get("audit_status", ""),
        "confidence": resource.get("confidence", ""),
        "reason": resource.get("reason", ""),
    }


def filename_from_url(url: str, content_type: str = "") -> str:
    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path)).name
    if not name or "." not in name:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        ext = ".zip" if "zip" in content_type.lower() else ".bin"
        name = f"download_{digest}{ext}"
    return re.sub(r"[/\\\\:]+", "_", name)


def is_download_candidate(url: str, text: str = "") -> bool:
    parsed = urllib.parse.urlparse(url)
    suffix = Path(parsed.path.lower()).suffix
    haystack = f"{url} {text}".lower()
    if suffix in DOWNLOAD_EXTENSIONS:
        return True
    return "download" in haystack and any(token in haystack for token in ("workflow", "knime", "knwf", "zip"))


def host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def read_limited(response: Any, max_bytes: int) -> tuple[bytes, bool]:
    if max_bytes <= 0:
        return response.read(), False
    body = response.read(max_bytes + 1)
    return (body[:max_bytes], True) if len(body) > max_bytes else (body, False)


def direct_download(url: str, directory: Path, args: argparse.Namespace) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": args.user_agent})
    started = now_iso()
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            body, truncated = read_limited(response, args.max_bytes)
            final_url = response.geturl()
            output = directory / filename_from_url(final_url, content_type)
            directory.mkdir(parents=True, exist_ok=True)
            output.write_bytes(body)
            return {
                "url": url,
                "started_at": started,
                "finished_at": now_iso(),
                "status": "downloaded",
                "http_status_code": response.getcode(),
                "final_url": final_url,
                "content_type": content_type,
                "file": output.as_posix(),
                "bytes": len(body),
                "truncated": truncated,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {
            "url": url,
            "started_at": started,
            "finished_at": now_iso(),
            "status": "http_error",
            "http_status_code": exc.code,
            "final_url": exc.geturl(),
            "file": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return {
            "url": url,
            "started_at": started,
            "finished_at": now_iso(),
            "status": "fetch_error",
            "http_status_code": None,
            "final_url": None,
            "file": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def discover_browser_links(url: str, args: argparse.Namespace) -> dict[str, Any]:
    if args.no_browser:
        return {"status": "not_attempted", "links": [], "error": None}
    if host(url) in CAPTCHA_PROTECTED_DOMAINS:
        return {
            "status": "blocked_by_challenge",
            "links": [],
            "error": "Domain is known to require interactive challenge/captcha.",
        }
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        return {"status": "playwright_not_available", "links": [], "error": "Playwright is not installed."}

    with tempfile.TemporaryDirectory(prefix="workflow-download-browser-") as profile_dir:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="chrome",
                headless=args.headless,
                accept_downloads=True,
                viewport={"width": 1366, "height": 900},
                locale="en-US",
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.new_page()
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                anchors = page.eval_on_selector_all(
                    "a[href]",
                    "(nodes) => nodes.map(a => ({href: a.href, text: a.innerText || a.getAttribute('aria-label') || ''}))",
                )
                links = [
                    item
                    for item in anchors
                    if is_download_candidate(str(item.get("href", "")), str(item.get("text", "")))
                ]
                return {
                    "status": "fetched",
                    "http_status_code": response.status if response else None,
                    "final_url": page.url,
                    "links": links,
                    "error": None,
                }
            except Exception as exc:
                return {
                    "status": "browser_error",
                    "links": [],
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            finally:
                page.close()
                context.close()


def workflow_files_in_zip(path: Path) -> list[str]:
    found: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                lower = name.lower()
                if lower.endswith("/workflow.knime") or lower.endswith(".knwf"):
                    found.append(f"{path.name}::{name}")
    except zipfile.BadZipFile:
        return []
    return found


def scan_workflow_files(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    found: list[str] = []
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower == "workflow.knime" or lower.endswith(".knwf"):
            found.append(path.relative_to(directory).as_posix())
        elif lower.endswith(".zip"):
            found.extend(workflow_files_in_zip(path))
    return sorted(set(found))


def existing_by_rank(existing: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        int(record["rank"]): record
        for record in existing.get("records", [])
        if isinstance(record.get("rank"), int)
    }


def record_for_article(
    article: dict[str, Any],
    existing_record: dict[str, Any] | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    directory = article_dir(article, args.workflow_root)
    references = [workflow_reference(resource) for resource in article.get("linked_resources", [])]
    existing_result = (existing_record or {}).get("download_result", {})
    attempts: list[dict[str, Any]] = []

    if directory.exists():
        workflow_files = scan_workflow_files(directory)
        status = (
            existing_result.get("status")
            if existing_result.get("status") and workflow_files
            else ("downloaded_workflow_files" if workflow_files else "existing_directory_no_workflow_file_found")
        )
        download_result = {
            **existing_result,
            "directory": directory.as_posix(),
            "status": status,
            "downloaded_files": sorted(
                path.relative_to(directory).as_posix()
                for path in directory.rglob("*")
                if path.is_file()
            ),
            "workflow_files_found": workflow_files,
            "notes": existing_result.get("notes")
            or "Directory already existed; automatic download attempt skipped and local files were scanned.",
            "automatic_attempts": existing_result.get("automatic_attempts", []),
        }
    else:
        for resource in article.get("linked_resources", []):
            url = resource.get("url", "")
            if not url:
                continue
            if is_download_candidate(url):
                attempts.append(direct_download(url, directory, args))
            discovery = discover_browser_links(url, args)
            attempts.append({"url": url, "status": "browser_discovery", "browser": discovery})
            for link in discovery.get("links", []):
                href = str(link.get("href", ""))
                if href:
                    attempts.append(direct_download(href, directory, args))

        workflow_files = scan_workflow_files(directory)
        downloaded_files = (
            sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())
            if directory.exists()
            else []
        )
        if workflow_files:
            status = "downloaded_workflow_files_automatic"
        elif attempts:
            status = "automatic_attempt_no_workflow_file_found"
        else:
            status = "not_attempted_in_current_workflow_download_pass"
        download_result = {
            "directory": directory.as_posix(),
            "status": status,
            "downloaded_files": downloaded_files,
            "workflow_files_found": workflow_files,
            "notes": "Automatic browser/HTTP workflow download attempt completed.",
            "automatic_attempts": attempts,
        }

    return {
        "rank": article.get("rank"),
        "title": article.get("title", ""),
        "doi": article.get("doi", ""),
        "workflow_artifact_status": "workflow_reference_in_article_audit_report",
        "workflow_references": references,
        "download_result": download_result,
        "manual_knime_opening_tests": (existing_record or {}).get("manual_knime_opening_tests", []),
    }


def has_workflow_files(record: dict[str, Any]) -> bool:
    files = record.get("download_result", {}).get("workflow_files_found", [])
    return isinstance(files, list) and bool(files)


def status(record: dict[str, Any]) -> str:
    return str(record.get("download_result", {}).get("status", ""))


def summary_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "article_records_with_downloadable_workflow_references": len(records),
        "downloaded_with_workflow_files_or_workflow_directory": sum(1 for r in records if has_workflow_files(r)),
        "existing_directory_no_workflow_file_found": sum(
            1 for r in records if status(r) == "existing_directory_no_workflow_file_found"
        ),
        "automatic_attempt_no_workflow_file_found": sum(
            1 for r in records if status(r) == "automatic_attempt_no_workflow_file_found"
        ),
        "not_attempted_in_current_workflow_download_pass": sum(
            1 for r in records if status(r) == "not_attempted_in_current_workflow_download_pass"
        ),
        "failed_or_not_obtained": sum(
            1 for r in records if any(token in status(r) for token in ("failed", "not_obtained", "unavailable"))
        ),
    }


def main() -> int:
    args = parse_args()
    report = load_json(args.report)
    existing = load_json(args.existing)
    old_by_rank = existing_by_rank(existing)
    selected_ranks = set(args.rank or [])
    articles = [
        article
        for article in report.get("articles", [])
        if article.get("linked_resources")
        and (not selected_ranks or article.get("rank") in selected_ranks)
    ]
    if args.limit > 0:
        articles = articles[: args.limit]

    new_records = [
        record_for_article(article, old_by_rank.get(article.get("rank")), args)
        for article in articles
    ]
    new_ranks = {record.get("rank") for record in new_records}
    retained = [
        record
        for record in existing.get("records", [])
        if record.get("rank") not in new_ranks
    ]
    records = sorted(new_records + retained, key=lambda r: r.get("rank") if r.get("rank") is not None else 10**9)
    result = {
        "created_at": now_iso(),
        "source_assessment": args.report.as_posix(),
        "selection_rule": "Workflow-relevant linked_resources in article_audit_report.json are attempted automatically unless an article workflow directory already exists.",
        "url_status_note": "Automatic attempts do not solve captchas or bypass access controls. Manual follow-up should use this inventory as the checklist.",
        "records": records,
        "summary_counts": summary_counts(records),
    }
    write_json(args.output, result)
    print(f"Wrote {len(records)} workflow-reference records to {args.output}.")
    print(f"Attempted articles this run: {len(new_records)}.")
    print(f"Records with workflow files found: {result['summary_counts']['downloaded_with_workflow_files_or_workflow_directory']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
