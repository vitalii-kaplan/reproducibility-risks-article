#!/usr/bin/env python3
"""Refresh article-audit provenance from extracted article text files."""

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


DEFAULT_ASSESSMENT = Path("data/processed/audit/old_article_assessments.json")
DEFAULT_QUESTIONS = Path("data/processed/audit/knime_article_audit_questions.json")
DEFAULT_TEXT_DIR = Path("data/processed/articles")
DEFAULT_ENV_FILE = Path(".env")
DEFAULT_LLM_PROMPT = Path("data/processed/audit/old/old_llm_support_validation_prompt.json")
DEFAULT_LLM_DECISION_LOG = Path(
    "data/processed/audit/logs/llm_support_validation_decisions.jsonl"
)
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
MAX_REJECTED_CANDIDATE_QUOTES = 5


FLAG_PATTERNS: dict[str, list[str]] = {
    "uses_knime": [
        r"\bKNIME\b",
        r"Konstanz Information Miner",
    ],
    "reports_knime_version": [
        r"\bKNIME\b.{0,120}\b(version|Desktop|Analytics Platform|v[0-9])\b",
        r"\b(version|Desktop|Analytics Platform|v[0-9])\b.{0,120}\bKNIME\b",
        r"\bKNIME\s+[0-9]+(?:\.[0-9]+)+\b",
        r"\bKNIME\b.{0,80}\b[0-9]+\.[0-9]+(?:\.[0-9]+)?\b",
    ],
    "provides_downloadable_knime_workflow_files": [
        r"workflow.{0,160}(available|download|Supporting Information)",
        r"(available|download|Supporting Information).{0,160}workflow",
        r"myexperiment\.org/workflows",
    ],
    "provides_workflow_screenshots_or_figures": [
        r"(Fig\.|Figure|Supplementary Fig).{0,180}\bKNIME\b.{0,80}(\bworkflow\b|workﬂow|\bmodel\b|\bnodes\b)",
        r"\bKNIME\b.{0,180}(\bworkflow\b|workﬂow|\bmodel\b|\bnodes\b).{0,180}(Fig\.|Figure|Supplementary Fig)",
        r"\bKNIME\b.{0,80}workflows?.{0,80}Supplementary Figs?",
        r"workflows?.{0,80}Supplementary Figs?",
    ],
    "describes_workflow_or_nodes_in_text": [
        r"\bKNIME\b.{0,220}(predictive model|model deployed|algorithms)",
        r"\bKNIME\b.{0,220}(Random Forest|Tree Ensemble|Decision Tree|Naive Bayes|Logistic Regression|Multi-Layer Perceptron|Rprop|statistics node|X-Partitioner|Normalizer|Meta node)",
        r"(Random Forest|Tree Ensemble|Decision Tree|Naive Bayes|Logistic Regression|Multi-Layer Perceptron|Rprop|statistics node|X-Partitioner|Normalizer|Meta node).{0,220}\bKNIME\b",
        r"\bKNIME\b.{0,160}(\bworkflow\b|workﬂow|\bnode\b|\bnodes\b|\bmodule\b|\bmodules\b|\bpipeline\b|\bpipelines\b)",
        r"(\bworkflow\b|workﬂow|\bnode\b|\bnodes\b|\bmodule\b|\bmodules\b|\bpipeline\b|\bpipelines\b).{0,160}\bKNIME\b",
        r"\b(GroupBy|RDKit|Indigo|CDK|X-Partitioner|Normalizer|GCNLearner|GCNDatasetBuilder|GCNDatasetSplitter|GCNPredictor|GCNGraphViewer)\b",
        r"\b(node called|through the nodes)\b",
    ],
    "provides_input_data_direct_url": [
        r"(training and test data|data|dataset).{0,160}https?://",
        r"https?://[^ ]*(data|dataset|publications-sites|uci)[^ ]*",
    ],
    "reports_input_data_availability": [
        r"(reference set|structures|SMARTS filters|PAINS filters).{0,220}(made available|available|website|used)",
        r"(made available|available|website|used).{0,220}(reference set|structures|SMARTS filters|PAINS filters)",
        r"(Availability of data|Data availability|Availability of data and materials).{0,200}(data|dataset|repository|available|http)",
        r"(dataset|data set|data).{0,220}(used in this research|used in this study|investigated in this study|obtained from|downloaded from|collected from|available from|available as|available at|analysed|analyzed)",
        r"(used in this research|used in this study|investigated in this study|obtained from|downloaded from|collected from|available from|available as|available at|analysed|analyzed).{0,220}(dataset|data set|data)",
        r"(data|dataset|training and test data|Supplementary data).{0,160}(available|repository|download|UCI)",
        r"(available|repository|download|UCI).{0,160}(data|dataset|training and test data|Supplementary data)",
        r"(data|dataset).{0,160}(obtained from|available from|generated|analysed|analyzed)",
        r"(obtained from|available from|generated|analysed|analyzed).{0,160}(data|dataset)",
    ],
    "provides_code_or_scripts": [
        r"(source code|code|scripts|public repository).{0,160}(available|github|http)",
        r"(github|http).{0,160}(source code|code|scripts|repository)",
    ],
    "reports_extension_or_plugin_dependencies": [
        r"\b(RDKit|Indigo|CDK|ChemAxon)\b.{0,120}\b(nodes|plug-in|plugin|extension|version|v[0-9])\b",
        r"\b(nodes|plug-in|plugin|extension|version|v[0-9])\b.{0,120}\b(RDKit|Indigo|CDK|ChemAxon)\b",
    ],
    "reports_extension_installation_source": [
        r"(update mechanism|community contributions|Project URL|available via|tech\.knime\.org/community|knime\.org/community)",
    ],
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("._")
    return slug or "article"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--llm-mode",
        choices=["off", "validate-support"],
        default="off",
        help=(
            "Use an LLM for selected support-validation decisions. "
            "'off' preserves the deterministic regex/heuristic workflow."
        ),
    )
    parser.add_argument(
        "--llm-model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        help="OpenAI model used when --llm-mode is not off.",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=0.0,
        help="Temperature for LLM support validation. Use 0 for maximum repeatability.",
    )
    parser.add_argument(
        "--llm-env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="Optional .env file containing OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--llm-prompt",
        type=Path,
        default=DEFAULT_LLM_PROMPT,
        help="JSON prompt/protocol file for LLM support validation.",
    )
    parser.add_argument(
        "--llm-decision-log",
        type=Path,
        default=DEFAULT_LLM_DECISION_LOG,
        help=(
            "JSONL file that records every uncached LLM support-validation "
            "decision when --llm-mode is not off."
        ),
    )
    parser.add_argument(
        "--llm-apply-rejections",
        action="store_true",
        help=(
            "Apply LLM false decisions to candidate quote selection. By default, "
            "LLM decisions are logged for review and deterministic validation "
            "continues to control audit edits."
        ),
    )
    parser.add_argument(
        "--reset-flags-from-descriptions",
        action="store_true",
        help=(
            "Rebuild flag_audit_fields from description_audit_fields before "
            "refreshing support. By default, existing audited flags are preserved."
        ),
    )
    parser.add_argument(
        "--apply-flag-removals",
        action="store_true",
        help=(
            "Set positive flags to false when no valid support is found. By "
            "default, unsupported or disputed flags are preserved for manual review."
        ),
    )
    parser.add_argument("--assessment", type=Path, default=DEFAULT_ASSESSMENT)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--text-dir", type=Path, default=DEFAULT_TEXT_DIR)
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


