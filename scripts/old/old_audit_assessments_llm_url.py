#!/usr/bin/env python3
"""Classify linked_resource URL types with bounded LLM calls.

The script does not open or fetch URLs. It sends only the local paragraph for
each URL to the LLM, then updates linked_resources[*].type.
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
from urllib.parse import urlparse


DEFAULT_INPUT = Path("data/processed/audit/old/article_deterministic_assessments.json")
DEFAULT_OUTPUT = Path("data/processed/audit/old/article_llm_url_assessments.json")
DEFAULT_TEXT_DIR = Path("data/processed/articles")
DEFAULT_PROMPT = Path("data/processed/audit/old/article_llm_url_prompts.json")
DEFAULT_ENV_FILE = Path(".env")
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


def repo_relative_script_path() -> str:
    path = Path(__file__).resolve()
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return Path(__file__).name

URL_TYPE_ALIASES = {
    "workflow_artifact": "workflow",
    "cited_workflow_artifact": "workflow",
    "input_data": "dataset",
    "cited_dataset": "dataset",
    "code_or_scripts": "code",
    "article_code": "code",
    "source_code": "code",
    "software_or_tool": "third_party_software",
    "cited_software_or_tool": "third_party_software",
    "cited_code_or_repository": "third_party_software",
    "software": "third_party_software",
    "tool": "third_party_software",
    "documentation_or_project_page": "documentation",
    "cited_documentation_or_project_page": "documentation",
    "article_or_publisher": "other_publication",
    "cited_article": "other_publication",
    "cited_other": "other_publication",
    "citation_or_reference": "other_publication",
    "malformed": "malformed_url",
    "partial_url": "malformed_url",
}
MAX_OPENAI_RETRIES = 3
URL_INVISIBLE_CHARS_RE = re.compile(r"[\u00ad\u200b\u200c\u200d\ufeff]")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-assessment", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--text-dir", type=Path, default=DEFAULT_TEXT_DIR)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        help="OpenAI model used for URL type classification.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperature for URL type classification. Use 0 for maximum repeatability.",
    )
    parser.add_argument("--rank", type=int, action="append", help="Assess only this citation rank.")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum records to process. 0 means all selected records.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=1800,
        help="Maximum characters sent for each URL paragraph.",
    )
    parser.add_argument(
        "--urls-per-call",
        type=int,
        default=20,
        help="Maximum URL contexts sent in a single LLM request.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


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


def clean_url_text(value: str) -> str:
    return URL_INVISIBLE_CHARS_RE.sub("", value)


def match_text(value: str) -> str:
    return clean_url_text(value).lower()


def compact_match_text(value: str) -> str:
    return re.sub(r"\s+", "", match_text(value))


def line_label(start: int, end: int) -> str:
    return str(start + 1) if start == end - 1 else f"{start + 1}-{end}"


def article_section_for_line(lines: list[str], start_index: int) -> str:
    heading_patterns = [
        re.compile(
            r"^(Abstract|Introduction|Background|Methods?|Results|Discussion|Conclusions?|Data availability|Code availability|Software availability|Availability)",
            re.IGNORECASE,
        ),
        re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z0-9,()/:;\- ]{2,90}$"),
    ]
    for index in range(start_index, -1, -1):
        value = compact(lines[index])
        if not value or len(value) > 120:
            continue
        if any(pattern.match(value) for pattern in heading_patterns):
            return value
    return "Abstract" if start_index < 80 else "Main text"


class HtmlBlockParser(HTMLParser):
    BLOCK_TAGS = {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "li",
        "figcaption",
        "td",
        "th",
    }
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[str] = []
        self._parts: list[str] = []
        self._current_tag = ""
        self.blocks: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.BLOCK_TAGS:
            self._stack.append(tag)
            if len(self._stack) == 1:
                self._parts = []
                self._current_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if tag not in self.BLOCK_TAGS or not self._stack:
            return
        if tag in self._stack:
            while self._stack:
                current = self._stack.pop()
                if current == tag:
                    break
        if not self._stack and self._parts:
            text = compact(" ".join(self._parts))
            if text:
                self.blocks.append(
                    {
                        "tag": self._current_tag,
                        "text": clean_url_text(text),
                        "is_heading": "true" if self._current_tag in self.HEADING_TAGS else "false",
                    }
                )
            self._parts = []
            self._current_tag = ""

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._parts.append(data)


def html_blocks(path: Path) -> list[dict[str, str]]:
    parser = HtmlBlockParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.blocks


def article_section_for_block(blocks: list[dict[str, str]], index: int) -> str:
    for prior in range(index, -1, -1):
        block = blocks[prior]
        if block.get("is_heading") == "true":
            return block.get("text", "")[:160] or "Main text"
    return "Main text"


def processed_text_path(article: dict[str, Any], text_dir: Path) -> Path | None:
    meta = article.get("meta", {})
    if meta.get("article_text_match_status") and meta.get("article_text_match_status") != "matched":
        return None
    candidates = [
        meta.get("processed_text_file"),
        article.get("processed_text_file"),
        article.get("source_text_file"),
    ]
    for candidate in candidates:
        if candidate:
            path = Path(str(candidate))
            if path.exists():
                return path
    return None


def url_variants(url: str) -> list[str]:
    variants = [url]
    stripped = re.sub(r"^https?://", "", url, flags=re.IGNORECASE).rstrip("/")
    if stripped:
        variants.append(stripped)
    no_trailing_slash = url.rstrip("/")
    if no_trailing_slash:
        variants.append(no_trailing_slash)
    return list(dict.fromkeys(variant for variant in variants if variant))


def url_tokens(url: str) -> list[str]:
    return url_variants(url)


def url_matches_window(url_re: re.Pattern[str], tokens: list[str], window: str) -> bool:
    normalized_window = match_text(window)
    compact_window = compact_match_text(window)
    if url_re.search(normalized_window):
        return True
    for token in tokens:
        normalized_token = match_text(token)
        compact_token = compact_match_text(token)
        if normalized_token and normalized_token in normalized_window:
            return True
        if compact_token and compact_token in compact_window:
            return True
    return False


def exact_url_in_text(url: str, text: str) -> bool:
    normalized_text = match_text(text)
    compact_text = compact_match_text(text)
    for variant in url_variants(url):
        normalized_variant = match_text(variant)
        compact_variant = compact_match_text(variant)
        if normalized_variant and normalized_variant in normalized_text:
            return True
        if compact_variant and compact_variant in compact_text:
            return True
    return False


def malformed_url_reason(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return "URL cannot be parsed."
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    if host in {"doi.org", "dx.doi.org"} and (not path or re.fullmatch(r"10\.\d+", path)):
        return "DOI URL is incomplete."
    if host in {"www.simulation"}:
        return "Host appears truncated."
    if host.endswith(".readthedoc"):
        return "Documentation URL appears truncated."
    if url.rstrip("/").lower() in {"https://doi.org", "http://doi.org", "https://dx.doi.org", "http://dx.doi.org"}:
        return "Bare DOI resolver URL has no DOI."
    return None


def url_spans(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in re.finditer(r"https?://\S+", text, re.IGNORECASE)]


def inside_span(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in spans)


def sentence_spans(text: str) -> list[tuple[int, int]]:
    text = text.strip()
    if not text:
        return []
    protected_spans = url_spans(text)
    spans: list[tuple[int, int]] = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in ".?!" and not inside_span(index, protected_spans):
            next_index = index + 1
            while next_index < len(text) and text[next_index] in "\"')]}":
                next_index += 1
            is_end = next_index >= len(text)
            is_boundary = is_end or (
                text[next_index].isspace()
                and (
                    next_index + 1 >= len(text)
                    or text[next_index + 1].isupper()
                    or text[next_index + 1].isdigit()
                    or text[next_index + 1] in "\"'([{"
                )
            )
            if is_boundary:
                spans.append((start, next_index))
                start = next_index
                while start < len(text) and text[start].isspace():
                    start += 1
                index = start
                continue
        index += 1
    if start < len(text):
        spans.append((start, len(text)))
    return [(start, end) for start, end in spans if text[start:end].strip()]


def find_url_position(text: str, url: str) -> int:
    lowered = text.lower()
    compact_lowered = compact_match_text(text)
    for variant in url_variants(url):
        exact = text.find(variant)
        if exact >= 0:
            return exact
        exact_lower = lowered.find(variant.lower())
        if exact_lower >= 0:
            return exact_lower
        compact_index = compact_lowered.find(compact_match_text(variant))
        if compact_index >= 0:
            return max(0, min(len(text) - 1, compact_index))
    return -1


def sentence_context_for_url(paragraph: str, url: str, max_chars: int) -> str:
    paragraph = compact(clean_url_text(paragraph))
    if not paragraph or max_chars <= 0 or len(paragraph) <= max_chars:
        return paragraph
    position = find_url_position(paragraph, url)
    if position < 0:
        return paragraph
    spans = sentence_spans(paragraph)
    if not spans:
        return paragraph
    sentence_index = 0
    for index, (start, end) in enumerate(spans):
        if start <= position < end:
            sentence_index = index
            break

    start_index = max(0, sentence_index - 2)
    end_index = min(len(spans), sentence_index + 3)
    selected = paragraph[spans[start_index][0] : spans[end_index - 1][1]].strip()
    while len(selected) < max_chars and (start_index > 0 or end_index < len(spans)):
        left = spans[start_index - 1] if start_index > 0 else None
        right = spans[end_index] if end_index < len(spans) else None
        candidates: list[tuple[str, int, int]] = []
        if left:
            candidates.append(("left", left[0], spans[end_index - 1][1]))
        if right:
            candidates.append(("right", spans[start_index][0], right[1]))
        fitting = [
            candidate
            for candidate in candidates
            if len(paragraph[candidate[1] : candidate[2]].strip()) <= max_chars
        ]
        if not fitting:
            break
        direction, _start, _end = min(
            fitting,
            key=lambda candidate: len(paragraph[candidate[1] : candidate[2]].strip()),
        )
        if direction == "left":
            start_index -= 1
        else:
            end_index += 1
        selected = paragraph[spans[start_index][0] : spans[end_index - 1][1]].strip()
    return selected


def paragraph_bounds(lines: list[str], index: int) -> tuple[int, int]:
    start = index
    while start > 0 and lines[start - 1].strip():
        start -= 1

    end = index + 1
    while end < len(lines) and lines[end].strip():
        end += 1

    # PDF extraction sometimes collapses paragraphs. Keep context local.
    if end - start > 14:
        start = max(0, index - 3)
        end = min(len(lines), index + 4)
    elif end - start < 2:
        start = max(0, index - 1)
        end = min(len(lines), index + 2)
    return start, end


def build_url_contexts(lines: list[str], urls: list[str]) -> list[dict[str, str]]:
    contexts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for url in urls:
        tokens = url_tokens(url)
        patterns = [re.escape(match_text(token)) for token in tokens]
        if not patterns:
            continue
        url_re = re.compile("|".join(patterns), re.IGNORECASE)
        for index, _line in enumerate(lines):
            window = "\n".join(lines[max(0, index - 1) : min(len(lines), index + 3)])
            if not url_matches_window(url_re, tokens, window):
                continue
            start, end = paragraph_bounds(lines, index)
            label = line_label(start, end)
            marker = (url, label)
            if marker in seen:
                continue
            seen.add(marker)
            contexts.append(
                {
                    "url": url,
                    "extracted_text_lines": label,
                    "article_section": article_section_for_line(lines, start),
                    "paragraph": clean_url_text(
                        "\n".join(line.rstrip() for line in lines[start:end] if line.strip())
                    ),
                }
            )
            break
    return contexts


def build_url_contexts_from_html(path: Path, urls: list[str]) -> list[dict[str, str]]:
    blocks = html_blocks(path)
    contexts: list[dict[str, str]] = []
    seen: set[str] = set()
    for url in urls:
        for index, block in enumerate(blocks):
            paragraph = block.get("text", "")
            if not exact_url_in_text(url, paragraph):
                continue
            if url in seen:
                break
            seen.add(url)
            contexts.append(
                {
                    "url": url,
                    "extracted_text_lines": f"html_block_{index + 1}",
                    "article_section": article_section_for_block(blocks, index),
                    "paragraph": paragraph,
                }
            )
            break
    return contexts


def truncate_url_contexts(contexts: list[dict[str, str]], max_chars: int) -> list[dict[str, str]]:
    truncated: list[dict[str, str]] = []
    for context in contexts:
        item = dict(context)
        paragraph = item.get("paragraph", "")
        item["paragraph"] = sentence_context_for_url(paragraph, item.get("url", ""), max_chars)
        truncated.append(item)
    return truncated


def chunks(items: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    if size <= 0:
        return [items]
    return [items[index : index + size] for index in range(0, len(items), size)]


def selected_articles(articles: list[dict[str, Any]], ranks: list[int] | None, limit: int) -> list[dict[str, Any]]:
    selected = [article for article in articles if not ranks or article.get("rank") in ranks]
    return selected[:limit] if limit > 0 else selected


def url_resources_to_classify(article: dict[str, Any]) -> list[dict[str, str]]:
    resources = article.get("linked_resources", [])
    if not isinstance(resources, list):
        return []
    return [
        item
        for item in resources
        if isinstance(item, dict)
        and item.get("url")
        and item.get("type", "undefined") == "undefined"
    ]


def merge_url_types(
    article: dict[str, Any],
    candidate: dict[str, Any],
    allowed_types: set[str],
    url_paragraphs: list[dict[str, str]],
) -> tuple[dict[str, Any], int]:
    updated = copy.deepcopy(article)
    resources = updated.get("linked_resources", [])
    if not isinstance(resources, list):
        return updated, 0

    paragraph_by_url = {
        item["url"]: item.get("paragraph", "")
        for item in url_paragraphs
        if isinstance(item.get("url"), str)
    }
    scoped_urls = set(paragraph_by_url)
    candidate_types: dict[str, str] = {}
    for item in candidate.get("linked_resources", []):
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        url_type = item.get("type")
        if isinstance(url_type, str):
            url_type = URL_TYPE_ALIASES.get(url_type, url_type)
        if (
            isinstance(url, str)
            and isinstance(url_type, str)
            and url_type in allowed_types
        ):
            candidate_types[url] = url_type

    changed = 0
    for item in resources:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if url not in scoped_urls:
            continue
        if isinstance(url, str):
            item["paragraph"] = paragraph_by_url.get(url, "")
        if url in candidate_types and item.get("type") == "undefined":
            item["type"] = candidate_types[url]
            changed += 1
        elif item.get("type") == "undefined":
            item["type"] = "unclear"
            changed += 1
    return updated, changed


def mark_urls(
    article: dict[str, Any],
    updates: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], int]:
    updated = copy.deepcopy(article)
    resources = updated.get("linked_resources", [])
    if not isinstance(resources, list):
        return updated, 0
    changed = 0
    for item in resources:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or url not in updates:
            continue
        update = updates[url]
        if item.get("type") == "undefined":
            item["type"] = update.get("type", "unclear")
            changed += 1
        item["paragraph"] = update.get("paragraph", item.get("paragraph", ""))
        if update.get("note"):
            item["note"] = update["note"]
    return updated, changed


class OpenAIUrlAssessor:
    def __init__(self, *, api_key: str, model: str, temperature: float, prompt: dict[str, Any]) -> None:
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.prompt = prompt
        self.calls = 0

    def classify_urls(
        self,
        *,
        article: dict[str, Any],
        resources: list[dict[str, str]],
        url_paragraphs: list[dict[str, str]],
    ) -> dict[str, Any]:
        meta = article.get("meta", {})
        seed = meta.get("openalex_seed_fields", {})
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self.prompt["system_instruction"]},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": self.prompt["user_task"],
                            "limitations": self.prompt["limitations"],
                            "allowed_types": self.prompt["allowed_types"],
                            "type_definitions": self.prompt["type_definitions"],
                            "required_json_schema": self.prompt["required_json_schema"],
                            "article_metadata": {
                                "rank": article.get("rank"),
                                "article_identifier": meta.get("article_identifier", ""),
                                "title": seed.get("title", ""),
                                "year": seed.get("publication_year", ""),
                                "venue": seed.get("source", ""),
                                "doi": seed.get("doi", ""),
                            },
                            "urls_to_classify": resources,
                            "url_paragraphs": url_paragraphs,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            OPENAI_CHAT_COMPLETIONS_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        for attempt in range(1, MAX_OPENAI_RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    data = json.load(response)
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code < 500 or attempt == MAX_OPENAI_RETRIES:
                    raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
                time.sleep(2 * attempt)
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt == MAX_OPENAI_RETRIES:
                    reason = getattr(exc, "reason", exc)
                    raise RuntimeError(f"OpenAI API request failed after retries: {reason}") from exc
                time.sleep(2 * attempt)
        else:
            raise RuntimeError("OpenAI API request failed without a response.")

        self.calls += 1
        if self.calls % 5 == 0:
            print(f"LLM URL-classification calls completed: {self.calls}", file=sys.stderr, flush=True)
        return json.loads(data["choices"][0]["message"]["content"])


def main() -> int:
    args = parse_args()
    input_assessment = load_json(args.input_assessment)
    prompt = load_json(args.prompt)
    input_articles = input_assessment.get("articles", [])
    articles = selected_articles(input_articles, args.rank, args.limit)
    allowed_types = set(prompt.get("allowed_types", []))

    calls_needed = any(url_resources_to_classify(article) for article in articles)
    if calls_needed:
        load_env_file(args.env_file)
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY is required. Put it in .env or export it in the environment.")
    else:
        api_key = "not-used"

    assessor = OpenAIUrlAssessor(
        api_key=api_key,
        model=args.model,
        temperature=args.temperature,
        prompt=prompt,
    )
    result_articles: list[dict[str, Any]] = []
    skipped_no_urls = 0
    skipped_no_text = 0
    typed_urls = 0
    urls_marked_malformed = 0

    for article in articles:
        resources = url_resources_to_classify(article)
        if not resources:
            result_articles.append(copy.deepcopy(article))
            skipped_no_urls += 1
            continue

        text_path = processed_text_path(article, args.text_dir)
        if text_path is None:
            result_articles.append(copy.deepcopy(article))
            skipped_no_text += 1
            continue

        urls = [item["url"] for item in resources]
        contexts = truncate_url_contexts(build_url_contexts_from_html(text_path, urls), args.max_chars)
        context_by_url = {item["url"]: item for item in contexts}
        updated = copy.deepcopy(article)
        changed = 0

        malformed_updates: dict[str, dict[str, str]] = {}
        llm_resources: list[dict[str, str]] = []
        for resource in resources:
            url = resource["url"]
            reason = malformed_url_reason(url)
            if reason:
                malformed_updates[url] = {
                    "type": "malformed_url",
                    "paragraph": context_by_url.get(url, {}).get("paragraph", ""),
                    "note": reason,
                }
            elif url not in context_by_url:
                malformed_updates[url] = {
                    "type": "malformed_url",
                    "paragraph": "",
                    "note": "Exact URL was not found in the generated article HTML text.",
                }
            else:
                llm_resources.append(resource)

        if malformed_updates:
            updated, malformed_changed = mark_urls(updated, malformed_updates)
            changed += malformed_changed
            urls_marked_malformed += malformed_changed

        for resource_batch in chunks(llm_resources, args.urls_per_call):
            batch_contexts = [
                context_by_url[item["url"]]
                for item in resource_batch
                if item.get("url") in context_by_url
            ]
            if not batch_contexts:
                candidate = {"linked_resources": []}
            else:
                candidate = assessor.classify_urls(
                    article=article,
                    resources=resource_batch,
                    url_paragraphs=batch_contexts,
                )
            updated, batch_changed = merge_url_types(updated, candidate, allowed_types, batch_contexts)
            changed += batch_changed
        result_articles.append(updated)
        typed_urls += changed

    result = copy.deepcopy(input_assessment)
    result["created_by"] = repo_relative_script_path()
    result["source_assessment"] = args.input_assessment.as_posix()
    result["text_dir"] = args.text_dir.as_posix()
    result["prompt"] = args.prompt.as_posix()
    result["model"] = args.model
    result["temperature"] = args.temperature
    result["method"] = {
        "input_files": "URL-normalized deterministic assessment and processed article text.",
        "assessment_focus": [
            "linked_resources URL type classification",
            "paragraph-local URL context",
        ],
        "url_policy": "URLs under audit are not opened, fetched, or externally checked.",
    }
    result["limitations"] = [
        "This step uses an LLM.",
        "The LLM may use only the supplied paragraph for each URL.",
        "URL type assignments are not evidence that the URL is currently reachable.",
        "Unclear paragraph evidence should leave URL type as unclear.",
        "No article_audit_fields are changed by this step.",
    ]
    result["scope"] = {
        "limit": args.limit,
        "ranks": args.rank or [],
        "records_written": len(result_articles),
        "llm_api_calls": assessor.calls,
        "records_skipped_no_undefined_urls": skipped_no_urls,
        "records_skipped_no_local_text": skipped_no_text,
        "url_types_filled": typed_urls,
        "urls_marked_malformed_without_llm": urls_marked_malformed,
        "url_call_policy": "URLs were not opened or fetched; classification used only article text.",
        "urls_per_call": args.urls_per_call,
        "max_chars_per_url_context": args.max_chars,
    }
    result["articles"] = result_articles

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)

    print(f"Wrote {len(result_articles)} URL-typed article records to {args.output}.")
    print(f"LLM URL-classification API calls: {assessor.calls}.")
    print(f"URL types filled: {typed_urls}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
