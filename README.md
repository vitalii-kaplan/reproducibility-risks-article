# KNIME Workflows in Scientific Studies

This repository contains the source, data, and scripts for the article
**"KNIME Workflows in Scientific Studies: Publication Practices and
Reproducibility Risks"**.

The article studies how KNIME workflows are reported in scientific
publications, and how long-term reproducibility can be affected when workflow
artifacts, version information, data, and extension context are incomplete. It
uses KNIME as a case study because KNIME is an open-source visual workflow
platform with a long public development history and substantial visibility in
scientific literature.

The article itself is the source of truth for the current claims. This README
summarizes the project for repository visitors and points to the files needed
to inspect or rebuild the work.

## Main Findings

- An OpenAlex title-and-abstract search for `KNIME`, restricted to article
  records and collected on June 29, 2026, returned 963 article-type records.
- A manual assessment of the 20 most-cited KNIME-matching article records found
  that influential studies often report KNIME through figures, descriptions, or
  tool mentions rather than downloadable workflow artifacts.
- In the assessed set, the PAINS filters paper was the only non-KNIME-focused
  case with retrievable KNIME workflow files suitable for a current-KNIME import
  experiment.
- In the PAINS experiment, the RDKit workflow executed in KNIME Analytics
  Platform 5.8.3 LTS after extension installation, while the Indigo workflow
  was blocked by a missing third-party extension.
- Repository mining shows that deprecated ordinary nodes increased from 14.83%
  of registered ordinary nodes in the 2018 source baseline to 33.33% in the
  June 28, 2026 local source snapshot.

The article does **not** claim that KNIME workflows are generally
unreproducible. The claim is narrower: weak workflow preservation and evolving
node metadata create reproducibility risks, especially when papers preserve
only workflow images or textual descriptions.

## Repository Layout

```text
.
|-- article/
|   |-- article.tex
|   |-- references.bib
|   |-- article.bbl
|   |-- article.pdf
|   |-- figs/
|   |-- llncs.cls
|   `-- splncs04.bst
|-- data/
|   |-- original/
|   `-- processed/
|-- scripts/
|-- notes/
|-- Methods.md
|-- Deprecated.md
|-- README.md
`-- AGENTS.md
```

Key files:

- `article/article.tex`: article source.
- `article/references.bib`: BibTeX database.
- `article/article.bbl`: generated bibliography included for reproducible
  article builds.
- `article/article.pdf`: generated article PDF.
- `article/figs/`: figures used by the article.
- `data/processed/articles/knime_most_cited_article_assessments.json`: manual
  assessment of the top-cited records.
- `data/processed/knime_snapshots/knime_node_snapshot_summary.csv`: processed
  KNIME repository-mining summary.
- `data/processed/knime_snapshots/knime_oss_repositories.csv`: repository list
  used for KNIME source mining.
- `Methods.md`: repository-mining and data-collection method notes.
- `Deprecated.md`: notes on deprecated-node semantics and related article
  tasks.

## Building The Article

Build from the `article/` directory:

```sh
latexmk -pdf -interaction=nonstopmode article.tex
```

The article uses Springer LNCS / S-LNCS formatting:

```tex
\documentclass[runningheads]{llncs}
\bibliographystyle{splncs04}
```

The repository vendors the LNCS files used for the current build:

- `article/llncs.cls`: Springer `llncs` class, v2.26, dated 2025-02-25.
- `article/splncs04.bst`: Springer LNCS BibTeX style.
- `article/llncsdoc.pdf`: Springer LNCS class documentation.
- `article/llncs-README.md`: LNCS bundle readme.

These files were downloaded from:

```text
https://mirrors.ctan.org/macros/latex/contrib/llncs.zip
```

Current author metadata in `article/article.tex`:

- author: Vitalii Kaplan
- ORCID: `0009-0009-8181-2863`
- email: `2333275007@alu.istinye.edu.tr`

## Evidence Sources

The article combines four evidence streams:

1. OpenAlex bibliometrics for article records matching `KNIME` in title and
   abstract.
2. Manual assessment of the 20 most-cited KNIME-matching article records.
3. A current-KNIME import and execution experiment for the PAINS workflows.
4. Repository-level mining of KNIME node metadata across date-based source
   snapshots.

The PAINS case records the following reproduction-relevant context:

- article DOI: `10.1002/minf.201100076`
- reported KNIME version: 2.3.4
- RDKit nodes: 1.0.0.886
- Indigo nodes: 1.0.0.951
- current test environment: KNIME Analytics Platform 5.8.3 LTS

The PAINS figures used in the article are copied to `article/figs/` so the
article package does not depend on `data/manual/`.

## KNIME Repository Mining

The repository-mining analysis starts from the earliest locally available
KNIME Analytics Platform source-code baseline in the `knime-product` tag
history:

| Date | Version context | Registered ordinary nodes | Deprecated ordinary nodes | Deprecated share |
|---|---|---:|---:|---:|
| 2018-04-03 | KNIME Analytics Platform 3.5.3 source-date anchor | 1301 | 193 | 14.83% |
| 2019-12-05 | KNIME Analytics Platform 4.1.0 source-date anchor | 1191 | 227 | 19.06% |
| 2023-02-22 | KNIME Analytics Platform 5.0.0 source-date anchor | 1442 | 433 | 30.03% |
| 2026-03-03 | KNIME Analytics Platform 5.11.0 source-date anchor | 1503 | 503 | 33.47% |
| 2026-06-28 | Current local source-date snapshot | 1506 | 502 | 33.33% |

The source-mining scripts parse structured XML rather than grepping strings.
Only case-insensitive `deprecated="true"` on ordinary node registrations is
treated as a deprecation marker. Hidden nodes are tracked separately.

Important scripts:

- `scripts/checkout_knime_oss_by_date.sh`
- `scripts/collect_knime_node_snapshot.py`
- `scripts/build_knime_node_snapshot_summary.py`

Per-snapshot audit files are stored under
`data/original/knime_snapshots/<snapshot-date>/`. The processed cross-snapshot
summary is stored at
`data/processed/knime_snapshots/knime_node_snapshot_summary.csv`.

## Bibliography Notes

The final bibliography pass checked DOI-bearing entries in `article.bbl`
against DOI registry resolution and Crossref metadata where available.

## Scope And Limitations

- Repository-level deprecation statistics are evidence of source metadata
  evolution, not direct evidence that published workflows fail.
- The PAINS experiment is a single manual current-KNIME compatibility test, not
  a population-level workflow failure-rate estimate.
- The top-cited article assessment records both evidence and absence of
  evidence, such as whether workflow files, KNIME versions, data, code, or
  extension context were reported.
- k2pweb.org and `knime2py` are discussed only as possible future sources of
  workflow-level usage evidence. Private k2pweb.org logs are not part of this
  repository and should not be committed.

## Reuse

When reusing this repository, cite the article and preserve the connection
between claims, data, and scripts. If new workflow-level evidence or k2pweb.org
usage evidence is added later, use only anonymized aggregate outputs and
document the aggregation method.