class LLMSupportValidator:
    def __init__(
        self,
        *,
        model: str,
        temperature: float,
        api_key: str,
        questions: dict[str, Any],
        prompt: dict[str, Any],
        apply_rejections: bool,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.api_key = api_key
        self.questions = questions
        self.prompt = prompt
        self.apply_rejections = apply_rejections
        self.cache: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.decisions: list[dict[str, Any]] = []
        self.calls = 0

    def validate(
        self,
        flag: str,
        item: dict[str, str],
        deterministic_result: bool,
    ) -> bool:
        quote = item.get("quote", "").strip()
        if not quote:
            return deterministic_result

        key = (flag, quote, item.get("article_section", ""))
        if key in self.cache:
            cached = self.cache[key]
            return (
                bool(cached["llm_supported"])
                if self.apply_rejections
                else deterministic_result
            )

        question = self.questions.get("flag_questions", {}).get(flag, {}).get(
            "question", ""
        )
        acceptance_rules = self.prompt.get("flag_acceptance_rules", {}).get(flag, {})
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": self.prompt["system_instruction"],
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": self.prompt.get(
                                "user_task",
                                "Decide whether the quote supports the audit flag.",
                            ),
                            "decision_rule": self.prompt.get("decision_rule", ""),
                            "flag": flag,
                            "audit_question": question,
                            "article_section": item.get("article_section", ""),
                            "quote": quote,
                            "deterministic_validator_result": deterministic_result,
                            "flag_acceptance_rule": acceptance_rules,
                            "required_json_schema": self.prompt[
                                "required_json_schema"
                            ],
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
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI API request failed: {exc.reason}") from exc

        self.calls += 1
        if self.calls % 25 == 0:
            print(
                f"LLM support-validation calls completed: {self.calls}",
                file=sys.stderr,
                flush=True,
            )
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        decision = {
            "flag": flag,
            "audit_question": question,
            "article_section": item.get("article_section", ""),
            "extracted_text_lines": item.get("extracted_text_lines", ""),
            "quote": quote,
            "deterministic_validator_result": deterministic_result,
            "llm_supported": bool(parsed.get("supported")),
            "llm_reason": str(parsed.get("reason", "")),
            "model": self.model,
            "temperature": self.temperature,
        }
        self.cache[key] = decision
        self.decisions.append(decision)
        return decision["llm_supported"] if self.apply_rejections else deterministic_result

    def write_decision_log(self, path: Path) -> None:
        if not self.decisions:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for decision in self.decisions:
                json.dump(decision, handle, ensure_ascii=False)
                handle.write("\n")


