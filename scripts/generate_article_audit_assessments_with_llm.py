#!/usr/bin/env python3
"""Generate LLM article-audit assessment candidates from extracted article text."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ASSESSMENT = Path("data/processed/audit/knime_most_cited_article_assessments.json")
DEFAULT_QUESTIONS = Path("data/processed/audit/knime_article_audit_questions.json")
DEFAULT_TEXT_DIR = Path("data/processed/articles")
DEFAULT_ENV_FILE = Path(".env")
DEFAULT_PROMPT = Path("data/processed/audit/llm_article_assessment_prompt.json")
DEFAULT_OUTPUT = Path("data/processed/audit/logs/llm_article_assessment_candidates.jsonl")
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

EXCERPT_PATTERNS = [
    r"\bKNIME\b",
    r"Konstanz Information Miner",
    r"\bworkflow\b",
    r"work\ufb02ow",
    r"\bnodes?\b",
    r"\bpipeline\b",
    r"Data availability",
    r"Availability of data",
    r"Code availability",
    r"Software availability",
    r"Supplement",
    r"Supporting Information",
    r"GitHub",
    r"Figshare",
    r"Zenodo",
    r"myExperiment",
    r"KNIME Hub",
    r"version",
    r"plug-?in",
    r"extension",
    r"update site",
    r"RDKit",
    r"Indigo",
    r"CDK",
    r"ChemAxon",
    r"ImageJ",
    r"FIJI",
    r"https?://",
]

FLAG_NAMES = [
    "full_text_accessible",
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
    "linked_workflow_artifacts_retrievable",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, default=DEFAULT_ASSESSMENT)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--text-dir", type=Path, default=DEFAULT_TEXT_DIR)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        help="OpenAI model used for article assessment.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperature for LLM article assessment. Use 0 for maximum repeatability.",
    )
    parser.add_argument(
        "--rank",
        type=int,
        action="append",
        help="Assess only this rank. Can be passed more than once.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of articles to assess in this run. 0 means no limit.",
    )
    parser.add_argument(
        "--max-excerpts",
        type=int,
        default=45,
        help="Maximum excerpt windows sent to the LLM per article.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=22000,
        help="Approximate maximum excerpt text characters sent to the LLM per article.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Apply generated article_audit_fields to the assessment JSON. "
            "Default only writes candidate records to --output."
        ),
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


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("._")
    return slug or "article"


def text_path_for_article(article: dict[str, Any], text_dir: Path) -> Path | None:
    processed = article.get("processed_text_file")
    if processed:
        candidate = Path(processed)
        if candidate.exists():
            return candidate
    pdf_file = article.get("pdf_file")
    if not pdf_file:
        return None
    candidate = text_dir / f"{slugify(Path(pdf_file).stem)}.txt"
    if candidate.exists():
        return candidate
    return None


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def line_label(start: int, end: int) -> str:
    return str(start + 1) if start == end - 1 else f"{start + 1}-{end}"


def article_section_for_line(lines: list[str], start_index: int) -> str:
    heading_patterns = [
        re.compile(r"^(Abstract|Introduction|Background|Methods?|Results|Discussion|Conclusions?|Data availability|Code availability|Software availability|Availability)", re.IGNORECASE),
        re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z0-9,()/:;\- ]{2,90}$"),
    ]
    for index in range(start_index, -1, -1):
        value = compact(lines[index])
        if not value or len(value) > 120:
            continue
        if any(pattern.match(value) for pattern in heading_patterns):
            return value
    if start_index < 80:
        return "Abstract"
    return "Main text"


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def build_excerpts(
    lines: list[str],
    *,
    max_excerpts: int,
    max_chars: int,
) -> list[dict[str, str]]:
    ranges: list[tuple[int, int]] = []
    if lines:
        ranges.append((0, min(len(lines), 80)))

    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in EXCERPT_PATTERNS]
    for index, line in enumerate(lines):
        haystack = compact(" ".join(lines[index : index + 2]))
        if any(pattern.search(haystack) for pattern in patterns):
            ranges.append((max(0, index - 4), min(len(lines), index + 7)))

    excerpts: list[dict[str, str]] = []
    total_chars = 0
    for start, end in merge_ranges(ranges):
        text = "\n".join(line.rstrip() for line in lines[start:end] if line.strip())
        if not text.strip():
            continue
        item = {
            "extracted_text_lines": line_label(start, end),
            "article_section": article_section_for_line(lines, start),
            "text": text[:2200],
        }
        item_chars = len(item["text"])
        if excerpts and total_chars + item_chars > max_chars:
            break
        excerpts.append(item)
        total_chars += item_chars
        if len(excerpts) >= max_excerpts:
            break
    return excerpts


def empty_not_assessed_candidate(article: dict[str, Any]) -> dict[str, Any]:
    desc = {
        "article_identifier": str(article.get("article_identifier", "")),
        "title": str(article.get("title", "")),
        "year": str(article.get("publication_year", "")),
        "venue": str(article.get("venue", "")),
        "doi_or_url": str(article.get("doi_or_url") or article.get("doi") or ""),
        "knime_role_source_field": "not_assessed_no_local_text",
        "knime_article_relation": "not_assessed",
        "knime_version_values": "",
        "workflow_artifact_status": "not_assessed",
        "provides_input_data": "not_assessed",
        "provides_code_or_scripts": "not_assessed",
        "reports_extension_or_plugin_dependencies": "not_assessed",
        "reports_extension_installation_source": "not_assessed",
        "linked_workflow_artifacts_retrievable": "not_assessed",
        "evidence_notes": "No local processed article text was available for LLM assessment.",
    }
    return {
        "description_audit_fields": desc,
        "flag_audit_fields": {flag: False for flag in FLAG_NAMES},
        "flag_audit_support": {},
        "linked_resources": article.get("linked_resources", {}),
        "confidence": "low",
        "needs_human_review": True,
    }


def normalize_candidate(candidate: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    desc = candidate.setdefault("description_audit_fields", {})
    desc.setdefault("article_identifier", str(article.get("article_identifier", "")))
    desc.setdefault("title", str(article.get("title", "")))
    desc.setdefault("year", str(article.get("publication_year", "")))
    desc.setdefault("venue", str(article.get("venue", "")))
    desc.setdefault("doi_or_url", str(article.get("doi_or_url") or article.get("doi") or ""))
    desc.setdefault("knime_role_source_field", "llm_assessed")
    desc.setdefault("knime_version_values", "")
    desc.setdefault("evidence_notes", "")

    flags = candidate.setdefault("flag_audit_fields", {})
    for flag in FLAG_NAMES:
        flags[flag] = bool(flags.get(flag, False))

    relation = desc.get("knime_article_relation")
    if relation == "about_knime":
        candidate["flag_audit_fields"] = {}
        candidate["flag_audit_support"] = {}
    else:
        support = candidate.setdefault("flag_audit_support", {})
        if flags.get("full_text_accessible") and "full_text_accessible" not in support:
            support["full_text_accessible"] = [
                {
                    "extracted_text_lines": "processed_text_file",
                    "article_section": "Local text",
                    "quote": "",
                    "note": "Processed article text was available to the LLM assessment script.",
                }
            ]
        for flag, value in list(flags.items()):
            if value and flag != "full_text_accessible" and not support.get(flag):
                flags[flag] = False
                candidate["needs_human_review"] = True
    candidate.setdefault("linked_resources", article.get("linked_resources", {}))
    candidate.setdefault("confidence", "low")
    candidate.setdefault("needs_human_review", True)
    return candidate


class OpenAIArticleAssessor:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        temperature: float,
        prompt: dict[str, Any],
        questions: dict[str, Any],
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.prompt = prompt
        self.questions = questions
        self.calls = 0

    def assess(self, article: dict[str, Any], excerpts: list[dict[str, str]]) -> dict[str, Any]:
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
                            "evidence_rules": self.prompt["evidence_rules"],
                            "allowed_description_values": self.prompt[
                                "allowed_description_values"
                            ],
                            "flag_definitions": self.prompt["flag_definitions"],
                            "audit_questions": self.questions,
                            "required_json_schema": self.prompt["required_json_schema"],
                            "article_metadata": {
                                "rank": article.get("rank"),
                                "article_identifier": article.get("article_identifier", ""),
                                "title": article.get("title", ""),
                                "year": article.get("publication_year", ""),
                                "venue": article.get("venue", ""),
                                "doi_or_url": article.get("doi_or_url")
                                or article.get("doi")
                                or "",
                            },
                            "resource_hints": article.get("linked_resources", {}),
                            "article_excerpts": excerpts,
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
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI API request failed: {exc.reason}") from exc

        self.calls += 1
        if self.calls % 5 == 0:
            print(f"LLM article-assessment calls completed: {self.calls}", file=sys.stderr, flush=True)
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)


def summary_counts(articles: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, Any] = {flag: 0 for flag in FLAG_NAMES}
    counts["total_records"] = len(articles)
    relation_counts: dict[str, int] = {}
    for article in articles:
        audit = article.get("article_audit_fields", {})
        desc = audit.get("description_audit_fields", {})
        relation = desc.get("knime_article_relation", "")
        if relation:
            relation_counts[relation] = relation_counts.get(relation, 0) + 1
        if relation == "about_knime":
            continue
        flags = audit.get("flag_audit_fields", {})
        for flag in FLAG_NAMES:
            if flags.get(flag) is True:
                counts[flag] += 1
    counts["knime_article_relation_counts"] = relation_counts
    return counts


def selected_articles(articles: list[dict[str, Any]], ranks: list[int] | None, limit: int) -> list[dict[str, Any]]:
    selected = [article for article in articles if not ranks or article.get("rank") in ranks]
    if limit > 0:
        selected = selected[:limit]
    return selected


def main() -> int:
    args = parse_args()
    assessment = load_json(args.assessment)
    questions = load_json(args.questions)
    prompt = load_json(args.prompt)
    load_env_file(args.env_file)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is required. Put it in .env or export it in the environment."
        )

    assessor = OpenAIArticleAssessor(
        api_key=api_key,
        model=args.model,
        temperature=args.temperature,
        prompt=prompt,
        questions=questions,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    articles = selected_articles(assessment["articles"], args.rank, args.limit)
    written = 0
    applied = 0
    with args.output.open("w", encoding="utf-8") as output:
        for article in articles:
            text_path = text_path_for_article(article, args.text_dir)
            if text_path is None:
                candidate = empty_not_assessed_candidate(article)
                source_text_file = None
            else:
                lines = text_path.read_text(encoding="utf-8", errors="replace").splitlines()
                excerpts = build_excerpts(
                    lines,
                    max_excerpts=args.max_excerpts,
                    max_chars=args.max_chars,
                )
                candidate = assessor.assess(article, excerpts)
                source_text_file = text_path.as_posix()

            candidate = normalize_candidate(candidate, article)
            record = {
                "rank": article.get("rank"),
                "article_identifier": article.get("article_identifier", ""),
                "title": article.get("title", ""),
                "source_text_file": source_text_file,
                "model": args.model if source_text_file else None,
                "temperature": args.temperature if source_text_file else None,
                "llm_assessment": candidate,
            }
            json.dump(record, output, ensure_ascii=False)
            output.write("\n")
            written += 1

            if args.apply:
                article["article_audit_fields"] = {
                    "description_audit_fields": candidate["description_audit_fields"],
                    "flag_audit_fields": candidate["flag_audit_fields"],
                    "flag_audit_support": candidate.get("flag_audit_support", {}),
                }
                article["linked_resources"] = candidate.get(
                    "linked_resources", article.get("linked_resources", {})
                )
                if source_text_file:
                    article["processed_text_file"] = source_text_file
                    article["manual_assessment_status"] = "llm_assessed_from_local_text"
                applied += 1

    if args.apply:
        assessment["article_audit_summary_counts"] = summary_counts(assessment["articles"])
        write_json(args.assessment, assessment)

    print(
        f"Wrote {written} LLM article-assessment candidate records to {args.output}."
    )
    print(f"LLM article-assessment API calls: {assessor.calls}.")
    if args.apply:
        print(f"Applied {applied} candidate assessments to {args.assessment}.")
    else:
        print("Main assessment JSON was not modified. Use --apply to update it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
