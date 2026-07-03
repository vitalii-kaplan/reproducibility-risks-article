# KNIME Workflows in Scientific Studies

This repository supports the article **"KNIME Workflows in Scientific Studies:
Publication Practices and Reproducibility Risks"**.

The project studies how scientific papers report KNIME workflows and what that
means for long-term reproducibility. It focuses on whether papers preserve
enough information for later researchers to inspect, import, or rerun the
workflow: executable workflow files, KNIME versions, input data, code, and
extension or plugin context.

KNIME is used as the case study because it is a widely used open-source visual
workflow platform with a long public development history.

## What This Project Contains

- The paper source and generated PDF.
- OpenAlex-based bibliographic evidence for KNIME-related articles.
- Manual audit data for highly cited KNIME-related papers.
- A current-KNIME compatibility case study for the PAINS workflows.
- KNIME source-repository mining data on node metadata and deprecation.
- Scripts used to extract, process, and summarize the evidence.

The paper is the source of truth for the current scientific claims. The data
and scripts in this repository are here to make those claims inspectable.

## Current Findings

- An OpenAlex title-and-abstract search for `KNIME`, restricted to article
  records and collected on June 29, 2026, returned 963 article-type records.
- A manual audit of the 20 most-cited KNIME-matching article records found that
  influential papers often present KNIME through text, figures, or tool
  mentions rather than downloadable workflow artifacts.
- In that top-cited audit, the PAINS filters paper was the only
  non-KNIME-focused case with retrievable KNIME workflow files suitable for a
  current-KNIME import experiment.
- In the PAINS experiment, the RDKit workflow executed in KNIME Analytics
  Platform 5.8.3 LTS after extension installation, while the Indigo workflow
  was blocked by a missing third-party extension.
- Repository mining found that deprecated ordinary nodes increased from 14.83%
  of registered ordinary nodes in the 2018 source baseline to 33.33% in the
  June 28, 2026 local source snapshot.

These results do **not** show that KNIME workflows are generally
unreproducible. The narrower claim is that weak artifact preservation and
platform evolution create reproducibility risks, especially when papers provide
only workflow images or textual descriptions.

## Repository Map

```text
article/                 Paper source, bibliography, figures, and PDF
data/original/           Raw or source evidence where included
data/processed/audit/    Structured article-audit data and audit questions
data/processed/knime_snapshots/
                         Processed KNIME repository-mining outputs
scripts/                 Data extraction and analysis scripts
Methods.md               Method notes for repository mining and data collection
Deprecated.md            Notes on deprecated-node semantics
AGENTS.md                Detailed working rules for future project updates
```

Generated text extracted from article PDFs is written to
`data/processed/articles/`. That directory is ignored by Git because it can be
regenerated from local PDFs with:

```sh
scripts/extract_article_texts.py
```

## Key Data Files

- `data/processed/audit/knime_most_cited_article_assessments.json`: structured
  manual assessment of the top-cited KNIME-related article records.
- `data/processed/audit/knime_article_audit_questions.json`: questions and
  field definitions used in the article audit.
- `data/processed/audit/article_text_extraction_manifest.csv`: manifest for
  the PDF-to-text extraction run.
- `data/processed/knime_snapshots/knime_node_snapshot_summary.csv`: summary of
  KNIME node metadata across source snapshots.
- `data/processed/knime_snapshots/knime_oss_repositories.csv`: repository list
  used for KNIME source mining.

## Requirements

The Python scripts use only Python standard-library modules. A Python virtual
environment is not currently required.

Command-line tools used by the scripts and paper build:

- Python 3
- Bash
- Git
- curl
- jq
- `pdftotext`, from Poppler
- `latexmk`, for rebuilding the paper PDF

OpenAlex and GitHub collection scripts require network access. Locally captured
tool versions are recorded in
`data/processed/environment/tool_versions.txt`.

## Scripts

Run scripts from the repository root unless noted otherwise.

- `scripts/collect_openalex_knime_works.py`: collects OpenAlex article records
  matching `KNIME` in title and abstract and writes raw results to
  `data/original/openalex/`.

  ```sh
  python3 scripts/collect_openalex_knime_works.py
  ```

- `scripts/build_openalex_knime_bibliometrics.py`: builds processed OpenAlex
  summary tables from `data/original/openalex/works.jsonl`.

  ```sh
  python3 scripts/build_openalex_knime_bibliometrics.py
  ```

- `scripts/extract_article_texts.py`: converts local article PDFs from
  `data/original/articles/` to plain-text files in `data/processed/articles/`
  and writes an extraction manifest.

  ```sh
  scripts/extract_article_texts.py
  ```

- `scripts/clone_knime_oss_repos.sh`: clones public repositories from the
  `knime-oss` GitHub organization into a local directory.

  ```sh
  scripts/clone_knime_oss_repos.sh /path/to/knime-oss
  ```

- `scripts/checkout_knime_oss_by_date.sh`: checks each cloned KNIME repository
  out to the latest commit at or before a chosen date and records a manifest.

  ```sh
  scripts/checkout_knime_oss_by_date.sh /path/to/knime-oss 2026-06-28
  ```

- `scripts/collect_knime_node_snapshot.py`: extracts node, nodeset,
  deprecation, hidden-node, class-mapper, and migration-rule metadata from one
  checked-out KNIME source snapshot.

  ```sh
  python3 scripts/collect_knime_node_snapshot.py /path/to/knime-oss \
    --snapshot-id date-2026-06-28 \
    --snapshot-date 2026-06-28
  ```

- `scripts/build_knime_node_snapshot_summary.py`: builds the processed
  cross-snapshot KNIME node summary from extracted snapshot directories.

  ```sh
  python3 scripts/build_knime_node_snapshot_summary.py
  ```

## The Paper formatting

The paper uses Springer LNCS / S-LNCS formatting and vendors the LNCS class and
BibTeX style files needed for the current build.

## Current Extension Plan

The next empirical step is to increase the scale of the workflow evidence. The
goal is to audit more KNIME-related papers, collect every retrievable KNIME
workflow found during that audit, and inspect those workflows for compatibility
risk signals such as deprecated nodes, missing nodes, unresolved extensions,
and current-KNIME import or execution failures.

The planned statistics are deliberately simple: counts, percentages, and
distributions for article-level reporting practices and workflow-level
compatibility signals. Formal statistical tests should only be added if the
eventual sample size supports them.

Cross-platform comparison is lower priority unless it can be done
systematically. The stronger near-term contribution is a deeper KNIME workflow
corpus with traceable node-level compatibility analysis.

## Scope And Limits

- Repository-level deprecation statistics show source metadata evolution; they
  do not by themselves prove that published workflows fail.
- The PAINS experiment is a single manual compatibility case study, not a
  population-level workflow failure-rate estimate.
- The article audit records both evidence and absence of evidence, including
  whether papers report workflow files, KNIME versions, data, code, and
  extension context.

## Reuse

When reusing this repository, cite the article and preserve the connection
between claims, data, and scripts. New evidence should be added with enough
metadata to show where it came from and how it was processed.