def build_llm_validator(
    args: argparse.Namespace,
    questions: dict[str, Any],
) -> LLMSupportValidator | None:
    if args.llm_mode == "off":
        return None
    load_env_file(args.llm_env_file)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is required when --llm-mode is not off. "
            "Put it in .env or export it in the environment."
        )
    prompt = load_json(args.llm_prompt)
    return LLMSupportValidator(
        model=args.llm_model,
        temperature=args.llm_temperature,
        api_key=api_key,
        questions=questions,
        prompt=prompt,
        apply_rejections=args.llm_apply_rejections,
    )


def rename_line_keys(value: Any) -> None:
    if isinstance(value, dict):
        if "pdf_text_lines" in value and "extracted_text_lines" not in value:
            value["extracted_text_lines"] = value.pop("pdf_text_lines")
        elif "pdf_text_lines" in value:
            value.pop("pdf_text_lines")
        for child in value.values():
            rename_line_keys(child)
    elif isinstance(value, list):
        for child in value:
            rename_line_keys(child)


def text_path_for_article(article: dict[str, Any], text_dir: Path) -> Path | None:
    pdf_file = article.get("pdf_file")
    if not pdf_file:
        return None
    stem = Path(pdf_file).stem
    candidate = text_dir / f"{slugify(stem)}.html"
    if candidate.exists():
        return candidate
    return None


def normalize_line(line: str) -> str:
    line = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", line)
    line = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", line)
    return re.sub(r"\s+", " ", line).strip()


def line_window(lines: list[str], index: int, radius: int = 1) -> tuple[str, str]:
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    label = str(start + 1) if start == end - 1 else f"{start + 1}-{end}"
    snippet = " ".join(normalize_line(line) for line in lines[start:end])
    return label, snippet[:500]


def line_label(start: int, end: int) -> str:
    return str(start + 1) if start == end - 1 else f"{start + 1}-{end}"


def line_ends_sentence(line: str) -> bool:
    value = line.strip()
    if not value:
        return False
    if re.search(r"\b(Fig|Figs|Table|Eq|Ref|Refs|Dr|Prof|et al)\.$", value):
        return False
    return bool(re.search(r"[.!?][\"')\]]?$", value))


def citation_window_for_index(
    lines: list[str], index: int, before_limit: int = 8, after_limit: int = 8
) -> tuple[str, str]:
    start = index
    lower_bound = max(0, index - before_limit)
    while start > lower_bound:
        previous = lines[start - 1]
        current = lines[start]
        if not previous.strip() or not current.strip():
            break
        if looks_like_section_heading(previous):
            break
        if line_ends_sentence(previous):
            break
        start -= 1

    end = index + 1
    upper_bound = min(len(lines), index + after_limit + 1)
    while end < upper_bound:
        current = lines[end - 1]
        next_line = lines[end]
        if line_ends_sentence(current):
            break
        if not next_line.strip():
            break
        if looks_like_section_heading(next_line):
            break
        end += 1

    quote_lines = [line.rstrip() for line in lines[start:end] if line.strip()]
    if not quote_lines:
        return line_label(index, index + 1), normalize_line(lines[index])
    return line_label(start, end), trim_trailing_sentence_fragment("\n".join(quote_lines))


def trim_trailing_sentence_fragment(quote: str) -> str:
    stripped = quote.rstrip()
    if not stripped or re.search(r"[.!?][\"')\]]?$", stripped):
        return stripped
    if re.search(r"https?://\S+$", stripped):
        return stripped

    last_end: int | None = None
    for match in re.finditer(r"[.!?][\"')\]]?(?=\s|$)", stripped):
        last_end = match.end()
    if last_end is None:
        return stripped
    return stripped[:last_end].rstrip()


