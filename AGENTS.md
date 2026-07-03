# AGENTS.md

## Project

This repository is for preparing an ICECCS 2026 short paper on how published
studies report KNIME workflows and how KNIME source evolution, especially node
deprecation, can affect long-term workflow reproducibility.

Target venue: The 30th International Conference on Engineering of Complex Computer Systems (ICECCS 2026), Brisbane, Australia, 23-24 November 2026.

Paper type: Short paper, 11 pages including references, formatted using Springer
LNCS / S-LNCS.

Conference page: https://formal-analysis.com/iceccs/2026/

## Current Article Location And Formatting

The active article source is in `article/`:

- main source: `article/article.tex`
- BibTeX database: `article/references.bib`
- generated bibliography: `article/article.bbl`
- generated PDF: `article/article.pdf`
- journal-shippable figures: `article/figs/`

The article uses Springer LNCS / S-LNCS formatting:

```tex
\documentclass[runningheads]{llncs}
\bibliographystyle{splncs04}
```

The repository vendors the Springer LNCS files downloaded from CTAN on
July 1, 2026:

- `article/llncs.cls` -- Springer `llncs` class, v2.26, dated 2025-02-25
- `article/splncs04.bst` -- Springer LNCS BibTeX style
- `article/llncsdoc.pdf` -- Springer LNCS class documentation
- `article/llncs-README.md` -- bundle readme

Download source:

```text
https://mirrors.ctan.org/macros/latex/contrib/llncs.zip
```

Build from the `article/` directory:

```sh
latexmk -pdf -interaction=nonstopmode article.tex
```

Current author metadata in the article:

- author: Vitalii Kaplan
- ORCID: `0009-0009-8181-2863`
- email: `2333275007@alu.istinye.edu.tr`

Do not invent an affiliation. If a full affiliation is supplied later, update
the `\institute{...}` block in `article/article.tex`.

## Research Thesis

KNIME is open-source and widely used in scientific workflows, but the
reproducibility value of a published KNIME-based study depends on more than a
workflow diagram or a platform mention. Authors need to publish executable
workflow artifacts, version information, data, and extension context. At the
same time, KNIME evolves: nodes can become deprecated, hidden, migrated,
removed, or dependent on third-party extensions that are difficult to recover.
The current paper investigates this claim using OpenAlex bibliometrics, manual
assessment of the 20 most-cited KNIME-matching article records, one
current-KNIME import experiment for the PAINS workflows, and longitudinal
repository mining of KNIME node metadata.

## Core Research Questions

1. How visible is KNIME in the scientific literature?
2. Do influential KNIME-matching papers publish executable workflow artifacts,
   or do they mainly report workflows through text and figures?
3. When a published KNIME workflow artifact is available, can it still be
   imported and executed in a current KNIME version without special effort?
4. How has KNIME node deprecation evolved over time in the source repository
   metadata?
5. How do publication practices and source-code evolution together create
   reproducibility risks for older KNIME-based studies?

## Expected Evidence Sources

- OpenAlex search results for publications matching "KNIME".
- KNIME source repositories and release history.
- Highly cited KNIME-related papers from OpenAlex.
- Public workflow artifacts linked from papers, repositories, supplements, or KNIME Hub.
- Manual PAINS workflow import results from the author's current KNIME
  environment.
- k2pweb.org workflow usage logs or request records, if available, are future
  evidence rather than part of the current article's empirical core.

## Working Rules

- The user has said the preprint is ready. Do not change `article/article.tex`,
  `article/references.bib`, `article/article.bbl`, figures, or generated PDF
  unless the user explicitly asks for article changes.
- Do not invent statistics, counts, citations, paper metadata, workflow availability, or execution results.
- Mark preliminary numbers clearly as provisional until the data collection scripts and raw data are present.
- Preserve raw data, scripts, and derived tables separately.
- Prefer reproducible scripts over manual spreadsheet edits.
- Keep paper claims traceable to a source, dataset, script, or explicit manual assessment note.
- When assessing a paper, record both the evidence and the absence of evidence, for example whether the paper mentions a KNIME version or provides a downloadable workflow.
- Keep writing concise and suitable for an 11-page LNCS short paper.

## Suggested Repository Layout

