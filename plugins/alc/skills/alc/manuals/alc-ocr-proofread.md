# ALC OCR Proofreading Quick Start

`alc-ocr-proofread` compares MinerU page-mapped Markdown with complete PDF page
images and records exact corrections in a durable ALC project.

## Start

```bash
alc-ocr-proofread --help
alc-ocr-proofread proofread source.md --pdf source.pdf \
  --content-list source_content_list.json --project-dir project \
  --workers 30 --max-workers 200
```

If the bare command is unavailable, use the portable Skill runtime:

```bash
<skill-dir>/scripts/alc-runtime alc-ocr-proofread --help
```

Markdown, PDF, and MinerU content list are all required. The package does not
perform OCR or infer page alignment. It validates page indices before any
provider call. Private durable state is under
`<project-dir>/.alc/ocr-proofread/`.

## Observe and Control

```bash
alc-ocr-proofread status --project-dir project
alc-ocr-proofread workers get --project-dir project
alc-ocr-proofread workers set --project-dir project --workers 10
alc-ocr-proofread stop --project-dir project --reason "user requested stop"
```

The default is 30 workers and the configured maximum cannot exceed 200.
Lowering the target does not cancel active work. Status includes completed and
failed pages, correction records, and average correction records per completed
page. Hourly checks are normally enough; do not busy-poll.

Page correction is followed by model review of every adjacent page pair. Both
complete page images are attached. Every proposed paragraph join and every
uncertain result requires a main-agent decision; page-edge position alone does
not prove that the selected OCR blocks are the prose visible across the page
turn. For an accepted join, select the exact left and right paragraph block IDs
from the request's candidate lists; this safely handles intervening page
numbers, figure labels, and sidebars. If a page contains no paragraph, the
candidate list reaches only to the nearest nonempty page in that direction;
accepted text can span a full-page plate while page notes and non-text blocks
stay in source order. A boundary provider that remains interrupted after
bounded retries is routed through the same main-agent review instead of losing
completed boundary work. PDF page markers become structured, default-hidden
reader notes and never translation fragments.

## Review and Resume

A pause reports `resume.request_artifact` and `resume.resume_key`. Read that
artifact, inspect every referenced full page, and create one JSON input covering
every requested item. Source-typo candidates are never applied automatically.
Accept an obvious printed typo only after visual confirmation; reject uncertain
cases. An accepted uncertainty must provide an exact edit.

The next pause requests deterministic samples of up to 10 changes, 10 boundary
repairs, and 10 whole pages. Pages from rejected or uncertain proposed joins
come first so missed OCR at a suspicious page turn can be corrected with an
exact page edit. Inspect every sample and submit `pass` or `fail` for every
listed ID:

```bash
alc-ocr-proofread resume --project-dir project --input decisions.json
```

Resume uses the same durable run. A failed audit prevents delivery.

To add boundary review to an older verified delivery without repeating page
proofreading:

```bash
alc-ocr-proofread reconcile-boundaries --project-dir project \
  --pdf source.pdf --workers 30 --max-workers 200
```

The command binds to current delivery and PDF digests and refuses already
reconciled output.

## Results

```bash
alc-ocr-proofread validate --project-dir project
alc-ocr-proofread get-result --project-dir project
```

Successful output is `proofread.md`, `proofread.manifest.json`,
`proofread.changes.jsonl`, and `proofread-assets/`. The manifest distinguishes
OCR corrections, main-agent-approved source corrections, and page-boundary
repairs, and reports corrections per page.

## Help

```bash
alc-ocr-proofread --help
alc-ocr-proofread <command> --help
```

## Optional proofreading of a native PDF bundle

For the PDF translation/Companion route, prefer `proofread-bundle` with the
verified manifest returned by `ac-document`. First obtain authorization to send
original page images and OCR text to the user's selected vision-capable
provider/model. Do not silently substitute a model or enable proofreading.

```bash
alc-ocr-proofread proofread-bundle --manifest bundle/manifest.json \
  --project-dir project --provider provider-id --model model-id --workers 4
alc-ocr-proofread get-result-bundle --project-dir project --run-id RUN_ID
```

This mode returns an unapproved HTML candidate and preserves source IDs, image
assets, tables and formulas. Present its page edits and uncertainties alongside
the original PDF. Model success is not approval. The user must review all pages;
unresolved uncertainties prohibit adoption. Only after explicit approval of the
exact candidate may the agent run:

```bash
alc-ocr-proofread approve-bundle --manifest bundle/manifest.json \
  --project-dir project --run-id RUN_ID --candidate-digest CANDIDATE_SHA256 \
  --confirm-reviewed --output-dir reviewed-bundle
```

Pass the returned source and manifest to the learning workflow. If declined,
continue with the original bundle and retain the unproofread warning. Use
`status-bundle`, `stop-bundle` and `resume-bundle` with `--project-dir` and
`--run-id` to control this separate durable workflow. This mode does not perform
the older Markdown workflow's adjacent-pair reconciliation or sample audit.
Runtime pins must include these commands before using them in an installed
plugin; a source checkout alone does not update the installed runtime.