def parse_line_ref(line_ref: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", line_ref)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if start < 1 or end < start:
        return None
    return start, end


def exact_line_window(lines: list[str], line_ref: str) -> list[tuple[int, str]]:
    parsed = parse_line_ref(line_ref)
    if parsed is None:
        return []
    start, end = parsed
    start_index = max(0, start - 1)
    end_index = min(len(lines), end)
    return [(index + 1, lines[index].rstrip()) for index in range(start_index, end_index)]


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def citation_patterns_for(flag: str, note: str) -> list[re.Pattern[str]]:
    raw_patterns = list(FLAG_PATTERNS.get(flag, []))
    for url in re.findall(r"https?://\S+", note):
        raw_patterns.insert(0, re.escape(url.rstrip(".,;)")))
    if "KNIME" in note and not raw_patterns:
        raw_patterns.append(r"\bKNIME\b")
    return [re.compile(pattern, re.IGNORECASE) for pattern in raw_patterns]


def direct_quote_for_support(
    lines: list[str], flag: str, item: dict[str, str]
) -> str | None:
    line_ref = item.get("extracted_text_lines", item.get("pdf_text_lines", ""))
    window = exact_line_window(lines, line_ref)
    if not window:
        return None

    patterns = citation_patterns_for(flag, item.get("note", ""))
    matching_indexes: list[int] = []
    for index, (_line_number, line) in enumerate(window):
        if any(pattern.search(compact(line)) for pattern in patterns):
            matching_indexes.append(index)

    if matching_indexes:
        target_line = window[matching_indexes[0]][0] - 1
    else:
        nonempty = [index for index, (_line_number, line) in enumerate(window) if line.strip()]
        if not nonempty:
            return None
        target_line = window[nonempty[0]][0] - 1

    _label, quote = citation_window_for_index(lines, target_line)
    return quote or None


SECTION_HEADING_PATTERNS = [
    re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z0-9,()/:;\- ]{2,90}$"),
    re.compile(r"^(Abstract|Introduction|Background|Methods?|Materials and methods|Results|Discussion|Conclusion|Conclusions|Availability|Availability and requirements|Data availability|Code availability|Software availability|Implementation|KNIME interface|References)$", re.IGNORECASE),
]


def looks_like_section_heading(line: str) -> bool:
    value = compact(line)
    if not value:
        return False
    left_column = compact(re.split(r"\s{2,}", line.strip(), maxsplit=1)[0])
    if left_column and left_column != value:
        if looks_like_section_heading(left_column):
            return True
    if len(value) > 110:
        return False
    if re.match(r"^(Results?|Conclusions?|Experimental|Methods?|Discussion):?(?:\s|$)", value, re.IGNORECASE):
        return True
    if value.endswith((".", ",", ";", ":")) and not re.match(r"^\d+(?:\.\d+)*\.", value):
        return False
    if any(pattern.match(value) for pattern in SECTION_HEADING_PATTERNS):
        return True
    if value.isupper() and 3 <= len(value) <= 80:
        return True
    return False


def article_section_for_line(lines: list[str], line_ref: str) -> str | None:
    parsed = parse_line_ref(line_ref)
    if parsed is None:
        return None
    start, _end = parsed
    _start, end = parsed
    forward_start = max(0, start - 1)
    forward_end = min(len(lines), end)
    search_indexes = list(range(forward_start, forward_end))
    search_indexes.extend(range(forward_start - 1, -1, -1))
    for index in search_indexes:
        line = lines[index]
        if looks_like_section_heading(line):
            value = compact(line)
            inline = re.match(
                r"^(Results?|Conclusions?|Experimental|Methods?|Discussion):?(?:\s|$)",
                value,
                re.IGNORECASE,
            )
            if inline:
                return inline.group(1).rstrip(":")
            left_column = compact(re.split(r"\s{2,}", line.strip(), maxsplit=1)[0])
            return left_column if left_column else value
    if start <= 80:
        return "Abstract"
    return "Main text"


def quote_text(item: dict[str, str]) -> str:
    return compact(item.get("quote", ""))


def quote_lower(item: dict[str, str]) -> str:
    return quote_text(item).lower()


def is_reference_section(item: dict[str, str]) -> bool:
    return item.get("article_section", "").strip().lower() in {"references", "reference"}


def has_url(value: str) -> bool:
    return bool(re.search(r"https?://", normalize_line(value), re.IGNORECASE))


def resource_key(value: str) -> str:
    key = normalize_line(value).lower()
    key = re.sub(r"https?://", "", key)
    key = re.sub(r"\s+", "", key)
    key = key.rstrip(".,;)")
    return key


