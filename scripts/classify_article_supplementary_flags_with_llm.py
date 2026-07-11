#!/usr/bin/env python3
"""Classify supplementary article-level workflow-reporting flags with an LLM.

Input is the reference-page classification file plus processed article HTML.
This step is intentionally separate from reference-page workflow discovery. It
adds article-level signals such as KNIME version reporting, workflow figures,
data/code availability, and dependency reporting for analysis.
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


DEFAULT_INPUT = Path("data/processed/audit/article_reference_llm_classifications.json")
DEFAULT_PROMPT = Path("data/processed/audit/article_supplementary_flag_prompt.json")
DEFAULT_OUTPUT = Path("data/processed/audit/article_supplementary_llm_flags.json")
DEFAULT_ENV_FILE = Path(".env")
DEFAULT_MODEL = "gpt-4.1-mini"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
MAX_OPENAI_RETRIES = 3

FLAG_NAMES = [
    "uses_knime",
    "reports_knime_version",
    "provides_downloadable_knime_workflow_files",
    "provides_workflow_screenshots_or_figures",
    "describes_workflow_or_nodes_in_text",
    "provides_input_data_direct_url",
    "reports_input_data_availability",
    "provides_code_or_scripts",
    "reports_extension_or_plugin_dependencies",
    "reports_extension_installation_source",
]

KEYWORD_RE = re.compile(
    r"\b("
    r"KNIME|workflow|workflows|node|nodes|component|metanode|version|"
    r"data availability|available at|available from|dataset|datasets|"
    r"code|script|scripts|github|gitlab|repository|source code|"
    r"supplementary|supporting information|extension|plugin|update site|"
    r"installation|install|dependency|dependencies|download|downloadable"
    r")\b",
    re.IGNORECASE,
)


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
    parser.add_argument("--max-article-chars", type=int, default=18000)
    parser.add_argument("--max-reference-evidence", type=int, default=30)
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


class ArticleHtmlParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg"}
    BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "figcaption"}

    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.current_tag = ""
        self.current_id = ""
        self.current_class = ""
        self.current_parts: list[str] = []
        self.blocks: list[dict[str, str]] = []

    def flush(self) -> None:
        text = compact(" ".join(self.current_parts))
        if text:
            self.blocks.append(
                {
                    "tag": self.current_tag,
                    "id": self.current_id,
                    "class": self.current_class,
                    "text": text,
                }
            )
        self.current_tag = ""
        self.current_id = ""
        self.current_class = ""
        self.current_parts = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag in self.BLOCK_TAGS:
            if self.current_parts:
                self.flush()
            attr = {name: value or "" for name, value in attrs}
            self.current_tag = tag
            self.current_id = attr.get("id", "")
            self.current_class = attr.get("class", "")
        if tag == "br" and self.current_parts:
            self.current_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in self.BLOCK_TAGS and self.current_parts:
            self.flush()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.current_tag:
            self.current_parts.append(data)


def article_blocks(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    parser = ArticleHtmlParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    if parser.current_parts:
        parser.flush()
    return parser.blocks


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


def block_kind(block: dict[str, str]) -> str:
    class_name = block.get("class", "")
    block_id = block.get("id", "")
    text = block.get("text", "")
    if "figure" in class_name or block_id.startswith("fig_") or text.lower().startswith("fig."):
        return "figure"
    return block.get("tag", "")


def article_excerpt(blocks: list[dict[str, str]], max_chars: int) -> list[dict[str, str]]:
    candidates: dict[int, int] = {}

    def add(index: int, priority: int) -> None:
        if 0 <= index < len(blocks):
            candidates[index] = min(priority, candidates.get(index, priority))

    for index, block in enumerate(blocks):
        text = block.get("text", "")
        lowered = text.lower()
        kind = block_kind(block)

        if index < 6:
            add(index, 5)
        if any(
            marker in lowered
            for marker in [
                "data availability",
                "availability of data",
                "code availability",
                "software availability",
                "supporting information",
                "supplementary information",
            ]
        ):
            add(index, 0)
            add(index + 1, 0)
            add(index + 2, 1)
        if re.search(r"\bknime\b", text, re.IGNORECASE):
            add(index, 1)
        if re.search(r"\b(workflow|workflows|node|nodes|metanode|component)\b", text, re.IGNORECASE):
            add(index, 2)
        if any(marker in lowered for marker in ["github", "gitlab", "source code", "script", "scripts"]):
            add(index, 2)
        if any(marker in lowered for marker in ["dataset", "datasets", "repository", "accession", "available at"]):
            add(index, 2)
        if kind == "figure" and re.search(r"\b(knime|workflow|node|nodes)\b", text, re.IGNORECASE):
            add(index, 1)
        if KEYWORD_RE.search(text):
            add(index, 4)

    selected: list[dict[str, str]] = []
    seen = set()
    for index, _priority in sorted(candidates.items(), key=lambda item: (item[1], item[0])):
        text = blocks[index].get("text", "")
        key = text[:160]
        if key in seen:
            continue
        seen.add(key)
        if len(text) > 1400:
            text = text[:1400]
        selected.append(
            {
                "block_index": str(index),
                "kind": block_kind(blocks[index]),
                "text": text,
            }
        )

    total = 0
    clipped = []
    for block in selected:
        text = block["text"]
        if total + len(text) > max_chars:
            remaining = max_chars - total
            if remaining <= 200:
                break
            block = dict(block)
            block["text"] = text[:remaining]
            clipped.append(block)
            break
        clipped.append(block)
        total += len(text)
    return clipped


def reference_evidence(article: dict[str, Any], max_items: int) -> list[dict[str, Any]]:
    refs = article.get("reference_classifications", [])
    priority_access = {
        "direct_workflow_available",
        "workflow_landing_page_available",
        "possible_workflow_requires_inspection",
        "manual_check_required",
    }
    priority_types = {
        "knime_workflow_direct_file",
        "knime_hub_workflow",
        "myexperiment_workflow",
        "workflow_repository",
        "possible_workflow_supplement",
        "code_repository",
        "dataset_or_input_data",
        "third_party_software_or_documentation",
    }

    selected = [
        ref
        for ref in refs
        if ref.get("workflow_access") in priority_access
        or ref.get("reference_type") in priority_types
    ]
    if len(selected) < max_items:
        selected.extend(ref for ref in refs if ref not in selected)

    evidence = []
    for ref in selected[:max_items]:
        evidence.append(
            {
                "url": ref.get("url", ""),
                "reference_type": ref.get("reference_type", ""),
                "workflow_access": ref.get("workflow_access", ""),
                "workflow_form": ref.get("workflow_form", ""),
                "evidence_quote": ref.get("evidence_quote", ""),
                "reason": ref.get("reason", ""),
                "confidence": ref.get("confidence", ""),
            }
        )
    return evidence


def build_messages(
    prompt: dict[str, Any],
    article: dict[str, Any],
    excerpts: list[dict[str, str]],
    refs: list[dict[str, Any]],
) -> list[dict[str, str]]:
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
            "processed_text_file": meta.get("processed_text_file"),
        },
        "flags_to_fill": prompt.get("flags"),
        "limitations": prompt.get("limitations"),
        "required_json_schema": prompt.get("required_json_schema"),
        "article_text_excerpts": excerpts,
        "reference_page_classifications": refs,
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
            with urllib.request.urlopen(request, timeout=120) as response:
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


def normalize_flags(result: dict[str, Any]) -> dict[str, bool]:
    raw = result.get("flag_audit_fields", {})
    return {name: bool(raw.get(name, False)) for name in FLAG_NAMES}


def classify_article(
    article: dict[str, Any],
    prompt: dict[str, Any],
    *,
    api_key: str,
    model: str,
    temperature: float,
    max_article_chars: int,
    max_reference_evidence: int,
) -> dict[str, Any]:
    meta = article.get("meta", {})
    text_file = meta.get("processed_text_file")
    text_path = Path(text_file) if text_file and text_file != "undefined" else None
    blocks = article_blocks(text_path)
    excerpts = article_excerpt(blocks, max_article_chars)
    refs = reference_evidence(article, max_reference_evidence)
    result = call_openai(
        api_key=api_key,
        model=model,
        temperature=temperature,
        messages=build_messages(prompt, article, excerpts, refs),
    )
    if excerpts:
        assessment_status = "assessed"
    elif refs:
        assessment_status = "assessed_from_reference_evidence_only"
    else:
        assessment_status = "assessed_from_metadata_only"
    return {
        "rank": article.get("rank"),
        "meta": copy.deepcopy(meta),
        "assessment_status": assessment_status,
        "flag_audit_fields": normalize_flags(result),
        "flag_evidence": result.get("flag_evidence", {}),
        "confidence": result.get("confidence", "low"),
        "input_summary": {
            "article_excerpt_blocks_sent": len(excerpts),
            "reference_classifications_sent": len(refs),
        },
    }


def build_output(args: argparse.Namespace, classified: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {name: 0 for name in FLAG_NAMES}
    for article in classified:
        flags = article.get("flag_audit_fields", {})
        for name in FLAG_NAMES:
            if flags.get(name) is True:
                counts[name] += 1
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
        "scope": "Supplementary article-level flags from processed article text plus prior URL/reference-page evidence.",
        "summary": {
            "articles_processed": len(classified),
            "true_flag_counts": counts,
        },
        "articles": classified,
    }


def main() -> int:
    args = parse_args()
    load_env_file(args.env_file)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required. Put it in .env or export it.")

    source = load_json(args.input)
    prompt = load_json(args.prompt)
    articles = selected_articles(
        source.get("articles", []), args.rank, args.rank_from, args.rank_to, args.limit
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
                max_article_chars=args.max_article_chars,
                max_reference_evidence=args.max_reference_evidence,
            )
        )
        output = build_output(args, classified)
        output["status"] = "partial" if index < len(articles) else "complete"
        write_json(args.output, output)

    output = build_output(args, classified)
    output["status"] = "complete"
    write_json(args.output, output)
    print(f"Wrote {len(classified)} supplementary article flag records to {args.output}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        sys.exit(130)
