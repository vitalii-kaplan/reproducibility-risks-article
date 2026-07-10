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
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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
HTML_METADATA_RE = re.compile(
    r'<script[^>]+id=["\']article-html-metadata["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
HTML_COMMENT_METADATA_RE = re.compile(
    r"<!--\s*article_html_metadata:\s*(.*?)\s*-->",
    re.IGNORECASE | re.DOTALL,
)
HTML_META_RE = re.compile(
    r'<meta\s+name=["\']article:([^"\']+)["\']\s+content=["\']([^"\']*)["\']\s*/?>',
    re.IGNORECASE,
)
EXCLUDED_OPENALEX_SEED_FIELDS = {
    "has_fulltext",
    "has_pdf",
    "knime_role",
    "likely_uses_knime_workflow_platform",
    "classification_reason",
}
COMMON_URL_TLDS = {
    "ac",
    "at",
    "au",
    "be",
    "biz",
    "ca",
    "ch",
    "cn",
    "co",
    "com",
    "de",
    "edu",
    "es",
    "eu",
    "fi",
    "fr",
    "gov",
    "info",
    "io",
    "it",
    "jp",
    "ly",
    "me",
    "net",
    "nl",
    "nz",
    "org",
    "uk",
    "us",
}

DESCRIPTION_FIELDS = [
    "knime_article_relation",
    "knime_version_values",
    "workflow_artifact_status",
    "provides_input_data",
    "provides_code_or_scripts",
    "reports_extension_or_plugin_dependencies",
    "reports_extension_installation_source",
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
]

URL_RE = re.compile(r"https?://[^\s<>\[\])\]}>\"']+", re.IGNORECASE)
VERSION_RE = re.compile(r"\bKNIME(?: Analytics Platform)?\s*(?:version|v\.?|ver\.?)?\s*(\d+(?:\.\d+){1,3})\b", re.IGNORECASE)
URL_INVISIBLE_CHARS_RE = re.compile(r"[\u00ad\u200b\u200c\u200d\ufeff]")

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
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if not first_line.startswith(TEXT_METADATA_PREFIX):
        for pattern in (HTML_METADATA_RE, HTML_COMMENT_METADATA_RE):
            match = pattern.search(text[:6000])
            if not match:
                continue
            try:
                metadata = json.loads(html.unescape(match.group(1).strip()))
            except json.JSONDecodeError:
                continue
            return metadata if isinstance(metadata, dict) else {}
        meta_fields = {
            key: html.unescape(value)
            for key, value in HTML_META_RE.findall(text[:6000])
        }
        return meta_fields
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
    files = [path for path in text_dir.glob("*.html") if path.is_file()]
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
        context = clean_url_text(compact(" ".join(lines[max(0, index - 2) : min(len(lines), index + 3)])))
        candidates = [line]
        seen_in_line: set[str] = set()
        for candidate in candidates:
            for url in URL_RE.findall(clean_url_text(candidate)):
                if url in seen_in_line:
                    continue
                seen_in_line.add(url)
                contexts.append((url, context))
    return contexts


def clean_url_text(value: str) -> str:
    return URL_INVISIBLE_CHARS_RE.sub("", value)


def normalized_url(raw_url: str, context: str = "") -> str | None:
    url = clean_url_text(raw_url).strip().rstrip(",;:")
    if url.endswith("-"):
        return None
    if url.endswith("."):
        without_dot = url.rstrip(".")
        try:
            parsed_without_dot = urlparse(without_dot)
        except ValueError:
            return None
        suffix = parsed_without_dot.netloc.lower().rsplit(".", 1)[-1]
        if suffix in COMMON_URL_TLDS:
            url = url.rstrip(".")
        else:
            continuation = re.search(
                rf"{re.escape(url)}\s+([A-Za-z0-9][A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+)",
                context,
            )
            if continuation:
                url = f"{url}{continuation.group(1).rstrip('.,;:])')}"
            else:
                url = url.rstrip(".")
    url = re.sub(r"\.[A-Z][A-Za-z]+$", "", url)
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    if "." not in host:
        return None
    if host in {"www.knime", "www.mdpi", "www.pubmedcentral.nih", "www.ncbi.nlm.nih"}:
        return None
    suffix = host.rsplit(".", 1)[-1]
    if suffix not in COMMON_URL_TLDS:
        return None
    if len(suffix) < 2 or not suffix.isalpha():
        return None
    if parsed.path.count("(") != parsed.path.count(")"):
        return None
    if host in {"doi.org", "dx.doi.org"} and re.fullmatch(r"/10\.\d+/?", parsed.path):
        return None
    return url


def tei_url(raw_url: str) -> str | None:
    url = clean_url_text(html.unescape(raw_url)).strip().rstrip(".,;:")
    if url.endswith("-"):
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if "." not in parsed.netloc:
        return None
    return url


def unique_normalized_urls_from_tei(path: Path) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return urls
    content_roots = [
        element
        for query in (
            ".//{http://www.tei-c.org/ns/1.0}profileDesc/{http://www.tei-c.org/ns/1.0}abstract",
            ".//{http://www.tei-c.org/ns/1.0}text/{http://www.tei-c.org/ns/1.0}body",
            ".//{http://www.tei-c.org/ns/1.0}text/{http://www.tei-c.org/ns/1.0}back",
            ".//{http://www.tei-c.org/ns/1.0}listBibl/{http://www.tei-c.org/ns/1.0}biblStruct",
        )
        for element in root.findall(query)
    ]
    for content_root in content_roots:
        for element in content_root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            target = element.attrib.get("target", "")
            if tag in {"ref", "ptr"} and target.startswith(("http://", "https://")):
                values = [target]
            else:
                values = list(element.attrib.values())
                if element.text:
                    values.append(element.text)
            if element.tail:
                values.append(element.tail)
            for value in values:
                for raw_url in URL_RE.findall(html.unescape(value)):
                    cleaned = tei_url(raw_url)
                    seen_key = cleaned.lower() if cleaned else ""
                    if cleaned and seen_key not in seen:
                        seen.add(seen_key)
                        urls.append(cleaned)
    return urls

def linked_resources_from_sources(
    lines: list[str],
    tei_path: Path | None,
    workflow_record: dict[str, Any] | None,
) -> list[dict[str, str]]:
    resources: list[dict[str, str]] = []
    seen: set[str] = set()
    source_urls: list[str] = []
    if tei_path and tei_path.exists():
        source_urls = unique_normalized_urls_from_tei(tei_path)
    if not source_urls:
        for url, context in url_contexts(lines):
            cleaned = normalized_url(url, context)
            if cleaned:
                source_urls.append(cleaned)
    for cleaned in source_urls:
        seen_key = cleaned.lower()
        if seen_key not in seen:
            seen.add(seen_key)
            resources.append({"url": cleaned, "type": UNDEFINED})
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
        openalex_seed_fields = {
            key: value for key, value in row.items() if key not in EXCLUDED_OPENALEX_SEED_FIELDS
        }
        articles.append(
            {
                "rank": index,
                "article_identifier": row.get("openalex_id", ""),
                "title": row.get("title", ""),
                "publication_year": row.get("publication_year", ""),
                "venue": row.get("source", ""),
                "doi_or_url": normalize_doi(row.get("doi", "")),
                "doi": normalize_doi(row.get("doi", "")),
                "openalex_seed_fields": openalex_seed_fields,
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
    tei_file = metadata.get("tei_file") or ""
    tei_path = Path(tei_file) if tei_file else None
    relation = determine_relation(article, lines)

    desc = {field: UNDEFINED for field in DESCRIPTION_FIELDS}
    desc.update(
        {
            "knime_article_relation": relation,
        }
    )

    resources = linked_resources_from_sources(lines or [], tei_path, workflow_record)
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
        flags["reports_input_data_availability"] = true_or_undefined(data_support)
        flags["provides_input_data_direct_url"] = UNDEFINED
        add_support(support, "reports_input_data_availability", data_support)
        desc["provides_input_data"] = "yes" if flags["reports_input_data_availability"] is True else UNDEFINED

        code_support = first_match_support(
            lines,
            CODE_RE,
            note="Deterministic text pattern found code, script, software, or repository evidence.",
        )
        flags["provides_code_or_scripts"] = true_or_undefined(code_support)
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

        desc["evidence_notes"] = (
            "Deterministic candidate generated from OpenAlex metadata, processed article text, "
            "URL extraction, and workflow-reference inventory. Undefined fields require LLM review."
        )

    processed_text_file = text_path.as_posix() if text_path else None
    meta = {
        "article_identifier": article["article_identifier"],
        "pdf_file": pdf_file,
        "tei_file": tei_file or UNDEFINED,
        "processed_text_file": processed_text_file,
        "openalex_seed_fields": article.get("openalex_seed_fields", {}),
    }

    return {
        "rank": article["rank"],
        "meta": meta,
        "linked_resources": resources,
        "article_audit_fields": {
            "description_audit_fields": desc,
            "flag_audit_fields": flags,
            "flag_audit_support": support,
        },
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
            "description": "Deterministic non-bibliographic assessment fields. Bibliographic metadata and OpenAlex role fields are stored once under each article's meta object.",
            "fields": DESCRIPTION_FIELDS,
        },
        "flag_audit_fields": {
            "description": "Deterministic article-level flags. Later workflow retrieval, opening, and execution fields are excluded from this candidate file.",
            "fields": FLAG_NAMES,
        },
        "flag_audit_support": {
            "description": "Map from true deterministic flags to direct quote or article-level workflow-reference support objects.",
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
            "input_files": "OpenAlex seed CSV, processed GROBID article HTML, audit questions, and workflow-reference inventory.",
            "text_extraction": "Uses existing processed GROBID article HTML under data/processed/articles.",
            "assessment_focus": [
                "bibliographic metadata from OpenAlex",
                "direct regex-supported text evidence",
                "URLs normalized and validated from article text",
                "article-level downloadable or linked workflow evidence from text and the workflow-reference inventory",
            ],
        },
        "limitations": [
            "No LLM is called.",
            "The curated assessment JSON is not read.",
            "Undefined means the deterministic rules cannot decide from the available inputs.",
            "False is used only for local full-text absence or non-use classification.",
            "Regex matches can over-detect generic software, repository, or extension mentions and should be reviewed before replacing curated audit values.",
        ],
        "articles": articles,
        "article_audit_schema": schema_from_questions(questions),
        "article_audit_summary_counts": summary_counts(articles),
        "article_text_source": {
            "directory": args.text_dir.as_posix(),
            "articles_with_extracted_text": sum(
                1 for article in articles if article.get("meta", {}).get("processed_text_file")
            ),
            "line_reference_semantics": "extracted_text_lines refer to processed GROBID HTML files under data/processed/articles.",
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
