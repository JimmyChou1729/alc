# Local Web 使用指南

[English](README.md) | 简体中文

通过浏览器创建翻译、伴读或原文阅读任务。

## 启动

需要 Python 3.11+、Git、Node.js（20.x 中的 20.19+ 或 22.12+）及 npm。在 ALC 仓库根目录执行：

```bash
python3 scripts/alc-web.py --project-dir local/reading-workspace
```

首次启动联网安装依赖并构建前端，随后自动打开浏览器。无需单独克隆 Foundation。Windows 使用 `python` 代替 `python3`。

## 创建任务

1. 在“模型与设置”选择 CLI 或添加 API 连接，填写 API 根地址、模型和密钥。
2. 输入 HTTPS 链接、DOI、arXiv ID，或上传 Markdown、HTML、TeX、PDF。
3. 选择处理方式、目标语言、并发和校对次数，然后开始任务。
4. 完成后打开或下载 Reader；运行期间可以暂停和恢复。

| 预设 | 并发批次 | 内容校对 |
| --- | ---: | --- |
| 快速初稿 | 4 | 不校对 |
| 标准 | 2 | 一轮 |
| 加强校对 | 2 | 最多两轮 |

并发可选 1–8，校对可选 0–2 轮，其他组合显示为“自定义”。校对对翻译和伴读均生效；关闭校对仍保留程序检查。并发越多不一定越快。

## 常用启动参数

在启动命令后追加参数：

| 参数 | 用途 |
| --- | --- |
| `--project-dir PATH` | 数据目录，默认 `~/ALC` |
| `--port 8766` | 指定端口，默认自动分配 |
| `--no-open` | 不自动打开浏览器 |
| `--foreground` | 在终端前台运行 |
| `--input URL` | 预填来源，不自动开始任务 |
| `--target-language zh-CN` | 预选目标语言 |

同一项目重复启动会复用已有服务。固定端口需在首次启动时指定。关闭浏览器不会停止任务。

只安装或检查环境：

```bash
python3 scripts/alc-web.py --runtime-setup
python3 scripts/alc-web.py --runtime-doctor
```

## 使用须知

- **模型**：CLI 使用官方服务的已有登录；自定义服务通过 API 连接配置，支持 Responses、Chat Completions 和 Anthropic Messages。
- **密钥**：保存在服务会话或受支持的系统凭据库中，不写入浏览器 Local Storage。系统密钥按工作区隔离；旧版保存的密钥需重新填写。
- **PDF**：使用已配置的 MinerU 识别并保留图片和结构，或明确选择仅文字提取；详见下方 PDF 识别。
- **恢复**：复用已完成内容和原任务配置；修改模型设置只影响新任务。已发出的请求仍可能产生用量。
- **费用**：仅供参考；CLI 订阅任务显示的 API 等价费用不是额外账单。
- **数据**：保存在本机，模型处理会将所需内容发送给所选服务。服务仅供本机访问。

| 项目目录内的路径 | 内容 |
| --- | --- |
| `.alc/web/` | 任务、设置和上传文件 |
| `.ac/cache/ac-document/` | 文档缓存 |
| `deliveries/<job-id>/reader.html` | Reader |

## 开发

使用本地 Foundation 源码：

```bash
export AC_FOUNDATION_REPO_ROOT=/path/to/ac-foundation
python3 scripts/alc-web.py --runtime-setup
```

使用已安装兼容依赖的 Python 环境，可设置 `ALC_WEB_PYTHON` 跳过自动安装。依赖约束位于 `plugins/alc/skills/alc/scripts/runtime-constraints.txt` 和 `packages/alc-web/runtime-constraints.txt`。

```bash
export ALC_WEB_PYTHON=/path/to/prepared/environment/bin/python
python3 scripts/alc-web.py --project-dir local/reading-workspace
```

构建和测试：

```bash
npm --prefix apps/web ci
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
python -m pytest --import-mode=importlib packages/alc-web/tests
```

前端修改后重新构建；非 editable 安装需重装改动的包。重启前先暂停或完成活动任务。

## PDF 识别

ALC 不自动安装 MinerU。运行 Local Web 后，可通过“PDF 识别”区域的
“查看 MinerU 安装与配置说明”打开内置 `/mineru-help.html`，查看手动安装、
独立环境、首次模型下载验证和服务配置步骤。说明随应用打包，可离线阅读。
未配置提示也提供此链接；“已配置”只表示配置已保存，不代表运行环境可用。
安装说明的源码位于 [`apps/web/public/mineru-help.html`](../../apps/web/public/mineru-help.html)。

在“模型与设置”选择 MinerU 本机可执行文件或已有服务，保存后可检测连接。
配置保存在 `<project>/.ac/mineru.json`，与同项目的 Agent 插件共用；这里只
保存 token 的环境变量名，不保存密钥值。本机运行需独立安装 MinerU 3.4.5
pipeline，已有服务需支持其 FastAPI protocol 2。连接远端服务时，新建任务
必须明确同意向界面显示的服务上传 PDF。

