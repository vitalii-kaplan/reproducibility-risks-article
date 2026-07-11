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
The current paper investigates this claim using OpenAlex bibliometrics, a
100-record expanded top-cited article audit registry with not-assessed
placeholders for records without local full text, current-KNIME opening and
execution attempts for retrievable workflows, and longitudinal repository mining
of KNIME node metadata.

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
- Manual current-KNIME opening and execution results for retrievable workflow
  artifacts from the top-cited article audit.
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
- Keep `Makefile` as the project workflow index. It should document every
  script target, important parameters, and whether a target requires network
  access or an external local KNIME source clone.
- Keep paper claims traceable to a source, dataset, script, or explicit manual assessment note.
- When assessing a paper, record both the evidence and the absence of evidence, for example whether the paper mentions a KNIME version or provides a downloadable workflow.
- Keep writing concise and suitable for an 11-page LNCS short paper.
- Keep `README.md` as a public GitHub front page for readers: current high-level
  findings, repository map, key files, rebuild basics, and scope limits. Do not
  move detailed internal audit rules, raw extraction details, or agent workflow
  notes from `AGENTS.md` into `README.md`.

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
- `data/processed/openalex/openalex_knime_most_cited.csv` is the
  citation-ranked seed table for the expanded audit and currently contains the
  top 100 OpenAlex records by citation count. It is generated by
  `scripts/build_openalex_knime_bibliometrics.py` with
  `--most-cited-limit 100`, exposed in the `Makefile` as
  `OPENALEX_MOST_CITED_LIMIT`.
- `data/original/articles/registry.bbl` is the canonical registry for local
  source article PDFs. Its `\bibitem{...}` keys are source PDF stems without
  `.pdf`; DOI-bearing PDFs use full normalized DOI-derived filesystem keys, and
  no-DOI PDFs use curated stable keys. Use this registry as the source of truth
  for local article title, authors, year, venue/proceedings, DOI, and PDF
  identity.
- Do not guess, infer, or invent article DOI, title, authors, year, venue, or
  source identity. If a value is absent from the registry, DOI metadata, source
  PDF front matter, or another explicit source, mark it unknown or unverified.
  OpenAlex records are seed/provenance records and can disagree with local
  PDFs; do not silently overwrite registry metadata from OpenAlex.
- Treat DOI as an indivisible primary key. Scripts and heuristics must not
  match articles by DOI suffix, DOI tail, compacted DOI fragments, path
  fragments, or partial DOI strings. For local article matching, use the full
  normalized DOI-derived registry key or an explicit no-DOI registry key only.
- The top-cited article audit registry now contains 100 records, including all
  records from citation ranks 1-100. Eighty-two records currently have local
  PDFs or full text and processed GROBID HTML; eighteen records are retained as
  not-assessed placeholders because no local full text is available.
- Current local article retrieval for ranks 41-60 is recorded in
  `data/processed/audit/logs/article_download_attempts_41-60.csv`: 14 of 20
  records have local PDFs, including one user-provided record without DOI. The
  six records still not downloaded in that rank range are ranks 47, 48, 49, 50,
  56, and 60 in the current OpenAlex top-60 order.
- Current local article retrieval for ranks 61-80 is recorded in
  `data/processed/audit/logs/article_download_attempts_61-80.csv`. Fifteen of
  those 20 records currently have local PDFs or full text; ranks 67, 72, 74,
  76, and 79 are retained as not-assessed placeholders in the expanded
  audit.
- The top-cited article assessment file
  `data/processed/audit/old_article_assessments.json` now has
  an explicit `article_audit_fields` block for each record. The block is split
  into `description_audit_fields` for traceability and `flag_audit_fields` for
  statistics, with `article_audit_schema` and `article_audit_summary_counts` at
  the top level. Use `flag_audit_fields` for article-level workflow-presentation
  statistics before reinterpreting prose notes.
- The creation process for
  `data/processed/audit/old_article_assessments.json` is now
  described in the Methods subsection "Top-Cited Article Assessment" in
  `article/article.tex`. Keep that method description synchronized with the
  audit JSON, `knime_article_audit_questions.json`, and the support-refresh
  script.
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
- The `flag_audit_support` object maps each `true` flag to citation objects.
  Article-text support should include `extracted_text_lines`, `quote`,
  `article_section`, and `note`. The `quote` field is direct wording from the
  extracted article text; `note` is the audit explanation. The line references
  point to processed article files under `data/processed/articles/`, not to
  intrinsic PDF line numbers. Current processed article files are GROBID HTML.
  Reuse extracted-text line references where available; use source labels such
  as `linked_resources`, `local_pdf`, `article_audit_fields`, or
  `manual_assessment` for resource values and manual classification notes.
  False flags intentionally have no support entry. Keep it in sync when
  changing any flag value.