def validates_true_flag(flag: str, item: dict[str, str]) -> bool:
    text = quote_lower(item)
    if not text:
        return False

    if flag == "full_text_accessible":
        return True

    if flag == "uses_knime":
        if "knime" not in text and "konstanz information miner" not in text:
            return False
        if text.startswith("correlation review") and "this paper" not in text:
            return False
        if "roving the medical diagnosis" in text:
            return False
        return bool(
            re.search(
                r"\b(this study|this paper|use[ds]?|using|implemented|deployed|workflow|workﬂow|platform|"
                r"interface|tools such as|toolkits?|comparison|compared|model|nodes?|chosen|includes?)\b",
                text,
            )
        )

    if flag == "reports_knime_version":
        return bool(
            re.search(r"\bknime\b", text)
            and re.search(r"\b\d+\.\d+(?:\.\d+)?\b", text)
        )

    if flag == "provides_downloadable_knime_workflow_files":
        return bool(
            re.search(r"workflow|workﬂow", text)
            and re.search(r"available|download|supporting information|myexperiment", text)
        )

    if flag == "provides_workflow_screenshots_or_figures":
        if quote_text(item).strip().lower() in {"fig.", "figure", "fig"}:
            return False
        return bool(
            re.search(r"fig\.|figure|supplementary fig", text)
            and re.search(r"workflow|workﬂow|model|nodes?", text)
            and re.search(r"knime", text)
        )

    if flag == "describes_workflow_or_nodes_in_text":
        if is_reference_section(item):
            return False
        if re.match(r"^\d+\.\s+[a-z].+\bj comput\b", text):
            return False
        if quote_text(item).strip().lower() in {"fig.", "figure", "fig"}:
            return False
        generic_knime_only = (
            "well-known" in text
            and "data mining application" in text
            and not re.search(
                r"random forest|tree ensemble|decision tree|naive bayes|logistic regression|"
                r"multi-layer perceptron|statistics node|x-partitioner|normalizer|gcn|rdkit|indigo",
                text,
            )
        )
        if generic_knime_only:
            return False
        return bool(
            (
                re.search(r"\bknime\b|kgcn", text)
                and re.search(
                    r"workflow|workﬂow|nodes?|modules?|pipeline|data flow|model deployed|"
                    r"random forest|tree ensemble|decision tree|naive bayes|logistic regression|"
                    r"multi-layer perceptron|algorithms",
                    text,
                )
            )
            or re.search(
                r"statistics node|x-partitioner|normalizer|gcnlearner|gcndatasetbuilder|"
                r"gcndatasetsplitter|gcnpredictor|gcngraphviewer|rdkit nodes|indigo nodes|"
                r"node called|through the nodes",
                text,
            )
        )

    if flag == "provides_input_data_direct_url":
        return bool(
            has_url(text)
            and re.search(
                r"data|dataset|repository|uci|publications-sites|heart\+disease|archive\.ics|"
                r"pains|smarts|filters|blog\.rguha",
                text,
            )
        )

    if flag == "reports_input_data_availability":
        generic_phrases = [
            "data mining is",
            "huge amount of data",
            "what differentiates between a good and a bad machine learning model is data",
            "data at hand",
            "training data errone",
            "educational data mining is the extraction",
            "volumes of data are daily generated",
            "data mining and knowledge discovery tools and software are available",
            "open-source data mining tools and software are available",
            "available data mining software and tools",
            "applied on the dataset using",
            "relationship among the data features analysed",
            "supplementary data are available at bioinformatics online",
        ]
        if any(phrase in text for phrase in generic_phrases):
            return "supplementary data are available at bioinformatics online" in text
        if item.get("article_section", "").strip().lower().endswith("background") and "this study" not in text:
            return False
        if not re.search(
            r"dataset|data set|data sets|training and test data|training data|supplementary data|"
            r"student records|patient records|uci|pains|smarts|filters|reference set|structures",
            text,
        ):
            return False
        return bool(
            re.search(r"data|dataset|data set|supplementary data|records|reference set|structures|filters", text)
            and re.search(
                r"available|repository|downloaded|obtained|collected|used in this research|"
                r"used in this study|investigated in this study|based on the dataset|"
                r"analysed|analyzed|uci|additional files|supporting information|available in smarts|"
                r"available.*website|made available",
                text,
            )
        )

    if flag == "provides_code_or_scripts":
        return bool(
            re.search(r"source code|code|scripts?|public repository|github|project home page", text)
            and re.search(r"available|github|repository|http|project home page", text)
        )

    if flag == "reports_extension_or_plugin_dependencies":
        return bool(
            re.search(r"rdkit|indigo|cdk|chemaxon", text)
            and re.search(r"nodes?|plug-in|plugin|extension|version|library|distributed", text)
        )

    if flag == "reports_extension_installation_source":
        return bool(
            re.search(
                r"community contributions|update site|project url|available via|tech\.knime\.org/community|"
                r"knime\.org/community",
                text,
            )
        )

    if flag == "linked_workflow_artifacts_retrievable":
        return True

    return True


def support_item_is_valid(
    flag: str,
    item: dict[str, str],
    llm_validator: LLMSupportValidator | None,
) -> bool:
    deterministic_result = validates_true_flag(flag, item)
    if llm_validator is None:
        return deterministic_result
    return llm_validator.validate(flag, item, deterministic_result)


