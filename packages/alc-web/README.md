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
- **PDF**: Requires text-only extraction confirmation. Images are excluded; formulas, tables and reading order are not verified. Convert scans to OCR Markdown or HTML externally first.
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
