---
name: alc
description: Use for source-faithful OCR proofreading, translation, interactive HTML rendering, or textbook-style Companion reading guides. Also use when the user explicitly invokes ALC or `$alc` for one of these learning workflows.
---

# Agentic Learning Copilot (ALC)

ALC turns local source material into verified text, translations, interactive
readers, and source-anchored learning companions. It does not own academic
paper discovery or research judgment.

## Select one capability

- OCR proofreading against a PDF: read `workflows/ocr-proofread.md` and
  `manuals/alc-ocr-proofread.md`.
- Standalone translation: read `manuals/alc-translate.md`.
- Rich-document or standalone HTML rendering: read
  `manuals/ac-document.md` and `manuals/alc-render.md`.
- Companion build, resume, revision, or render: read
  `workflows/companion.md` and `manuals/alc-companion.md`.

When the requested result includes a reading guide, paragraph companion,
visible glossary, or a complete learning Reader, select the Companion workflow.
Standalone translation owns source-plus-translation delivery; it does not
substitute for Companion merely because it builds a glossary prerequisite.

Read `rules/interaction.md` for user-choice and automation behavior and
`rules/operating.md` for shared local-state rules. Do not preload unrelated
manuals.

## CLI resolution

Use `alc-ocr-proofread`, `alc-translate`, `alc-render`, or `alc-companion`
directly when exposed by the host. Shared Foundation commands such as
`ac-document`, `ac-jobs`, `ac-llm`, and `ac-proposer-reviewer` are intentionally
not separate plugin wrappers; invoke them through the product launcher:

```bash
<skill-dir>/scripts/alc-runtime ac-document <command> [args...]
```

For an ALC command unavailable on `PATH`, use the same launcher:

```bash
<skill-dir>/scripts/alc-runtime alc-translate <command> [args...]
```

In DeepSeek Harness, use `$DSH_ALC_RUNTIME` in place of the launcher path.
Prewarm with `alc-runtime setup`; inspect source identity and readiness with
`alc-runtime doctor`. Runtime locks pin full Git SHAs for both ALC and AC
Foundation.

Generic document cache defaults to `.ac/cache/ac-document` under the launch
directory. Durable learning state stays under the selected project's `.alc/`
directory. Never treat durable runs as shared cache.

## Optional academic enrichment

`alc-companion` itself neither imports ARC nor performs academic research. If
a Companion would materially benefit from paper discovery or literature
review, the Skill may suggest using ARC first and passing reviewed local
supplements into ALC. If ARC is unavailable, state that it is optional and ask
whether the user wants to install it or continue without enrichment. Never
install ARC automatically and never make it a Python or runtime dependency of
ALC.

## Direct HTML sources

For a URL or paper identifier supplied for translation or Companion, use the same
Foundation acquisition route as Local Web. Convert a bare arXiv ID (including
its explicit vN suffix) or arXiv: identifier to https://arxiv.org/html/<id>.
Convert a DOI to https://doi.org/<doi>. Preserve an existing public HTTPS URL.
Do not choose an alternate acquisition route merely because ARC is installed.
ARC remains optional for explicitly requested discovery or enrichment.

```bash
<skill-dir>/scripts/alc-runtime ac-document acquire-html-bundle <html-url> \
  --output-dir <bundle-dir>
```

Retain source.html, manifest.json and local resources together. Pass
`--html-source-manifest <bundle-dir>/manifest.json` to Companion. If a URL returns
PDF or another format, identify that format and use its supported explicit input
workflow; do not silently replace the requested source with a different edition.
Acquisition warnings and source identity remain attached to the result.

## Completion

Validate the owning workflow before delivery. Publish visible HTML or native
source artifacts; hidden state is not the final deliverable. Preserve exact
source identity, returned run IDs, assumptions, and warnings.

Keep following a model-backed command until its execution session returns a
terminal result. A yielded tool session or a period without stdout is not a
completed command. Do not end the task with "still running" while that session
remains active; poll the session and use the workflow's public status command
for progress. A run snapshot's timestamp alone does not measure live progress.
Never infer that no work was saved from an absent final Layer or HTML file.
After successful standalone translation, compose and validate the Reader as
documented in manuals/alc-translate.md; a Layer JSON is not the requested HTML
delivery. Stop or defer only when the user requests it or a concrete blocker
requires user input, and describe the verified state at that point.

## Workflow and resource policy

Use the shared Local Web processing defaults for new translation and Companion:
`--execution-profile local-app`, 2 workers, and `--review-rounds 1`. Specify the
same provider/model/language chosen by the user; do not silently substitute a
model. Use the medium-tier default when no model is requested. The local-app
profile uses the official CLI login and isolated execution; custom API routes
must be configured explicitly rather than inherited from host CLI settings.

Presets: fast draft = 4 workers / 0 reviews; standard = 2 / 1; strengthened review
= 2 / 2. User-chosen combinations are custom. Accept 1–8 workers and review
rounds 0, 1 or 2. Zero skips model content review while retaining programmatic
source and output validation. Two stops early when no correction is needed.
Pass `--workers N` to Companion and `--window-workers N` to translation.

Companion preloads complete original and frozen translated chapter inputs before
guide generation. Do not silently fall back to incomplete agent-directed reads.
Treat unavailable input as retryable preparation failure and oversized input as
an explicit capacity limit. Resume keeps the frozen review and evidence policy;
use `--execution-profile local-app` and the task's saved worker count on resume.
Do not rewrite old requests to upgrade them in place. Do not add a separate
cross-chapter review flag to new explicit-policy tasks; review_rounds governs it.

Concurrency is a per-task upper limit. Independent tasks do not divide one
user-wide pool: two tasks configured for eight can issue sixteen requests in
total. Hardware, network and provider limits can reduce actual throughput.
Local Web separately limits the number of simultaneous document jobs.