- For article-text flags, a `true` value requires direct quote support. After
  finding a candidate quote, check whether the quote actually supports the flag
  and answers the corresponding question in
  `data/processed/audit/knime_article_audit_questions.json`. If it does not,
  find another quote. If more than five candidates fail and no supporting quote
  is found, set the flag to `false`. Do not keep keyword-only support that does
  not make the claim true.
- Use `scripts/refresh_article_audit_support.py` as the provenance/support
  refresher for the top-cited article audit. It rebuilds candidate flags from
  `description_audit_fields`, searches the processed one-column article text,
  records direct quotes and section names, rejects invalid quote support, and
  removes positive article-text flags that have no valid quote. Treat it as a
  support/provenance updater, not as a substitute for human assessment.
- As of the current quote-validated audit, every remaining `true` article-text
  flag has at least one direct quote in `flag_audit_support`; false flags have
  no support entry. Do not manually add a `true` article-text flag without
  adding a quote-backed support object.
- Do not silently upgrade `not_checked_in_this_pass`, `unclear`, or
  `reported_without_direct_url` values to stronger claims unless new evidence
  is recorded and the relevant quote support is added.
- Processed article text is GROBID-derived semantic HTML under
  `data/processed/articles/*.html`, with source TEI XML under
  `data/processed/articles/grobid_tei/*.tei.xml`. Generate these files with
  `scripts/extract_article_grobid_html.py` or `make article-grobid-html-all`
  after starting a local GROBID service:
  `docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf`.
  The manifest is
  `data/processed/audit/logs/article_grobid_html_manifest.csv`.
- The parser comparison and rationale are recorded in
  `PDF_parser_comparison.md`. The 83-file GROBID run produced 83 HTML files,
  83 TEI XML files, and no failed records.
- Current article-to-workflow discovery should use reference-page content
  analysis as the preferred evidence path. Article text is useful for context,
  but the strongest signal for whether a reader can obtain a workflow is often
  the target of the article's links: KNIME Hub pages, myExperiment pages,
  GitHub repositories, publisher supplements, datasets, code repositories, or
  dead/blocked URLs.
- The current reference-page chain is:
  `scripts/collect_article_urls.py` ->
  `scripts/fetch_article_url_pages.py` ->
  `scripts/attach_url_fetch_metadata.py` ->
  `scripts/browser_fetch_403_urls.py` when needed ->
  `scripts/classify_article_references_with_llm.py`.
  The main intermediate/output files are
  `data/processed/audit/article_url_collection.json`,
  `data/processed/audit/pages/`,
  `data/processed/audit/browser_pages/`, and
  `data/processed/audit/article_reference_llm_classifications.json`.
- Treat `data/processed/audit/article_reference_llm_classifications.json` as
  the current best machine-generated evidence for article-to-workflow
  relations. Interpret `workflow_landing_page_available`,
  `direct_workflow_available`, and `possible_workflow_requires_inspection` as
  stronger URL-level evidence than `manual_check_required`; manually review
  `manual_check_required` before counting it as confirmed workflow
  availability.
- The older article-text and candidate-assessment scripts are retained only as
  reference material and are prefixed with `old_`:
  `scripts/old_audit_assessments_deterministic.py`,
  `scripts/old_audit_assessments_llm_url.py`, and
  `scripts/old_audit_assessments_llm_flag.py`. Do not use them as the active
  article-to-workflow discovery path unless explicitly restoring the old
  workflow for comparison.
- The empirical expansion priority is now lower than formalizing the framework,
  evidence model, and score dimensions. Continue assessing KNIME-related article
  records beyond the current 100-record audit registry only if time allows, and
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
- Use `scripts/build_article_audit_tables.py` to generate the Table 3 CSV
  source from `flag_audit_fields` and relation fields. The generated CSVs live
  under `article/tables/`: `top_cited_article_audit_summary.csv`. Comparison
  and summary-check outputs live under `article/tables/logs/`:
  `article_audit_table_comparison.csv` and
  `article_audit_summary_count_check.csv`. Run
  `python3 scripts/build_article_audit_tables.py --fail-on-mismatch` after
  changing the audit JSON or Table 3.
