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
OPENALEX_MOST_CITED_LIMIT ?= 100
OPENALEX_RAW_DIR ?= data/original/openalex
OPENALEX_WORKS ?= data/original/openalex/works.jsonl
OPENALEX_PROCESSED_DIR ?= data/processed/openalex

# Article PDF processing parameters.
ARTICLE_PDF_DIR ?= data/original/articles
ARTICLE_REGISTRY ?= data/original/articles/registry.bbl
ARTICLE_TEXT_DIR ?= data/processed/articles
ARTICLE_GROBID_TEI_DIR ?= data/processed/articles/grobid_tei
GROBID_URL ?= http://localhost:8070
AUDIT_LOG_DIR ?= data/processed/audit/logs
START ?= 61
END ?= 80
DOWNLOAD_TIMEOUT ?= 45

# Article-audit and table parameters.
ASSESSMENT ?= data/processed/audit/old_article_assessments.json
AUDIT_QUESTIONS ?= data/processed/audit/knime_article_audit_questions.json
WORKFLOW_REFERENCES ?= data/processed/audit/knime_downloadable_workflow_references.json
ARTICLE_TEX ?= article/article.tex
ARTICLE_TABLE_DIR ?= article/tables
FAIL_ON_MISMATCH ?= --fail-on-mismatch
LLM_MODE ?= off
LLM_MODEL ?= gpt-4.1-mini
LLM_TEMPERATURE ?= 0
LLM_ENV_FILE ?= .env
LLM_PROMPT ?= data/processed/audit/old_llm_support_validation_prompt.json
LLM_FLAG_ASSESSMENT_PROMPT ?= data/processed/audit/article_llm_flag_assessment_prompt.json
LLM_FLAG_ASSESSMENT_INPUT ?= $(LLM_URL_ASSESSMENT_OUTPUT)
LLM_FLAG_ASSESSMENT_OUTPUT ?= data/processed/audit/article_llm_flag_assessments.json
LLM_URL_ASSESSMENT_PROMPT ?= data/processed/audit/article_llm_url_prompts.json
LLM_URL_ASSESSMENT_OUTPUT ?= data/processed/audit/article_llm_url_assessments.json
DETERMINISTIC_ARTICLE_ASSESSMENT_OUTPUT ?= data/processed/audit/article_deterministic_assessments.json
DETERMINISTIC_LIMIT ?= 0
LLM_DECISION_LOG ?= data/processed/audit/logs/llm_support_validation_decisions.jsonl
LLM_APPLY_REJECTIONS ?=
RESET_FLAGS_FROM_DESCRIPTIONS ?=
APPLY_FLAG_REMOVALS ?=
LIMIT ?= 10
RANK ?=

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
	@printf '  ARTICLE_REGISTRY=%s               canonical local article registry\n' "$(ARTICLE_REGISTRY)"
	@printf '  FAIL_ON_MISMATCH=%s               pass empty to allow table mismatches\n' "$(FAIL_ON_MISMATCH)"
	@printf '  LLM_MODE=%s LLM_MODEL=%s          audit-support LLM mode/model\n' "$(LLM_MODE)" "$(LLM_MODEL)"
	@printf '  LLM_APPLY_REJECTIONS=%s           empty logs LLM decisions without applying rejections\n' "$(LLM_APPLY_REJECTIONS)"
	@printf '  APPLY_FLAG_REMOVALS=%s            empty preserves audited positive flags\n' "$(APPLY_FLAG_REMOVALS)"
	@printf '  LIMIT=%s RANK=%s                  optional LLM article-assessment subset\n' "$(LIMIT)" "$(RANK)"
	@printf '  GROBID_URL=%s                     local GROBID service URL\n' "$(GROBID_URL)"

.PHONY: all
all: openalex-bibliometrics article-grobid-html audit-tables knime-snapshot-summary article ## Rebuild local derived outputs that do not require network access.

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

.PHONY: article-grobid-html
article-grobid-html: ## Extract GROBID TEI and render semantic article HTML. Requires local GROBID service.
	$(PYTHON) scripts/extract_article_grobid_html.py \
	  --input-dir "$(ARTICLE_PDF_DIR)" \
	  --output-dir "$(ARTICLE_TEXT_DIR)" \
	  --tei-dir "$(ARTICLE_GROBID_TEI_DIR)" \
	  --manifest "$(AUDIT_LOG_DIR)/article_grobid_html_manifest.csv" \
	  --grobid-url "$(GROBID_URL)"

