# Reproducibility-risks project Makefile.
#
# This file is primarily documentation for the project workflow. Targets wrap
# the scripts in ./scripts and expose the main parameters as make variables.
#
# Examples:
#   make help
#   make article
#   make audit-tables
#   make download-rank-range START=61 END=80
#   make knime-snapshot KNIME_OSS_ROOT=../2026-06-knime-oss SNAPSHOT_DATE=2026-06-28
#
# Network-using targets are not dependencies of the default target.

.DEFAULT_GOAL := help

PYTHON ?= python3
SHELL := /bin/bash

# OpenAlex collection parameters.
OPENALEX_SEARCH ?= KNIME
OPENALEX_SEARCH_PARAM ?= search.title_and_abstract
OPENALEX_FILTER ?= type:article
OPENALEX_PER_PAGE ?= 200
OPENALEX_MAILTO ?=
OPENALEX_SLEEP ?= 0.2
OPENALEX_MAX_PAGES ?= 0
OPENALEX_MOST_CITED_LIMIT ?= 80
OPENALEX_RAW_DIR ?= data/original/openalex
OPENALEX_WORKS ?= data/original/openalex/works.jsonl
OPENALEX_PROCESSED_DIR ?= data/processed/openalex

# Article PDF/text processing parameters.
ARTICLE_PDF_DIR ?= data/original/articles
ARTICLE_TEXT_RAW_DIR ?= data/processed/articles/raw
ARTICLE_TEXT_DIR ?= data/processed/articles
AUDIT_LOG_DIR ?= data/processed/audit/logs
PDFTOTEXT ?= pdftotext
START ?= 61
END ?= 80
DOWNLOAD_TIMEOUT ?= 45

# Article-audit and table parameters.
ASSESSMENT ?= data/processed/audit/knime_most_cited_article_assessments.json
AUDIT_QUESTIONS ?= data/processed/audit/knime_article_audit_questions.json
WORKFLOW_REFERENCES ?= data/processed/audit/knime_downloadable_workflow_references.json
ARTICLE_TEX ?= article/article.tex
ARTICLE_TABLE_DIR ?= article/tables
FAIL_ON_MISMATCH ?= --fail-on-mismatch

# KNIME source-mining parameters. Override KNIME_OSS_ROOT for your local clone.
KNIME_OSS_ROOT ?= ../2026-06-knime-oss
SNAPSHOT_DATE ?= 2026-06-28
SNAPSHOT_ID ?= date-$(SNAPSHOT_DATE)
KNIME_SNAPSHOT_ROOT ?= data/original/knime_snapshots
KNIME_SNAPSHOT_OUT ?= $(KNIME_SNAPSHOT_ROOT)/$(SNAPSHOT_DATE)
KNIME_SNAPSHOT_SUMMARY ?= data/processed/knime_snapshots/knime_node_snapshot_summary.csv
SNAPSHOT_DATES ?= 2018-04-03 2019-01-01 2019-12-05 2020-01-01 2021-01-01 2022-01-01 2023-01-01 2023-02-22 2024-01-01 2025-01-01 2026-01-01 2026-03-03 2026-06-28

.PHONY: help
help: ## Show target descriptions and important parameters.
	@printf 'Project targets:\n'
	@awk 'BEGIN {FS = ":.*## "}; /^[A-Za-z0-9_.-]+:.*## / {printf "  %-34s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nCommon parameters:\n'
	@printf '  START=%s END=%s                         rank range for article download attempts\n' "$(START)" "$(END)"
	@printf '  SNAPSHOT_DATE=%s SNAPSHOT_ID=%s   KNIME source snapshot id/date\n' "$(SNAPSHOT_DATE)" "$(SNAPSHOT_ID)"
	@printf '  KNIME_OSS_ROOT=%s                 local knime-oss clone root\n' "$(KNIME_OSS_ROOT)"
	@printf '  OPENALEX_MAILTO=%s                optional email for OpenAlex polite pool\n' "$(OPENALEX_MAILTO)"
	@printf '  OPENALEX_MOST_CITED_LIMIT=%s      citation-ranked OpenAlex subset size\n' "$(OPENALEX_MOST_CITED_LIMIT)"
	@printf '  FAIL_ON_MISMATCH=%s               pass empty to allow table mismatches\n' "$(FAIL_ON_MISMATCH)"