def find_support(
    lines: list[str],
    flag: str,
    llm_validator: LLMSupportValidator | None,
    limit: int = 2,
) -> list[dict[str, str]]:
    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in FLAG_PATTERNS.get(flag, [])]
    support: list[dict[str, str]] = []
    seen_ranges: set[str] = set()
    rejected_candidates = 0
    for index, line in enumerate(lines):
        if flag in {
            "provides_workflow_screenshots_or_figures",
            "describes_workflow_or_nodes_in_text",
            "reports_extension_or_plugin_dependencies",
        } and index < 10:
            continue
        haystack = normalize_line(" ".join(lines[index : index + 5]))
        if not haystack:
            continue
        if not any(pattern.search(haystack) for pattern in patterns):
            continue
        target_index = index
        for offset, candidate_line in enumerate(lines[index : index + 5]):
            if any(pattern.search(normalize_line(candidate_line)) for pattern in patterns):
                target_index = index + offset
                break
        label, quote = citation_window_for_index(lines, target_index)
        if label in seen_ranges:
            continue
        seen_ranges.add(label)
        snippet = normalize_line(quote)
        if not snippet:
            continue
        support.append(
            {
                "extracted_text_lines": label,
                "quote": quote,
                "article_section": article_section_for_line(lines, label) or "Unknown",
                "note": f"Extracted text evidence: {snippet}",
            }
        )
        if not support_item_is_valid(flag, support[-1], llm_validator):
            support.pop()
            rejected_candidates += 1
            if rejected_candidates > MAX_REJECTED_CANDIDATE_QUOTES and not support:
                break
            continue
        if len(support) >= limit:
            break
    return support


def find_linked_resource_support(
    lines: list[str],
    urls: list[str],
    flag: str,
    llm_validator: LLMSupportValidator | None,
    limit: int = 2,
) -> list[dict[str, str]]:
    support: list[dict[str, str]] = []
    compact_lines = [resource_key(line) for line in lines]
    for url in urls:
        compact_url = resource_key(url)
        if not compact_url:
            continue
        for index, compact_line in enumerate(compact_lines):
            if compact_url not in compact_line:
                continue
            label, quote = citation_window_for_index(lines, index)
            snippet = normalize_line(quote)
            item = {
                "extracted_text_lines": label,
                "quote": quote,
                "article_section": article_section_for_line(lines, label) or "Unknown",
                "note": f"Extracted text evidence for linked resource {url}: {snippet}",
            }
            if support_item_is_valid(flag, item, llm_validator):
                support.append(item)
            break
        if len(support) >= limit:
            break
    return support


def find_version_value_support(
    lines: list[str],
    version_values: str,
    llm_validator: LLMSupportValidator | None,
    limit: int = 2,
) -> list[dict[str, str]]:
    values = [
        value.strip()
        for value in re.split(r"[,;/]", version_values)
        if re.search(r"\d", value)
    ]
    support: list[dict[str, str]] = []
    seen_ranges: set[str] = set()
    for value in values:
        value_pattern = re.compile(re.escape(value), re.IGNORECASE)
        for index, line in enumerate(lines):
            if not value_pattern.search(normalize_line(line)):
                continue
            label, quote = citation_window_for_index(lines, index, before_limit=3, after_limit=5)
            if label in seen_ranges:
                continue
            seen_ranges.add(label)
            snippet = normalize_line(quote)
            support.append(
                {
                    "extracted_text_lines": label,
                    "quote": quote,
                    "article_section": article_section_for_line(lines, label) or "Unknown",
                    "note": f"Extracted text evidence for reported KNIME version {value}: {snippet}",
                }
            )
            if not support_item_is_valid(
                "reports_knime_version", support[-1], llm_validator
            ):
                support.pop()
                continue
            break
        if len(support) >= limit:
            break
    return support


def has_numeric_line_ref(item: dict[str, str]) -> bool:
    line_ref = item.get("extracted_text_lines", item.get("pdf_text_lines", ""))
    return bool(re.fullmatch(r"\d+(?:-\d+)?", line_ref))


def is_generated_text_support(item: dict[str, str]) -> bool:
    return item.get("note", "").startswith("Extracted text evidence")


def keep_non_text_support(item: dict[str, str]) -> bool:
    if has_numeric_line_ref(item):
        return False
    if is_generated_text_support(item):
        return False
    line_ref = str(item.get("extracted_text_lines", item.get("pdf_text_lines", "")))
    if line_ref in {"article_audit_fields", "processed_text_file"}:
        return False
    return True


