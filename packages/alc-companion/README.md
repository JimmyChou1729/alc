# alc-companion

`alc-companion` generates source-anchored translation and guide overlays for
an `ac-document` `RichDocument`. Its durable output is an `alc-render`
publication: atomic Markdown fragment revisions, producer layers, the complete
rich source, bibliography and glossary metadata, and run-owned source
resources.

The package does not own a second book model or rendering engine. Use
`alc-render` to render or edit the publication workspace.

For translated builds, every chapter translation is frozen before guide
generation. Chapter proposers and reviewers receive exact commands for reading
both the original and translated cached documents, so guide wording can follow
the accepted names and terminology without copying whole document bodies into
model-request JSON. Companion automatically executes only these predeclared
read-only `ac-document` commands through a bounded host broker; unknown
commands, writes, network access, and another source identity are refused.
Author verification receives bounded front-matter evidence directly and does
not require a host read during an ordinary build.

Guide writing uses `ac-proposer-reviewer`. A reviewer may accept a strong
proposal immediately or give concrete, constructive suggestions for up to two
complete revisions. Both roles compare the guide with the corresponding source
and translation. Inline guide fragments add information rather than compress
or restate the source; chapter guides may use concise orientation as one part
of a broader guide.

## Quick start

Use `alc-companion` directly when installed on `PATH`. If it is unavailable in
an installed ALC Skill, use `<skill-dir>/scripts/alc-runtime alc-companion`.
From this source checkout, use
`packages/alc-companion/.venv/bin/alc-companion`.

Build from a local source:

```bash
alc-companion build note.md \
  --project-dir local/example \
  --target-language zh-CN \
  --user-intent "Explain the main argument and its assumptions." \
  --provider codex \
  --model gpt-5.6-luna \
  --effort medium \
  --host-authority unknown

alc-companion status --project-dir local/example
alc-companion render --project-dir local/example
alc-companion validate --project-dir local/example
```

`build` accepts `--processing-mode fast|standard|deep` independently of
`--reasoning-effort`. Fast allows one guide revision; standard and deep allow up
to two, and deep enables cross-chapter editorial review. Translation still uses
review in every mode unless an explicit `--review-rounds` policy is supplied.
Omitting these options preserves existing recipe identity
and defaults. Extended mode/effort options require the matching AC Foundation
development runtime described in [alc-web](../alc-web/README.md).

Markdown, HTML, or flattened single-file TeX is authoritative. For local
sources, `--pdf note.pdf` supplies an optional validator; PDF is never the
reader source or output. Use `unrestricted` only when the host explicitly
grants it. Otherwise use `unknown`, or `restricted` when known, and preserve the
same authority on resume.

For the Codex provider, the frozen default is `gpt-5.6-luna` with `medium`
reasoning effort. `--model` and `--effort` can be overridden independently;
the selected pair is part of run identity and is reused on resume.

## Direct HTML acquisition

`alc-companion` does not acquire remote URLs. Materialize one local bundle
first, then pass its exact `source.html` and manifest to the build:

```bash
alc-companion build bundle/source.html \
  --html-source-manifest bundle/manifest.json \
  --project-dir local/example --target-language zh-CN \
  --host-authority unknown
```

For an ordinary direct HTML URL, use ALC's explicit provider-neutral document
acquisition command:

```bash
<skill-dir>/scripts/alc-runtime ac-document acquire-html-bundle <html-url> \
  --output-dir bundle
```

ARC is optional and remains outside the Python package. Supplied URLs use the
same Foundation acquisition route as Local Web, preserving explicit arXiv
versions. Discovery and enrichment may use ARC when requested. The materialized
export remains authoritative; Companion validates its manifest, source bytes and
resources before creating project state. Unavailable resources remain source
diagnostics.

Every command prints an `ac.command_result.v2` envelope. For `build` and
`resume`, read the selected durable identity at top-level `run.id`, lifecycle at
`data.run.status`, and delivered reader at `data.delivery.html`. Publication
identity and consistency are at `data.publication_digest`,
`data.edition_digest`, `data.selected_revision_digests[]`, and
`data.workspace_html_consistent`. A generation may complete while rendering
fails: in that case top-level `status` is `"completed"`, but
`data.published` is false, `data.delivery` is empty, and warnings include
`web_render_failed`.

Inspect and recover a paused selected run with:

```bash
alc-companion status --project-dir local/example

alc-companion resume \
  --project-dir local/example \
  --input resume-input.json \
  --host-authority unknown

alc-companion render --project-dir local/example
alc-companion validate --project-dir local/example
```

