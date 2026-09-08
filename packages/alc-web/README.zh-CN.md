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
- **PDF**：需确认仅提取文字，不保留图片或核验公式、表格及阅读顺序。扫描版需先在外部转换为 OCR Markdown 或 HTML。
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
