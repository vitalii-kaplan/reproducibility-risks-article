# Framework Reframing Notes

## Reply From Dr. Hou

Hi Vitalii,

this version is stronger is evaluation. I’d suggest further improving the method
section. You can frame the methodological contributions as an automated workflow
compatibility assessment or repair framework, together with statistical analysis
of the observed compatibility results and comparisons with other scientific
workflow platforms. Give detailed theoretical/mathematical descriptions as much
as you can. This will make the paper look less like a report and more like a
computer science paper.

## Interpretation

The main signal is that the current empirical evaluation is acceptable, but the
paper needs stronger methodological framing. The priority should not be adding
more articles to the audit. The priority should be to make the existing study
look like a computer science contribution:

- define a structured workflow-preservation and compatibility assessment
  framework;
- define a visual workflow reproducibility score as the framework output;
- instantiate the framework on KNIME as a concrete case study;
- report statistical summaries over the observed assessment results;
- derive preservation recommendations from the evidence;
- describe future automation and repair support without claiming that a full
  repair system has already been implemented.

The safest framing is:

> The paper proposes a scoring framework for assessing the reproducibility
> readiness of published visual workflow studies, and applies it empirically to
> KNIME as a concrete case study.

A more computer-science-oriented version is:

> We define a visual workflow reproducibility scoring framework for studying
> whether published scientific workflows remain discoverable, inspectable,
> executable, and reproducibility-ready over time. The framework is instantiated
> on KNIME workflows because KNIME is a widely used graphical workflow platform
> with publicly available publication-linked artefacts.

Avoid presenting the completed contribution as a full workflow repair framework
unless repair is actually implemented. A safer claim is:

> The method is designed as a foundation for automated compatibility assessment
> and future workflow repair.

The application goal can be stated as a target implementation of the framework:

> Given a publication and its linked artefacts, the assessment application
> extracts preservation signals, classifies artefact and compatibility states,
> and computes a visual workflow reproducibility score.

For the current paper, this should be presented as a framework plus
semi-automated pipeline, not as a fully completed general-purpose application
unless the software is actually implemented end to end.

## Contribution Structure

The revised contribution should have three layers.

1. **Framework and methodology.** Define assessment states, controlled
   categories, metrics, failure taxonomy, the scoring model, and the assessment
   procedure.

2. **Empirical instantiation.** Apply the framework to the KNIME/OpenAlex
   top-cited article sample, retrieved workflow artefacts, current-KNIME opening
   and execution attempts, and KNIME source metadata.

3. **Application and automation path.** Explain how the method can be
   implemented as a semi-automated assessment application for compatibility
   checking, dependency reconstruction, environment capture, scoring, and repair
   recommendations.

## Visual Workflow Reproducibility Score

The central framework output can be a visual workflow reproducibility score. The
score should measure reproducibility readiness from observable evidence, not
claim to prove that a study is scientifically reproducible in all respects.

The score can combine several sub-scores:

- **Artefact availability:** whether the executable workflow file or workflow
  directory is available, not only a screenshot or textual description.
- **Inspectability:** whether the workflow can be opened in a current workflow
  platform.
- **Executability:** whether the workflow can be executed, and if not, which
  failure category applies.
- **Platform metadata:** whether the article reports the workflow-platform
  version.
- **Dependency completeness:** whether required extensions, plugins, packages,
  and installation sources are reported or recoverable.
- **Data availability:** whether input data are provided or linked through a
  stable source.
- **Code and script context:** whether surrounding scripts or code are available
  when they are needed to reproduce the workflow.
- **Compatibility risk:** whether the workflow contains deprecated, migrated,
  missing, or unresolved nodes.

Possible notation:

```text
VWRS = f(A, I, E, M, D, X, C, R)

A = artefact availability
I = inspectability
E = executability
M = platform metadata completeness
D = dependency completeness
X = data and external-resource availability
C = code/script context
R = compatibility-risk adjustment
```

The score should be accompanied by the underlying enum values and evidence. A
low score should be explainable, for example: no workflow file, missing platform
version, unresolved extension dependency, or execution failure due to missing
input data.

This framing supports an application-oriented goal:

> The long-term goal is an assessment application that takes an article and its
> linked artefacts as input, extracts reproducibility signals, classifies
> workflow preservation and compatibility states, and returns a visual workflow
> reproducibility score with evidence-backed explanations.

## Next Steps

### 1. Formalize The Output

Make the classification more rigid. Prefer controlled vocabularies, enums, and
explicit states over long prose notes.

Possible field groups:

- article relation;
- artefact availability;
- preservation signals;
- workflow retrieval result;
- import/opening result;
- execution result;
- dependency status;
- node-compatibility status;
- failure category;
- repair or mitigation potential;
- visual workflow reproducibility score and sub-scores.

Possible enum examples:

```text
article_relation =
  about_platform | uses_workflow_platform | not_a_workflow_use_case | not_assessed

artifact_status =
  no_artifact | link_only | link_unavailable | downloaded_archive |
  downloaded_workflow_directory | repository_available

workflow_open_status =
  not_tested | opens_cleanly | opens_with_warnings | fails_import |
  missing_extensions | missing_nodes

execution_status =
  not_attempted | success | fails_missing_data | fails_missing_extension |
  fails_configuration | fails_runtime_error | not_confidently_executable

dependency_status =
  not_reported | reported_names_only | reported_with_install_source |
  resolved | unresolved

failure_category =
  no_failure_observed | unavailable_artifact | missing_platform_version |
  missing_dependency_metadata | unresolved_extension | missing_data |
  deprecated_node | missing_node | configuration_error | runtime_error
```

The goal is to make the assessment reproducible and machine-checkable where
possible, so that the score is computed from explicit evidence rather than from
free-form judgment.

### 2. Make The Pipeline More Automatic

Reduce reliance on LLM interpretation. Use scripts for deterministic extraction,
normalization, validation, and table generation wherever possible. Manual or LLM
steps should remain explicit fallback stages, not hidden parts of the method.

Good automation targets:

- DOI, title, venue, and year normalization;
- article download-attempt logging, including institutional-access attempts
  where available and legally appropriate;
- PDF-to-text extraction and column normalization;
- detection of KNIME version mentions;
- detection of workflow links, supplementary files, repositories, and KNIME Hub
  references;
- detection of extension, plugin, data, and code availability statements;
- workflow archive and directory inventory;
- KNIME workflow XML parsing;
- node and factory-class extraction;
- comparison against deprecated-node and migration metadata;
- sub-score and total-score calculation;
- regeneration of article and workflow summary tables.

The method should distinguish deterministic script output from human assessment.
Use explicit values such as `manual_required`, `not_checked`, `not_confident`,
and `not_assessed` when automation cannot support a stronger claim.

### 3. Add Evidence-Based Recommendations

The recommendations should be derived from the observed preservation gaps. For
example, if many papers show workflow screenshots but do not preserve executable
workflow files, the recommendation should be:

> Workflow screenshots are useful explanatory material, but they should not be
> treated as workflow-preservation artefacts. Authors should archive executable
> workflow files in addition to figures.

Recommended preservation checklist:

- archive the executable workflow file, not only a screenshot;
- report the exact workflow-platform version;
- list required extensions or plugins;
- provide extension installation sources;
- preserve input datasets or stable links to them;
- provide expected outputs or validation checks;
- include execution instructions;
- preserve scripts used around the workflow;
- use persistent repositories or identifiers for workflow artefacts;
- capture the execution environment where feasible.

The paper should clearly separate empirical observations from recommendations:

- observed evidence: what the KNIME audit found;
- recommendation: what authors, repositories, and workflow platforms should do
  to improve long-term preservation and executability.

### 4. Define Score Dimensions Without Final Calibration

For the conference paper, it is enough to propose the score structure and define
the observable parameters:

```text
VWRS = f(A, I, E, M, D, X, C, R)

A = artefact availability
I = inspectability
E = executability
M = platform metadata completeness
D = dependency completeness
X = external data/resource availability
C = code/script context
R = compatibility risk
```

The paper should define what each parameter means, how it is observed, and which
article-level or workflow-level evidence supports it. The final weighting or
aggregation function `f` does not need to be fixed in this work.

Recommended wording:

> In this paper, we define the dimensions of the Visual Workflow
> Reproducibility Score and operationalize each dimension using observable
> article-level and workflow-level evidence. We do not prescribe a final
> weighting or aggregation function `f`; calibrating `f` across platforms and
> validating it against independent reproducibility outcomes is left for future
> work.

This makes the score a concrete methodological contribution while keeping the
scope realistic for a short paper.

## Comparison With Other Workflow Platforms

Do not start a new empirical cross-platform study before the deadline. Mention
other platforms only in related work or discussion, for example Galaxy, Taverna,
Kepler, Nextflow, and Snakemake.

The claim should be limited:

> The empirical instantiation in this paper focuses on KNIME, while the
> assessment framework is intended to generalize to other scientific workflow
> systems with appropriate platform-specific extractors and compatibility
> checks.

## Practical Priority

The immediate priority is not to expand the article sample. The immediate
priority is to make the existing 100-record audit and workflow evidence look
formal, reproducible, score-based, and framework-driven.

Order of work:

1. Define the framework states, metrics, score, and sub-scores.
2. Align the JSON audit fields with the framework.
3. Add or refine scripts that regenerate tables and score summaries from those
   fields.
4. Add a concise methodology subsection describing the framework.
5. Add a discussion/recommendations subsection based on the observed gaps.
6. Mention future repair support as a direction, not as a completed system.
