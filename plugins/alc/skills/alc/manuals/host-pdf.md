# PDF recognition with the host

This route uses the current agent's page-vision capability instead of installing
MinerU. It is optional; retain existing configured MinerU execution and imported
bundles. Reading an HTML source or an adequate PDF text layer does not require
an OCR model. Do not silently downgrade scanned or layout-rich PDF input to
plain text.

Confirm that the host can inspect rendered page images and that a PDF renderer
is available. Keep the supplied edition, original bytes and a persistent project
directory. Start with a small representative PDF for a newly supported host:

```bash
<skill-dir>/scripts/alc-runtime ac-document parse-pdf-host <source.pdf> \
  --project-dir <project-dir> --output-dir <bundle-dir>
```

Follow `host-execution.md` for each exported page task. Transcribe visible
content faithfully, preserve reading order, equations, tables and page identity.
Do not summarize, correct the author's science, invent unreadable symbols, or
claim a precise region was located when it was not. Retain ambiguity and missing
content as warnings. Figures must use original rendered evidence; full-page
fallback images must be labeled rather than presented as precise crops.
Leave table/figure text empty when there is no visible caption; do not invent
one to satisfy parsing. Existing verified bundles with empty caption elements
can enter OCR proofreading directly, without rewriting their HTML or manifest.

Submit and repeat the original command with the returned `--run-id` to resume.
Completed pages remain accepted. Use `ac-document status --run-root <project-dir>
--run-id <run-id>` to inspect the run. After correcting a concrete renderer or
output failure, repeat with `--retry` to reuse accepted pages. Do not use retry
to bypass an explicit user stop. Optional `--model` / `--reasoning-effort` are
bound to the initial request and must stay identical on resume. Only after the owner validates and publishes
the bundle, pass its `source.html` and `manifest.json` to translation or
Companion via `--pdf-source-manifest`. Retain the PDF, evidence and resources
alongside it. Do not present Host recognition as MinerU output or as independently
proofread text. Optional OCR proofreading remains a separate workflow.

Structural validation checks identities, resources and page coverage metadata;
it does not establish that every visible character was correctly recognized.
For real-host acceptance, compare plain text, multi-column scientific pages,
formulas/tables, scans and figures against the original; measure omissions and
transcription errors and inspect the final Reader. Long books should use page
checkpoints and bounded dispatch rather than one full-document model response.
