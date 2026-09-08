# Agentic Learning Copilot (ALC)

English | [简体中文](README.zh-CN.md)

ALC turns source documents into translations, interactive HTML readers, and
source-anchored learning companions.

## Install

ALC currently offers two ways to use it: Local Web and an agent plugin.

**Local Web** runs a document workspace on your computer. Configure models,
create translation or Companion tasks, and open or download Readers in a browser.

**Agent plugin** lets Codex, Claude Code, or DeepSeek Harness run ALC workflows
from natural-language instructions.

Both entry points use the same Python workflow packages. Their model settings
and task state are not automatically shared; the plugin does not start Local Web.

### Local Web

Requirements: Python 3.11+ and Git. Building the frontend from source also needs
Node.js 20.19+ in the 20.x line, or 22.12+, with npm. An installed Web package
includes its frontend and can run through `alc-web` without Node.js.

```bash
git clone https://github.com/tririver/alc.git
cd alc
python3 scripts/alc-web.py --runtime-setup
```

On Windows, replace `python3` with `python`. If you already have the source,
run only the last command from the ALC directory. Initial setup needs internet
access to build the frontend and prepare a private Python environment with pinned
Foundation dependencies. No separate Foundation clone or manual activation is needed.

### Agent plugin

Codex:

```bash
codex plugin marketplace add tririver/alc --ref stable
codex plugin add alc@alc
```

Claude Code:

```text
/plugin marketplace add tririver/alc@stable
/plugin install alc
```

DeepSeek Harness:

```bash
dsh plugin --profile alc add github:tririver/alc
```

## Usage

### Local Web

From the ALC directory, run this command to start the service and open the webpage:

```bash
python3 scripts/alc-web.py --project-dir local/reading-workspace
```

See the [Local Web guide](packages/alc-web/README.md) for task creation,
credentials, supported inputs, launch options, and development setup.

### Agent plugin

After installation, select ALC in your agent and send a document link or attach
a local file with your request. These are **chat instructions, not terminal commands**:

> Use @ALC to create a Simplified Chinese Companion for the attached document. Explain it for a beginner.

> Use @ALC to translate https://arxiv.org/html/2609.04315v1 into Simplified Chinese. Only translate, use 8 concurrent batches, skip content review, and deliver an HTML Reader.

You can specify these options in the same message:

| Option | What to say / behavior when omitted |
| --- | --- |
| Result | Translation, Companion, or original-only Reader. State the result you want. |
| Target language | For example, Simplified Chinese or English; specify it to avoid ambiguity. |
| Concurrency | 1–8 concurrent batches per task; default **2**. |
| Content review | **0** (none), **1** round, or **at most 2** rounds; default **1**. Applies to translation and Companion. |
| Model and effort | Specify an available model and supported effort. Codex's current default is `gpt-5.6-luna` / `medium`; other providers resolve their own defaults. |
| Additional requirements | Terminology, writing style, intended audience, or output directory. |

Presets are shorthand: **fast draft = 4 / 0**, **standard = 2 / 1**, and
**strengthened review = 2 / 2** (concurrency / review rounds). Other combinations
are custom. More concurrency does not guarantee faster processing: hardware,
network and model-service limits also matter. Zero review skips model content
review but retains source/output validation; two rounds may finish early.
These settings concern translation and Companion.

The plugin prepares its runtime on demand using pinned Git revisions; no manual
repository clone is needed. See the [Skill guide](plugins/alc/skills/alc/SKILL.md)
for detailed workflows.

## Packages and architecture

| Package | Responsibility |
| --- | --- |
| [`alc-ocr-proofread`](packages/alc-ocr-proofread/README.md) | PDF-vision review of page-mapped OCR |
| [`alc-translate`](packages/alc-translate/README.md) | Language detection, glossary, translation and review |
| [`alc-render`](packages/alc-render/README.md) | Document composition and interactive HTML |
| [`alc-companion`](packages/alc-companion/README.md) | Source-anchored Companion builds and revisions |
| [`alc-web`](packages/alc-web/README.md) | Local HTTP application, task queue and Reader delivery |

[AC Foundation](https://github.com/tririver/ac-foundation) owns durable jobs,
model execution, neutral documents, and proposer-reviewer orchestration.
ALC does not depend on ARC; optional research can be coordinated by the Skill.

## Development

The frontend is in `apps/web`; the local server is in `packages/alc-web`.
See the [development setup](packages/alc-web/README.md#development) for explicit
Foundation overrides, frontend builds and an existing Python environment.

Run tests and build distributions from the repository root in a prepared environment:

```bash
python -m pytest --import-mode=importlib packages/*/tests tests
scripts/build-packages.sh
```

Build the frontend before packaging `alc-web`. Keep generated files and local
experiments under ignored `local/` paths. See [AGENTS.md](AGENTS.md) for repository
rules.

## Release

From a clean worktree, run:

```bash
scripts/release-alc.sh VERSION
```

`VERSION` uses the `MAJOR.MINOR.PATCH` format. The release script coordinates
package and plugin versions. No PyPI publication is assumed.

## License

MIT. See [LICENSE](LICENSE).
