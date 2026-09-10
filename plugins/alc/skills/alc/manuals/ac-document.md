# ALC Document Quick Start

`ac-document` owns provider-neutral source import, deterministic parsing,
content-addressed document references, structural reads, literal text/equation
search, keyword inventory, rich-document export, and document-cache
administration. It does not identify papers, query arXiv/INSPIRE, or traverse
citations. An optional ARC installation owns those academic capabilities.

Commands return the standard ALC JSON envelope. Check `status`, `warnings`,
`error`, then `data`. The cache defaults to `.ac/cache/ac-document` below the
launch directory; set `AC_DOCUMENT_CACHE` or pass `--cache-root` consistently.

## Run ALC Document

Use `ac-document` on `PATH`, the portable Skill launcher, or the source-checkout
development fallback:

```bash
ac-document --help
<skill-dir>/scripts/alc-runtime ac-document --help
<alc-venv>/bin/ac-document --help
```

## Import, Parse, and Export

Import one local Markdown, HTML, flattened TeX, or PDF source:

```bash
ac-document import-source source.md
ac-document parse-local source.md --validator source.pdf
```

Export the neutral `RichDocument` workspace consumed by `alc-render`:

```bash
ac-document export-rich-document source.md \
  --validator source.pdf --output-dir publication
```

The export contains `rich-source.json`, `metadata.json`, and copied resources.
Do not hand-edit resource identities after export.

## Acquire a Direct HTML Source

For one direct public HTML URL, use the explicit acquisition command through
the ALC runtime rather than a local import command. It materializes a local
primary and a materialized export containing an
`ac.document.html_source_bundle.v1` bundle; it is not an implicit parser
network operation:

```bash
<skill-dir>/scripts/alc-runtime ac-document acquire-html-bundle <html-url> \
  --output-dir <materialization-dir>
```

The command atomically publishes `<materialization-dir>/source.html`,
`<materialization-dir>/manifest.json`, and any materialized local resources.

When the source will feed a Companion, retain that one primary and materialized
export, then run:

```bash
alc-companion build <materialization-dir>/source.html \
  --html-source-manifest <materialization-dir>/manifest.json
```

Use this Foundation route for supplied URLs, matching Local Web. Optional ARC
discovery or enrichment does not automatically replace the source bundle.

Build an approximate durable keyword inventory from a local source:

```bash
ac-document extract-keywords source.md --project-dir run/keywords
```

## Frozen Cached Reads

Operations such as import/cache return a `CachedDocumentRef`. Preserve its JSON
and the cache root to make provider-free reads against the exact source digest,
parser contract, and parsed-document digest:

```bash
ac-document get-table-of-contents --document-ref '<ref JSON>'
ac-document get-section --document-ref '<ref JSON>' "Conclusion"
ac-document read-cached-source-range --document-ref '<ref JSON>' 10 30
ac-document search-full-text --document-ref '<ref JSON>' --term "phrase"
ac-document search-equations --document-ref '<ref JSON>' --term "2.1"
```

These commands never discover or download a paper. If the source is identified
only by arXiv, DOI, INSPIRE, URL, or academic title, the ALC Skill may suggest
using optional ARC first; it must not install ARC silently.

## Cache Administration

List neutral derived entries, then select exact document or entry IDs. Removal
is a dry run unless `--yes` is supplied:

```bash
ac-document cache list
ac-document cache remove --entry-id '<exact entry id>'
ac-document cache remove --entry-id '<exact entry id>' --yes
```

Paper provider-response cache, academic identities, portable paper-cache
archives, and refresh remain outside AC Document and ALC.

Generic run controls are available as `ac-document status`, `stop`, and
`validate` for document workflows that publish durable runs.

## Help

```bash
ac-document --help
ac-document <command> --help
```

## PDF input with MinerU

For a PDF intended for translation or Companion, prefer the configured MinerU
route, including PDFs with a text layer. It preserves images and structure;
OCR extraction is not OCR proofreading. Read the project configuration at
`<project-dir>/.ac/mineru.json` through the commands below. This is the same file
used by Local Web for that project. The optional MinerU runtime is installed
separately; local mode currently supports macOS/Linux, and service mode also
supports Windows. The supported engine is MinerU 3.4.5 pipeline / API protocol 2.

### Resolve the configuration before declaring it missing

1. Use `<project-dir>/.ac/mineru.json` when it exists. Project configuration
   always wins, including an invalid configuration that needs correction.
2. Otherwise check `${ALC_CATALOG_DIR:-$HOME/.alc/catalog}/mineru.json`, the
   shared user default saved by LocalWeb. Read only the non-secret executable
   and language fields. If it specifies an existing local executable and no
   `api_url`, use `configure-mineru` below to write that executable and language
   into this project's configuration, then run `doctor-configured-mineru`.
   This reuse of an already configured local executable needs no new installation
   or user confirmation. Do not use a remote service from the shared default.