```text
.
|-- README.md
|-- AGENTS.md
|-- paper/
|   |-- main.tex
|   |-- references.bib
|   `-- sections/
|-- data/
|   |-- raw/
|   |-- interim/
|   `-- processed/
|-- scripts/
|-- notebooks/
|-- results/
|   |-- figures/
|   `-- tables/
`-- notes/
```

Create directories only when they are needed. Keep generated files out of version control if they are large or can be reproduced.

## Writing Style

- Use direct, careful academic prose.
- Prefer precise claims over broad language such as "many", "often", or "significant" unless quantified.
- Distinguish between reproducibility, repeatability, executability, artifact availability, and workflow compatibility.
- Avoid overstating the conclusion. The likely contribution is an empirical characterization of reproducibility risks, not a claim that KNIME workflows are generally unreproducible.
- Frame KNIME fairly: the issue is long-term workflow compatibility in an evolving open-source ecosystem, not a criticism of open source itself.

## Data And Analysis Notes

- OpenAlex data should include query date, API endpoint or snapshot version, query parameters, and any filters.
- KNIME repository analysis should record repository URLs, commit ranges, tags, and the exact method used to identify deprecated nodes.
- The KNIME repository-mining method is documented in `Methods.md`;
  deprecated-node semantics and paper TODOs are documented in `Deprecated.md`.
- The current OpenAlex query uses title-and-abstract search for `KNIME` and
  `type:article`, collected on June 29, 2026. The processed result contains
  963 article-type records.
- The top-cited article audit uses the 20 most-cited records from the processed
  OpenAlex result. Eighteen records were assessed from full text; two were not
  available at the time of assessment.
- The top-cited article assessment file
  `data/processed/audit/knime_most_cited_article_assessments.json` now has
  an explicit `article_audit_fields` block for each record. The block is split
  into `description_audit_fields` for traceability and `flag_audit_fields` for
  statistics, with `article_audit_schema` and `article_audit_summary_counts` at
  the top level. Use `flag_audit_fields` for article-level workflow-presentation
  statistics before reinterpreting prose notes.
- The audit questions and field definitions are recorded in
  `data/processed/audit/knime_article_audit_questions.json`. Keep this file
  synchronized when adding, removing, renaming, or changing the meaning of any
  article-audit field.
- The article-audit fields cover article identifier, title, year, venue, DOI or
  URL, full-text accessibility, simplified KNIME article relation
  (`about_knime`, `uses_knime`, `not_a_knime_use_case`, or `not_assessed`), the
  `uses_knime` presence flag, KNIME version reporting, downloadable
  workflow-file availability, workflow screenshot or figure presentation, input
  data, code/scripts, whether the article describes workflow steps, nodes,
  modules, or components in text, extension or plugin dependency information,
  extension installation/source information, linked-workflow retrievability, and
  evidence notes.
- `flag_audit_fields` must contain only presence flags. A `true` value means
  the item or category is present in the current evidence; a `false` value means
  absent, unsupported, not applicable, not assessed, or not verified. Do not add
  flags whose true value means `no`, `not_applicable`, `not_assessed`, or
  `unclear`; preserve those labels in `description_audit_fields`.
- Records with `description_audit_fields.knime_article_relation` equal to
  `about_knime` are background/platform papers, not deeper workflow-reporting
  audit cases. Keep their descriptive metadata, but leave `flag_audit_fields`
  and `flag_audit_support` empty so they do not enter workflow-reporting
  statistics.
- Detailed KNIME presentation categories are not represented as flag fields.
  Use `description_audit_fields.knime_article_relation` for the simplified
  relation and `flag_audit_fields.uses_knime` for statistics. Workflow-artifact
  presentation is represented by direct presence flags for downloadable
  workflows, screenshots/figures, and text descriptions.
- The `flag_audit_support` object maps each `true` flag to citation objects
  with `extracted_text_lines` and `note`, following the same shape as
  article-level `evidence` entries. The line references point to generated
  `pdftotext -layout` text files under `data/processed/articles/`, not to
  intrinsic PDF line numbers. Reuse extracted-text line references where
  available; use source labels such as `linked_resources`, `local_pdf`,
  `article_audit_fields`, or `manual_assessment` for resource values and
  manual classification notes.
  False flags intentionally have no support entry. Keep it in sync when
  changing any flag value.
