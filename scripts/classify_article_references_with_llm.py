#!/usr/bin/env python3
"""Classify article reference URLs for KNIME workflow obtainability with an LLM.

Input is ``article_url_collection.json`` plus local fetched page files. The
script does not fetch URLs and does not read the full article text. It sends
only URL metadata and local downloaded page excerpts to the LLM.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/processed/audit/article_url_collection.json")
DEFAULT_PROMPT = Path("data/processed/audit/article_reference_classification_prompt.json")
DEFAULT_OUTPUT = Path("data/processed/audit/article_reference_llm_classifications.json")
DEFAULT_ENV_FILE = Path(".env")
DEFAULT_MODEL = "gpt-4.1-mini"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
MAX_OPENAI_RETRIES = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--rank", type=int, action="append")
    parser.add_argument("--rank-from", type=int, default=None)
    parser.add_argument("--rank-to", type=int, default=None)
    parser.add_argument("--limit", type=int, default=10, help="Maximum articles to process. 0 means all.")
    parser.add_argument("--urls-per-call", type=int, default=8)
    parser.add_argument("--max-page-chars", type=int, default=5000)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


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


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class TextExtractingHtmlParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "td", "th", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        self.parts.append(data)

    @property
    def title(self) -> str:
        return compact(" ".join(self.title_parts))

    @property
    def text(self) -> str:
        return compact(" ".join(self.parts))


def html_title_and_text(path: Path) -> tuple[str, str]:
    parser = TextExtractingHtmlParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.title, parser.text


def local_page_text(entry: dict[str, Any], max_chars: int) -> dict[str, Any]:
    body_file = entry.get("browser_page_body_file") or entry.get("browser_body_file")
    if not body_file:
        body_file = entry.get("page_body_file")
    if not body_file:
        return {"local_page_file": "", "local_page_title": "", "local_page_excerpt": ""}
    path = Path(str(body_file))
    if not path.exists():
        return {"local_page_file": body_file, "local_page_title": "", "local_page_excerpt": ""}
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm", ".txt", ".json", ".xml"}:
        if suffix in {".html", ".htm"}:
            title, text = html_title_and_text(path)
        else:
            title = ""
            text = compact(path.read_text(encoding="utf-8", errors="replace"))
        return {
            "local_page_file": path.as_posix(),
            "local_page_title": title,
            "local_page_excerpt": text[:max_chars],
        }
    return {
        "local_page_file": path.as_posix(),
        "local_page_title": "",
        "local_page_excerpt": f"Downloaded non-text file with suffix {suffix}.",
    }


def selected_articles(
    articles: list[dict[str, Any]],
    ranks: list[int] | None,
    rank_from: int | None,
    rank_to: int | None,
    limit: int,
) -> list[dict[str, Any]]:
    selected = []
    for article in articles:
        rank = article.get("rank")
        if ranks and rank not in ranks:
            continue
        if rank_from is not None and (rank is None or rank < rank_from):
            continue
        if rank_to is not None and (rank is None or rank > rank_to):
            continue
        selected.append(article)
    return selected[:limit] if limit > 0 else selected


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if size <= 0:
        return [items]
    return [items[index : index + size] for index in range(0, len(items), size)]


def build_reference_context(entry: dict[str, Any], max_page_chars: int) -> dict[str, Any]:
    page = local_page_text(entry, max_page_chars)
    return {
        "url": entry.get("url", ""),
        "fetch_status": entry.get("fetch_status"),
        "http_status_code": entry.get("http_status_code"),
        "final_url": entry.get("final_url"),
        "page_body_file": entry.get("page_body_file"),
        "browser_fetch_status": entry.get("browser_fetch_status"),
        "browser_http_status_code": entry.get("browser_http_status_code"),
        "browser_final_url": entry.get("browser_final_url"),
        "browser_title": entry.get("browser_title"),
        "browser_page_body_file": entry.get("browser_page_body_file"),
        **page,
    }


def article_reference_contexts(article: dict[str, Any], max_page_chars: int) -> list[dict[str, Any]]:
    refs = []
    for entry in article.get("urls", []):
        if isinstance(entry, dict) and entry.get("url"):
            refs.append(build_reference_context(entry, max_page_chars))
    return refs


def build_messages(prompt: dict[str, Any], article: dict[str, Any], refs: list[dict[str, Any]]) -> list[dict[str, str]]:
    meta = article.get("meta", {})
    seed = meta.get("openalex_seed_fields", {})
    user_payload = {
        "task": prompt.get("user_task"),
        "article_context": {
            "rank": article.get("rank"),
            "article_identifier": meta.get("article_identifier"),
            "title": seed.get("title"),
            "doi": seed.get("doi"),
            "source": seed.get("source"),
            "publication_year": seed.get("publication_year"),
        },
        "allowed_reference_types": prompt.get("allowed_reference_types"),
        "reference_type_definitions": prompt.get("reference_type_definitions"),
        "allowed_workflow_access": prompt.get("allowed_workflow_access"),
        "workflow_access_definitions": prompt.get("workflow_access_definitions"),
        "allowed_workflow_forms": prompt.get("allowed_workflow_forms"),
        "limitations": prompt.get("limitations"),
        "required_json_schema": prompt.get("required_json_schema"),
        "references_to_classify": refs,
    }
    return [
        {"role": "system", "content": prompt["system_instruction"]},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
    ]


def call_openai(
    *,
    api_key: str,
    model: str,
    temperature: float,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    encoded = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_CHAT_COMPLETIONS_URL,
        data=encoded,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(1, MAX_OPENAI_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            return json.loads(data["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == MAX_OPENAI_RETRIES:
                raise
            time.sleep(2 * attempt)
        except (urllib.error.URLError, TimeoutError):
            if attempt == MAX_OPENAI_RETRIES:
                raise
            time.sleep(2 * attempt)
    raise RuntimeError("OpenAI call failed after retries")


def classify_article(
    article: dict[str, Any],
    prompt: dict[str, Any],
    *,
    api_key: str,
    model: str,
    temperature: float,
    urls_per_call: int,
    max_page_chars: int,
) -> dict[str, Any]:
    refs = article_reference_contexts(article, max_page_chars)
    classifications = []
    for chunk in chunks(refs, urls_per_call):
        result = call_openai(
            api_key=api_key,
            model=model,
            temperature=temperature,
            messages=build_messages(prompt, article, chunk),
        )
        classifications.extend(result.get("references", []))
    return {
        "rank": article.get("rank"),
        "meta": copy.deepcopy(article.get("meta", {})),
        "reference_classifications": classifications,
    }


def main() -> int:
    args = parse_args()
    load_env_file(args.env_file)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required. Put it in .env or export it.")

    collection = load_json(args.input)
    prompt = load_json(args.prompt)
    articles = selected_articles(
        collection.get("articles", []), args.rank, args.rank_from, args.rank_to, args.limit
    )

    classified = []
    for index, article in enumerate(articles, start=1):
        print(f"[{index}/{len(articles)}] rank {article.get('rank')}")
        classified.append(
            classify_article(
                article,
                prompt,
                api_key=api_key,
                model=args.model,
                temperature=args.temperature,
                urls_per_call=args.urls_per_call,
                max_page_chars=args.max_page_chars,
            )
        )
        output = build_output(args, classified)
        output["status"] = "partial" if index < len(articles) else "complete"
        write_json(args.output, output)

    output = build_output(args, classified)
    output["status"] = "complete"
    write_json(args.output, output)
    print(f"Wrote {output['summary']['references_classified']} reference classifications to {args.output}.")
    return 0


def build_output(args: argparse.Namespace, classified: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "created_by": repo_relative_script_path(),
        "input": args.input.as_posix(),
        "prompt": args.prompt.as_posix(),
        "model": args.model,
        "temperature": args.temperature,
        "selection": {
            "ranks": args.rank or [],
            "rank_from": args.rank_from,
            "rank_to": args.rank_to,
            "limit": args.limit,
        },
        "scope": "LLM classification of article reference URLs using local fetched-page evidence only.",
        "summary": {
            "articles_processed": len(classified),
            "references_classified": sum(
                len(article.get("reference_classifications", [])) for article in classified
            ),
        },
        "articles": classified,
    }


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        sys.exit(130)