3. Only after both locations have been checked, report missing configuration.
   Absence from PATH does not mean MinerU is uninstalled; isolated virtual
   environments commonly expose it only through an absolute executable path.

### Missing runtime or configuration

When both configuration locations are absent, offer four choices:
1. Let Agent install and configure MinerU automatically.
2. Provide an existing local executable.
3. Connect a compatible MinerU service.
4. Explicitly use text-only extraction, explaining its limitations.

For automatic installation, first display the program-owned plan:

```bash
<skill-dir>/scripts/alc-runtime alc-ocr-proofread setup-mineru --project-dir <project-dir>
```

Summarize its installation directory, supported platform/Python checks and disk
reserve. Explain that packages and OCR model weights may be downloaded; exact
size/time depends on cache and network, so do not invent an ETA. After the user
selects automatic installation (or has already explicitly requested it), run:

```bash
<skill-dir>/scripts/alc-runtime alc-ocr-proofread setup-mineru \
  --project-dir <project-dir> --install --accept-downloads
```

In Codex, request host execution for this command through the normal tool approval
mechanism. Do not ask another chat confirmation for the already selected install.
Keep following the command until it exits. On success require both `configured`
and `inference_verified`, then continue the original PDF task automatically.
The installer uses the supported pinned pipeline version in a private venv,
reuses configured local runtimes, and adopts configuration only after real OCR
of a generated one-page sample. It does not modify system Python, install an OS
package manager, or switch to remote upload. If unsupported or failed, report the
specific reason and retained diagnostics; do not invent shell installation steps
or bypass the failed check. Manual installation remains an alternative via the
[official guide](https://opendatalab.github.io/MinerU/quick_start/).

For manual macOS/Linux setup with Python 3.11, the user can create an isolated
virtual environment and install `mineru[pipeline]==3.4.5` there. They should run a
small PDF with `mineru -p sample.pdf -o output -b pipeline` before configuring ALC;
the first inference may download model files. A version check alone does not
verify model readiness. Local Web includes `/mineru-help.html` with full steps.

If a configured path is missing, identify that path as unavailable rather than
claiming no installation exists. Correcting or replacing an explicit project
configuration requires the user's choice; never silently overwrite it.
If text-only extraction yields no usable text, retain the PDF and explain that
OCR is needed; wait for a usable configuration instead of delivering an empty result.

### Configure and run

```bash
<skill-dir>/scripts/alc-runtime ac-document configure-mineru \
  --config-path <project-dir>/.ac/mineru.json --executable /path/to/mineru --language en
# Alternative: --api-url https://ocr.example.org --token-env MINERU_SERVICE_TOKEN
<skill-dir>/scripts/alc-runtime ac-document doctor-configured-mineru \
  --config-path <project-dir>/.ac/mineru.json
<skill-dir>/scripts/alc-runtime ac-document parse-pdf-configured-mineru source.pdf \
  --config-path <project-dir>/.ac/mineru.json --job-dir <project-dir>/.ac/pdf-job
```

Before a service-mode parse, identify the configured destination and obtain
permission to upload this PDF unless the user has already authorized that
upload. Configuration alone is not upload authorization. Never print the token
value; the configuration contains only its environment variable name. Do not
switch to a remote service because local parsing failed. `doctor` checks
availability, not model completeness or OCR quality.

Keep the returned `source` and `manifest` together with all bundled files. For
Companion, use `alc-companion build <source> --pdf-source-manifest <manifest>`.
For translation, pass `--pdf-source-manifest <manifest>` to every source-taking
step (`detect-language`, `build-glossary`, `translate-blocks`). To render/export,
use `ac-document export-rich-document <source> --pdf-source-manifest <manifest>
--output-dir <publication>`. Do not pass a PDF manifest as an HTML manifest or
as a text-layer validator. Preserve coverage warnings and `proofread=false`.
Optional native-bundle proofreading uses `alc-ocr-proofread proofread-bundle`; read `alc-ocr-proofread.md` for model authorization and explicit candidate approval. Preserve the returned revised manifest when approved; extraction alone retains `proofread=false`.

Repeat the same parse command and job directory to resume a saved service task
or reuse completed results. Unknown submissions, missing server tasks and
interrupted local execution are not silently resubmitted. Inspect the reported
error before choosing a new job directory. If the user chooses text-only
extraction, explain that images and scanned pages are not supported in that
mode. Never report an empty text extraction as successful PDF processing.

These commands require the matching Foundation and ALC runtime containing PDF
support. If the pinned installed runtime lacks them, report the version mismatch;
do not fall back to an unverified ad hoc conversion or edit runtime pins.