- The current `article_audit_fields` values were derived from existing manual
  notes and the OpenAlex top-cited CSV without rereading the article full
  texts. Do not silently upgrade `not_checked_in_this_pass`, `unclear`, or
  `reported_without_direct_url` values to stronger claims unless new evidence
  is recorded.
- Processed article text extracted from local PDFs belongs under
  `data/processed/articles/`, one text file per article/PDF. This directory is
  ignored by Git because it is generated; use `scripts/extract_article_texts.py`
  to regenerate it and keep the extraction manifest under `data/processed/audit/`.
- The empirical expansion priority is to increase the scale of article and
  workflow evidence, not to restart the paper. Continue assessing
  KNIME-related article records beyond the top-20 sample as time allows, and
  use only the number actually completed by the deadline.
- For every retrievable KNIME workflow found during article assessment, record
  the source article, workflow source URL, retrieval date, package or file name,
  available workflow metadata, node identifiers or factory classes where
  extractable, deprecated nodes, legacy nodes, missing nodes, unresolved
  extension dependencies, import outcome in current KNIME, and execution outcome
  when execution is feasible.
- Keep workflow-level failure categories distinct: import failure,
  extension-resolution failure, data-missing failure, configuration failure,
  and execution failure should not be collapsed into a single failure label.
- Article-level statistics should include counts and percentages for assessed
  records, full-text accessibility, KNIME-use articles, KNIME version reporting,
  downloadable workflow files, workflow screenshots or text descriptions, input
  data, code/scripts, and extension or plugin information.
- Workflow-level statistics should include the number of retrieved workflows,
  importable workflows, executable workflows where feasible, workflows with
  deprecated nodes, legacy nodes, missing nodes, unresolved extensions, and the
  distribution of deprecated-node counts per workflow.
- Formal statistical tests are optional and should be added only if the
  collected sample size supports them. Prefer simple, defensible counts,
  percentages, and distributions over underpowered tests.
- Frame the expanded work as a reproducibility-risk audit method for visual
  workflow studies: collect bibliometric records, assess publication-level
  preservation signals, retrieve workflow artifacts, extract node metadata,
  compare nodes with platform compatibility metadata, and classify risks from
  missing artifacts, missing versions, unresolved extensions, deprecated nodes,
  and failed imports or executions.
- Do not prioritize a cross-platform comparison before the deadline unless it
  becomes systematic and evidence-backed. A shallow comparison with Galaxy,
  Weka, RapidMiner, Orange, Taverna, or similar systems would weaken the paper;
  the stronger near-term contribution is a deeper KNIME workflow corpus with
  quantitative node-level compatibility analysis.
- In the current assessment, PAINS is the only non-KNIME-focused top-cited case
  with retrievable KNIME workflow files suitable for a current-KNIME import
  experiment.
- The PAINS figures used in the article have been copied to `article/figs/`.
  The article should use these copies, not files from `data/manual/`, so that
  the journal submission package is self-contained.
- The final bibliography pass checked DOI-bearing entries in `article.bbl`
  against DOI registry resolution and Crossref metadata where available. The
  applied metadata corrections are:
  - Walker et al. provenance paper: `Aiden Slingsby`
  - JSS test-flakiness review: author order starts with `Amjed Tahir` and
    `Shawn Rasheed`
  - PAINS paper: issue `30(10)`, pages `847--850`
- The same three metadata corrections were copied to
  `/Users/vitaly/Home/harbour/projects/2026-06-LR-k2p/publications.json`.
- URL-only project and documentation references, including `knime2py`,
  `k2pweb.org`, and KNIME documentation/schema URLs, do not have DOI records.
  `Priem2022OpenAlex` resolves through the arXiv DOI
  `10.48550/arXiv.2205.01833`; it is not a Crossref journal article record.
