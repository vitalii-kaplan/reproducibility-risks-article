#!/usr/bin/env python3
"""Extract plain text from local article PDFs for audit support."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path


TEXT_METADATA_PREFIX = "# article_text_metadata: "


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("._")
    return slug or "article"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert article PDFs to one text file per PDF."
    )
    parser.add_argument(
        "--input-dir",
        default="data/original/articles",
        type=Path,
        help="Directory containing source PDF files.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed/articles/raw",
        type=Path,
        help="Directory for raw generated text files.",
    )
    parser.add_argument(
        "--manifest",
        default="data/processed/audit/logs/article_text_extraction_manifest.csv",
        type=Path,
        help="CSV manifest describing the extraction result for each PDF.",
    )
    parser.add_argument(
        "--pdftotext",
        default="pdftotext",
        help="pdftotext executable to use.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-create text files for all PDFs, including PDFs that already have output text.",
    )
    return parser.parse_args()


def read_existing_manifest(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["pdf_file"]: row
            for row in csv.DictReader(handle)
            if row.get("pdf_file")
        }


def write_text_metadata_header(path: Path, metadata: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if lines and lines[0].startswith(TEXT_METADATA_PREFIX):
        text = "\n".join(lines[1:])
        if text:
            text += "\n"
    header = TEXT_METADATA_PREFIX + json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    path.write_text(header + "\n" + text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    pdfs = sorted(args.input_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDF files found in {args.input_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    used_names: set[str] = set()
    failures = 0
    processed = 0
    skipped = 0
    existing_manifest = read_existing_manifest(args.manifest)

    for pdf in pdfs:
        base = slugify(pdf.stem)
        name = f"{base}.txt"
        counter = 2
        while name in used_names:
            name = f"{base}_{counter}.txt"
            counter += 1
        used_names.add(name)

        output = args.output_dir / name
        existing_row = existing_manifest.get(pdf.as_posix())
        if (
            not args.all
            and output.exists()
            and output.stat().st_size > 0
            and existing_row
            and existing_row.get("status") == "ok"
            and existing_row.get("text_file") == output.as_posix()
        ):
            rows.append(existing_row)
            skipped += 1
            continue
        if not args.all and output.exists() and output.stat().st_size > 0:
            rows.append(
                {
                    "pdf_file": pdf.as_posix(),
                    "text_file": output.as_posix(),
                    "status": "existing",
                    "returncode": "",
                    "stderr": "",
                }
            )
            skipped += 1
            continue

        result = subprocess.run(
            [args.pdftotext, "-layout", str(pdf), str(output)],
            check=False,
            capture_output=True,
            text=True,
        )
        status = "ok" if result.returncode == 0 else "failed"
        if result.returncode != 0:
            failures += 1
            output.unlink(missing_ok=True)
        else:
            write_text_metadata_header(
                output,
                {
                    "source_pdf": pdf.as_posix(),
                    "raw_text_file": output.as_posix(),
                    "text_stage": "raw_pdftotext_layout",
                    "text_extractor": args.pdftotext,
                },
            )
            processed += 1

        rows.append(
            {
                "pdf_file": pdf.as_posix(),
                "text_file": output.as_posix() if result.returncode == 0 else "",
                "status": status,
                "returncode": str(result.returncode),
                "stderr": " ".join(result.stderr.split()),
            }
        )

    with args.manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["pdf_file", "text_file", "status", "returncode", "stderr"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Extracted {processed} PDFs, skipped {skipped} existing PDFs, "
        f"failed {failures}, total {len(rows)}; output: "
        f"{args.output_dir}; manifest: {args.manifest}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
