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
data/original/           Source evidence included in the replication package
data/processed/          Derived datasets and analysis outputs
scripts/                 Data collection, audit, and table-generation scripts
Methods.md               Method notes
Deprecated.md            Notes on deprecated-node semantics
AGENTS.md                Detailed maintenance notes for future project updates
```

## Audit Process

The canonical map of the article/workflow audit process is
`scripts/audit_script_chain.json`. It records the ordered steps, scripts,
inputs, outputs, handoff type, network requirements, and manual actions for the
current audit pipeline. The `Makefile` provides common runnable targets, but
`scripts/audit_script_chain.json` is the best starting point for understanding
how the audit is produced.

The current workflow-link discovery process uses reference-page content
analysis: article URLs are collected from processed article HTML/TEI, fetched
and cached, then classified from the locally stored target pages. This gave
clearer article-to-workflow evidence than article-text-only LLM analysis.

## Rebuilding

The main convenience targets are:

```sh
make help
make audit-tables
make article
```

The paper uses Springer LNCS / S-LNCS formatting. Build the PDF from the
`article/` directory:

```sh
latexmk -pdf -interaction=nonstopmode article.tex
```

Some collection steps require network access, institutional article access, or
manual workflow download checks. Those manual boundaries are documented in
`scripts/audit_script_chain.json`.

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