- The current local `knime-oss` clone contains 91 immediate Git repositories, but date-based mining processes 90 non-hidden immediate repositories. The hidden `.github` repository is excluded as organization metadata. The exact repository list is recorded in `data/processed/knime_snapshots/knime_oss_repositories.csv`.
- Use `scripts/collect_knime_node_snapshot.py` as the canonical KNIME source extractor. Older count-only scripts are obsolete because the study needs per-node records and cross-snapshot transitions, not only aggregate deprecated-node counts.
- For KNIME source mining, parse structured XML rather than grepping strings. Treat only case-insensitive `deprecated="true"` as a deprecation marker, and keep `hidden="true"` separate from deprecation.
- Exclude generated/build and repository-control directories during source walks, especially `.git`, `target`, `bin`, and `.metadata`.
- Keep snapshot-specific outputs self-contained under `data/original/knime_snapshots/<snapshot-date>/`, including the checkout manifest, `plugin_nodes.csv`, `node_descriptions.csv`, `factory_class_mappers.csv`, `migration_rules.csv`, and `summary.csv`.
- Treat `data/processed/knime_snapshots/knime_node_snapshot_summary.csv` as a derived cross-snapshot table. The authoritative evidence is the per-record snapshot data.
- Transition columns in `data/processed/knime_snapshots/knime_node_snapshot_summary.csv` compare adjacent chronological snapshots. The node identity key is `factory_class` when present; otherwise it falls back to `plugin_xml:element:category_path`. Treat these transition counts as metadata-level approximations.
- Current date-based snapshots cover 2018-04-03, 2019-01-01, 2019-12-05, 2020-01-01, 2021-01-01, 2022-01-01, 2023-01-01, 2023-02-22, 2024-01-01, 2025-01-01, 2026-01-01, 2026-03-03, and 2026-06-28.
- Key current repository-mining result: the 2026-06-28 local source-date snapshot has 1506 registered ordinary nodes and 502 deprecated ordinary nodes, or 33.33%. Use this as repository-level evidence only; do not infer workflow execution failure without workflow-level testing.
- The local `knime-product` repository has `analytics-platform/*` product tags starting at `analytics-platform/3.5.3`, dated 2018-04-03. Treat KNIME Analytics Platform 3.5.3 as the current earliest source-code baseline for longitudinal tag-based analysis. Do not claim source-code results for versions earlier than 3.5.3 unless a separate archive or repository source is added and documented.
- Major-version anchors from the local product tags are:
  - KNIME Analytics Platform 3.5.3, 2018-04-03, tag `analytics-platform/3.5.3`
  - KNIME Analytics Platform 4.1.0, 2019-12-05, tag `analytics-platform/4.1.0`
  - KNIME Analytics Platform 5.0.0, 2023-02-22, tag `analytics-platform/5.0.0`
  - KNIME Analytics Platform 5.11.0, 2026-03-03, tag `analytics-platform/5.11.0`
- Next repository-mining tasks are to build a node-level lifecycle table, link deprecated nodes to `NodeFactoryClassMapper` and `NodeMigrationRule` evidence, and manually validate a sample of deprecated, hidden, removed, migrated, and inconsistent records.
- k2pweb.org usage statistics should be anonymized and aggregated. Do not
  commit private logs. Treat k2pweb as a possible extension of this study, not
  as evidence already used in the current article unless new aggregate data are
  added.
- Case-study reproduction attempts should record environment details: operating system, KNIME version, extension installation steps, workflow source URL, errors, and outcome.
- For each selected paper, maintain a structured assessment with fields such as:
  - article identifier, title, year, venue, DOI or URL
  - full-text accessibility
  - KNIME article relation: about KNIME, uses KNIME, not a KNIME use case, or
    not assessed
  - whether the article uses KNIME
  - KNIME version reporting
  - downloadable KNIME workflow-file availability
  - workflow screenshot or figure presentation
  - workflow, node, module, or component description in text
  - input-data availability
  - code/script availability
  - extension or plugin dependency information
  - extension installation/source information
  - linked workflow artifact retrievability
  - current KNIME import result, when workflow-level testing is performed
  - current KNIME execution result, when workflow-level testing is performed
  - deprecated nodes observed, when workflow-level inspection is performed
  - notes and evidence links

## Verification

Before finalizing paper claims, rerun the data collection and analysis scripts from a clean checkout where practical. Record any steps that require private data, manual access, or non-reproducible web resources.

## Move-To-GitHub Checklist

When moving this project to a separate GitHub directory, keep these files and
directories together:

- `article/article.tex`, `article/references.bib`, and `article/article.bbl`
- `article/figs/`
- `article/llncs.cls` and `article/splncs04.bst`
- `data/processed/`
- `data/original/` when raw evidence is intended to be part of the replication
  package
- `scripts/`
- `Methods.md`, `Deprecated.md`, `README.md`, and `AGENTS.md`

Do not commit private k2pweb.org logs. If usage evidence is later added, commit
only anonymized aggregate outputs and document the aggregation method.