For `status`, lifecycle is at `data.selected_run.status`; status deliberately
has no `data.delivery`. A valid promoted reader is reported as an artifact with
role `web`. On a pause, inspect top-level `resume.input_required` and
`resume.request_artifact`; `--input` accepts inline JSON or a JSON file and may
be omitted when no input is required. Resume replays verified completed work in
the same durable run. Keep the original document-cache root and host authority.
`data.progress` exposes the current phase, completed/total units and chapters,
frozen provider/model, last progress time, partial Reader availability, and the
single valid next action. Failed semantic validation also exposes its supported
editable candidate path there; repair it and resume the same run rather than
starting a fallback source, provider, or project.
While a planned group is starting, `status` reports zero completed units until
its atomic group state is published; an existing malformed state remains a
strict error.
Recoverable block-translation and review failures do not pause the build:
invalid translated units fall back to source text, and invalid reviews retain
the validated pre-review translation. Invalid glossary entries are retried once
and then omitted individually rather than stopping the build. Status reports
source-text and skipped-review counts plus glossary fallback reasons at
`data.progress.translation_fallbacks`; final fragment provenance identifies the
affected translated blocks. Source corruption, permission decisions, explicit
stops, and an invalid final publication still stop safely.
Before guide generation, each persisted translation is independently checked
for renderable Markdown. A legacy or interrupted run containing one malformed
translation feeds that block's source text to guide generation and omits only
the unsafe translation overlay from publication, with a `translation_omitted`
delivery-ledger issue. Translation model-view cache v2 prevents an older unsafe
chapter view from being reused after this recovery.
When provider transport, timeout, rate-limit, quota, unavailability, or an
open provider circuit prevents one translation window, only that window is
source-preserved. A successful later window resets the streak; two consecutive
failed windows source-preserve the remaining model-dependent windows while
retaining every earlier accepted translation. Status reports the sanitized
provider/model, failure category/detail, first failed window, failed-window
count, and remaining skipped-window count. Guide exhaustion omits only the
affected guide and still publishes source plus translation. A static
source-only Reader is reserved for provider failure before a usable optional
overlay exists. Companion treats five
minutes without provider pipe activity as a typed timeout; this is an
inactivity deadline, not a total build deadline.
A provider that keeps emitting activity may run longer, while a disappeared or
interrupted provider releases its execution leases and enters the same safe
delivery path. Provider authentication, host-authority, request/schema,
source-identity, durable-state, and publication-integrity failures remain hard
stopping boundaries.
Completed publications include a versioned `delivery_ledger` and matching
`alc-companion-delivery-ledger.json` resource. The ledger reconciles source
units and every stage's expected, produced, and accounted counts; unaccounted
content or an undeclared fallback fails validation. A duplicate or conflicting
host request ID from `guide-reviewer` is isolated only after a persisted
proposer artifact passes normal guide validation. ACF still refuses the changed
instruction. Companion publishes the validated proposal with an explicit
`review_skipped` issue, or records the chapter as source-and-translation-only
when no admissible proposal remains. Exhausted
early provider availability failures use the explicit source-only delivery above;
authentication, permission, source-identity, lineage, schema, and durable-
corruption errors still stop.
`status` reads the selected snapshot and already materialized publication
without acquiring the delivery write lease. To attach a terminal owner to a
long-running build, use:

```bash
alc-companion wait --project-dir local/example --poll-seconds 15
```

The command emits progress heartbeats on stderr and returns one JSON status
when the durable run reaches a terminal state or an actionable pause. For a `RUNNING`
snapshot it resumes the same run to recover an orphaned execution; an active
owner's lease remains authoritative, so `wait` continues observing without
starting or taking over another run. Delivery results
expose `delivery_mode` (`bilingual`, `partial_bilingual`, `source_only`, or
`source_language`) alongside the canonical ledger `delivery_grade`. When a
validated interactive-admission fallback produced static source-only HTML,
subsequent status reads report that actual source-only delivery rather than the
pre-fallback publication grade.
An actionable pause is not a final delivery; inspect its resume descriptor and
continue the same lineage.
`build` refuses to replace a different selected source or recipe unless
`--new-lineage` is explicit; that flag is not a retry mechanism.
After an explicit render, use `data.delivery.html`; an empty delivery with
`publication_not_selected` means a different run won selection before
promotion.

Add `--cross-chapter-editorial-review` to `build` to run one optional,
single-worker proposer-reviewer pass after all chapter-local guides finish.
The pass may revise or omit a guide only when the final reviewer explicitly
approves the exact digest-bound edit. Original accepted guides remain as the
audit baseline. The resolved publication includes a lightweight summary and a
downloadable `alc.companion.editorial_review.v1` JSON report. Builds without
the flag retain their non-editorial recipe identity and make no editorial
model calls.