def dedupe_support(items: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        line_ref = item.get("extracted_text_lines", item.get("pdf_text_lines", ""))
        key = (line_ref, item.get("note", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def enrich_support_with_citations(
    support: dict[str, list[dict[str, str]]], lines: list[str]
) -> int:
    enriched = 0
    for flag, items in support.items():
        if flag == "full_text_accessible":
            continue
        for item in items:
            if "quote" in item and validates_true_flag(flag, item):
                continue
            line_ref = item.get("extracted_text_lines", item.get("pdf_text_lines", ""))
            if not re.fullmatch(r"\d+(?:-\d+)?", line_ref):
                continue
            quote = direct_quote_for_support(lines, flag, item)
            section = article_section_for_line(lines, line_ref)
            if quote:
                item["quote"] = quote
                enriched += 1
            if section:
                item["article_section"] = section
            elif "article_section" not in item:
                item["article_section"] = "Unknown"
    return enriched


def remove_invalid_quote_support(
    support: dict[str, list[dict[str, str]]],
    flags: dict[str, Any],
    llm_validator: LLMSupportValidator | None,
    apply_flag_removals: bool,
) -> None:
    if not apply_flag_removals:
        return
    for flag, items in list(support.items()):
        if flag == "full_text_accessible":
            continue
        valid_items = [
            item
            for item in items
            if (
                "quote" in item and support_item_is_valid(flag, item, llm_validator)
                or (flag == "linked_workflow_artifacts_retrievable" and "quote" not in item)
            )
        ]
        if valid_items:
            support[flag] = valid_items
        else:
            support.pop(flag, None)
            if apply_flag_removals and flag != "linked_workflow_artifacts_retrievable":
                flags[flag] = False


def reset_candidate_flags_from_descriptions(audit: dict[str, Any]) -> None:
    descriptions = audit.get("description_audit_fields", {})
    flags = audit.setdefault("flag_audit_fields", {})
    relation = descriptions.get("knime_article_relation", "")

    if relation in {"about_knime", "not_assessed"}:
        for flag in list(flags):
            if flag != "full_text_accessible":
                flags[flag] = False
        return

    workflow_status = descriptions.get("workflow_artifact_status", "")
    input_status = descriptions.get("provides_input_data", "")

    flags["uses_knime"] = relation == "uses_knime"
    flags["reports_knime_version"] = bool(descriptions.get("knime_version_values", ""))
    flags["provides_downloadable_knime_workflow_files"] = (
        workflow_status == "published_or_linked_in_text"
    )
    flags["provides_workflow_screenshots_or_figures"] = workflow_status in {
        "shown_or_described_but_no_public_workflow_found",
        "shown_or_described_but_no_public_artifact_found_in_pdf",
        "published_or_linked_in_text",
    }
    flags["describes_workflow_or_nodes_in_text"] = workflow_status in {
        "shown_or_described_but_no_public_workflow_found",
        "shown_or_described_but_no_public_artifact_found_in_pdf",
        "published_or_linked_in_text",
    }
    flags["provides_input_data_direct_url"] = input_status == "yes"
    flags["reports_input_data_availability"] = input_status in {
        "yes",
        "reported_without_direct_url",
    }
    flags["provides_code_or_scripts"] = (
        descriptions.get("provides_code_or_scripts", "") == "yes"
    )
    flags["reports_extension_or_plugin_dependencies"] = (
        descriptions.get("reports_extension_or_plugin_dependencies", "") == "yes"
    )
    flags["reports_extension_installation_source"] = (
        descriptions.get("reports_extension_installation_source", "") == "yes"
    )
    flags["linked_workflow_artifacts_retrievable"] = (
        descriptions.get("linked_workflow_artifacts_retrievable", "")
        == "retrievable_in_current_project_notes"
    )


def summary_counts(articles: list[dict[str, Any]], flag_names: list[str]) -> dict[str, Any]:
    counts = {flag: 0 for flag in flag_names}
    counts["total_records"] = len(articles)
    relation_counts: dict[str, int] = {}
    for article in articles:
        audit = article.get("article_audit_fields", {})
        relation = (
            audit.get("description_audit_fields", {}).get("knime_article_relation", "")
        )
        if relation:
            relation_counts[relation] = relation_counts.get(relation, 0) + 1
        if relation == "about_knime":
            continue
        flags = audit.get("flag_audit_fields", {})
        for flag in flag_names:
            if flags.get(flag) is True:
                counts[flag] += 1
    counts["knime_article_relation_counts"] = relation_counts
    return counts


def main() -> int:
    args = parse_args()
    assessment = load_json(args.assessment)
    questions = load_json(args.questions)
    llm_validator = build_llm_validator(args, questions)
    rename_line_keys(assessment)
    flag_names = list(questions["flag_questions"].keys())

    updated_articles = 0
    text_backed_flags = 0
    citation_enriched_items = 0

    for article in assessment["articles"]:
        audit = article.setdefault("article_audit_fields", {})
        relation = (
            audit.get("description_audit_fields", {}).get("knime_article_relation", "")
        )
        text_path = text_path_for_article(article, args.text_dir)
        if text_path is None:
            article["processed_text_file"] = None
        else:
            updated_articles += 1
            article["processed_text_file"] = text_path.as_posix()

        if relation == "about_knime":
            audit["flag_audit_fields"] = {}
            audit["flag_audit_support"] = {}
            continue

        if text_path is None:
            continue

        if args.reset_flags_from_descriptions:
            reset_candidate_flags_from_descriptions(audit)
        lines = text_path.read_text(encoding="utf-8", errors="replace").split("\n")

        flags = audit.setdefault("flag_audit_fields", {})
        old_support = audit.get("flag_audit_support", {})
        support: dict[str, list[dict[str, str]]] = {}

        if flags.get("full_text_accessible") is True:
            support["full_text_accessible"] = [
                {
                    "extracted_text_lines": "processed_text_file",
                    "note": f"Extracted article text available: {text_path.as_posix()}",
                }
            ]

        for flag in flag_names:
            if flag == "full_text_accessible" or flags.get(flag) is not True:
                continue
            existing_non_text = [
                item for item in old_support.get(flag, []) if keep_non_text_support(item)
            ]
            existing_support = old_support.get(flag, [])

            if flag == "linked_workflow_artifacts_retrievable":
                support[flag] = dedupe_support(existing_non_text or existing_support)
                continue

            if flag == "provides_input_data_direct_url":
                candidates = find_linked_resource_support(
                    lines,
                    article.get("linked_resources", {}).get("data_urls", []),
                    flag,
                    llm_validator,
                )
            elif flag == "reports_knime_version":
                candidates = find_version_value_support(
                    lines,
                    audit.get("description_audit_fields", {}).get(
                        "knime_version_values", ""
                    ),
                    llm_validator,
                )
                if not candidates:
                    candidates = find_support(lines, flag, llm_validator)
            elif flag == "provides_code_or_scripts":
                candidates = find_linked_resource_support(
                    lines,
                    article.get("linked_resources", {}).get("code_urls", []),
                    flag,
                    llm_validator,
                )
                if not candidates:
                    candidates = find_support(lines, flag, llm_validator)
            else:
                candidates = find_support(lines, flag, llm_validator)
            if candidates:
                text_backed_flags += 1

            valid_support = [
                item
                for item in dedupe_support([*candidates, *existing_non_text])
                if "quote" not in item
                or support_item_is_valid(flag, item, llm_validator)
            ]
            if not valid_support:
                if args.apply_flag_removals:
                    flags[flag] = False
                elif existing_support:
                    support[flag] = existing_support
                continue

            support[flag] = valid_support

        citation_enriched_items += enrich_support_with_citations(support, lines)
        remove_invalid_quote_support(
            support, flags, llm_validator, args.apply_flag_removals
        )
        audit["flag_audit_support"] = {
            flag: items for flag, items in support.items() if flags.get(flag) is True
        }

    article_text_source = dict(assessment.get("article_text_source", {}))
    processed_text_file_count = len(list(args.text_dir.glob("*.html")))
    article_text_source.update(
        {
            "directory": args.text_dir.as_posix(),
            "method": article_text_source.get(
                "method",
                "Processed article files are generated from local PDFs with GROBID using scripts/extract_article_grobid_html.py.",
            ),
            "articles_with_extracted_text": processed_text_file_count,
            "articles_matched_to_audit_records": updated_articles,
            "line_reference_semantics": article_text_source.get(
                "line_reference_semantics",
                "extracted_text_lines refer to processed GROBID HTML files under data/processed/articles, not original PDF page lines.",
            ),
        }
    )
    assessment["article_text_source"] = article_text_source
    assessment["article_audit_summary_counts"] = summary_counts(
        assessment["articles"], flag_names
    )
    if llm_validator is not None:
        llm_validator.write_decision_log(args.llm_decision_log)

    write_json(args.assessment, assessment)
    print(
        f"Updated {updated_articles} articles with extracted text provenance; "
        f"found text-backed support for {text_backed_flags} positive flags; "
        f"added direct citation fields to {citation_enriched_items} support items."
    )
    if llm_validator is not None:
        print(
            f"LLM mode {args.llm_mode}: made {llm_validator.calls} "
            f"support-validation API calls with model {args.llm_model}."
        )
        print(f"LLM decisions written to {args.llm_decision_log}.")
        if not args.llm_apply_rejections:
            print(
                "LLM decisions were logged only; deterministic validation controlled "
                "audit edits. Use --llm-apply-rejections to apply LLM false decisions."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
