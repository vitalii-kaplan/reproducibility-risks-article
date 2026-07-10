#!/usr/bin/env python3
"""Extract article TEI with GROBID and render semantic HTML files.

Requires a running GROBID service, for example:

    docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


DEFAULT_INPUT_DIR = Path("data/original/articles")
DEFAULT_OUTPUT_DIR = Path("data/processed/articles")
DEFAULT_TEI_DIR = Path("data/processed/articles/grobid_tei")
DEFAULT_MANIFEST = Path("data/processed/audit/logs/article_grobid_html_manifest.csv")
DEFAULT_GROBID_URL = "http://localhost:8070"
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--tei-dir", type=Path, default=DEFAULT_TEI_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--grobid-url", default=DEFAULT_GROBID_URL)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Regenerate TEI and HTML for all PDFs, including existing outputs.",
    )
    parser.add_argument(
        "--reuse-existing-tei",
        action="store_true",
        help="Render HTML from existing TEI files when present instead of calling GROBID.",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("._")
    return slug or "article"


def grobid_is_alive(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/isalive", timeout=5) as response:
            body = response.read().decode("utf-8", errors="replace").strip().lower()
        return response.status == 200 and body == "true"
    except (OSError, urllib.error.URLError):
        return False


def request_grobid_tei(pdf_file: Path, base_url: str) -> bytes:
    boundary = "----codex-grobid-html"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="input"; filename="{pdf_file.name}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8") + pdf_file.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/processFulltextDocument",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join(" ".join(element.itertext()).split())


def article_text(element: ET.Element | None) -> str:
    if element is None:
        return ""

    parts: list[str] = []

    def append(value: str | None) -> None:
        if value:
            parts.append(value)

    def walk(node: ET.Element) -> None:
        target = node.attrib.get("target", "")
        tag = node.tag.rsplit("}", 1)[-1]
        if target.startswith(("http://", "https://")) and tag in {"ref", "ptr"}:
            append(target)
        else:
            append(node.text)
            for child in node:
                walk(child)
                append(child.tail)

    walk(element)
    return " ".join(" ".join(parts).split())


def target_urls(element: ET.Element) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for child in element.iter():
        target = child.attrib.get("target")
        if not target or not target.startswith(("http://", "https://")):
            continue
        if target not in seen:
            seen.add(target)
            urls.append(target)
    return urls


def element_text_with_target_urls(element: ET.Element | None) -> str:
    if element is None:
        return ""
    text = article_text(element)
    urls = target_urls(element)
    if urls:
        existing = re.sub(r"\s+", "", text.lower())
        missing_urls = [
            url
            for url in urls
            if re.sub(r"\s+", "", url.lower()) not in existing
        ]
        if missing_urls:
            text = (text + " " + " ".join(missing_urls)).strip()
    return text


def find_title(root: ET.Element) -> str:
    title = root.find(".//tei:titleStmt/tei:title", TEI_NS)
    if title is not None and element_text(title):
        return element_text(title)
    title = root.find(".//tei:title", TEI_NS)
    return element_text(title) or "Untitled article"


def render_paragraph(element: ET.Element) -> str:
    text = element_text_with_target_urls(element)
    if not text:
        return ""
    attrs = []
    xml_id = element.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
    if xml_id:
        attrs.append(f'id="{html.escape(xml_id)}"')
    attr_text = " " + " ".join(attrs) if attrs else ""
    return f"<p{attr_text}>{html.escape(text)}</p>"


def render_text_block(element: ET.Element, class_name: str) -> str:
    text = element_text_with_target_urls(element)
    if not text:
        return ""
    attrs = [f'class="{html.escape(class_name)}"']
    xml_id = element.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
    if xml_id:
        attrs.append(f'id="{html.escape(xml_id)}"')
    return f"<p {' '.join(attrs)}>{html.escape(text)}</p>"


def render_div(div: ET.Element, depth: int = 2) -> list[str]:
    parts: list[str] = []
    heading_level = min(max(depth, 2), 6)
    head = div.find("tei:head", TEI_NS)
    if head is not None and element_text(head):
        parts.append(f"<h{heading_level}>{html.escape(element_text(head))}</h{heading_level}>")
    for child in div:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = render_paragraph(child)
            if paragraph:
                parts.append(paragraph)
        elif tag == "div":
            parts.extend(render_div(child, depth + 1))
        elif tag in {"figure", "figDesc", "note", "table"}:
            block = render_text_block(child, tag)
            if block:
                parts.append(block)
    return parts


def render_bibliography(root: ET.Element) -> list[str]:
    entries = root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)
    if not entries:
        return []
    parts = ["<section id=\"references\">", "<h2>References</h2>", "<ol>"]
    for entry in entries:
        text = element_text_with_target_urls(entry)
        if text:
            parts.append(f"<li>{html.escape(text)}</li>")
    parts.extend(["</ol>", "</section>"])
    return parts


def render_back_matter(root: ET.Element) -> list[str]:
    back = root.find(".//tei:text/tei:back", TEI_NS)
    if back is None:
        return []
    parts: list[str] = []
    for child in back:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "listBibl":
            continue
        if not parts:
            parts.extend(["<section id=\"back-matter\">", "<h2>Back Matter</h2>"])
        if tag == "div":
            parts.extend(render_div(child))
        elif tag == "p":
            rendered = render_paragraph(child)
            if rendered:
                parts.append(rendered)
        elif tag in {"figure", "figDesc", "note", "table"}:
            block = render_text_block(child, tag)
            if block:
                parts.append(block)
        else:
            block = render_text_block(child, tag)
            if block:
                parts.append(block)
    if parts:
        parts.append("</section>")
    return parts


def tei_to_html(tei_bytes: bytes, metadata: dict[str, Any]) -> tuple[str, dict[str, int | str]]:
    root = ET.fromstring(tei_bytes)
    title = find_title(root)
    abstract_div = root.find(".//tei:profileDesc/tei:abstract", TEI_NS)
    body = root.find(".//tei:text/tei:body", TEI_NS)
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    parts = [
        "<!doctype html>",
        "<html>",
        "<head>",
        "<meta charset=\"utf-8\">",
        f"<meta name=\"article:source_pdf\" content=\"{html.escape(str(metadata.get('source_pdf', '')))}\">",
        f"<meta name=\"article:tei_file\" content=\"{html.escape(str(metadata.get('tei_file', '')))}\">",
        f"<meta name=\"article:html_file\" content=\"{html.escape(str(metadata.get('html_file', '')))}\">",
        f"<meta name=\"article:text_extractor\" content=\"{html.escape(str(metadata.get('text_extractor', '')))}\">",
        f"<meta name=\"article:text_stage\" content=\"{html.escape(str(metadata.get('text_stage', '')))}\">",
        f"<title>{html.escape(title)}</title>",
        "<script type=\"application/json\" id=\"article-html-metadata\">"
        + html.escape(metadata_json)
        + "</script>",
        "</head>",
        "<body>",
        "<!-- article_html_metadata: " + html.escape(metadata_json) + " -->",
        f"<h1>{html.escape(title)}</h1>",
    ]
    if abstract_div is not None:
        parts.append("<section id=\"abstract\">")
        parts.append("<h2>Abstract</h2>")
        for paragraph in abstract_div.findall(".//tei:p", TEI_NS):
            rendered = render_paragraph(paragraph)
            if rendered:
                parts.append(rendered)
        parts.append("</section>")
    if body is not None:
        parts.append("<main>")
        for child in body:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "div":
                parts.extend(render_div(child))
            elif tag == "p":
                rendered = render_paragraph(child)
                if rendered:
                    parts.append(rendered)
            elif tag in {"figure", "figDesc", "note", "table"}:
                block = render_text_block(child, tag)
                if block:
                    parts.append(block)
        parts.append("</main>")
    parts.extend(render_back_matter(root))
    parts.extend(render_bibliography(root))
    parts.extend(["</body>", "</html>"])
    html_text = "\n".join(parts) + "\n"
    stats = {
        "title": title,
        "tei_text_chars": len(" ".join(root.itertext())),
        "tei_divs": len(root.findall(".//tei:div", TEI_NS)),
        "tei_paragraphs": len(root.findall(".//tei:p", TEI_NS)),
        "tei_bibliography_entries": len(root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)),
        "html_bytes": len(html_text.encode("utf-8")),
    }
    return html_text, stats


def main() -> int:
    args = parse_args()
    pdf_files = sorted(args.input_dir.glob("*.pdf"))
    if not pdf_files:
        raise SystemExit(f"No PDF files found in {args.input_dir}")
    if not args.reuse_existing_tei and not grobid_is_alive(args.grobid_url):
        raise SystemExit(f"GROBID service is not available at {args.grobid_url}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.tei_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    processed = 0
    skipped = 0
    failed = 0
    for pdf_file in pdf_files:
        stem = slugify(pdf_file.stem)
        tei_file = args.tei_dir / f"{stem}.tei.xml"
        html_file = args.output_dir / f"{stem}.html"
        if (
            not args.all
            and tei_file.exists()
            and tei_file.stat().st_size > 0
            and html_file.exists()
            and html_file.stat().st_size > 0
        ):
            rows.append(
                {
                    "pdf_file": pdf_file.as_posix(),
                    "tei_file": tei_file.as_posix(),
                    "html_file": html_file.as_posix(),
                    "status": "existing",
                    "title": "",
                    "tei_text_chars": "",
                    "tei_divs": "",
                    "tei_paragraphs": "",
                    "tei_bibliography_entries": "",
                    "html_bytes": str(html_file.stat().st_size),
                    "error": "",
                }
            )
            skipped += 1
            continue

        try:
            metadata = {
                "source_pdf": pdf_file.as_posix(),
                "tei_file": tei_file.as_posix(),
                "html_file": html_file.as_posix(),
                "text_extractor": "GROBID",
                "grobid_url": args.grobid_url,
                "text_stage": "semantic_html_from_tei",
            }
            if args.reuse_existing_tei and tei_file.exists() and tei_file.stat().st_size > 0:
                tei_bytes = tei_file.read_bytes()
            else:
                tei_bytes = request_grobid_tei(pdf_file, args.grobid_url)
            html_text, stats = tei_to_html(tei_bytes, metadata)
            tei_file.write_bytes(tei_bytes)
            html_file.write_text(html_text, encoding="utf-8")
            rows.append(
                {
                    "pdf_file": pdf_file.as_posix(),
                    "tei_file": tei_file.as_posix(),
                    "html_file": html_file.as_posix(),
                    "status": "ok",
                    "title": str(stats["title"]),
                    "tei_text_chars": str(stats["tei_text_chars"]),
                    "tei_divs": str(stats["tei_divs"]),
                    "tei_paragraphs": str(stats["tei_paragraphs"]),
                    "tei_bibliography_entries": str(stats["tei_bibliography_entries"]),
                    "html_bytes": str(stats["html_bytes"]),
                    "error": "",
                }
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            rows.append(
                {
                    "pdf_file": pdf_file.as_posix(),
                    "tei_file": tei_file.as_posix(),
                    "html_file": html_file.as_posix(),
                    "status": "failed",
                    "title": "",
                    "tei_text_chars": "",
                    "tei_divs": "",
                    "tei_paragraphs": "",
                    "tei_bibliography_entries": "",
                    "html_bytes": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    with args.manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "pdf_file",
                "tei_file",
                "html_file",
                "status",
                "title",
                "tei_text_chars",
                "tei_divs",
                "tei_paragraphs",
                "tei_bibliography_entries",
                "html_bytes",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"GROBID HTML extraction processed {processed}, skipped {skipped}, "
        f"failed {failed}, total {len(rows)}; output: {args.output_dir}; "
        f"TEI: {args.tei_dir}; manifest: {args.manifest}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