Post-publication corrections use a canonical request and create immutable
child revisions without changing the run-owned publication:

```bash
alc-companion revise \
  --project-dir local/example \
  --request revision-request.json
```

The request binds the selected run and publication digest. Each replacement
binds the current fragment semantic digest and supplies the complete new title
and Markdown body. Citations must already exist in the publication
bibliography; source identity, anchors, language, role, and priority are
inherited. Committed reviews live below
`.alc/companion/operator-revisions/<run-id>/` and are replayed by status,
render, revise, and validate. The immutable `publication_digest` identifies
the base publication; `edition_digest` identifies that publication plus its
ordered current fragment heads. Glossary revision heads are carried separately
by the Reader/export contract and do not change this existing digest.

Use `alc-companion --help` and each subcommand's `--help` for the complete
durable-control and publication options. `--document-cache-root` overrides document
storage; otherwise the command uses `AC_DOCUMENT_CACHE` or
`<launch-directory>/.ac/cache/ac-document`. This cache is separate from durable
project state.

A successful build writes its immutable artifacts under
`<project-dir>/.alc/companion/jobs/` and materializes the selected publication
under `<project-dir>/.alc/companion/publications/<run-id>/`. The `render`
command first writes and validates a run-specific reader there, then atomically
promotes it to portable standalone `<project-dir>/companion.html` only if that
run is still selected.

ALC publishes and validates the publication workspace and standalone HTML
only. A PDF made manually with a browser's print command is a user-side
derivative, not an ALC release artifact, and ALC does not promise to validate,
reproduce, retain, or automatically publish it.

The publication workspace is self-contained:

```text
publication.json
layers/translation.json
layers/companion.json
fragments/revision-....md
glossary/revision-....md
glossary-batches/<batch-id>/fragments/revision-....md
resources/<sha256>
```

Translation fragments use priority 10. Inline Companion fragments use priority
20; chapter and section guides use priority 101. Fragment location is anchored
to immutable rich-source block identity, while the Markdown file contains only
the human-authored semantic content. The validated JSON front matter owns
fragment identity; directory names are never semantic identities.
Model-authored display math is canonicalized before publication: opening and
closing `$$` delimiters occupy separate lines around the TeX body. Ambiguous or
unbalanced display-math delimiters are rejected instead of being published as
literal Reader text.
Structured guide titles remain plain text. Accidental `$...$` or `\\(...\\)`
inline-math delimiters are removed while their title content is retained, so a
title-formatting defect cannot stop or visibly leak markup into the Reader.

## Reader assumptions

For a paper with one title heading above its body sections, an explicit
`--chapter-heading-level 2` on build partitions chapter tasks at level-two
source headings. The equivalent public request field is
`CompanionBuildRequest.chapter_heading_level`. The choice is frozen in the
request; resume retains it. Source blocks, formulas and IDs are unchanged,
and preceding front matter belongs to the first selected chapter. At this
explicit boundary, exact References/Bibliography/Acknowledgements headings
form display-and-translation chapters without generating guides. A missing
requested level is rejected. This option cannot be combined with a document
structure overlay; omitting it retains historical chapter planning and request
identity.

User intent is also passed to Companion's embedded glossary, translation and
translation-review stages under their fixed source-faithful contracts. An
explicit reader background in user intent takes precedence for guide content. Otherwise,
popular or weakly specialized writing assumes a generally educated adult
without specialist training; research papers assume a student who has
completed the relevant foundational courses; textbooks assume completion of
standard prerequisites without assuming difficult prerequisite material is
already mastered.

## Tests

```bash
python -m pytest packages/alc-companion/tests
```

Chapter translation results retain source-note translations as separate render
fragments. Companion validates body order and note ownership/coverage separately;
note text never replaces its owner paragraph in the guide input.

Local-app builds check `ac-document` availability before model execution and
require persisted successful host-read receipts covering every declared source
and translation part before accepting chapter guides. Nonzero exits, empty
output and truncated reads do not establish coverage; complete smaller reads
can satisfy it. Missing coverage fails with `chapter_source_read_incomplete`,
even when the model reports a completed review. Direct host execution retains
its existing review contract because commands executed outside the broker do
not produce these receipts. Existing completed publications are not rewritten.

After a failed build, recovery retains accepted chapter guides and translations
and rebuilds the pending guide batch in a fresh execution scope. It does not
require manual deletion of old batch/request indexes or reuse old model sessions.

New Companion builds use chapter pipelines by default, in both CLI/API and Web.
Each chapter validates its translation before generating its guide, while other
chapters can translate. Provider gates remain shared and chapter order is
preserved. The saved strategy is retained on resume, including legacy staged
jobs. These workflow optimizations are not user-facing settings.

