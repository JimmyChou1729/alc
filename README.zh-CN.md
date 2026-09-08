# Agentic Learning Copilot（ALC）

[English](README.md) | 简体中文

ALC 将源文档处理为译文、交互式 HTML 阅读器，以及与原文对应的伴读内容。

## 安装

目前，ALC 提供两种使用方式：Local Web 本地工作台和 Agent 插件。

**Local Web 本地工作台**在自己的电脑上运行。通过浏览器配置模型、创建翻译或
伴读任务，以及打开、下载 Reader。

**智能体插件**让 Codex、Claude Code 或 DeepSeek Harness 根据自然语言指令
执行 ALC 工作流。

两个入口使用同一套 Python 工作流包。模型配置与任务状态不会自动互通；
安装插件也不会启动 Local Web。

### Local Web

需要 Python 3.11+ 和 Git。从源码构建前端还需要 Node.js 20.x 中的 20.19+
或 22.12+，以及 npm。已安装的 Web 包自带前端，直接运行 `alc-web` 无需 Node.js。

```bash
git clone https://github.com/tririver/alc.git
cd alc
python3 scripts/alc-web.py --runtime-setup
```

Windows 将 `python3` 换成 `python`。已有源码时，在 ALC 目录执行最后一条命令即可。
首次安装需要联网，自动构建前端并准备独立 Python 环境和锁定版本的 Foundation 依赖。
无需另行克隆 Foundation，也无需手动激活环境。

### 智能体插件

Codex：

```bash
codex plugin marketplace add tririver/alc --ref stable
codex plugin add alc@alc
```

Claude Code：

```text
/plugin marketplace add tririver/alc@stable
/plugin install alc
```

DeepSeek Harness：

```bash
dsh plugin --profile alc add github:tririver/alc
```

## 使用

### Local Web

在 ALC 目录执行以下命令，启动服务并自动打开网页：

```bash
python3 scripts/alc-web.py --project-dir local/reading-workspace
```

任务创建、凭据、输入格式、启动参数及开发环境说明见
[Local Web 使用指南](packages/alc-web/README.zh-CN.md)。

### 智能体插件

安装后，在智能体中选择 ALC，发送文档链接或附上本地文件，并说明处理要求。
以下是**发送给智能体的聊天指令，不是终端命令**：

> 用 @ALC 为附件生成简体中文伴读，面向初学者讲解。

> 用 @ALC 将 https://arxiv.org/html/2609.04315v1 翻译成简体中文。只翻译，并发 8，不校对，交付 HTML Reader。

可以在同一条消息中指定这些选项：

| 选项 | 写法与省略时的行为 |
| --- | --- |
| 处理方式 | 翻译、伴读或原文 Reader。请说明想要的结果。 |
| 目标语言 | 如简体中文、英文；建议明确写出，避免歧义。 |
| 处理并发 | 每个任务同时处理 1–8 个批次；默认 **2**。 |
| 内容校对 | **不校对**、**校对一轮**、**最多两轮**；默认 **一轮**，对翻译和伴读均生效。 |
| 模型与思考强度 | 可指定可用的模型和它支持的 effort。Codex 当前默认 `gpt-5.6-luna` / `medium`，其他服务使用各自解析出的默认值。 |
| 其他要求 | 术语、行文风格、读者水平或输出目录等。 |

也可以直接说预设：**快速初稿 = 并发 4 / 不校对**，**标准 = 并发 2 / 校对一轮**，
**加强校对 = 并发 2 / 最多两轮**。其他搭配按自定义参数执行。
并发越多不一定越快，还取决于电脑性能、网络和模型服务限制。
“不校对”仍保留程序对原文和输出的检查；“最多两轮”可以在无需修正时提前结束。
这些处理参数适用于翻译和伴读。

插件按需准备运行环境并使用锁定的 Git revision，无需手动克隆仓库。
详细工作流见 [Skill 指南](plugins/alc/skills/alc/SKILL.md)。

## 包与架构

| 包 | 职责 |
| --- | --- |
| [`alc-ocr-proofread`](packages/alc-ocr-proofread/README.md) | 根据 PDF 页面图像校对带页码映射的 OCR |
| [`alc-translate`](packages/alc-translate/README.md) | 语言识别、术语表、翻译和校对 |
| [`alc-render`](packages/alc-render/README.md) | 文档组合与交互式 HTML |
| [`alc-companion`](packages/alc-companion/README.md) | 与原文对应的伴读构建和修订 |
| [`alc-web`](packages/alc-web/README.zh-CN.md) | 本地 HTTP 应用、任务队列与 Reader 交付 |

[AC Foundation](https://github.com/tririver/ac-foundation) 负责持久化任务、模型执行、
通用文档及生成—审核编排。ALC 不依赖 ARC；可选的研究流程由 Skill 协调。

## 开发

前端位于 `apps/web`，本地服务位于 `packages/alc-web`。
Foundation 显式开发覆盖、前端构建及已有 Python 环境的使用方法见
[开发环境说明](packages/alc-web/README.zh-CN.md#开发)。

在准备好的环境中，从仓库根目录运行测试和构建：

```bash
python -m pytest --import-mode=importlib packages/*/tests tests
scripts/build-packages.sh
```

打包 `alc-web` 前应先构建前端。生成文件与本地实验放在被忽略的 `local/` 目录下。
仓库规则见 [AGENTS.md](AGENTS.md)。

## 发布

在干净的工作区执行：

```bash
scripts/release-alc.sh VERSION
```

`VERSION` 使用 `MAJOR.MINOR.PATCH` 格式。发布脚本统一更新包和插件版本。
本项目不假设包已在 PyPI 发布。

## 许可证

MIT，见 [LICENSE](LICENSE)。
