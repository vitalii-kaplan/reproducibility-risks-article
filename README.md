# KNIME Workflows in Scientific Studies

This repository supports the article **"KNIME Workflows in Scientific Studies:
Publication Practices and Reproducibility Risks"**.

The project studies how scientific papers report KNIME workflows and what that
means for long-term reproducibility. It asks whether published studies preserve
the information needed to inspect, open, and rerun a KNIME-based workflow later:
workflow files, KNIME versions, input data, code, and extension or plugin
context.

KNIME is used as the case study because it is a widely used open-source visual
workflow platform with a long public development history.

## What Is In This Repository

- The paper source and generated PDF in `article/`.
- OpenAlex bibliographic data for KNIME-related articles.
- A structured audit of highly cited KNIME-related papers.
- Workflow retrieval notes and manual KNIME opening/execution results for the
  workflow artifacts that could be obtained.
- KNIME source-repository mining outputs about node metadata and deprecation.
- Scripts used to reproduce the main tables and data summaries.
- GROBID-derived semantic HTML/TEI article extractions used for structured
  article-text inspection.

The paper is the main narrative. The data and scripts are included so the
claims can be inspected and updated.

## Current Findings

- An OpenAlex title-and-abstract search for `KNIME`, restricted to article
  records and collected on June 29, 2026, returned 963 article-type records.
- The expanded top-cited audit covers 100 KNIME-matching article records. Of
  these, 82 have local full text or PDFs and 18 remain not assessed because no
  local full text was available.
- In the 100-record audit, 67 records use KNIME as a workflow, tool, interface,
  or implementation context.
- Twenty-eight records report downloadable or linked KNIME workflow files.
  Workflow artifacts or workflow directories were obtained for 12 article
  records.
- Workflows from all 12 obtained article records opened in the local KNIME
  environment used for the manual check. Four article records had at least one
  workflow execute successfully: PAINS, Webinar Pricing Analytics, ImageJ
  ecosystem integration, and high-content organelle trafficking.
- Repository mining found that deprecated ordinary nodes increased from 14.83%
  of registered ordinary nodes in the 2018 source baseline to 33.33% in the
  June 28, 2026 local source snapshot.

These results do **not** show that KNIME workflows are generally
unreproducible. The narrower claim is that weak artifact preservation and
platform evolution create reproducibility risks, especially when papers provide
only workflow images or textual descriptions.

## Repository Map

```text
article/                 Paper source, bibliography, LNCS files, and PDF
article/tables/          CSV tables used by the paper
data/original/           Source evidence included in the repository
data/original/articles/  Canonical article registry; source PDFs are ignored
data/original/workflows/ Retrieved workflow artifacts and opening screenshots
data/processed/audit/    Structured article-audit data
data/processed/articles/ GROBID-derived semantic article HTML and TEI XML
data/processed/openalex/ Processed OpenAlex bibliometric outputs
data/processed/knime_snapshots/
                         Processed KNIME repository-mining outputs
scripts/                 Data collection and table-generation scripts
Methods.md               Method notes
Deprecated.md            Notes on deprecated-node semantics
AGENTS.md                Detailed maintenance notes for future project updates
```

## Key Files

- `article/article.pdf`: current generated paper PDF.
- `article/article.tex`: main paper source.
- `data/processed/audit/old_article_assessments.json`: structured
  article audit.
- `data/original/articles/registry.bbl`: canonical registry for local source
  articles. Its `\bibitem{...}` keys correspond to source PDF stems; DOI-bearing
  records use full DOI-derived filesystem keys.
- `data/processed/articles/*.html`: semantic article HTML rendered from GROBID
  TEI XML.
- `data/processed/articles/grobid_tei/*.tei.xml`: GROBID TEI XML extracted
  from local article PDFs.
- `data/original/workflows/knime_downloadable_workflow_references.json`:
  workflow-link records, retrieval outcomes, and manual KNIME opening results.
- `article/tables/top_cited_article_audit_summary.csv`: article-audit summary
  table source.
- `article/tables/knime_use_workflow_reporting_signals.csv`: KNIME-use
  workflow-reporting table source.
- `data/processed/knime_snapshots/knime_node_snapshot_summary.csv`: summary of
  KNIME node metadata across source snapshots.

## Rebuilding

The repository includes a `Makefile` as a compact workflow index. It documents
the main scripts, parameters, and common rebuild targets:

```sh
make help
make audit-tables
make article
```

The paper uses Springer LNCS / S-LNCS formatting. The required LNCS class and
BibTeX style files are vendored in `article/`.

Build the PDF from the `article/` directory:

```sh
latexmk -pdf -interaction=nonstopmode article.tex
```

The main analysis scripts are in `scripts/`. Most use only the Python standard
library. Some collection steps require network access. Article extraction uses
GROBID for semantic TEI/HTML output.

For local articles, `data/original/articles/registry.bbl` is the source of
truth for article metadata and PDF identity. OpenAlex records are used as a
citation-ranked seed and provenance source, not as authority over local PDF
metadata when the registry is more specific.

Run GROBID locally before regenerating semantic article HTML:

```sh
docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
curl http://localhost:8070/api/isalive
make article-grobid-html-all
```

The most commonly regenerated outputs are:

```sh
python3 scripts/build_article_audit_tables.py --fail-on-mismatch
python3 scripts/build_knime_use_workflow_reporting_table.py --fail-on-mismatch
python3 scripts/build_knime_node_snapshot_summary.py
```

## Scope And Limits

- The workflow-opening experiment is a manual compatibility check over
  retrieved artifacts from the top-cited audit. It is not a population-level
  estimate of workflow failure rates.
- Repository-level deprecation statistics show KNIME source metadata evolution.
  They do not by themselves prove that published workflows fail.
- Data and code availability signals in the article audit mean that the paper
  reports such resources; they are not independent verification that every
  linked resource is still usable.
- New evidence should preserve the connection between claims, data files, and
  scripts.

## Reuse

When reusing this repository, cite the article and preserve the link between
claims, data, and scripts. If you extend the audit or add new workflow checks,
record enough metadata to show where the evidence came from and how it was
processed.
