#!/usr/bin/env python3
"""Review and correct article-audit fields with bounded LLM calls."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/processed/audit/article_deterministic_assessments.json")
DEFAULT_QUESTIONS = Path("data/processed/audit/knime_article_audit_questions.json")
DEFAULT_TEXT_DIR = Path("data/processed/articles")
DEFAULT_ENV_FILE = Path(".env")
DEFAULT_PROMPT = Path("data/processed/audit/article_llm_flag_assessment_prompt.json")
DEFAULT_OUTPUT = Path(
    "data/processed/audit/article_llm_flag_assessments.json"
)
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

KNIME_USE_EVIDENCE_PATTERNS = [
    r"\bimplemented in KNIME\b",
    r"\bmodel(?:ing)?\s+using KNIME\b",
    r"\bstandardi[sz]ed\b.{0,80}\busing KNIME\b",
    r"\bdata mining\b.{0,80}\busing KNIME and Orange platforms\b",
    r"\bKNIME\b.{0,120}\bworkflow was used\b",
    r"\bKNIME workflow was used\b",
    r"\bKNIME platform is adopted\b",
    r"\badopted to set-up the model workflow\b",
    r"\bKNIME based model\b",
    r"\bdeployed on KNIME\b",
    r"\bdata mining model was deployed on KNIME\b",
    r"\bKNIME and Orange platforms\b",
]

KNIME_FIGURE_EVIDENCE_PATTERNS = [
    r"\bFigure\s+\d+[^.]{0,160}\bKNIME workflow\b",
    r"\bKNIME workflow[^.]{0,160}\bFigure\s+\d+",
    r"\bKNIME workflows?\s*\(Supplementary Figs?\.",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-assessment",
        type=Path,
        default=DEFAULT_INPUT,
        help="Assessment JSON whose article_audit_fields should be reviewed.",
    )
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
        default=10,
        help="Maximum number of deterministic assessment records to process in this run. 0 means no limit.",
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


def normalize_doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    return value.lower()


def text_path_for_article(article: dict[str, Any], text_dir: Path) -> Path | None:
    meta = article.get("meta", {})
    if meta.get("article_text_match_status") and meta.get("article_text_match_status") != "matched":
        return None
    existing = (
        meta.get("processed_text_file")
        or article.get("processed_text_file")
        or article.get("source_text_file")
    )
    if existing:
        path = Path(str(existing))
        if path.exists():
            return path

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
        ranges.append((0, min(len(lines), 30)))

    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in EXCERPT_PATTERNS]
    for index, line in enumerate(lines):
        haystack = compact(" ".join(lines[index : index + 2]))
        if any(pattern.search(haystack) for pattern in patterns):
            ranges.append((max(0, index - 3), min(len(lines), index + 4)))

    excerpts: list[dict[str, str]] = []
    total_chars = 0
    used_ranges: list[tuple[int, int]] = []
    for start, end in ranges:
        if any(start >= used_start and end <= used_end for used_start, used_end in used_ranges):
            continue
        text = "\n".join(line.rstrip() for line in lines[start:end] if line.strip())
        if not text.strip():
            continue
        if len(text) > 2200:
            match = next((pattern.search(text) for pattern in patterns if pattern.search(text)), None)
            if match:
                slice_start = max(0, match.start() - 900)
                slice_end = min(len(text), slice_start + 2200)
                text = text[slice_start:slice_end]
            else:
                text = text[:2200]
        item = {
            "extracted_text_lines": line_label(start, end),
            "article_section": article_section_for_line(lines, start),
            "text": text,
        }
        item_chars = len(item["text"])
        if excerpts and total_chars + item_chars > max_chars:
            break
        excerpts.append(item)
        used_ranges.append((start, end))
        total_chars += item_chars
        if len(excerpts) >= max_excerpts:
            break
    return excerpts


def assessment_targets(article: dict[str, Any]) -> dict[str, list[str]]:
    audit = article.get("article_audit_fields", {})
    desc = audit.get("description_audit_fields", {})
    flags = audit.get("flag_audit_fields", {})
    return {
        "description_audit_fields": list(desc.keys()),
        "flag_audit_fields": list(flags.keys()) or FLAG_NAMES,
    }


def has_assessment_targets(targets: dict[str, list[str]]) -> bool:
    return any(targets.values())


def excerpts_text(excerpts: list[dict[str, str]]) -> str:
    return "\n".join(str(excerpt.get("text", "")) for excerpt in excerpts)


def has_pattern_evidence(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns)


def apply_direct_evidence_guards(
    article: dict[str, Any],
    excerpts: list[dict[str, str]],
) -> tuple[dict[str, Any], int]:
    updated = copy.deepcopy(article)
    changed = 0
    evidence_text = excerpts_text(excerpts)
    audit = updated.setdefault("article_audit_fields", {})
    desc = audit.setdefault("description_audit_fields", {})
    flags = audit.setdefault("flag_audit_fields", {})

    if (
        desc.get("knime_article_relation") != "about_knime"
        and has_pattern_evidence(evidence_text, KNIME_USE_EVIDENCE_PATTERNS)
    ):
        if desc.get("knime_article_relation") != "uses_knime":
            desc["knime_article_relation"] = "uses_knime"
            changed += 1
        for flag in FLAG_NAMES:
            if flag not in flags:
                flags[flag] = False
                changed += 1
        if flags.get("uses_knime") is not True:
            flags["uses_knime"] = True
            changed += 1

    if flags and has_pattern_evidence(evidence_text, KNIME_FIGURE_EVIDENCE_PATTERNS):
        if flags.get("provides_workflow_screenshots_or_figures") is not True:
            flags["provides_workflow_screenshots_or_figures"] = True
            changed += 1

    return updated, changed


def normalize_implied_absences(article: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(article)
    audit = updated.get("article_audit_fields", {})
    desc = audit.get("description_audit_fields", {})
    flags = audit.get("flag_audit_fields", {})
    if (
        desc.get("knime_version_values") == "undefined"
        and (
            flags.get("reports_knime_version") is False
            or desc.get("knime_article_relation") == "about_knime"
        )
    ):
        desc["knime_version_values"] = ""
    return updated


def merge_llm_review(
    article: dict[str, Any],
    candidate: dict[str, Any],
    targets: dict[str, list[str]],
) -> tuple[dict[str, Any], int]:
    updated = copy.deepcopy(article)
    changed = 0
    audit = updated.setdefault("article_audit_fields", {})
    desc = audit.setdefault("description_audit_fields", {})
    flags = audit.setdefault("flag_audit_fields", {})

    candidate_desc = candidate.get("description_audit_fields", {})
    for field in targets["description_audit_fields"]:
        value = candidate_desc.get(field)
        if value is not None and value != desc.get(field):
            desc[field] = value
            changed += 1

    candidate_flags = candidate.get("flag_audit_fields", {})
    for field in targets["flag_audit_fields"]:
        value = candidate_flags.get(field)
        if isinstance(value, bool) and value != flags.get(field):
            flags[field] = value
            changed += 1
    has_workflow_resource = any(
        resource.get("type") == "workflow"
        for resource in updated.get("linked_resources", [])
        if isinstance(resource, dict)
    )
    if flags.get("provides_downloadable_knime_workflow_files") is True and not has_workflow_resource:
        flags["provides_downloadable_knime_workflow_files"] = False
        changed += 1
        if desc.get("workflow_artifact_status") == "published_or_linked_in_text":
            desc["workflow_artifact_status"] = "shown_or_described_but_no_public_workflow_found"
            changed += 1
    if desc.get("knime_article_relation") == "about_knime" and flags:
        flags.clear()
        changed += 1
    return updated, changed


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

    def assess(
        self,
        article: dict[str, Any],
        excerpts: list[dict[str, str]],
        targets: dict[str, list[str]],
    ) -> dict[str, Any]:
        audit = article.get("article_audit_fields", {})
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
                            "task": (
                                self.prompt["user_task"]
                                + " Review and correct only the fields listed in fields_to_review. "
                                + "Return corrected description_audit_fields and flag_audit_fields for those fields. "
                                + "Do not return or modify flag_audit_support."
                            ),
                            "evidence_rules": self.prompt["evidence_rules"],
                            "allowed_description_values": self.prompt[
                                "allowed_description_values"
                            ],
                            "flag_definitions": self.prompt["flag_definitions"],
                            "audit_questions": self.questions,
                            "required_json_schema": self.prompt["required_json_schema"],
                            "article_metadata": {
                                "rank": article.get("rank"),
                                "article_identifier": meta.get("article_identifier", ""),
                                "title": seed.get("title", ""),
                                "year": seed.get("publication_year", ""),
                                "venue": seed.get("source", ""),
                                "doi_or_url": article.get("doi_or_url")
                                or article.get("doi")
                                or seed.get("doi")
                                or "",
                            },
                            "deterministic_candidate": {
                                "description_audit_fields": audit.get(
                                    "description_audit_fields", {}
                                ),
                                "flag_audit_fields": audit.get("flag_audit_fields", {}),
                            },
                            "fields_to_review": targets,
                            "typed_linked_resources": article.get("linked_resources", []),
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
    input_assessment = load_json(args.input_assessment)
    input_articles = input_assessment.get("articles", [])
    questions = load_json(args.questions)
    prompt = load_json(args.prompt)
    articles = selected_articles(input_articles, args.rank, args.limit)

    calls_needed = any(text_path_for_article(article, args.text_dir) is not None for article in articles)
    if calls_needed:
        load_env_file(args.env_file)
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise SystemExit(
                "OPENAI_API_KEY is required. Put it in .env or export it in the environment."
            )
    else:
        api_key = "not-used"

    assessor = OpenAIArticleAssessor(
        api_key=api_key,
        model=args.model,
        temperature=args.temperature,
        prompt=prompt,
        questions=questions,
    )
    written = 0
    skipped_no_targets = 0
    skipped_no_text = 0
    total_fields_changed = 0
    result_articles: list[dict[str, Any]] = []
    for article in articles:
        article = normalize_implied_absences(article)
        targets = assessment_targets(article)
        if not has_assessment_targets(targets):
            result_articles.append(article)
            skipped_no_targets += 1
            written += 1
            continue

        text_path = text_path_for_article(article, args.text_dir)
        if text_path is None:
            result_articles.append(article)
            skipped_no_text += 1
            written += 1
            continue
        else:
            lines = text_path.read_text(encoding="utf-8", errors="replace").splitlines()
            excerpts = build_excerpts(
                lines,
                max_excerpts=args.max_excerpts,
                max_chars=args.max_chars,
            )
            candidate = assessor.assess(article, excerpts, targets)

        reviewed_article, changed_count = merge_llm_review(article, candidate, targets)
        reviewed_article, guard_changed_count = apply_direct_evidence_guards(
            reviewed_article, excerpts
        )
        result_articles.append(reviewed_article)
        total_fields_changed += changed_count + guard_changed_count
        written += 1

    result = {
        "created_by": Path(__file__).as_posix(),
        "source_assessment": args.input_assessment.as_posix(),
        "text_dir": args.text_dir.as_posix(),
        "prompt": args.prompt.as_posix(),
        "model": args.model,
        "temperature": args.temperature,
        "scope": {
            "limit": args.limit,
            "ranks": args.rank or [],
            "records_written": written,
            "llm_api_calls": assessor.calls,
            "records_skipped_no_reviewable_fields": skipped_no_targets,
            "records_skipped_no_local_text": skipped_no_text,
            "article_audit_fields_changed": total_fields_changed,
        },
        "article_audit_summary_counts": summary_counts(result_articles),
        "articles": result_articles,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)

    print(f"Wrote {written} LLM-reviewed article-assessment records to {args.output}.")
    print(f"LLM article-assessment API calls: {assessor.calls}.")
    print(f"Article audit fields changed: {total_fields_changed}.")
    print("Curated assessment JSON was not read or modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