.PHONY: all
all: openalex-bibliometrics article-texts audit-tables knime-snapshot-summary article ## Rebuild local derived outputs that do not require network access.

.PHONY: article
article: ## Build article/article.pdf with latexmk.
	cd article && latexmk -pdf -interaction=nonstopmode article.tex

.PHONY: article-force
article-force: ## Force rebuild article/article.pdf.
	cd article && latexmk -g -pdf -interaction=nonstopmode article.tex

.PHONY: openalex-collect
openalex-collect: ## Collect OpenAlex KNIME article records. Network access required. Params: OPENALEX_*.
	$(PYTHON) scripts/collect_openalex_knime_works.py \
	  --search "$(OPENALEX_SEARCH)" \
	  --search-param "$(OPENALEX_SEARCH_PARAM)" \
	  --filter "$(OPENALEX_FILTER)" \
	  --per-page "$(OPENALEX_PER_PAGE)" \
	  --mailto "$(OPENALEX_MAILTO)" \
	  --out-dir "$(OPENALEX_RAW_DIR)" \
	  --sleep "$(OPENALEX_SLEEP)" \
	  --max-pages "$(OPENALEX_MAX_PAGES)"

.PHONY: openalex-bibliometrics
openalex-bibliometrics: ## Build processed OpenAlex bibliometric CSV/JSON summaries.
	$(PYTHON) scripts/build_openalex_knime_bibliometrics.py \
	  --input "$(OPENALEX_WORKS)" \
	  --out-dir "$(OPENALEX_PROCESSED_DIR)" \
	  --most-cited-limit "$(OPENALEX_MOST_CITED_LIMIT)"

.PHONY: download-rank-range
download-rank-range: ## Try to download article PDFs for ranks START-END. Network access required.
	$(PYTHON) scripts/download_openalex_rank_range_articles.py \
	  --start "$(START)" \
	  --end "$(END)" \
	  --works "$(OPENALEX_WORKS)" \
	  --out-dir "$(ARTICLE_PDF_DIR)" \
	  --manifest-dir "$(AUDIT_LOG_DIR)" \
	  --timeout "$(DOWNLOAD_TIMEOUT)"

.PHONY: extract-texts
extract-texts: ## Extract raw article text for PDFs missing text output.
	$(PYTHON) scripts/extract_article_texts.py \
	  --input-dir "$(ARTICLE_PDF_DIR)" \
	  --output-dir "$(ARTICLE_TEXT_RAW_DIR)" \
	  --manifest "$(AUDIT_LOG_DIR)/article_text_extraction_manifest.csv" \
	  --pdftotext "$(PDFTOTEXT)"

.PHONY: extract-texts-all
extract-texts-all: ## Re-extract raw article text for all local PDFs.
	$(PYTHON) scripts/extract_article_texts.py \
	  --input-dir "$(ARTICLE_PDF_DIR)" \
	  --output-dir "$(ARTICLE_TEXT_RAW_DIR)" \
	  --manifest "$(AUDIT_LOG_DIR)/article_text_extraction_manifest.csv" \
	  --pdftotext "$(PDFTOTEXT)" \
	  --all

.PHONY: normalize-texts
normalize-texts: ## Normalize raw article text into one-column reading order where possible.
	$(PYTHON) scripts/normalize_article_text_columns.py \
	  --input-dir "$(ARTICLE_TEXT_RAW_DIR)" \
	  --output-dir "$(ARTICLE_TEXT_DIR)" \
	  --manifest "$(AUDIT_LOG_DIR)/article_text_column_normalization_manifest.csv"

.PHONY: normalize-texts-all
normalize-texts-all: ## Re-normalize all raw article text files.
	$(PYTHON) scripts/normalize_article_text_columns.py \
	  --input-dir "$(ARTICLE_TEXT_RAW_DIR)" \
	  --output-dir "$(ARTICLE_TEXT_DIR)" \
	  --manifest "$(AUDIT_LOG_DIR)/article_text_column_normalization_manifest.csv" \
	  --all

.PHONY: article-texts
article-texts: extract-texts normalize-texts ## Extract and normalize article text using incremental defaults.

.PHONY: refresh-audit-support
refresh-audit-support: ## Refresh quote/provenance support in the structured article audit.
	$(PYTHON) scripts/refresh_article_audit_support.py \
	  --assessment "$(ASSESSMENT)" \
	  --questions "$(AUDIT_QUESTIONS)" \
	  --text-dir "$(ARTICLE_TEXT_DIR)"