.PHONY: article-grobid-html-all
article-grobid-html-all: ## Regenerate all GROBID TEI and semantic article HTML. Requires local GROBID service.
	$(PYTHON) scripts/extract_article_grobid_html.py \
	  --input-dir "$(ARTICLE_PDF_DIR)" \
	  --output-dir "$(ARTICLE_TEXT_DIR)" \
	  --tei-dir "$(ARTICLE_GROBID_TEI_DIR)" \
	  --manifest "$(AUDIT_LOG_DIR)/article_grobid_html_manifest.csv" \
	  --grobid-url "$(GROBID_URL)" \
	  --all

.PHONY: article-grobid-html-from-tei
article-grobid-html-from-tei: ## Regenerate semantic article HTML from existing GROBID TEI files.
	$(PYTHON) scripts/extract_article_grobid_html.py \
	  --input-dir "$(ARTICLE_PDF_DIR)" \
	  --output-dir "$(ARTICLE_TEXT_DIR)" \
	  --tei-dir "$(ARTICLE_GROBID_TEI_DIR)" \
	  --manifest "$(AUDIT_LOG_DIR)/article_grobid_html_manifest.csv" \
	  --grobid-url "$(GROBID_URL)" \
	  --all \
	  --reuse-existing-tei

.PHONY: refresh-audit-support
refresh-audit-support: ## Refresh quote/provenance support in the structured article audit.
	$(PYTHON) scripts/refresh_article_audit_support.py \
	  --llm-mode "$(LLM_MODE)" \
	  --llm-model "$(LLM_MODEL)" \
	  --llm-temperature "$(LLM_TEMPERATURE)" \
	  --llm-env-file "$(LLM_ENV_FILE)" \
	  --llm-prompt "$(LLM_PROMPT)" \
	  --llm-decision-log "$(LLM_DECISION_LOG)" \
	  $(LLM_APPLY_REJECTIONS) \
	  $(RESET_FLAGS_FROM_DESCRIPTIONS) \
	  $(APPLY_FLAG_REMOVALS) \
	  --assessment "$(ASSESSMENT)" \
	  --questions "$(AUDIT_QUESTIONS)" \
	  --text-dir "$(ARTICLE_TEXT_DIR)"

.PHONY: deterministic-article-assessments
deterministic-article-assessments: ## Generate deterministic article_audit_fields candidates without network or LLM.
	$(PYTHON) scripts/audit_assessments_deterministic.py \
	  --seed-csv "$(OPENALEX_PROCESSED_DIR)/openalex_knime_most_cited.csv" \
	  --questions "$(AUDIT_QUESTIONS)" \
	  --text-dir "$(ARTICLE_TEXT_DIR)" \
	  --registry "$(ARTICLE_REGISTRY)" \
	  --workflow-references "$(WORKFLOW_REFERENCES)" \
	  --output "$(DETERMINISTIC_ARTICLE_ASSESSMENT_OUTPUT)" \
	  --limit "$(DETERMINISTIC_LIMIT)" \
	  $(if $(RANK),--rank "$(RANK)",)

.PHONY: llm-url-assessments
llm-url-assessments: ## Classify linked_resources URL types with LLM calls. Network access required.
	$(PYTHON) scripts/audit_assessments_llm_url.py \
	  --model "$(LLM_MODEL)" \
	  --temperature "$(LLM_TEMPERATURE)" \
	  --env-file "$(LLM_ENV_FILE)" \
	  --prompt "$(LLM_URL_ASSESSMENT_PROMPT)" \
	  --input-assessment "$(DETERMINISTIC_ARTICLE_ASSESSMENT_OUTPUT)" \
	  --text-dir "$(ARTICLE_TEXT_DIR)" \
	  --output "$(LLM_URL_ASSESSMENT_OUTPUT)" \
	  --limit "$(LIMIT)" \
	  $(if $(RANK),--rank "$(RANK)",)

.PHONY: llm-flag-assessments
llm-flag-assessments: ## Review/correct article_audit_fields flags with LLM calls. Network access required.
	$(PYTHON) scripts/audit_assessments_llm_flag.py \
	  --model "$(LLM_MODEL)" \
	  --temperature "$(LLM_TEMPERATURE)" \
	  --env-file "$(LLM_ENV_FILE)" \
	  --prompt "$(LLM_FLAG_ASSESSMENT_PROMPT)" \
	  --input-assessment "$(LLM_FLAG_ASSESSMENT_INPUT)" \
	  --questions "$(AUDIT_QUESTIONS)" \
	  --text-dir "$(ARTICLE_TEXT_DIR)" \
	  --output "$(LLM_FLAG_ASSESSMENT_OUTPUT)" \
	  --limit "$(LIMIT)" \
	  $(if $(RANK),--rank "$(RANK)",)

.PHONY: llm-article-assessments
llm-article-assessments: llm-flag-assessments ## Backward-compatible alias for llm-flag-assessments.

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
