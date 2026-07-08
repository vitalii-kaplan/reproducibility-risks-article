#!/usr/bin/env python3
"""Generate deterministic article-audit assessment candidates.

This script does not call an LLM and does not read the curated assessment JSON.
It combines OpenAlex seed metadata, processed article text, audit questions, and
the workflow-reference inventory. Fields that cannot be determined by these
rules are marked as "undefined".
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_SEED_CSV = Path("data/processed/openalex/openalex_knime_most_cited.csv")
DEFAULT_QUESTIONS = Path("data/processed/audit/knime_article_audit_questions.json")
DEFAULT_TEXT_DIR = Path("data/processed/articles")
DEFAULT_WORKFLOW_REFERENCES = Path(
    "data/processed/audit/knime_downloadable_workflow_references.json"
)
DEFAULT_OUTPUT = Path(
    "data/processed/audit/article_deterministic_assessments.json"
)

UNDEFINED = "undefined"
TEXT_METADATA_PREFIX = "# article_text_metadata: "

DESCRIPTION_FIELDS = [
    "article_identifier",
    "title",
    "year",
    "venue",
    "doi_or_url",
    "knime_role_source_field",
    "knime_article_relation",
    "knime_version_values",
    "workflow_artifact_status",
    "provides_input_data",
    "provides_code_or_scripts",
    "reports_extension_or_plugin_dependencies",
    "reports_extension_installation_source",
    "linked_workflow_artifacts_retrievable",
    "evidence_notes",
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

URL_RE = re.compile(r"https?://[^\s)\]}>\"']+", re.IGNORECASE)
VERSION_RE = re.compile(r"\bKNIME(?: Analytics Platform)?\s*(?:version|v\.?|ver\.?)?\s*(\d+(?:\.\d+){1,3})\b", re.IGNORECASE)

DIRECT_USE_RE = re.compile(
    r"\b(?:used|using|implemented|performed|built|designed|developed|adopted|created|constructed|processed|analysed|analyzed|executed|modelled|modeled)\b.{0,120}\bKNIME\b|"
    r"\bKNIME\b.{0,120}\b(?:workflow|workflows|platform|node|nodes|metanode|component|components|implementation|analysis|model|models|classifier|pipeline)\b",
    re.IGNORECASE,
)
ABOUT_RE = re.compile(
    r"\b(?:KNIME[- ](?:CDK|ImageJ|4Bio)|Integration of .* in KNIME|KNIME\s*-\s*the Konstanz information miner|Scientific workflow systems: Pipeline Pilot and KNIME)\b",
    re.IGNORECASE,
)
NON_USE_RE = re.compile(
    r"\b(?:tools like|tools including|review(?:ing)? and comparing|pros and cons|latest tools|survey)\b.{0,160}\bKNIME\b",
    re.IGNORECASE,
)
WORKFLOW_ARTIFACT_RE = re.compile(
    r"\b(?:\.knwf|workflow\.knime|KNIME Hub|kni\.me/w/|myExperiment|workflow(?:s)? (?:is|are) available|available .* workflow|download(?:able)? .* workflow|supplementary .* workflow|workflow archive)\b",
    re.IGNORECASE,
)
WORKFLOW_FIGURE_RE = re.compile(
    r"\b(?:Fig(?:ure)?\.?|Supplementary Fig(?:ure)?s?)\b.{0,120}\bKNIME\b.{0,80}\bworkflow\b|"
    r"\bKNIME\b.{0,80}\bworkflow\b.{0,120}\b(?:Fig(?:ure)?\.?|Supplementary Fig(?:ure)?s?)\b",
    re.IGNORECASE,
)
WORKFLOW_DESCRIPTION_RE = re.compile(
    r"\bKNIME\b.{0,120}\b(?:workflow|node|nodes|metanode|component|components|Reader|Learner|Predictor|Normalizer|Missing Values|R snippet|RDKit|CDK|ImageJ|Weka)\b",
    re.IGNORECASE,
)
DATA_AVAILABILITY_RE = re.compile(
    r"\b(?:Data availability|Availability of data|data (?:are|is|were|was) available|dataset(?:s)? (?:are|is|were|was) available|UCI machine learning repository|training and test data|input data)\b",
    re.IGNORECASE,
)
CODE_RE = re.compile(
    r"\b(?:Code availability|source code|scripts?|GitHub|GitLab|Zenodo|software package|repository)\b",
    re.IGNORECASE,
)
EXTENSION_RE = re.compile(
    r"\b(?:extension|plug-?in|plugin|RDKit|Indigo|CDK|ImageJ|FIJI|Weka|R snippet|ChemAxon|Erl Wood|Vernalis|OpenMS|Palladian)\b",
    re.IGNORECASE,
)
INSTALL_SOURCE_RE = re.compile(
    r"\b(?:update site|install(?:ation)?|download(?:s)?|available from|KNIME Hub|NodePit|hub\.knime\.com|knime\.com/downloads)\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-csv", type=Path, default=DEFAULT_SEED_CSV)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--text-dir", type=Path, default=DEFAULT_TEXT_DIR)
    parser.add_argument("--workflow-references", type=Path, default=DEFAULT_WORKFLOW_REFERENCES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=0, help="Maximum records to write. 0 means all.")
    parser.add_argument("--rank", type=int, action="append", help="Write only this citation rank.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def text_metadata(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        first_line = path.open(encoding="utf-8", errors="replace").readline().rstrip("\n")
    except OSError:
        return {}
    if not first_line.startswith(TEXT_METADATA_PREFIX):
        return {}
    try:
        metadata = json.loads(first_line[len(TEXT_METADATA_PREFIX) :])
    except json.JSONDecodeError:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("._")
    return slug or "article"


def normalize_doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    return value.lower()


def token_set(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) >= 4}


def doi_match_tokens(doi: str) -> set[str]:
    tokens = token_set(doi)
    compact_doi = re.sub(r"[^a-z0-9]+", "", doi.lower())
    if compact_doi:
        tokens.add(compact_doi)
        tokens.add(compact_doi[-4:])
        tokens.add(compact_doi[-5:])
    return tokens


def title_match_score(title_tokens: set[str], path: Path) -> int:
    stem_tokens = token_set(path.stem)
    score = len(title_tokens & stem_tokens) * 3
    try:
        head = " ".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:80])
    except OSError:
        return score
    return score + len(title_tokens & token_set(head)) * 2


def text_path_for_article(article: dict[str, Any], text_dir: Path) -> Path | None:
    files = [path for path in text_dir.glob("*.txt") if path.is_file()]
    if not files:
        return None
    doi = normalize_doi(str(article.get("doi_or_url") or article.get("doi") or ""))
    title_tokens = token_set(str(article.get("title", "")))
    rank = str(article.get("rank", ""))
    doi_tokens = doi_match_tokens(doi)
    best_path: Path | None = None
    best_score = 0
    for path in files:
        stem = path.stem.lower()
        score = 0
        if rank and stem.startswith(f"{rank}_"):
            score += 8
        if doi:
            doi_slug = slugify(doi).lower()
            if doi_slug and doi_slug in stem:
                score += 80
            score += sum(15 for token in doi_tokens if token and token in stem)
        score += title_match_score(title_tokens, path)
        if score > best_score:
            best_score = score
            best_path = path
    return best_path if best_score >= 12 else None


def line_label(start: int, end: int) -> str:
    return str(start + 1) if start == end - 1 else f"{start + 1}-{end}"


def section_for_line(lines: list[str], start_index: int) -> str:
    heading_re = re.compile(
        r"^(Abstract|Introduction|Background|Methods?|Results|Discussion|Conclusions?|Data availability|Code availability|Software availability|Availability)",
        re.IGNORECASE,
    )
    for index in range(start_index, -1, -1):
        value = compact(lines[index])
        if value and len(value) <= 120 and heading_re.match(value):
            return value
    return "Abstract" if start_index < 80 else "Main text"


def sentence_windows(lines: list[str]) -> list[tuple[int, int, str]]:
    windows: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        text = compact(" ".join(lines[max(0, index - 1) : min(len(lines), index + 3)]))
        if text:
            windows.append((max(0, index - 1), min(len(lines), index + 3), text))
    return windows


def first_match_support(
    lines: list[str],
    pattern: re.Pattern[str],
    *,
    note: str,
    resource_url: str | None = None,
) -> dict[str, str] | None:
    for start, end, text in sentence_windows(lines):
        if pattern.search(text):
            if resource_url and resource_url not in text:
                continue
            return {
                "extracted_text_lines": line_label(start, end),
                "quote": text[:1200],
                "article_section": section_for_line(lines, start),
                "note": note,
            }
    return None


def all_urls(lines: list[str]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for line in lines:
        for match in URL_RE.findall(line):
            url = match.rstrip(".,;:")
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def url_contexts(lines: list[str]) -> list[tuple[str, str]]:
    contexts: list[tuple[str, str]] = []
    for index, line in enumerate(lines):
        for url in URL_RE.findall(line):
            context = compact(" ".join(lines[max(0, index - 2) : min(len(lines), index + 3)]))
            contexts.append((url.rstrip(".,;:"), context))
    return contexts


def classify_url(url: str, context: str) -> str:
    haystack = f"{url} {context}".lower()
    if any(token in haystack for token in ["kni.me/w/", "hub.knime", "myexperiment", ".knwf", "workflow"]):
        return "workflow_urls"
    if any(token in haystack for token in ["github", "gitlab", "source code", "code availability", "script"]):
        return "code_urls"
    if any(token in haystack for token in ["uci", "figshare", "zenodo", "dryad", "dataset", "data availability", "training and test data", "input data"]):
        return "data_urls"
    if any(token in haystack for token in ["knime.com/download", "update site", "nodepit", "software", "download"]):
        return "software_urls"
    if "doi.org" in haystack or "supplement" in haystack:
        return "supplement_urls_or_dois"
    return "software_urls"


def linked_resources_from_text(lines: list[str], workflow_record: dict[str, Any] | None) -> dict[str, Any]:
    resources: dict[str, Any] = {
        "data_urls": [],
        "code_urls": [],
        "workflow_urls": [],
        "software_urls": [],
        "supplement_urls_or_dois": [],
        "notes": "",
    }
    for url, context in url_contexts(lines):
        bucket = classify_url(url, context)
        if url not in resources[bucket]:
            resources[bucket].append(url)
    if workflow_record:
        for ref in workflow_record.get("workflow_references", []):
            url = ref.get("url", "")
            if url and url not in resources["workflow_urls"]:
                resources["workflow_urls"].append(url)
    return resources


def workflow_index(path: Path) -> dict[int, dict[str, Any]]:
    if not path.exists():
        return {}
    data = load_json(path)
    return {
        int(record["rank"]): record
        for record in data.get("records", [])
        if str(record.get("rank", "")).isdigit()
    }


def load_seed_articles(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    articles: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        articles.append(
            {
                "rank": index,
                "article_identifier": row.get("openalex_id", ""),
                "title": row.get("title", ""),
                "publication_year": row.get("publication_year", ""),
                "venue": row.get("source", ""),
                "doi_or_url": normalize_doi(row.get("doi", "")),
                "doi": normalize_doi(row.get("doi", "")),
                "openalex_seed_fields": row,
            }
        )
    return articles


def selected_articles(articles: list[dict[str, Any]], ranks: list[int] | None, limit: int) -> list[dict[str, Any]]:
    selected = [article for article in articles if not ranks or article["rank"] in ranks]
    return selected[:limit] if limit > 0 else selected


def determine_relation(article: dict[str, Any], lines: list[str] | None) -> str:
    if lines is None:
        return "not_assessed"
    title = article.get("title", "")
    seed = article.get("openalex_seed_fields", {})
    role = seed.get("knime_role", "")
    text_head = compact(" ".join(lines[:140]))
    if role == "about_knime_or_extension" or ABOUT_RE.search(title) or ABOUT_RE.search(text_head):
        return "about_knime"
    if NON_USE_RE.search(text_head) and not DIRECT_USE_RE.search(text_head):
        return "not_a_knime_use_case"
    if seed.get("likely_uses_knime_workflow_platform") == "True" or DIRECT_USE_RE.search(text_head):
        return "uses_knime"
    return UNDEFINED


def version_values(lines: list[str]) -> tuple[str, dict[str, str] | None]:
    values: list[str] = []
    support: dict[str, str] | None = None
    for start, end, text in sentence_windows(lines):
        for version in VERSION_RE.findall(text):
            if version not in values:
                values.append(version)
                if support is None:
                    support = {
                        "extracted_text_lines": line_label(start, end),
                        "quote": text[:1200],
                        "article_section": section_for_line(lines, start),
                        "note": f"Deterministic KNIME version match: {version}.",
                    }
    return "; ".join(values), support


def true_or_undefined(support: Any) -> bool | str:
    return True if support else UNDEFINED


def add_support(target: dict[str, list[dict[str, str]]], flag: str, support: dict[str, str] | None) -> None:
    if support:
        target.setdefault(flag, []).append(support)


def audit_article(
    article: dict[str, Any],
    text_path: Path | None,
    workflow_record: dict[str, Any] | None,
) -> dict[str, Any]:
    lines = text_path.read_text(encoding="utf-8", errors="replace").splitlines() if text_path else None
    metadata = text_metadata(text_path)
    pdf_file = metadata.get("source_pdf") or UNDEFINED
    relation = determine_relation(article, lines)

    desc = {field: UNDEFINED for field in DESCRIPTION_FIELDS}
    desc.update(
        {
            "article_identifier": article.get("article_identifier", ""),
            "title": article.get("title", ""),
            "year": str(article.get("publication_year", "")),
            "venue": article.get("venue", ""),
            "doi_or_url": article.get("doi_or_url", ""),
            "knime_role_source_field": article.get("openalex_seed_fields", {}).get("knime_role", UNDEFINED),
            "knime_article_relation": relation,
        }
    )

    resources = linked_resources_from_text(lines or [], workflow_record)
    flags: dict[str, bool | str] = {flag: UNDEFINED for flag in FLAG_NAMES}
    support: dict[str, list[dict[str, str]]] = {}

    if text_path is None:
        desc.update(
            {
                "workflow_artifact_status": "not_assessed",
                "provides_input_data": "not_assessed",
                "provides_code_or_scripts": "not_assessed",
                "reports_extension_or_plugin_dependencies": "not_assessed",
                "reports_extension_installation_source": "not_assessed",
                "linked_workflow_artifacts_retrievable": "not_assessed",
                "evidence_notes": "No local processed article text was matched by the deterministic script.",
            }
        )
        flags["full_text_accessible"] = False
    elif relation == "about_knime":
        desc.update(
            {
                "workflow_artifact_status": "not_applicable",
                "provides_input_data": "not_applicable",
                "provides_code_or_scripts": "not_applicable",
                "reports_extension_or_plugin_dependencies": "not_applicable",
                "reports_extension_installation_source": "not_applicable",
                "linked_workflow_artifacts_retrievable": "not_applicable_no_linked_workflow_artifact",
                "evidence_notes": "Deterministic classification marked this as a KNIME platform, extension, or background article; workflow-reporting flags are intentionally empty.",
            }
        )
        flags = {}
    else:
        assert lines is not None
        full_text_support = {
            "extracted_text_lines": "processed_text_file",
            "article_section": "Local text",
            "quote": "",
            "note": f"Extracted article text available: {text_path.as_posix()}",
        }
        flags["full_text_accessible"] = True
        add_support(support, "full_text_accessible", full_text_support)

        use_support = first_match_support(
            lines,
            DIRECT_USE_RE,
            note="Deterministic text pattern found KNIME use in the article.",
        )
        if relation == "uses_knime" and use_support is None:
            use_support = first_match_support(
                lines,
                re.compile(r"\bKNIME\b", re.IGNORECASE),
                note="OpenAlex seed metadata suggested KNIME use; deterministic text found KNIME mention.",
            )
        flags["uses_knime"] = True if relation == "uses_knime" and use_support else (False if relation == "not_a_knime_use_case" else UNDEFINED)
        add_support(support, "uses_knime", use_support if flags["uses_knime"] is True else None)

        versions, version_support = version_values(lines)
        desc["knime_version_values"] = versions if versions else UNDEFINED
        flags["reports_knime_version"] = true_or_undefined(version_support)
        add_support(support, "reports_knime_version", version_support)

        workflow_support = first_match_support(
            lines,
            WORKFLOW_ARTIFACT_RE,
            note="Deterministic text pattern found downloadable or linked KNIME workflow evidence.",
        )
        if workflow_record:
            workflow_support = workflow_support or {
                "extracted_text_lines": workflow_record.get("evidence_extracted_text_lines", "workflow_inventory"),
                "article_section": "Workflow inventory",
                "quote": "",
                "note": "Workflow-reference inventory records downloadable or linked KNIME workflow evidence for this article.",
            }
        flags["provides_downloadable_knime_workflow_files"] = true_or_undefined(workflow_support)
        add_support(support, "provides_downloadable_knime_workflow_files", workflow_support)
        desc["workflow_artifact_status"] = (
            workflow_record.get("workflow_artifact_status")
            if workflow_record
            else ("published_or_linked_in_text" if workflow_support else UNDEFINED)
        )

        figure_support = first_match_support(
            lines,
            WORKFLOW_FIGURE_RE,
            note="Deterministic text pattern found a KNIME workflow figure or screenshot reference.",
        )
        flags["provides_workflow_screenshots_or_figures"] = true_or_undefined(figure_support)
        add_support(support, "provides_workflow_screenshots_or_figures", figure_support)

        description_support = first_match_support(
            lines,
            WORKFLOW_DESCRIPTION_RE,
            note="Deterministic text pattern found KNIME workflow, node, or component description.",
        )
        flags["describes_workflow_or_nodes_in_text"] = true_or_undefined(description_support)
        add_support(support, "describes_workflow_or_nodes_in_text", description_support)

        data_support = first_match_support(
            lines,
            DATA_AVAILABILITY_RE,
            note="Deterministic text pattern found input-data availability evidence.",
        )
        data_urls = resources["data_urls"]
        flags["reports_input_data_availability"] = true_or_undefined(data_support or data_urls)
        flags["provides_input_data_direct_url"] = true_or_undefined(data_urls)
        if data_urls:
            add_support(
                support,
                "provides_input_data_direct_url",
                first_match_support(
                    lines,
                    re.compile(re.escape(data_urls[0]), re.IGNORECASE),
                    note=f"Deterministic URL classification marked this as an input-data URL: {data_urls[0]}",
                    resource_url=data_urls[0],
                )
                or {
                    "extracted_text_lines": "linked_resources",
                    "article_section": "Resource extraction",
                    "quote": "",
                    "note": f"Deterministic URL classification marked this as an input-data URL: {data_urls[0]}",
                },
            )
        add_support(support, "reports_input_data_availability", data_support)
        desc["provides_input_data"] = "yes" if flags["reports_input_data_availability"] is True else UNDEFINED

        code_support = first_match_support(
            lines,
            CODE_RE,
            note="Deterministic text pattern found code, script, software, or repository evidence.",
        )
        flags["provides_code_or_scripts"] = true_or_undefined(code_support or resources["code_urls"])
        add_support(support, "provides_code_or_scripts", code_support)
        desc["provides_code_or_scripts"] = "yes" if flags["provides_code_or_scripts"] is True else UNDEFINED

        extension_support = first_match_support(
            lines,
            EXTENSION_RE,
            note="Deterministic text pattern found KNIME extension, plugin, node-library, or named dependency evidence.",
        )
        flags["reports_extension_or_plugin_dependencies"] = true_or_undefined(extension_support)
        add_support(support, "reports_extension_or_plugin_dependencies", extension_support)
        desc["reports_extension_or_plugin_dependencies"] = "yes" if extension_support else UNDEFINED

        install_support = first_match_support(
            lines,
            INSTALL_SOURCE_RE,
            note="Deterministic text pattern found extension, plugin, software, or workflow installation/source evidence.",
        )
        flags["reports_extension_installation_source"] = true_or_undefined(install_support)
        add_support(support, "reports_extension_installation_source", install_support)
        desc["reports_extension_installation_source"] = "yes" if install_support else UNDEFINED

        if workflow_record:
            workflow_files = workflow_record.get("download_result", {}).get("workflow_files_found", [])
            retrievable = bool(workflow_files)
            flags["linked_workflow_artifacts_retrievable"] = retrievable
            desc["linked_workflow_artifacts_retrievable"] = (
                "retrieved_in_project_workflow_registry" if retrievable else "not_retrieved_in_project_workflow_registry"
            )
            if retrievable:
                add_support(
                    support,
                    "linked_workflow_artifacts_retrievable",
                    {
                        "extracted_text_lines": "workflow_inventory",
                        "article_section": "Workflow inventory",
                        "quote": "",
                        "note": "Workflow-reference inventory records obtained KNIME workflow files or workflow directories.",
                    },
                )
        else:
            desc["linked_workflow_artifacts_retrievable"] = UNDEFINED

        desc["evidence_notes"] = (
            "Deterministic candidate generated from OpenAlex metadata, processed article text, "
            "URL extraction, and workflow-reference inventory. Undefined fields require manual or LLM review."
        )

    return {
        "rank": article["rank"],
        "title": article["title"],
        "doi": article["doi_or_url"],
        "pdf_file": pdf_file,
        "workflow_artifact": {
            "status": desc["workflow_artifact_status"],
            "summary": desc["workflow_artifact_status"],
        },
        "knime_version_reported": [] if desc["knime_version_values"] in ("", UNDEFINED) else desc["knime_version_values"].split("; "),
        "nodes_or_components_reported": [],
        "linked_resources": resources,
        "reproducibility_relevance": desc["evidence_notes"],
        "evidence": [],
        "article_identifier": article["article_identifier"],
        "publication_year": article["publication_year"],
        "venue": article["venue"],
        "doi_or_url": article["doi_or_url"],
        "article_audit_fields": {
            "description_audit_fields": desc,
            "flag_audit_fields": flags,
            "flag_audit_support": support,
        },
        "processed_text_file": text_path.as_posix() if text_path else None,
    }


def summary_counts(articles: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, Any] = {flag: 0 for flag in FLAG_NAMES}
    undefined_counts: dict[str, int] = {flag: 0 for flag in FLAG_NAMES}
    relation_counts: dict[str, int] = {}
    for article in articles:
        audit = article["article_audit_fields"]
        relation = audit["description_audit_fields"].get("knime_article_relation", "")
        relation_counts[relation] = relation_counts.get(relation, 0) + 1
        if relation == "about_knime":
            continue
        for flag, value in audit["flag_audit_fields"].items():
            if value is True:
                counts[flag] += 1
            elif value == UNDEFINED:
                undefined_counts[flag] += 1
    counts["total_records"] = len(articles)
    counts["knime_article_relation_counts"] = relation_counts
    counts["undefined_flag_counts"] = undefined_counts
    return counts


def schema_from_questions(questions: dict[str, Any]) -> dict[str, Any]:
    return {
        "description_audit_fields": {
            "description": "Same field group as the curated assessment. Deterministic candidates use 'undefined' when a field cannot be derived from seed metadata, article text, or workflow-reference inventory.",
            "fields": list(questions.get("description_questions", {}).keys()) or DESCRIPTION_FIELDS,
        },
        "flag_audit_fields": {
            "description": "Same flag names as the curated assessment. This candidate file may use the string 'undefined' where deterministic rules cannot decide true or false.",
            "fields": list(questions.get("flag_questions", {}).keys()) or FLAG_NAMES,
        },
        "flag_audit_support": {
            "description": "Map from true deterministic flags to direct quote or inventory support objects.",
        },
    }


def main() -> int:
    args = parse_args()
    questions = load_json(args.questions) if args.questions.exists() else {}
    workflows = workflow_index(args.workflow_references)
    seed_articles = selected_articles(load_seed_articles(args.seed_csv), args.rank, args.limit)

    articles: list[dict[str, Any]] = []
    for article in seed_articles:
        text_path = text_path_for_article(article, args.text_dir)
        articles.append(audit_article(article, text_path, workflows.get(article["rank"])))

    result = {
        "created_at": date.today().isoformat(),
        "created_by": Path(__file__).as_posix(),
        "source_csv": {
            "top_cited_seed": args.seed_csv.as_posix(),
            "workflow_references": args.workflow_references.as_posix(),
            "audit_questions": args.questions.as_posix(),
        },
        "article_directory": args.text_dir.as_posix(),
        "scope": (
            "Deterministic candidate assessment generated without LLM calls and without reading "
            "data/processed/audit/article_assessments.json."
        ),
        "method": {
            "input_files": "OpenAlex seed CSV, processed article text, audit questions, and workflow-reference inventory.",
            "text_extraction": "Uses existing processed one-column article text under data/processed/articles.",
            "assessment_focus": [
                "bibliographic metadata from OpenAlex",
                "direct regex-supported text evidence",
                "URLs classified by nearby text context",
                "workflow artifact retrieval status from the workflow-reference inventory",
            ],
        },
        "limitations": [
            "No LLM is called.",
            "The curated assessment JSON is not read.",
            "Undefined means the deterministic rules cannot decide from the available inputs.",
            "False is used only for local full-text absence, non-use classification, or workflow retrievability where the workflow inventory records no obtained workflow files.",
            "Regex matches can over-detect generic software, repository, or extension mentions and should be reviewed before replacing curated audit values.",
        ],
        "articles": articles,
        "article_audit_schema": schema_from_questions(questions),
        "article_audit_summary_counts": summary_counts(articles),
        "article_text_source": {
            "directory": args.text_dir.as_posix(),
            "articles_with_extracted_text": sum(1 for article in articles if article.get("processed_text_file")),
            "line_reference_semantics": "extracted_text_lines refer to processed one-column text files under data/processed/articles.",
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)
    print(f"Wrote {len(articles)} deterministic article-assessment records to {args.output}.")
    print(f"Matched processed text for {result['article_text_source']['articles_with_extracted_text']} records.")
    print("Curated assessment JSON was not read or modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
