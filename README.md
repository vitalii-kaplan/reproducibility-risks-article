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
- Cached reference-page evidence used to classify article-to-workflow links.

The paper is the main narrative. The data and scripts are included so the
claims can be inspected and updated.

## Audit Process

The canonical map of the article/workflow audit process is
`scripts/audit_script_chain.json`. It records the ordered steps, scripts,
inputs, outputs, handoff type, network requirements, and manual actions for the
current audit pipeline. Use it as the first file to inspect when checking how
the audit is produced or deciding where a new script belongs.

The `Makefile` is the executable wrapper around common steps from that chain.
It is useful for running targets, but `scripts/audit_script_chain.json` is the
main source of knowledge about the audit process.

## Current Findings

- An OpenAlex title-and-abstract search for `KNIME`, restricted to article
  records and collected on June 29, 2026, returned 963 article-type records.
- The expanded top-cited audit covers 100 KNIME-matching article records. Of
  these, 79 have local PDFs recorded in the compact audit report.
- In the 100-record audit, 75 records use KNIME as a workflow, tool, interface,
  or implementation context.
- Twenty-two records report downloadable or linked KNIME workflow files.
  Workflow artifacts or workflow directories were obtained for 18 article
  records.
- The current workflow-link discovery process uses reference-page content
  analysis: article URLs are collected from GROBID HTML/TEI, fetched and cached,
  then classified from the locally stored target pages. This gave clearer
  article-to-workflow evidence than article-text-only LLM analysis.
- Workflows from all 18 obtained article records opened in the local KNIME
  environment used for the manual check. Five article records had at least one
  workflow execute successfully: PAINS, Webinar Pricing Analytics, ImageJ
  ecosystem integration, high-content organelle trafficking, and GediNET.
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
- `data/processed/audit/article_url_collection.json`: article metadata,
  normalized referenced URLs, and URL fetch metadata.
- `data/processed/audit/article_reference_llm_classifications.json`: LLM
  classification of cached reference pages for KNIME workflow obtainability.
- `data/processed/audit/article_supplementary_llm_flags.json`: optional
  article-level LLM flags for KNIME use, version reporting, workflow figures,
  data/code availability, and dependency reporting.
- `data/original/workflows/knime_downloadable_workflow_references.json`:
  workflow-link records, retrieval outcomes, and manual KNIME opening results.
- `article/tables/top_cited_article_audit_summary.csv`: article-audit summary
  table source.
- `article/tables/knime_use_workflow_reporting_signals.csv`: KNIME-use
  workflow-reporting table source.
- `data/processed/knime_snapshots/knime_node_snapshot_summary.csv`: summary of
  KNIME node metadata across source snapshots.

## Rebuilding

The repository includes a `Makefile` as a compact execution wrapper. It
documents the main runnable targets and common parameters, while
`scripts/audit_script_chain.json` documents the full audit-process sequence:

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

For workflow-link discovery, the current preferred evidence path is reference
page analysis rather than article-text-only classification: collect URLs from
processed article HTML/TEI, fetch and cache those pages, attach fetch metadata,
then classify the locally stored reference-page content for whether it provides
or points to an obtainable KNIME workflow.

The supplementary article-level flag step uses the article text plus the
reference-page classifications to fill additional analysis fields. These flags
are useful for descriptive statistics, but workflow obtainability should still
be grounded first in the reference-page evidence.

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
