# Local Web guide

English | [简体中文](README.zh-CN.md)

Create translation, Companion or source-only reading tasks in your browser.

## Launch

Requires Python 3.11+, Git, Node.js (20.19+ within 20.x, or 22.12+) and npm. From the ALC repository root:

```bash
python3 scripts/alc-web.py --project-dir local/reading-workspace
```

First launch downloads dependencies, builds the frontend and opens your browser. No separate Foundation clone is needed. On Windows, use `python` instead of `python3`.

## Create a task

1. In **Model settings**, choose a CLI or add an API connection with its API root URL, model and key.
2. Enter an HTTPS URL, DOI or arXiv ID, or upload Markdown, HTML, TeX or PDF.
3. Choose the output, target language, concurrency and review rounds, then start.
4. Open or download the Reader when complete; pause and resume as needed.

| Preset | Concurrent batches | Content review |
| --- | ---: | --- |
| Quick draft | 4 | None |
| Standard | 2 | One round |
| Enhanced review | 2 | Up to two rounds |

Choose 1–8 concurrent batches and 0–2 review rounds; other combinations show **Custom**. Review applies to translation and Companion; disabling it retains programmatic checks. More concurrency does not guarantee higher speed.

## Launch options

Append options to the launch command:

| Option | Purpose |
| --- | --- |
| `--project-dir PATH` | Data directory; default `~/ALC` |
| `--port 8766` | Fixed port; otherwise selected automatically |
| `--no-open` | Do not open the browser |
| `--foreground` | Run in the terminal foreground |
| `--input URL` | Prefill the source without starting a task |
| `--target-language zh-CN` | Preselect the target language |

Launching the same project again reuses its service. Choose a fixed port on first launch. Closing the browser does not stop tasks.

Install or inspect the environment without starting a service:

```bash
python3 scripts/alc-web.py --runtime-setup
python3 scripts/alc-web.py --runtime-doctor
```

## Notes

- **Models**: CLI connections use existing official-service logins. Configure custom services through API connections using Responses, Chat Completions or Anthropic Messages.
- **Keys**: Stored in the service session or a supported OS credential store, not browser Local Storage. Saved keys are isolated by workspace; keys saved by older versions must be entered again.
- **PDF**: Uses configured MinerU for OCR and image/structure preservation, or explicit text-only extraction. See PDF OCR below.
- **Resume**: Reuses completed work and the original task configuration. Model setting changes apply to new tasks. Requests already sent may still incur usage.
- **Cost**: Reference only. API-equivalent prices shown for CLI subscription tasks are not additional bills.
- **Data**: Stored locally; model processing sends required content to the selected service. The service is for local access only.

| Path within the project | Contents |
| --- | --- |
| `.alc/web/` | Tasks, settings and uploads |
| `.ac/cache/ac-document/` | Document cache |
| `deliveries/<job-id>/reader.html` | Reader |

## Development

Use a local Foundation checkout:

```bash
export AC_FOUNDATION_REPO_ROOT=/path/to/ac-foundation
python3 scripts/alc-web.py --runtime-setup
```

Set `ALC_WEB_PYTHON` to an environment with compatible dependencies to bypass setup. Constraints are in `plugins/alc/skills/alc/scripts/runtime-constraints.txt` and `packages/alc-web/runtime-constraints.txt`.

```bash
export ALC_WEB_PYTHON=/path/to/prepared/environment/bin/python
python3 scripts/alc-web.py --project-dir local/reading-workspace
```

Build and test:

```bash
npm --prefix apps/web ci
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
python -m pytest --import-mode=importlib packages/alc-web/tests
```

Rebuild after frontend edits; reinstall changed packages in non-editable environments. Pause or finish active tasks before restarting.

## PDF OCR

In Settings, choose MinerU local executable or an existing service and save/test
the configuration. It is shared with the agent plugin via
`<project>/.ac/mineru.json`; credential values are not stored there. Local mode
requires a separately installed MinerU 3.4.5 pipeline runtime; connected mode
requires its FastAPI protocol 2 service. Remote HTTPS uploads require explicit
consent to the displayed service when creating each task.

PDF tasks default to the saved MinerU configuration and preserve images, tables,
formulas and page provenance through translation/Companion. Text-only extraction
remains an explicit option. Missing OCR configuration offers text-only consent;
scanned pages require OCR. A task freezes its configuration; changing settings
affects new tasks only. OCR progress appears as a separate phase. Pause/cancel
stops local work; remote tasks may keep running and resume queries their saved
IDs. Unknown or expired submissions are not automatically repeated. OCR
extraction is not proofreading, and coverage warnings remain visible.

This source change needs the matching Foundation checkout containing the OCR
APIs; installed release pins are updated only during an authorized release.

Local file uploads have no fixed byte-size ceiling. Processing still depends on available memory, disk, document-parser limits and the selected OCR service.

Task details explain when translation is skipped because source and target languages match. OCR notices are deduplicated and grouped by page; un-emitted regions may be merged text or missing OCR, so they are not labeled as failed pages. Optional PDF image-based OCR proofreading is separate from translation/Companion content review. Selecting the OCR proofreading checkbox enables sending original page images and OCR text to the selected model; there is no second consent checkbox. By default, one model proofreading pass adopts structurally valid revisions and continues automatically, retaining uncertainty warnings without claiming human review. Local Web has no manual OCR editing or confirmation step. Completed candidates reuse saved model work, including compatible OCR/Web code updates before any downstream work starts. Figures, formulas, tables and page mappings are preserved. This source feature requires matching ALC and Foundation packages; runtime release pins are unchanged.

Legacy tasks paused at the removed review step can use the ordinary Resume control; it reuses the completed model candidate, ignores old manual drafts, and preserves uncertainty warnings.

OCR notices have a read-only disclosure for content ambiguity. Explicit layout differences, coverage status and execution diagnostics are excluded. Original ambiguity explanations remain accessible; no confirmation is required and counts do not mean verified errors.

New PDF runs use the shared `ocr-triage.v2` policy: apply confirmed edits, repair
no-op proposals at most once, and preserve genuinely ambiguous content. The
notice disclosure shows only content ambiguity; page furniture, coverage status
and application failures are not uncertainties. Technical diagnostics stay in
the run and failed applications have a separate warning. Legacy results are
normalized for display without resubmission or rewriting their output.

Agent history is discovered through the independent `alc-catalog` project index,
including projects registered before Web was installed. Settings supports
explicit import of older `--project-dir` directories. Records refresh from the
Agent project, including subsequent run status and available workflow progress.
Web can rename or hide its local list entries; project files and Agent execution
remain unchanged. Reader viewing and verified result downloads are supported,
but Web never claims or resumes an Agent run. The default catalog is `~/.alc/catalog`;
set `ALC_CATALOG_DIR` consistently in both entry points to override it. Missing
project files cannot be restored from the path index.

## Optional local speech

Settings supports optional Kokoro, Piper and KittenTTS installation, independent
Chinese/English previews and saved default voices. The Reader lists installed
model voices first and system voices afterward; selecting a voice selects its
engine automatically. Preview uses unsaved selections. No model is downloaded
by opening a document, and exported HTML contains no local connection credential.
See [Local TTS](../alc-render/LOCAL_TTS.md) for setup and standalone HTML usage.
