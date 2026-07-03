#!/usr/bin/env python3
"""Extract plain text from local article PDFs for audit support."""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from pathlib import Path


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
        default="data/processed/articles",
        type=Path,
        help="Directory for generated text files.",
    )
    parser.add_argument(
        "--manifest",
        default="data/processed/audit/article_text_extraction_manifest.csv",
        type=Path,
        help="CSV manifest describing the extraction result for each PDF.",
    )
    parser.add_argument(
        "--pdftotext",
        default="pdftotext",
        help="pdftotext executable to use.",
    )
    return parser.parse_args()


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

    for pdf in pdfs:
        base = slugify(pdf.stem)
        name = f"{base}.txt"
        counter = 2
        while name in used_names:
            name = f"{base}_{counter}.txt"
            counter += 1
        used_names.add(name)

        output = args.output_dir / name
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
        f"Extracted {len(rows) - failures} of {len(rows)} PDFs to "
        f"{args.output_dir}; manifest: {args.manifest}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
