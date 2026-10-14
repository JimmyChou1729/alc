# Host execution in Work and dot

Use this manual when the current agent can run shell/Python and inspect files,
but model work should use that agent or its subagents. A plugin does not provide
these capabilities itself. Check writable persistent project storage, network
access for initial setup, and the actual tools available in this session.

## Select the route before starting

Declare the capabilities actually available; do not infer independent contexts
or model selection from a platform name. For a host without subagents:

```bash
export AC_LLM_HOST_COORDINATOR='{"coordinator_id":"current-agent","default_provider":"host","native_fallback":false,"fresh_context":false,"model_selection":false}'
<skill-dir>/scripts/alc-runtime doctor
<skill-dir>/scripts/alc-runtime ac-llm doctor --provider host --environment
```

Run explicit `alc-runtime setup` if the private runtime is not ready. After an
installation failure, inspect the retained diagnostic and use `setup --retry`
only when its cause has been addressed. Doctor does not install dependencies.
Keep existing user cache configuration; use writable project/runtime paths,
never change HOME or system permissions to work around the host environment.

Work and dot normally select Host. In Codex, Claude Code or Kimi Code, keep the
native provider as `default_provider` and enable `native_fallback` only when
host execution is available and permitted. The Foundation policy falls back
only for confirmed native unavailability before launch. Authentication or
permission refusal, a user stop, and an already-started native session do not
permit a switch. DSH retains its native route.

For Host generation use `--provider host`, omit `--model` and effort unless the
user requests them. The recorded default is `inherit`, with effort unset. A tier
is not an effort setting. With explicit preferences, pass the exact provider,
model and effort to the owning CLI. Use actual subagent selection tools when
available; otherwise the exported `use_host_model` policy permits the host
model with truthful metadata. Never claim a requested model was selected when
it was not. Keep provider/model/review policy frozen on owning resume.

## Complete pending tasks

Python returns a typed pause containing `awaiting_host`; it does not wait for
the calling chat. Read the returned run identity and `details.run_root` /
`details.run_id` (possibly nested in the public resume descriptor). Do not guess
private paths or create a second run to recover one that is already paused.

For translation generation and resume, use `resume.details.run_root`, `run_id`,
and `host_task_id`. A read-only `alc-translate status` exposes the same details
under `data.run.resume.details` and the selected `data.steps` entry. Its outer
`status=completed` means the query completed; check `data.run.status` for the
workflow state. After upgrading an already-paused project, query status again:
the current location is supplied without changing its saved task or receipt.
The language/glossary/translation tasks share their owning workflow's run ID.
Use `host-pending` at that location to list other pending workers.

```bash
<skill-dir>/scripts/alc-runtime ac-llm host-pending --run-root <run-root> --run-id <run-id>
<skill-dir>/scripts/alc-runtime ac-llm host-export \
  --run-root <run-root> --run-id <run-id> --task-id <task-id> \
  --output-directory <project-dir>/.alc/host-exports/<task-id>
```

Read the exported control metadata, output contract, accepted history and
materialized input files. Parse `task.json` with Python and select the control
fields; do not dump embedded base64 or full books into the chat. Inspect page
images with the host's image tools when the task requires vision. Report a
missing capability instead of claiming images were examined. Read chapter
materials in bounded pieces while preserving their full coverage.

Complete `response.template.json` against its response schema. If its output
contract is `ac.llm.host_turn.v1`, return the entire envelope (`state`, `result`,
`host_request`). Source-reading requests go through the declared read-only
broker: submit a `request_host` turn, resume the workflow, then read the exported
continuation before finishing. Do not fabricate a source-read receipt. The
source broker and the execution coordinator have different responsibilities.

Use the current agent or available fresh-context subagents as allowed by the
export. Respect any required worker separation and actor binding; do not invent
subagents. Record actual actor identity and known model/effort, using null for
unknown metadata. Cap dispatched subagents at the host's available capacity;
Python worker limits do not imply an equal number of available agent contexts.
Companion guide/reviewer rounds require fresh contexts under the existing
proposer-reviewer contract. Without them, report `host_fresh_context_unavailable`
and retain accepted work; do not disable independence to force completion.

```bash
<skill-dir>/scripts/alc-runtime ac-llm host-submit \
  --run-root <run-root> --run-id <run-id> --response <response-file>
```

A successful submission is not workflow completion. Resume the owner:

- Translation: `alc-translate resume --project-dir <project-dir>` with the same
  execution settings. It owns language, glossary, translation and review stages.
- Companion: `<skill-dir>/scripts/alc-companion resume --project-dir <project-dir>`
  with the saved processing settings and authority.
- PDF recognition: repeat the same `ac-document parse-pdf-host` invocation and
  retain its run ID, PDF and output directory; see `host-pdf.md`.
- OCR proofreading: use `alc-ocr-proofread resume` or `resume-bundle`, as returned
  by the owning command. Host submission and explicit OCR review decisions are
  distinct. Supply `--input` only for the response the public resume requests.

Continue until completion, user stop or a genuine missing capability/input.
Identical submissions and completed replay are safe; conflicting submissions
must be investigated. Do not mutate private task state, hashes, accepted
results or installed packages. A waiting Host task is neither a timeout nor a
reason to publish untranslated source as a completed translation.

## Delivery and capability limits

Deliver a validated standalone HTML Reader and requested native source files.
Keep images, formulas and source anchors. Preview and download support depend
on the host; test downloaded HTML in a browser when previews restrict scripts.
Do not start Local Web, deploy a server, or assume localhost audio endpoints
are accessible from a cloud user's browser. Failed delivery should retry only
the export/render stage, retaining accepted translation and Companion work.

Offline fake-host tests validate the protocol and recovery. They do not prove
visual OCR accuracy, a particular account's tool permissions, or long-document
quality. Those require small real-host document samples after installation.
