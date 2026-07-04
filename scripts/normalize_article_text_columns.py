#!/usr/bin/env python3
"""Normalize two-column pdftotext output into one-column reading order."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        default="data/processed/articles/raw",
        type=Path,
        help="Directory containing raw pdftotext -layout article text files.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed/articles",
        type=Path,
        help="Directory for processed reading-order text files.",
    )
    parser.add_argument(
        "--manifest",
        default="data/processed/audit/logs/article_text_column_normalization_manifest.csv",
        type=Path,
        help="CSV manifest describing detected layouts and converted pages.",
    )
    parser.add_argument(
        "--min-gap",
        default=8,
        type=int,
        help="Minimum run of spaces treated as a possible column gap.",
    )
    parser.add_argument(
        "--min-two-column-lines",
        default=14,
        type=int,
        help="Minimum side-by-side lines required to treat a page as two-column.",
    )
    parser.add_argument(
        "--min-converted-page-share",
        default=0.25,
        type=float,
        help="Minimum candidate page share required to normalize a whole article.",
    )
    parser.add_argument(
        "--min-converted-pages",
        default=3,
        type=int,
        help="Minimum candidate pages required to normalize a whole article.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-create normalized text files for all raw text inputs.",
    )
    return parser.parse_args()


def read_existing_manifest(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["source_text_file"]: row
            for row in csv.DictReader(handle)
            if row.get("source_text_file")
        }


def has_text(value: str) -> bool:
    return bool(value.strip())


def space_runs(line: str, min_gap: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, char in enumerate(line):
        if char == " ":
            if start is None:
                start = index
        elif start is not None:
            if index - start >= min_gap:
                runs.append((start, index))
            start = None
    if start is not None and len(line) - start >= min_gap:
        runs.append((start, len(line)))
    return runs


def candidate_column_gaps(lines: list[str], min_gap: int) -> list[float]:
    candidates: list[float] = []
    for line in lines:
        stripped = line.rstrip()
        if len(stripped) < 60:
            continue
        for start, end in space_runs(stripped, min_gap):
            left = stripped[:start]
            right = stripped[end:]
            if has_text(left) and has_text(right):
                if len(left.strip()) < 18 or len(right.strip()) < 18:
                    continue
                # Ignore ordinary indentation and very late reference/table gaps.
                midpoint = (start + end) / 2
                if len(stripped) * 0.25 <= midpoint <= len(stripped) * 0.78:
                    candidates.append(midpoint)
                    break
    return candidates


def detect_split_column(
    lines: list[str], min_gap: int, min_two_column_lines: int
) -> int | None:
    content_lines = [line for line in lines if has_text(line)]
    if not content_lines:
        return None

    gaps = candidate_column_gaps(content_lines, min_gap)
    content_count = len(content_lines)
    if len(gaps) < min_two_column_lines:
        return None
    if len(gaps) / content_count < 0.25:
        return None

    return round(statistics.median(gaps))


def split_line_at_column(line: str, split_column: int) -> tuple[str, str]:
    padded = line.rstrip("\n")
    if len(padded) <= split_column:
        return padded.rstrip(), ""
    left = padded[:split_column].rstrip()
    right = padded[split_column:].strip()
    return left, right


def normalize_page(lines: list[str], split_column: int | None) -> list[str]:
    if split_column is None:
        return [line.rstrip() for line in lines]

    dual_indexes: list[int] = []
    for index, line in enumerate(lines):
        left, right = split_line_at_column(line, split_column)
        if has_text(left) and has_text(right):
            dual_indexes.append(index)

    if not dual_indexes:
        return [line.rstrip() for line in lines]

    first_dual = dual_indexes[0]
    last_dual = dual_indexes[-1]
    before = [line.rstrip() for line in lines[:first_dual] if has_text(line)]
    after = [line.rstrip() for line in lines[last_dual + 1 :] if has_text(line)]

    left_lines: list[str] = []
    right_lines: list[str] = []
    for line in lines[first_dual : last_dual + 1]:
        left, right = split_line_at_column(line, split_column)
        if has_text(left):
            left_lines.append(left)
        elif left_lines and left_lines[-1] != "":
            left_lines.append("")
        if has_text(right):
            right_lines.append(right)
        elif right_lines and right_lines[-1] != "":
            right_lines.append("")

    normalized: list[str] = []
    normalized.extend(before)
    if normalized and left_lines:
        normalized.append("")
    normalized.extend(trim_blank_edges(left_lines))
    if normalized and right_lines:
        normalized.append("")
    normalized.extend(trim_blank_edges(right_lines))
    if normalized and after:
        normalized.append("")
    normalized.extend(after)
    return normalized


def trim_blank_edges(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not has_text(lines[start]):
        start += 1
    while end > start and not has_text(lines[end - 1]):
        end -= 1
    return lines[start:end]


def normalize_text(
    text: str,
    min_gap: int,
    min_two_column_lines: int,
    min_converted_page_share: float,
    min_converted_pages: int,
) -> tuple[str, dict[str, int | bool]]:
    pages = text.split("\f")
    page_splits = [
        detect_split_column(page.split("\n"), min_gap, min_two_column_lines)
        for page in pages
    ]
    candidate_pages = sum(1 for split in page_splits if split is not None)
    should_normalize = (
        candidate_pages >= min_converted_pages
        and candidate_pages / max(len(pages), 1) >= min_converted_page_share
    )

    normalized_pages: list[str] = []
    converted_pages = 0
    one_column_pages = 0

    for page, split_column in zip(pages, page_splits, strict=True):
        lines = page.split("\n")
        if split_column is None or not should_normalize:
            one_column_pages += 1
            split_column = None
        else:
            converted_pages += 1
        normalized_pages.append("\n".join(normalize_page(lines, split_column)).rstrip())

    stats = {
        "pages": len(pages),
        "candidate_two_column_pages": candidate_pages,
        "converted_pages": converted_pages,
        "one_column_pages": one_column_pages,
        "normalized": should_normalize,
    }
    return "\f\n".join(normalized_pages).rstrip() + "\n", stats


def main() -> int:
    args = parse_args()
    text_files = sorted(path for path in args.input_dir.glob("*.txt") if path.is_file())
    if not text_files:
        raise SystemExit(f"No .txt files found in {args.input_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    existing_manifest = read_existing_manifest(args.manifest)
    processed = 0
    skipped = 0
    for source in text_files:
        target = args.output_dir / source.name
        existing_row = existing_manifest.get(source.as_posix())
        if (
            not args.all
            and target.exists()
            and target.stat().st_size > 0
            and existing_row
            and existing_row.get("normalized_text_file") == target.as_posix()
        ):
            rows.append(existing_row)
            skipped += 1
            continue
        if not args.all and target.exists() and target.stat().st_size > 0:
            rows.append(
                {
                    "source_text_file": source.as_posix(),
                    "normalized_text_file": target.as_posix(),
                    "layout": "existing",
                    "pages": "",
                    "candidate_two_column_pages": "",
                    "converted_pages": "",
                    "one_column_pages": "",
                }
            )
            skipped += 1
            continue

        text = source.read_text(encoding="utf-8", errors="replace")
        normalized, stats = normalize_text(
            text,
            min_gap=args.min_gap,
            min_two_column_lines=args.min_two_column_lines,
            min_converted_page_share=args.min_converted_page_share,
            min_converted_pages=args.min_converted_pages,
        )
        target.write_text(normalized, encoding="utf-8")
        layout = (
            "two_column_normalized"
            if stats["normalized"]
            else "one_column_or_complex_layout"
        )
        processed += 1
        rows.append(
            {
                "source_text_file": source.as_posix(),
                "normalized_text_file": target.as_posix(),
                "layout": layout,
                "pages": str(stats["pages"]),
                "candidate_two_column_pages": str(stats["candidate_two_column_pages"]),
                "converted_pages": str(stats["converted_pages"]),
                "one_column_pages": str(stats["one_column_pages"]),
            }
        )

    with args.manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_text_file",
                "normalized_text_file",
                "layout",
                "pages",
                "candidate_two_column_pages",
                "converted_pages",
                "one_column_pages",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    converted_files = sum(1 for row in rows if row["layout"] == "two_column_normalized")
    print(
        f"Normalized {processed} text files, skipped {skipped} existing files; "
        f"detected two-column pages in {converted_files} files; "
        f"output: {args.output_dir}; "
        f"manifest: {args.manifest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