.PHONY: article-audit-tables
article-audit-tables: ## Build Table 3 CSV and comparison/check logs from the audit JSON.
	$(PYTHON) scripts/build_article_audit_tables.py \
	  --assessment "$(ASSESSMENT)" \
	  --article "$(ARTICLE_TEX)" \
	  --output-dir "$(ARTICLE_TABLE_DIR)" \
	  $(FAIL_ON_MISMATCH)

.PHONY: knime-use-table
knime-use-table: ## Build Table 4 CSV and comparison log from Table 3, audit JSON, and workflow inventory.
	$(PYTHON) scripts/build_knime_use_workflow_reporting_table.py \
	  --assessment "$(ASSESSMENT)" \
	  --workflow-references "$(WORKFLOW_REFERENCES)" \
	  --table3 "$(ARTICLE_TABLE_DIR)/top_cited_article_audit_summary.csv" \
	  --article "$(ARTICLE_TEX)" \
	  --output "$(ARTICLE_TABLE_DIR)/knime_use_workflow_reporting_signals.csv" \
	  --comparison "$(ARTICLE_TABLE_DIR)/logs/knime_use_workflow_reporting_table_comparison.csv" \
	  $(FAIL_ON_MISMATCH)

.PHONY: audit-tables
audit-tables: article-audit-tables knime-use-table ## Rebuild article audit Table 3 and KNIME-use Table 4 CSV sources.

.PHONY: clone-knime-oss
clone-knime-oss: ## Clone public knime-oss repositories into KNIME_OSS_ROOT. Network access required.
	scripts/clone_knime_oss_repos.sh "$(KNIME_OSS_ROOT)"

.PHONY: checkout-knime-snapshot
checkout-knime-snapshot: ## Checkout KNIME_OSS_ROOT repositories at SNAPSHOT_DATE and write a logs/ checkout manifest.
	scripts/checkout_knime_oss_by_date.sh \
	  "$(KNIME_OSS_ROOT)" \
	  "$(SNAPSHOT_DATE)" \
	  "$(KNIME_SNAPSHOT_OUT)/logs/checkout_$(SNAPSHOT_DATE).csv"

.PHONY: collect-knime-snapshot
collect-knime-snapshot: ## Extract node metadata from checked-out KNIME_OSS_ROOT into KNIME_SNAPSHOT_OUT.
	$(PYTHON) scripts/collect_knime_node_snapshot.py \
	  "$(KNIME_OSS_ROOT)" \
	  --snapshot-id "$(SNAPSHOT_ID)" \
	  --snapshot-date "$(SNAPSHOT_DATE)" \
	  --out-dir "$(KNIME_SNAPSHOT_OUT)"

.PHONY: knime-snapshot
knime-snapshot: checkout-knime-snapshot collect-knime-snapshot ## Checkout and extract one KNIME source snapshot. Params: SNAPSHOT_DATE, SNAPSHOT_ID, KNIME_OSS_ROOT.

.PHONY: knime-snapshots-all
knime-snapshots-all: ## Checkout and extract all SNAPSHOT_DATES from the same KNIME_OSS_ROOT clone.
	for date in $(SNAPSHOT_DATES); do \
	  $(MAKE) knime-snapshot SNAPSHOT_DATE="$$date" SNAPSHOT_ID="date-$$date" KNIME_OSS_ROOT="$(KNIME_OSS_ROOT)"; \
	done

.PHONY: knime-snapshot-summary
knime-snapshot-summary: ## Build processed cross-snapshot KNIME node summary.
	$(PYTHON) scripts/build_knime_node_snapshot_summary.py \
	  "$(KNIME_SNAPSHOT_ROOT)" \
	  --out "$(KNIME_SNAPSHOT_SUMMARY)"

.PHONY: check-json
check-json: ## Validate main JSON files parse.
	$(PYTHON) -m json.tool "$(ASSESSMENT)" >/dev/null
	$(PYTHON) -m json.tool "$(AUDIT_QUESTIONS)" >/dev/null
	$(PYTHON) -m json.tool "$(WORKFLOW_REFERENCES)" >/dev/null

.PHONY: check
check: check-json audit-tables knime-snapshot-summary article ## Run local consistency checks and rebuild article.