PDF 默认使用已配置的 MinerU，保留图片、表格、公式与页码来源，再进入翻译
或伴读；仍可明确选择仅提取文字。没有配置时可选择仅文字继续，扫描页需要
OCR。任务创建后固定配置，设置变更只影响新任务。识别阶段可以暂停/取消；
远端任务可能继续运行，恢复时查询原任务 ID，不自动重复提交不确定或过期
任务。OCR 提取不等于校对，缺失页与识别警告会保留。

当前源码需配套包含 OCR 接口的 Foundation；已安装发行版的 runtime pin
要在获得发布授权后同步更新。

本地文件上传不设固定文件大小上限。实际处理能力仍取决于内存、磁盘、文档解析限制及所选 OCR 服务。

任务详情会说明原文与目标语言相同而跳过翻译的情况。OCR 提醒会去重并按页归并；未单独输出的区域可能已合并，也可能漏识别，不直接判定整页失败。可选的 OCR 校对独立于翻译/伴读的内容校对：勾选“对照原PDF校对”即启用，并同意将原始页图和 OCR 文本发给所选模型，无需再次确认。默认由模型校对一遍后自动采用通过结构校验的修订并继续，不确定提示会保留，结果不会标记为已人工复查。Local Web 不再提供人工 OCR 编辑或确认环节。图片、公式、表格与页码映射保留。此功能需配套当前 ALC 与 Foundation 源码，尚未更新发行版 runtime pin。

旧版本停在人工复查的任务可通过普通“继续”操作恢复：复用已完成的模型校对结果，忽略旧人工草稿，保留不确定提示。

校对提示提供只读展开列表，仅展示模型报告的内容歧义；明确的版面差异、检查状态和执行诊断不会混入列表。歧义的原始说明可展开查看，不要求确认。提示数量不是错误数量。

新 PDF 校对使用通用 `ocr-triage.v2` 规则：确定的修订直接应用；前后相同的无效指令最多请模型纠正一次；真正的内容歧义保留原识别结果。“查看校对提示”只展示内容歧义，不再列出装饰性页眉页码、覆盖状态或执行失败。程序诊断保存在任务记录，应用失败另作技术提示。历史结果仅重新整理展示，不自动重跑或改写。

整体预计进度按实际路线分配阶段权重：本地 PDF、解析成 PDF 的链接、文字来源，
以及是否启用 OCR 校对、翻译或伴读分别计算。初始权重参考本地任务耗时，
按页数调整，尚非广泛设备基准。阶段内随有效运行时间缓慢增长，并结合成功页数
或批次数；不会超出当前阶段预算，暂停期间停止增长，交付成功才到 100%。
OCR 校对另显示已校对页数。链接解析成 PDF 时重新计算路线并保持显示进度不倒退。

任务卡片在模型名称后显示思考强度。新任务在模型目录提供默认强度时将其保存并传入执行；旧任务或服务未提供具体值时显示“effort 未记录”，不推测历史设置。
展开“查看校对提示”后直接显示未能应用的修订，提供页码、原文片段和中文分类说明，不计为
内容歧义；无需修改的提案和通用检查状态不进入此列表。零歧义不代表没有遗漏。

“翻译＋伴读”的翻译由 Companion 流程内部执行。任务页面根据实际进度显示术语整理、翻译与审查、伴读生成等子阶段。

可编辑 Reader 使用独立的随机本地端口，与任务管理页面隔离。只有经过校验的交付 HTML 可以通过不可猜测的只读地址访问；该端口不提供任务 API。Reader 保留脚本和网络限制，同时允许用户选择本地保存文件夹。服务重启后请从任务页面重新打开 Reader。
独立 Reader 在校验原交付文件后使用当前版本的阅读器脚本，保留原始交付文件及内容数据不变，使已有文档也能获得编辑和显示修复。未知格式 HTML 不替换脚本。

### Agent 插件历史

新版 Agent 命令会通过独立的 `alc-catalog` 登记项目位置，无需预先安装或
启动 LocalWeb。LocalWeb 的最近任务列表会自动显示登记项目中的伴读、翻译
和 OCR 校对记录，标注“Agent 插件”。可打开已生成的 Reader，或下载可验证的
任务结果数据；暂停、恢复和删除仍由原插件负责，网页不会接管任务。

以前未登记的项目，可点击侧栏“导入插件项目”，填写原来的 `--project-dir`
目录。导入只添加位置索引，不复制内容或重新执行任务。默认索引位于
`~/.alc/catalog/`；若设置 `ALC_CATALOG_DIR`，插件和网页必须使用相同目录。
原文件被删除时无法恢复；项目移动后需重新导入。LocalWeb 自己管理的内部
项目不会重复显示为插件记录。语言检测和术语生成中间步骤不会单独列为文档。

本地 MinerU 配置保存后，会同步到 `~/.alc/catalog/mineru.json` 作为新项目默认值
（`ALC_CATALOG_DIR` 可覆盖目录）。项目 `.ac/mineru.json` 始终优先。
Agent 检查两处配置后才判断是否缺少识别工具；不会仅因 PATH 中没有 `mineru`
就要求重新安装。共享默认值只支持本地可执行文件，不继承远程上传目的地或凭据。
