# GROBID Article Parser

This note records the current PDF parsing method for the KNIME article-audit
pipeline.

The project now uses GROBID as the only article parser for processed article
text. Local article PDFs are submitted to a local GROBID service, stored as TEI
XML, and rendered into semantic HTML for the audit scripts.

## Local Service

Start GROBID with Docker:

```sh
docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
```

Check that the service is alive:

```sh
curl http://localhost:8070/api/isalive
```

Expected response:

```text
true
```

## Project Script

Parser script:

```text
scripts/extract_article_grobid_html.py
```

Makefile targets:

```text
article-grobid-html
article-grobid-html-all
```

Regenerate all processed article files:

```sh
make article-grobid-html-all
```

## Outputs

The active processed article files are:

```text
data/processed/articles/*.html
data/processed/articles/grobid_tei/*.tei.xml
data/processed/audit/logs/article_grobid_html_manifest.csv
```

The HTML files include:

- article title
- abstract
- body sections
- paragraphs
- bibliography entries
- machine-readable metadata linking the HTML file to the source PDF and TEI XML

Each generated HTML file records parser metadata in three forms:

```html
<meta name="article:source_pdf" content="data/original/articles/example.pdf">
<meta name="article:tei_file" content="data/processed/articles/grobid_tei/example.tei.xml">
<meta name="article:html_file" content="data/processed/articles/example.html">
<meta name="article:text_extractor" content="GROBID">
<meta name="article:text_stage" content="semantic_html_from_tei">
<script type="application/json" id="article-html-metadata">...</script>
```

The deterministic assessment script reads this metadata to populate
`meta.pdf_file`, `meta.processed_text_file`, and related provenance fields.

## Full Local Run

After starting the local GROBID service, the full local article corpus was
processed with:

```sh
make article-grobid-html-all
```

Run result:

```text
processed: 83
skipped: 0
failed: 0
HTML files: 83
TEI XML files: 83
```

Manifest aggregate counts:

```text
TEI text characters: 4,002,426
TEI sections/divs: 1,937
TEI paragraphs: 4,090
bibliography entries: 3,320
HTML bytes: 3,218,263
```

## Rationale

GROBID gives the pipeline semantic article structure rather than only visual or
line-oriented text. This is better aligned with the audit tasks because the
scripts need section, paragraph, bibliography, and local resource context.

The current audit chain therefore treats GROBID HTML and TEI XML as the
authoritative processed article-text representation.