Complete original and frozen translation evidence is preloaded for independent
proposers and reviewers before guide generation when exact cached source commands
are available. Non-local legacy text-only sources retain their attached source
input path. Local application jobs require complete verifiable evidence. If a complete chapter read is
truncated or unavailable, registered smaller part ranges are read to establish
complete original and translation coverage. Evidence includes source bindings,
content digests and compact location descriptors, with a 256,000-byte serialized
budget per guide batch; command descriptors remain in the surrounding context.
Oversized chapters are automatically partitioned at balanced section or block
boundaries until each batch fits. This changes only guide processing: source
chapter IDs, the outline, and completed translations remain intact. Each batch
is independently reviewed and cached, and its anchored learning units are merged
back in source order. Batch overviews appear inline at their own source location.
There is no aggregate chapter-size rejection when its blocks can be partitioned.
An individual indivisible block that still exceeds the read/evidence budget, or
an unavailable cached source, continues to return a preparation error; evidence
is never truncated. Failed preparation can be retried; only successful evidence
is cached. Existing jobs
keep their saved policy and already frozen guide requests, including legacy
on-demand reading.

Companion defaults to 2 workers; `--workers` is the invocation's shared model-task
budget. Translation windows within one chapter can use the budget, while
translation, review and guide tasks across chapters share the same limit. Chapter
and window worker counts do not multiply the number of active model tasks.
Changing workers on resume does not change semantic request identity or repeat
accepted translation windows. Custom translation adapters retain their existing
protocol and own any task execution they perform outside the supplied service.
`build` and `resume` accept `--execution-profile standard|local-app`.
The default remains `standard`; `local-app` uses the bounded local application's
model and source-read execution policy. An explicitly injected runtime policy
(such as Web execution) takes precedence over the CLI flag.
Guide depth and model reasoning effort are independent of concurrency. Internal
execution-policy overrides remain available for compatibility tests; legacy CLI
optimization flags are accepted but hidden and no longer required.

Independent chapter execution collects failed units instead of abandoning
unstarted neighbors after the first failed result. Shared pauses still stop
admission. Optional author output-format repair exhaustion reuses the validated
omitted-author fallback and records that decision for replay without a new
model call. This does not suppress authentication or quota pauses.

Both chapter pipelines and legacy staged guide batches isolate exhausted
model-content pauses from other chapters. Authority and shared-service pauses retain their normal stop boundary.
When chapter processing pauses or fails, a separate partial Reader snapshot can
include completed chapters and complete translation results from other chapters.
It is titled as a partial result and does not publish the final build artifact.
The partial state records the complete chapter count and unfinished chapter titles.
Successful units are reused during normal recovery. Completed source blocks
from chapter-internal translation windows can also appear in partial previews;
a split block is included only when all its units and source notes are complete.
Guide-only chapters remain available when their translation is unfinished.
Optional cross-chapter editorial and PDF label-review output-format exhaustion
retain accepted content and add an advisory rather than stopping delivery.


### Content review policy

`build --review-rounds 0|1|2` freezes a content-review limit into the durable
generation recipe. It applies independently to each translated batch and each
guide chapter. Zero skips model review and cross-chapter editorial work while
retaining structural/content validators. One allows one review and correction;
two allows a second review after correction, with early acceptance. This policy
is independent of `--workers` and overrides the legacy processing-mode review
behavior. Resume uses the stored recipe. Omitting it preserves legacy behavior
and recipe identity.

With a positive limit, cross-chapter editorial review also runs, with at most
that many reviewed proposals. Only explicitly approved, digest-bound edits are
applied; an unapproved final proposal never changes the guide. These rounds
are limits per stage, not a total model-call budget or a quality guarantee.

## Verified PDF sources

After `ac-document parse-pdf-mineru` (or `parse-pdf-configured-mineru`), pass its
normalized source HTML with `--pdf-source-manifest <manifest.json>`. This binds
all content to the original PDF pages and preserves extraction warnings, images
and structure. The manifest is verified before learning work; OCR is not marked
as proofread. Do not combine this route with an HTML acquisition manifest or
a PDF text-layer validator.
Use this flag on build; subsequent resume uses the frozen source identity.

Heading-only source chapters remain covered by source and translation but do not
request a guide or count as missing guides in the delivery ledger.

Provider failures during chapter or editorial work remain resumable failures.
They refresh the bilingual partial Reader from durable translations and accepted
guides instead of publishing a successful source-only replacement. Source-only
terminal delivery is limited to earlier preparation stages without chapter work.
