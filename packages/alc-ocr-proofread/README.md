# alc-ocr-proofread

`alc-ocr-proofread` compares MinerU page-mapped OCR with complete PDF page
images. It uses `ac-jobs` for durable page work, `ac-llm` for bounded model
calls, and the public `ac-document` PDF renderer.

```bash
alc-ocr-proofread --help
```

```bash
alc-ocr-proofread proofread book.md --pdf book_origin.pdf \
  --content-list book_content_list.json --project-dir project
alc-ocr-proofread status --project-dir project
alc-ocr-proofread resume --project-dir project --input review.json
alc-ocr-proofread reconcile-boundaries --project-dir project \
  --pdf book_origin.pdf
alc-ocr-proofread validate --project-dir project
```

The content list is mandatory and authoritative for page boundaries. The
package does not run OCR or infer page alignment. Every adjacent page pair is
reviewed against both full-page images; confirmed split paragraphs are joined,
while page boundaries remain structured provenance notes. The
`reconcile-boundaries` command adds this review to a verified older delivery
without repeating page proofreading. Private state lives below
`.alc/ocr-proofread/`; successful delivery is `proofread.md`,
`proofread.manifest.json`, `proofread.changes.jsonl`, and
`proofread-assets/`.

## Tests

```bash
python -m pytest packages/alc-ocr-proofread/tests
```

## Native PDF source bundles

For a verified `ac-document` MinerU bundle, `proofread-bundle` compares each
complete original page image with its page-mapped HTML. Choose a vision-capable
provider/model and authorize sending those images and OCR text before invoking
it. This optional mode preserves figures, tables, formulas and source IDs. It
proposes exact text, formula-alttext and image-alt edits; it never treats OCR
extraction or model completion as human approval. Printed source errors must
remain faithful to the source.

```bash
alc-ocr-proofread proofread-bundle --manifest bundle/manifest.json \
  --project-dir project --provider provider-id --model model-id --workers 4
alc-ocr-proofread status-bundle --project-dir project --run-id RUN_ID
alc-ocr-proofread get-result-bundle --project-dir project --run-id RUN_ID
```

`proofread-bundle --reasoning-effort high` optionally selects model reasoning
effort. The selection is frozen with the run and reused on resume; omitting it
keeps the provider default.

The result is an unapproved candidate with original/corrected content, exact
edits and uncertainties for every page, bound to the original PDF and source
hashes. Review every page against the original PDF. Missing extraction coverage,
unsupported structural changes and unresolved uncertainties prevent approval.
There is no automatic publication and no guarantee that all OCR errors were
found. After explicit user approval of the exact candidate:

```bash
alc-ocr-proofread approve-bundle --manifest bundle/manifest.json \
  --project-dir project --run-id RUN_ID --candidate-digest CANDIDATE_SHA256 \
  --confirm-reviewed --output-dir reviewed-bundle
```

Pass the returned source and manifest to translation or Companion. The new
bundle preserves the original source and approval evidence; the original bundle
is unchanged. To decline, use the original bundle. `stop-bundle` and
`resume-bundle` take the same project and run ID; resume accepts `--input` when
the reported pause requires it. Completed page work is reused.

This HTML candidate mode is separate from the older Markdown workflow above:
it does not join paragraphs across pages or inherit its adjacent-pair audit.
MinerU cross-page alignment must already have been restored from verified
preprocessing evidence by `ac-document`.

The Python `pdf_bundle_edit` module exposes `editable_candidate` and
`revise_candidate` for plain-text segment edits and explicit uncertainty
resolutions. Draft maps are relative to the original model candidate; source
IDs, image paths and HTML structure cannot be edited. `accepted` records a
human decision to retain the current content; `corrected` requires a manual
edit on that page. Original uncertainty records remain in the audit.
`pdf_bundle_delivery.adopt_pdf_candidate(mode="model")` retains unresolved
warnings and records model-only review; `mode="user"` requires confirmation
and zero unresolved items. Local Web uses model-only automatic continuation without
a manual OCR review interface; the CLI candidate/approval commands above remain explicit.

## Automatic OCR triage policy

New native PDF runs bind `review_policy_version=ocr-triage.v2` into durable run
identity. The rule is document-independent: visually confirmed transcription
edits are applied after exact-node/structure validation; truly ambiguous or
unreadable content retains its original wording and a concrete excerpt/reason.
Model issues are typed as `ambiguous`, `irrelevant`, or `limitation`. Decorative
page furniture is discarded, while coverage checks, known structural limitations
and rejected edits are diagnostics rather than content uncertainty. Diagnostics
remain in the saved run for troubleshooting, not in the uncertainty list.

Identical-before/after proposals get at most one additional model correction
request using the same original page and a separate durable task ID. Accepted
repair edits must target the original proposal; failed repairs cannot invent
text from a natural-language explanation. Repair pauses/resumes preserve input
routing and usage accounting. If a proposed edit is also flagged ambiguous for
the same source span, the original text wins. Printed source-book errors are
never silently corrected.

Runs without this policy field retain their frozen v1 execution behavior. Saved
results are not rewritten or resubmitted when the UI normalizes legacy notices.

Math edits cannot start or end inside a LaTeX command. For example, a proposal
to replace `s` must not alter the last letter of `\times`. Such an edit is
rejected as an execution diagnostic without shifting its occurrence to another
match. Prompts request complete formula context; complete command replacements
remain supported. New runs bind `math_edit_policy=command-boundaries.v1` so they
do not reuse candidates generated before this check. Existing delivered results
are not rewritten by this validation change.

## Opt-in local MinerU setup

`alc-ocr-proofread setup-mineru --project-dir PATH` prints a read-only plan.
After selecting automatic installation, add `--install --accept-downloads`.
The installer supports macOS/Linux, uses Python 3.11 for new installations, pins
`mineru[pipeline]==3.4.5`, requires wheels, and keeps its virtual environment under
`~/.alc/runtimes/mineru/`. It never installs system Python or replaces a configured
remote service. A new installation checks a conservative 20 GiB disk reserve;
this is a planning reserve, not a measured download size. See the
[upstream requirements](https://opendatalab.github.io/MinerU/quick_start/).

Existing local runtimes are reused. Every attempt verifies a generated one-page
PDF through the normal pipeline importer before adopting configuration. Version
output alone is insufficient. Installation state, the pip report and private log
remain in the managed directory after failure; retrying reuses that environment.
No user PDF is used for the installation probe. A failed probe leaves the previous
project configuration intact. Supported wheels may be unavailable on some hosts;
report that failure instead of compiling or modifying the host automatically.
