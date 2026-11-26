# AgentRelay Portable

[![Tests](https://github.com/FriedOnion2/agent-relay-portable/actions/workflows/tests.yml/badge.svg)](https://github.com/FriedOnion2/agent-relay-portable/actions/workflows/tests.yml)
[![Lint](https://github.com/FriedOnion2/agent-relay-portable/actions/workflows/lint.yml/badge.svg)](https://github.com/FriedOnion2/agent-relay-portable/actions/workflows/lint.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/FriedOnion2/agent-relay-portable?include_prereleases)](https://github.com/FriedOnion2/agent-relay-portable/releases)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

**中文** | [English](README.en.md)

**在本机浏览、导出和迁移 AI 编程助手的对话与 Skill，并可打包到移动盘，在另一台设备恢复。**

支持 **WorkBuddy、WorkBuddy AI 国际版、DeepSeek Harness（DSH）、CodeBuddy、Claude Code、Claude Agent SDK、OpenAI Codex、腾讯元宝 JSON 导出、Gemini CLI、Gemini Apps 与 Google Antigravity**，提供中英文网页和命令行，适用于 Windows、macOS、Ubuntu / Linux。

**WorkBuddy 国内版与国际版已分开识别**：国内版使用 `workbuddy` / `~/.workbuddy`，国际版使用 `workbuddy_ai` / `~/.workbuddy-ai`。两版拥有独立的来源、目标、目录配置和原生包标识，不自动混合会话；DSH、CodeBuddy 也保持独立。两版之间及各自与 DSH、Claude Code、Codex 的双向文件转换已加入回归验证；CodeBuddy CLI、Claude Agent SDK 也支持双向文件转换，元宝支持从兼容 JSON 迁出。文件转换通过不代表客户端续聊通过，详见[互传验证矩阵](docs/reference/compatibility.md#workbuddy-国内版与国际版互传)。

![AgentRelay 任务首页：迁移会话、跨设备搬运、全文搜索与 Skill 资产](docs/images/task-home.jpg)

> 🔒 **数据只在本机处理。** 服务只监听本机地址，不上传会话，不调用模型；迁移前先预览“保留 / 降级 / 丢弃 / 未知”，确认后才写入。

## 能做什么

- **查看与导出**：按来源浏览、搜索、预览会话，导出为 Markdown。
- **跨软件迁移**：把会话转换到 WorkBuddy、WorkBuddy AI 国际版、DSH、Claude Code、Codex，保留可表达的正文、思考和工具历史。
- **跨设备存储**：把对话、Skill 保存为原生 ZIP 包，复制到另一台设备后恢复到对应软件。
- **全文搜索**：本地 SQLite/FTS5 索引，支持中文短词、中英混合与来源 / 项目 / 时间 / 工具筛选。
- **提炼 Skill 草稿**：从多条相似的历史会话提炼带证据的 Skill 草稿，由你审核后导出，不自动安装或执行。
- **Windows ↔ Ubuntu**：双系统间搬迁同款软件的原生记录。

- **增量备份**：在「跨设备搬运」选择任意内置 Agent，可按项目路径和起始日期筛选会话。用上一次完整包或增量包作为基线，仅备份新增或变化的内容。保留完整包和各次增量，按顺序恢复。已有 ID 默认跳过；如需保留变化版本，请选择恢复为副本。DSH 子会话的父记录需已存在或在当前包中。
- **备份体检**：选择 ZIP 或填写路径，点击「备份体检」查看文件校验、会话／Skill 数量和原始导出错误。映射目录后再预览恢复冲突。
- **Claude 桌面接力**：在会话详情点「接力到 Claude 桌面」，检查下载的 TXT，并将其附到 Claude 桌面的新聊天中发送下一条请求。该流程会新建聊天。 [Claude 的文件上传说明](https://support.claude.com/en/articles/8241126-upload-files-to-claude)
- **中英切换**：用页面右上角的 `English`／`中文` 切换。CLI 可用 `relay --lang en` 或 `RELAY_LANG=en`。

## 快速开始

**正式版：[v1.6.0](https://github.com/FriedOnion2/agent-relay-portable/releases/tag/v1.6.0)**。各 Agent 的实测范围见下方支持表与 [兼容状态](docs/reference/compatibility.md)。

当前正式版本：**1.6.0**。便携启动与迁移验证范围见兼容状态；正式版不表示所有客户端均支持恢复后续聊。

**普通用户**：到 [Releases](https://github.com/FriedOnion2/agent-relay-portable/releases) 下载 `AgentRelay-<版本>-universal.zip`，完整解压后运行启动器。总包内置 Python 与依赖，**无需另装 Python / Node.js，首次启动不联网下载**。不要选择 GitHub 自动生成的 Source code 压缩包。

| 设备 | 启动入口 | 支持范围 |
|---|---|---|
| Windows | `启动_AgentRelay.bat` | Windows 10/11 x64 |
| macOS | `AgentRelay.app` 或 `bash 启动_AgentRelay.command` | Apple Silicon：macOS 14+；Intel：macOS 15+ |
| Linux | `bash 启动_AgentRelay.sh` | Ubuntu 22.04+ / glibc 2.35+ x64 |

启动后在浏览器打开提示的地址（默认 `http://127.0.0.1:8745/`）。退出请点网页右上角「退出服务」。macOS 应用未经 Apple 公证，被系统阻止时的处理见 [安装与启动](docs/guide/install.md)。

**从源码运行**（需要 Python 3.8+）：

```sh
python -m pip install -r requirements-optional.txt   # 读写 DSH 压缩历史需要 zstandard
python app/cli.py serve                              # 启动网页
python app/cli.py list codex                         # 命令行：列出某来源的会话
python app/cli.py export codex <会话id> -o out.md    # 导出 Markdown
python app/cli.py transfer codex <会话id> --to dsh --dry-run   # 先预览迁移
python app/cli.py --lang en list codex                # 命令行输出改为英文（或设 RELAY_LANG=en）
```

**用 pip / pipx 安装**（只用命令行和网页，不需要 U 盘便携）：

```sh
pipx install git+https://github.com/FriedOnion2/agent-relay-portable   # 或 pip install .
relay serve
relay list codex
```

这种方式下配置、日志和存储包放在每用户数据目录（Linux `~/.local/share/agent-relay`，macOS `~/Library/Application Support/AgentRelay`，Windows `%APPDATA%\AgentRelay`），可用 `RELAY_PORTABLE_ROOT` 指定别处。

Ubuntu / macOS 可用 `Ubuntu首次准备.sh` / `Mac首次准备.command` 自动建立隔离环境。完整步骤见 [安装与启动](docs/guide/install.md)。

## 支持的来源

| 来源 | 默认会话位置 | 读取 / 导出 | 作为迁移目标 | 实机验证 |
|---|---|:-:|:-:|---|
| WorkBuddy 国内版 | `~/.workbuddy/projects` | ✅ | ✅ | 仅文件层核对 |
| WorkBuddy AI 国际版 | `~/.workbuddy-ai/[user-…/]projects` | ✅ | ✅ | 5.8.4 原生读取及 ZIP 文件往返实测；不登记桌面历史索引，恢复副本续聊未通过验证 |
| DeepSeek Harness / DSH | `~/.dsh/sessions` | ✅（v0–v4） | ✅ | 真实客户端已验证 |
| CodeBuddy CLI / IDE | `~/.codebuddy/projects` 等 | ✅ | CLI | CodeBuddy Code 2.187.0 在 Windows 识别迁入 ID；IDE 仅迁出 |
| Claude Code | `~/.claude/projects` | ✅ | ✅ | 导出已验证 |
| Claude Agent SDK | `~/.claude/projects`（与 Claude Code 共享） | ✅ | ✅ | 官方 SDK 可列出并读取迁入问答 |
| OpenAI Codex | `~/.codex/sessions` | ✅ | ✅ | 真实客户端已验证 |
| 腾讯元宝 JSON 导出 | 便携目录 `imports/yuanbao` | ✅ | 仅导出文件存包恢复 | 合成 JSON 回归，未验证原生客户端 |

### Gemini 与 Antigravity

开发版支持从任意已接入的来源导出 Gemini CLI 会话。在会话详情点「导出 Gemini CLI 会话」，然后在目标项目运行 `gemini --session-file session-agentrelay.json`。CLI 也可运行 `relay gemini-session <来源> <ID> -o session-agentrelay.json`。文件含按角色排列、经过敏感值匹配脱敏的问答正文。源工具、附件与思考不会进入导入文件。Gemini CLI 0.71.1 的项目列表可找到导入记录。

Antigravity 可读取 `brain/<会话>/.system_generated/logs/transcript_full.jsonl` 的用户和助手正文，同一会话优先使用完整版。默认扫描桌面版、IDE 和 CLI 的三个数据目录；在环境设置指定目录后只扫描该位置。要把上下文带回反重力或元宝，在详情中点「导出新聊天接力 TXT」，将内容放入新聊天。这一步需要手动操作，目标客户端不会因此出现还原的原生历史线程。

| 来源 | 默认位置 | 支持范围 |
| --- | --- | --- |
| Gemini CLI | `~/.gemini/tmp/<项目>/chats/` | JSON／JSONL 会话、工具调用与结果、文本思考摘要 |
| Google Antigravity | `~/.gemini/antigravity/` | `brain/<任务>/` 下的任务、实施计划和走查 Markdown，以及数据目录顶层或 `exports/` 下手工保存的 Markdown／TXT |

Windows 用户可以展开 Gemini 桌面版的侧栏，在 AgentRelay 首页进入 **Gemini Apps → 浏览会话**，查看窗口里的最近聊天。在 Gemini 打开所需聊天，回到 AgentRelay 刷新，选择「保存当前聊天文字」。每次保存当前已加载的问答文字，内容相同会自动跳过。图片、附件和未加载的早期消息不在这份快照中。

Gemini 桌面端和网页端使用独立的 **Gemini Apps** 来源。在 Google Takeout 选择「我的活动 → Gemini Apps」和 JSON 格式，解压后在该来源选择活动 JSON 文件。每条活动单独保存，重复导入同一内容自动跳过。已导入的活动可搜索、导出、迁出及进行完整或增量备份。在会话详情选择「接力到 Gemini」可下载 TXT，将它附到 Gemini 新聊天，再发送下一条请求。 [Google Takeout 导出说明](https://support.google.com/gemini/answer/16920332)

在「环境设置」修改来源目录，在「迁移会话」查看、导出 Markdown 或转到可写的 Agent。两者支持全文搜索、会话 ZIP 和完整／增量备份。恢复时项目目录可留空，记录写入便携目录的 `imports/gemini` 或 `imports/antigravity`。Gemini 支持范围是 CLI 本地记录。Antigravity 恢复单位为单份产物或文本。若要保留图片附件、恢复客户端原生会话或同步云端历史，继续使用各客户端的对应功能。

元宝入口位于「迁移会话 → 腾讯元宝」：填入兼容 JSON 文件的本机绝对路径后导入。需要先取得 JSON 导出；本次不读取元宝电脑版数据库或云端账户，也不把 ZIP 写回元宝客户端。换设备后可恢复到 AgentRelay 再查看或迁出，见[元宝使用与格式说明](docs/reference/formats/yuanbao.md)。

“实机验证”指用真实客户端打开、续聊过迁移或恢复后的会话；其余只验证了文件层读写。厂商格式可能变化，详见 [兼容状态](docs/reference/compatibility.md) 与 [当前限制](docs/reference/limitations.md)。

## 文档

完整索引见 [docs/README.md](docs/README.md)，分为使用指南（`guide/`）、参考（`reference/`）、开发与维护（`dev/`）和调研记录（`research/`）。常用入口：

| 主题 | 文档 |
|---|---|
| 下载、安装、启动与退出 | [docs/guide/install.md](docs/guide/install.md) |
| 网页任务导航、恢复与草稿打包 | [docs/guide/web-workflow.md](docs/guide/web-workflow.md) |
| 批量存储、跨软件 / 双系统迁移与预览 | [docs/guide/storage-and-migration.md](docs/guide/storage-and-migration.md) |
| 搜索与 Skill 草稿 | [docs/guide/search-and-skills.md](docs/guide/search-and-skills.md) |
| 便携存储、Ubuntu 双系统 | [docs/guide/portable-storage.md](docs/guide/portable-storage.md) · [docs/guide/ubuntu-dual-boot.md](docs/guide/ubuntu-dual-boot.md) |
| 配置与数据目录、故障排查 | [docs/guide/configuration.md](docs/guide/configuration.md) · [docs/guide/troubleshooting.md](docs/guide/troubleshooting.md) |
| 兼容状态、已知限制、来源格式 | [docs/reference/compatibility.md](docs/reference/compatibility.md) · [docs/reference/limitations.md](docs/reference/limitations.md) · [docs/reference/source-formats.md](docs/reference/source-formats.md) |
| 腾讯元宝接入范围 | [docs/reference/yuanbao-compatibility.md](docs/reference/yuanbao-compatibility.md) |
| 适配器与插件开发、测试 | [docs/dev/adapters.md](docs/dev/adapters.md) · [docs/dev/writing-a-plugin.md](docs/dev/writing-a-plugin.md) · [docs/dev/testing.md](docs/dev/testing.md) |
| 命令行完整说明 | [命令行参考](docs/reference/cli.md)（快速上手见 [使用说明.md](使用说明.md)） |

## 参与贡献

欢迎提 issue 和 PR：请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请按 [SECURITY.md](SECURITY.md) 私密报告。版本变更见 [CHANGELOG.md](CHANGELOG.md)，维护流程见 [docs/dev/maintainers.md](docs/dev/maintainers.md)。

## 许可

[MIT License](LICENSE)