- Use `scripts/build_knime_use_workflow_reporting_table.py` to generate the
  Table 4 CSV source, `knime_use_workflow_reporting_signals.csv`, from
  `top_cited_article_audit_summary.csv` and
  `data/processed/audit/old_article_assessments.json`. The
  "Articles with successfully downloaded workflows" row is a workflow-retrieval
  outcome read
  from
  `data/original/workflows/knime_downloadable_workflow_references.json`,
  specifically
  `summary_counts.downloaded_with_workflow_files_or_workflow_directory`. The
  script also writes
  `article/tables/logs/knime_use_workflow_reporting_table_comparison.csv`. Run
  `python3 scripts/build_knime_use_workflow_reporting_table.py --fail-on-mismatch`
  after changing Table 3, Table 4, the audit JSON, or the workflow inventory.
- Generated logs, manifests, download-attempt files, and table comparison/check
  outputs belong in a `logs/` subdirectory of the corresponding evidence or
  output directory. Current examples are `data/processed/audit/logs/`,
  `article/tables/logs/`, per-snapshot
  `data/original/knime_snapshots/<snapshot-date>/logs/`, and per-workflow
  `data/original/workflows/<doi-safe-directory>/logs/` for HTTP header traces.
- Current 100-record structured audit counts in
  `data/processed/audit/old_article_assessments.json` are:
  - expanded audit records: 100
  - local full text available: 82
  - not assessed from full text: 18
  - about KNIME: 8
  - not a KNIME use case: 7
  - uses KNIME: 67
  - workflow or nodes described in text: 59
  - workflow screenshots or figures: 37
  - reports KNIME version: 18
  - downloadable KNIME workflow files: 28
  - articles with successfully downloaded workflows or workflow directories: 12
  - extension/plugin dependencies reported: 30
  - extension installation source reported: 19
  - code or scripts reported: 17
  - reports input-data availability: 55
  - direct input-data resource: 23
  Keep these counts synchronized with `article/article.tex`,
  `article/tables/*.csv`, and
  `data/processed/audit/old_article_assessments.json` when the
  audit changes.
- Linked workflow artifact retrievability is tracked in the project workflow
  inventory rather than in Table 3 or Table 4. The current workflow inventory
  records 12 article records with obtained workflow artifacts or workflow
  directories.
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
- The current workflow-reference inventory under
  `data/processed/audit/knime_downloadable_workflow_references.json` covers 28
  article records with
  downloadable or linked KNIME workflow evidence. Workflow artifacts or workflow
  directories have been obtained for 12 article records. Workflows from all 12
  article records opened in the local KNIME environment. Four article records
  had at least one workflow execute successfully: PAINS, Webinar Pricing
  Analytics, ImageJ ecosystem integration, and high-content organelle
  trafficking. PAINS is counted once at article-record level even though
  separate RDKit and Indigo workflow archives exist. The other opened article
  records failed during execution, required missing R packages or extensions,
  or could not be confidently executed from the available workflow state.
- Manual workflow-opening screenshots are stored under
  `data/original/workflows/<doi-safe-directory>/opened/`. Do not restore the
  obsolete `data/manual/` or `article/figs/` PAINS-only figure copies unless the
  article again needs standalone figure files.
- The workflow reference inventory is
  `data/processed/audit/knime_downloadable_workflow_references.json`. It
  records the 28 article records with downloadable or linked KNIME workflow
  evidence, download outcomes, reasons for unavailable workflows, manual KNIME
  opening tests, and the summary that 12 article records yielded workflow
  artifacts or workflow directories, workflows from all 12 were opened in the
  manual subset, and four article records had at least one workflow execute
  successfully.
- The reader-facing `README.md` should summarize the current 100-record audit as
  82 records with local full text, 18 not assessed, 67 KNIME-use records, 28
  records reporting downloadable or linked workflows, 12 article records with
  obtained workflow artifacts or workflow directories, and four article records
  with at least one successfully executed workflow. Keep it concise and avoid
  exposing the full internal audit schema there.
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
- Keep snapshot-specific outputs self-contained under
  `data/original/knime_snapshots/<snapshot-date>/`, including checkout
  manifests under `logs/` and the per-snapshot `plugin_nodes.csv`,
  `node_descriptions.csv`, `factory_class_mappers.csv`, `migration_rules.csv`,
  and `summary.csv`.
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
- `article/llncs.cls` and `article/splncs04.bst`
- `data/processed/`
- `data/original/` when raw evidence is intended to be part of the replication
  package
- `scripts/`
- `Methods.md`, `Deprecated.md`, `README.md`, and `AGENTS.md`

Do not commit private k2pweb.org logs. If usage evidence is later added, commit
only anonymized aggregate outputs and document the aggregation method.
