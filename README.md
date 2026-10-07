# AgentRelay Portable

[中文](#中文) | [English](#english)

## 中文

在本机浏览、导出和迁移 AI 编程助手的对话，也可以把对话和 Skill 打包到移动盘，在另一台设备恢复。
支持 **WorkBuddy、DeepSeek Harness（DSH）、CodeBuddy、Claude Code、Claude Agent SDK、OpenAI Codex** 六个来源入口，提供中文网页和命令行，适用于 Windows、macOS、Ubuntu / Linux。

**Release 总包内置 Python 3.12 和 `zstandard`：完整解压后即可启动，无需安装 Python、Node.js，也无需首次联网下载依赖。** 一个包包含 Windows、macOS 和 Linux 版本，适合放在移动盘上跨设备使用。

应用只监听本机地址，不上传会话，不调用模型。源码启动的 Python 与可选依赖要求见下方「源码启动」。

## 功能概览

- **查看与导出：** 按来源浏览、搜索和预览会话，导出 Markdown。
- **跨软件迁移：** 转换到 WorkBuddy、DSH、Claude Code、Codex 四个可写目标；保留可表达的正文、思考和工具历史。
- **对话跨设备存储：** 单项或勾选多项保存原生 ZIP 包，复制后恢复到对应软件。
- **Skill 跨设备存储：** 保存完整 `SKILL.md`、脚本与资源目录，支持复选框、全选和批量保存。
- **Windows ↔ Ubuntu 原生迁移：** 通过挂载目录或用户目录备份，在同款软件之间搬迁原生记录。
- **启动与退出：** 自动尝试空闲端口；网页「退出服务」可停止后台进程，并等待正在执行的请求结束。
- **设备配置：** 「环境与兼容」重选本机目录，按设备保存覆盖配置，提示旧路径失效。
- **迁移预览：** 通用迁移、双系统原生迁移和会话包恢复先列出保留、降级、丢弃与未知，确认后检查源内容及选项变化。
- **可信社区读取插件：** API v1，显式启用、文件 hash 检查、独立工作进程与超时；支持读取、导出和迁出。
- **格式健康度：** 本地合成样本自检、每日三系统回归与可下载静态报告，真实客户端续聊单独标为未验证。

| 来源 | 默认会话位置 | 能力 |
|---|---|---|
| WorkBuddy | `~/.workbuddy/projects` | 读取、导出、写入 |
| DeepSeek Harness / DSH | `~/.dsh/sessions` | 读取 v0–v4、导出、写入原生压缩历史 |
| CodeBuddy CLI | `~/.codebuddy/projects` | 读取、导出、迁出 |
| CodeBuddy CN IDE / Extension | 系统的 `CodeBuddyExtension/Data/**/history` | 读取 manifest 与消息文件、导出、迁出 |
| Claude Code | `~/.claude/projects` | 读取、导出、写入 |
| Claude Agent SDK | `~/.claude/projects`（与 Claude Code 共享） | 读取、导出、迁出 |
| OpenAI Codex | `~/.codex/sessions` | 读取、导出、写入 |

CodeBuddy CLI 与 IDE 在同一个独立来源下显示；DSH 与 WorkBuddy 不再共用名称、配置或目录。
SDK 与 Claude Code 共用默认存储，日志不能可靠证明创建者；SDK 入口明确标记“Claude 共享记录”，
两个列表可能显示同一会话。SDK 不会把 CLI 历史自动改成 SDK 专属来源。

## Release 下载即用

当前开发预览版：**v0.3.0-dev.1** · [下载三系统总包](https://github.com/FriedOnion2/agent-relay-portable/releases/download/v0.3.0-dev.1/AgentRelay-v0.3.0-dev.1-universal.zip) · [发布说明与校验文件](https://github.com/FriedOnion2/agent-relay-portable/releases/tag/v0.3.0-dev.1)

普通用户下载 [GitHub Releases](https://github.com/FriedOnion2/agent-relay-portable/releases) 中的
**`AgentRelay-<版本>-universal.zip`**，完整解压后按当前设备运行启动器。一个总包同时包含
Windows x64、Mac Apple Silicon / Intel 和 Linux x64，已内置 Python 与 `zstandard`，无需另装 Python 或 Node.js。
不要选择 GitHub 自动生成的 Source code 压缩包，那是开发源码。

| 当前设备 | Release 启动入口 | 支持范围 |
|---|---|---|
| Windows | `启动_AgentRelay.bat` | Windows 10/11 x64 |
| Mac | `AgentRelay.app` 或 `bash 启动_AgentRelay.command` | Apple Silicon：macOS 14+；Intel：macOS 15+ |
| Linux | `bash 启动_AgentRelay.sh` | Ubuntu 22.04+ / glibc 2.35+ x64 |

总包根目录共用 `config.json`（可选）与 `storage/`。把整个总包放在移动盘上，切换设备无需再下载另一系统的版本。
启动器只把当前平台的运行库解压到本机缓存，保留移动盘上的共享数据，避免 noexec 和 Mac 符号链接差异。
首次启动不联网下载依赖；不要删除 `runtimes/`。目标 Agent 软件仍需自行安装并配置其依赖与登录。本机目录选择存入 `devices/<设备ID>.json`，换设备默认自动探测新主机；共享配置中的旧路径失效会提示重选，留空并保存可恢复自动探测。

Mac 应用未经过 Apple 公证。如被系统阻止，在可信解压目录运行 `bash Mac首次运行.command`，再启动。
本机缓存分别位于 `%LOCALAPPDATA%/AgentRelay/<版本>/`、`~/Library/Caches/AgentRelay/<版本>/`、
`~/.cache/agentrelay/<版本>/`（Linux 尊重 `XDG_CACHE_HOME`）。如运行库解压中断，删除该版本缓存后重试。
Release 包只包含运行文件、启动入口、配置示例和「开始使用.txt」，不附带测试、开发资料、格式调研或个人数据。
开发预览版在 GitHub 标为 Pre-release；`SHA256SUMS.txt` 可用于验证下载的总包。

## 源码启动

以下仅适用于运行仓库源码；Release 用户可跳过本节。源码需要 **Python 3.8 或更新版本**。应用运行不需要 Node.js；Node.js 仅用于网页测试。
将仓库下载或克隆后，在项目目录执行以下操作。移动盘上应保留完整项目目录。

| 系统 | 首次准备 | 启动 |
|---|---|---|
| Windows | 安装 Python，或将完整 Windows 嵌入式 Python 放入 `runtime/python/`；DSH 依赖见下文 | 双击 `启动_AgentRelay.bat` |
| macOS | `bash Mac首次准备.command` | 双击 `AgentRelay.app` 或 `启动_AgentRelay.command` |
| Ubuntu / Linux | `bash Ubuntu首次准备.sh`；缺少 Python / venv 时先安装 `python3 python3-venv` | `bash 启动_AgentRelay.sh` |

也可直接运行：

```sh
python app/cli.py serve
python app/cli.py serve --no-browser --port 8745
python app/cli.py doctor
```

Linux / macOS 按实际解释器将 `python` 换为 `python3`。`RELAY_PYTHON` 可指定解释器完整路径。
默认网址为 `http://127.0.0.1:8745/`；占用时尝试后续 5 个端口，实际网址以启动输出或打开的网页为准。
程序会保留占用端口的旧服务或其他软件，**不会自动结束它们**。所有候选端口都被占用时才报错。
要释放旧 AgentRelay 的端口，打开旧网页，点击 **退出服务**，或在旧终端按 **Ctrl+C**。

### 退出与重新启动

点击网页右上角 **退出服务** 并确认，可停止当前服务，包括 `.app` 启动的后台服务。
正在执行的请求会完成后再退出；使用同一服务的其他页面也会断开。终端启动可按 **Ctrl+C**。
仅关闭网页不会停止后台服务。重新使用时再次运行启动器；更新代码后也应停止旧服务并重新启动。

### DSH 依赖与 Mac 启动

Release 已包含此依赖。仅源码用户需要使用启动器所选的 Python 安装可选依赖：

```sh
python -m pip install -r requirements-optional.txt
```

Mac 首次准备自动创建 `runtime/macos-<架构>/` 虚拟环境并安装 `zstandard`；安装失败可执行
`bash Mac安装依赖.command` 重试。换机器需重新准备，虚拟环境依赖本机 Python，不能当作跨设备便携解释器。
Ubuntu 首次准备使用用户级虚拟环境，避免系统 pip 的 PEP 668 限制。完整运行时说明见 [runtime/README.txt](runtime/README.txt)。
缺少解码器时仍会列出 DSH 会话并显示安装提示；损坏、未写完、过大或未知版本的日志会显示读取受限。

Mac `.app` 在 HTTP 就绪后打开浏览器，尊重 `open_browser` 配置。日志优先写入项目 `logs/`，
外置盘禁止写日志时改用 `~/Library/Logs/AgentRelay/`。文稿目录内双击曾出现 Python 探测停住，
可改用终端启动器，并检查 macOS 文件与文件夹访问权限；这不属于已确认根因。

## 对话与 Skill 的批量存储

**对话：** 在左侧当前来源列表勾选会话，或点击 **全选当前列表**，然后点击 **存储所选对话**。
单项预览后的 **存储此会话** 仍可使用。在「对话存储」面板可指定存储目录、查看包和恢复。

**Skill：** 打开 **Skill 存储**，选择来源 Agent，点击 **查找 Skill**；未找到时填写实际 Skill 根目录。
勾选目录或点击 **全选当前列表**，再点击 **存储所选 Skill**。也可直接填写目录进行单项存储。

全选仅包含当前列表中可读取的项目；对话搜索过滤、来源切换或重新扫描 Skill 会清空选择。
每项独立成包，逐项保存并显示成功、失败数量；成功项取消勾选，失败项保留勾选以便重试。
网页批量存储不提供批量恢复，恢复仍按单包操作。

默认目录：

```text
storage/
├── conversations/<agent>/<包ID>.zip
└── skills/<agent>/<包ID>.zip
```

复制 ZIP 或整个 `storage` 文件夹到目标设备后，运行该设备上的 AgentRelay：

- **对话恢复：** 在「对话存储」选择包或填包路径，填写本机已存在的项目目录，恢复到对应软件。
- **Skill 恢复：** 在「Skill 存储」选择包、目标 Agent 和实际技能根目录，再点击「恢复 Skill」。

恢复前校验内容和路径；已有同 ID 对话或同名 Skill 不覆盖，可指定新 ID / 新目录名。
Skill 指令和脚本不会自动执行。包没有加密；应用不会将包上传 GitHub。
对话包用于对应软件的原生恢复，跨软件转换使用「迁移到目标」。具体格式和限制见 [便携存储说明](docs/portable-storage.md)。

```sh
python app/cli.py store-sessions codex <ID1> <ID2>
python app/cli.py store-sessions codex --all
python app/cli.py stored-sessions --agent codex
python app/cli.py restore-session <会话包.zip> --cwd <本机项目绝对路径>
python app/cli.py skills codex
python app/cli.py store-skills codex --all --skills-dir <实际Skill根目录>
python app/cli.py stored-skills --agent codex
python app/cli.py restore-skill <Skill包.zip> --skills-dir <目标Skill根目录>
```

## 跨软件与双系统迁移

通用转换在网页选择来源会话和可写目标，按需填写本机目标项目目录，再点击「迁移到目标」。
向 DSH 导入时写入原生 v0 历史，不执行历史工具调用；跨系统的来源 cwd 应替换为本机绝对路径。

```sh
python app/cli.py list codex
python app/cli.py transfer codex <session-id> --to claude
python app/cli.py transfer codex <session-id> --to dsh
python app/cli.py export codex <session-id> -o handoff.md
```

**Ubuntu / Windows 双系统：** 在 Ubuntu 挂载 Windows 分区后执行：

```bash
python3 app/cli.py windows-users
python3 app/cli.py windows-use "/media/Ubuntu用户名/Windows分区/Users/Windows用户名"
bash 启动_AgentRelay.sh
```

网页同时保留 Ubuntu 来源，并新增六个 **Windows 只读来源**，可浏览、导出和迁出。
选择 Windows 会话、填写 Ubuntu 项目目录，点击 **“迁到 Ubuntu 对应软件”** 可保留原生记录迁入同款软件。
支持 WorkBuddy、Claude、SDK、Codex、DSH v4 / v0 seed、CodeBuddy CLI/IDE；IDE 需先创建本机工作区。
也可运行 `python3 app/cli.py import-windows codex <会话ID> --cwd /home/你的用户/项目`。
迁出时填写已存在的 Ubuntu 项目目录；不会自动改写历史中的 Windows 路径。
完整步骤和挂载排查见 [Ubuntu 双系统说明](docs/ubuntu-dual-boot.md)。

**反向 Ubuntu → Windows：** 在 Ubuntu 来源选择会话，填写 Windows 项目路径和该项目在 Ubuntu
中的挂载路径，点击 **“迁到 Windows 对应软件”**。也可运行：

```bash
python3 app/cli.py export-windows codex <Ubuntu会话ID> --cwd 'D:\project' --project-path /mnt/data/project
```

Windows 中也可用 `python app/cli.py ubuntu-use "D:\UbuntuBackup\alice"` 选择可访问的 Ubuntu
用户目录备份，再用 `import-ubuntu codex <会话ID> --cwd "D:\project"` 导入。Windows 不会直接读取 ext4。
双向搬迁保留源文件、拒绝覆盖同 ID，不自动合并两边继续后的历史；新 ID 可保留另一份。
GitHub 同类项目与源码差异见 [原生会话迁移调研](docs/session-migration-alternatives.md)。

## 配置与数据

复制 `config.example.json` 为 `config.json` 后可配置会话根目录、端口和是否打开浏览器。
目录覆盖优先级为：本机设备配置 → 共享配置文件 → `RELAY_<AGENT>_HOME` → agent 环境变量 → 当前用户默认目录。相对路径以便携根解析，不依赖当前工作目录。
网页「环境与兼容」保存目录只影响当前设备；`windows-use` / `ubuntu-use` 也仅保存本机选择。设备配置损坏会报告错误，不覆盖原文件；共享配置损坏仍尝试读取有效设备配置。

```sh
python app/cli.py device-config
python app/cli.py device-config --agent codex --home <当前设备Agent根目录>
python app/cli.py device-config --agent codex --home ""
python app/cli.py health --output health-output
python app/cli.py transfer claude <ID> --to codex --dry-run
```

迁移命令和 `restore-session` 支持 `--dry-run` 与 `--preview-token`；旧直接命令保持兼容。预览不会锁住源软件，操作前关闭正在写入会话的客户端。详见 [兼容与迁移预览](docs/compatibility.md)、[插件接口](docs/adapters.md) 和 [换设备排查](docs/troubleshooting.md)。
DSH 尊重 `DSH_HOME`，WorkBuddy 尊重 `WORKBUDDY_HOME`，CodeBuddy 尊重 `CODEBUDDY_HOME`。
SDK 默认尊重 `CLAUDE_CONFIG_DIR`；独立覆盖为 `agent_homes.claude_sdk` / `RELAY_CLAUDE_SDK_HOME`，
不会继承仅为 Claude Code 设置的 `RELAY_CLAUDE_HOME`。
目录应填写工具根目录，不要填写其 `projects` / `sessions` 子目录。

`windows_user_home` / `RELAY_WINDOWS_USER_HOME` 指向 Ubuntu 挂载的 Windows 用户目录，只在 Linux 生效。
临时 `--windows-user` 优先于保存的选择；此项追加只读来源，不改变本机写入目标。

**旧配置升级：** 如果原 `agent_homes.dsh` 或 `RELAY_DSH_HOME` 指向 `.workbuddy`，请把该值移到
`workbuddy` / `RELAY_WORKBUDDY_HOME`；`dsh` 现在只代表 DeepSeek Harness，不会静默别名为 WorkBuddy。

CodeBuddy 默认同时扫描 CLI 与 IDE。IDE Windows 根目录为 `%LOCALAPPDATA%/CodeBuddyExtension/Data`，
macOS 为 `~/Library/Application Support/CodeBuddyExtension/Data`，Linux 为 `~/.config/CodeBuddyExtension/Data`。
显式设置 CodeBuddy 根目录时仅扫描该目录，可填写备份的 `.codebuddy` 或 IDE `Data` 根目录。

程序只监听本机地址。转换读取源会话，并向目标 agent 的会话目录写入新文件；
同名目标不会被覆盖。日志、本机配置、Python 运行时、缓存和真实会话数据不应上传 GitHub，
仓库已提供对应忽略规则。

## 验证

```sh
python -m pip install -r requirements-optional.txt
python -m unittest discover -s tests -v
node --test tests/web.test.cjs
```

截至 2026-10-07，本机回归为 **104 项 Python 测试（Mac 上 4 项跳过）与 22 项网页测试**。
GitHub Actions 在 Windows、Ubuntu 和 macOS 上验证 Python 3.8、3.12、3.14，共 8 组；
macOS 不包含 Python 3.8。批量存储已用浏览器和临时样例实测，分别生成两条对话包与两个 Skill 包。
自动测试覆盖格式转换、存储包往返、完整性与冲突保护、端口占用、退出等待、异步列表及批量部分失败。
测试使用临时合成数据，不修改用户真实会话，也不执行 Skill 脚本。

可选实机验证：`python3 tests/macos_launch_smoke.py` 启动实际 `.app`，只读探测本机来源，
验证 HTTP 和退出接口后停止本次服务。DSH 官方原生验证可使用 `tests/dsh_native_smoke.mjs` / `tests/dsh_catalog_smoke.mjs`；运行参数见脚本头部。
Release 构建还在四类设备上验证内置依赖、DSH 导入、共享存储根目录、端口重试、HTTP 与退出，再发布同一个总包。
跨平台 CI 验证的是项目行为，厂商原生续聊、设备权限和挂载仍需在目标环境确认。

## 当前限制

- WorkBuddy / Claude / SDK / Codex / CodeBuddy CLI 最多读取 32 MiB，超出时可导出带标记的部分内容，迁移会停止；DSH 普通/解压数据与 CodeBuddy IDE 总读取量超过限制会拒绝读取。
- Claude / SDK 默认读取当前 parentUuid 主链，不合并旧分支与子代理；压缩前的旧原文仍在原文件中，但不作为当前上下文重复迁移。
- DSH 导出保留事件历史，不重放 surface replacement、compaction、seed 或 native resume 状态。
- 网页及 CLI 提供 WorkBuddy、DSH、Claude、Codex 四个迁移目标；CodeBuddy、SDK 仍只读。
- DSH 导入写入 v0 原生 Zstd 日志，兼容本机 0.1.2-rc.1，亦已通过官方 0.2.1-alpha.1 格式目录严格迁移到 v4 的验证。导入历史会关闭工具调用；缺失结果的工具调用保留为文字，不作为待执行工作。图片及非原生内容块降级为标注文本。目标工作目录必须是当前系统的绝对路径。
- CodeBuddy/SDK 的通用转换目标限制不影响双向对应软件原生文件迁移；后者保留原生记录，
  DSH 支持完整 v4 和可验证的 v0 seed，分叉先迁父会话，子代理不单独迁入；
  CodeBuddy IDE 需唯一匹配的已有原生工作区，并在关闭软件后导入。
- SDK 自行保存的 stream-json 输出不是 native transcript；关闭 persistence 或仅使用外部 SessionStore 的应用可能没有默认本地历史。
- CodeBuddy CLI/IDE 格式来自第三方消费者观测，未获得厂商原生续聊协议验证；格式依据见 [来源格式说明](docs/source-formats.md)。
- 图片、加密思考及厂商特有元数据不能保证完整保留。
- 工具名转换不会安装目标工具，也不会转换各家工具的参数协议。
- Codex Desktop 可能需要自己的数据库索引；生成 JSONL 不保证会话自动出现在桌面列表。
- 目标 agent 的格式可能变化，程序回读测试通过不能替代目标 agent 的实际续聊验证。
- `.app` 与终端启动已在 Apple Silicon Mac 上实测；其他机器的 Gatekeeper 权限和目标工具原生续聊仍需验证。

## 文档导航

- [使用说明](使用说明.md)：启动、批量存储、退出、配置与命令行。
- [便携存储说明](docs/portable-storage.md)：对话和 Skill 的跨设备包、恢复步骤与边界。
- [Ubuntu 双系统说明](docs/ubuntu-dual-boot.md)：挂载、双向原生迁移与故障排查。
- [来源格式说明](docs/source-formats.md)：来源格式和官方资料依据。
- [原生会话迁移调研](docs/session-migration-alternatives.md)：同类项目及实现差异。

---

## English

Browse, export, and migrate AI coding assistant conversations locally, or carry conversation and Skill archives on a portable drive and restore them on another device. AgentRelay provides a **Chinese web interface and a command-line interface** for Windows, macOS, and Ubuntu / Linux.

**The universal release bundles Python 3.12 and `zstandard`. Extract the complete archive and launch it: no Python or Node.js installation and no dependency downloads on first launch.** One archive contains Windows, macOS, and Linux runtimes for switching devices.

The service listens only on the local machine. It does not upload conversations or call models. Python installation instructions below apply only to running the source code.

### Features and supported sources

- Browse, search, preview, and export conversations to Markdown.
- Convert conversations to WorkBuddy, DSH, Claude Code, or Codex, preserving representable text, reasoning, and tool history.
- Save individual or selected conversations as native ZIP archives for another device.
- Archive complete Skill directories, including `SKILL.md`, scripts, and resources; select multiple items or the entire current list.
- Transfer native records between the same assistant on Windows and Ubuntu using mounted or backed-up user directories.
- Retry available ports automatically and stop the server from the web interface after active requests finish.

| Source | Default conversation location | Support |
|---|---|---|
| WorkBuddy | `~/.workbuddy/projects` | Read, export, write |
| DeepSeek Harness / DSH | `~/.dsh/sessions` | Read v0–v4, export, write native compressed history |
| CodeBuddy CLI | `~/.codebuddy/projects` | Read, export, migrate out |
| CodeBuddy CN IDE / Extension | System `CodeBuddyExtension/Data/**/history` | Read manifests and messages, export, migrate out |
| Claude Code | `~/.claude/projects` | Read, export, write |
| Claude Agent SDK | `~/.claude/projects` (shared with Claude Code) | Read, export, migrate out |
| OpenAI Codex | `~/.codex/sessions` | Read, export, write |

CodeBuddy CLI and IDE appear under one source. DSH and WorkBuddy have separate names, configuration, and directories. Claude Agent SDK shares Claude Code's default storage; logs cannot reliably identify the creator. The SDK entry is labelled “Claude 共享记录” (shared Claude records), and both lists may show the same conversation. CLI history is not automatically relabelled as SDK-specific history.

### Download and launch

Current development preview: **v0.3.0-dev.1** · [Download the universal archive](https://github.com/FriedOnion2/agent-relay-portable/releases/download/v0.3.0-dev.1/AgentRelay-v0.3.0-dev.1-universal.zip) · [Release notes and checksums](https://github.com/FriedOnion2/agent-relay-portable/releases/tag/v0.3.0-dev.1)

Download **`AgentRelay-<version>-universal.zip`** from [GitHub Releases](https://github.com/FriedOnion2/agent-relay-portable/releases), extract it completely, and use the launcher for your device. GitHub's automatically generated **Source code** archives are for development.

| Device | Release launcher | Supported systems |
|---|---|---|
| Windows | Double-click `启动_AgentRelay.bat` | Windows 10/11 x64 |
| Mac | `AgentRelay.app` or `bash 启动_AgentRelay.command` | Apple Silicon: macOS 14+; Intel: macOS 15+ |
| Linux | `bash 启动_AgentRelay.sh` | Ubuntu 22.04+ / glibc 2.35+ x64 |

Keep the entire extracted folder on your portable drive. Its optional `config.json` and `storage/` directory are shared across devices. The launcher extracts only the matching runtime into a local cache, avoiding portable-drive executable restrictions and Mac symlink differences. **Keep `runtimes/`; no runtime is downloaded at startup.** Device overrides live in `devices/<device-id>.json`; another device starts with its own defaults. Inaccessible shared paths prompt reselection in **环境与兼容** (Environment and compatibility); save an empty directory to restore automatic detection.

The Mac app is not notarized by Apple. If macOS blocks it, run `bash Mac首次运行.command` in the trusted extracted directory, then launch again. Runtime caches are `%LOCALAPPDATA%/AgentRelay/<version>/` on Windows, `~/Library/Caches/AgentRelay/<version>/` on Mac, and `~/.cache/agentrelay/<version>/` on Linux (respecting `XDG_CACHE_HOME`). If extraction is interrupted, remove that version's cache and retry.

Release archives contain only runtime files, launchers, a configuration example, and the short `开始使用.txt` getting-started guide. Tests, development documents, format research, and personal data are excluded. Development previews are marked **Pre-release**; use `SHA256SUMS.txt` to verify your download. The assistant you restore into still needs its own installation, dependencies, and authentication.

### Stop the server and release its port

The default URL is `http://127.0.0.1:8745/`. If occupied, AgentRelay tries the next five ports; use the URL printed by the launcher or opened in the browser. It does not terminate an existing service or another application. Startup fails if all candidate ports are occupied.

To free an old AgentRelay port, open that service's page and click **退出服务** (Exit service) at the top right, then confirm, or press **Ctrl+C** in its terminal. This also stops a background service launched by `.app`. Active requests finish before shutdown, and other pages connected to that service disconnect. Closing the browser alone does not stop the server. Run the launcher again to restart; stop the old service before restarting updated code.

### Run from source (optional)

Release users can skip this section. Source users need **Python 3.8 or later**. Node.js is used only for web tests. Download or clone the complete repository and run commands from its root.

| System | Initial setup | Launch |
|---|---|---|
| Windows | Install Python, or place a complete embedded Windows Python in `runtime/python/`; install the optional DSH dependency below | Double-click `启动_AgentRelay.bat` |
| macOS | `bash Mac首次准备.command` | Double-click `AgentRelay.app` or `启动_AgentRelay.command` |
| Ubuntu / Linux | `bash Ubuntu首次准备.sh`; install `python3 python3-venv` first if missing | `bash 启动_AgentRelay.sh` |

```sh
python app/cli.py serve
python app/cli.py serve --no-browser --port 8745
python app/cli.py doctor
python -m pip install -r requirements-optional.txt
```

Use `python3` where appropriate on Linux / macOS, or set `RELAY_PYTHON` to the interpreter's full path. Basic source functionality uses the Python standard library; reading compressed DSH sessions and generic DSH imports require `zstandard`. Installing source dependencies requires network access; releases already include them.

Mac setup creates `runtime/macos-<architecture>/` and installs `zstandard`; retry failed dependency installation with `bash Mac安装依赖.command`. Prepare again on another machine: this virtual environment depends on the local Python and is not a portable interpreter. Ubuntu setup uses a user-level virtual environment to avoid PEP 668 restrictions. See [runtime notes](runtime/README.txt) (Chinese). Without the decoder, DSH sessions are listed with an installation prompt; damaged, incomplete, oversized, or unknown-version logs show restricted reading.

The source Mac `.app` opens the browser after HTTP becomes ready and respects `open_browser`. Logs use project `logs/`, falling back to `~/Library/Logs/AgentRelay/` if the drive prevents writes. A source launcher in Documents previously stalled during Python detection; the cause is unconfirmed. Use the terminal launcher and check macOS file/folder permissions if affected.

### Batch conversation and Skill storage

For conversations, select rows in the current source list or click **全选当前列表** (Select all in current list), then **存储所选对话** (Store selected conversations). **存储此会话** (Store this conversation) remains available in an individual preview. Use **对话存储** (Conversation storage) to choose a storage directory, inspect archives, and restore.

For Skills, open **Skill 存储** (Skill storage), choose the source agent, and click **查找 Skill** (Find Skills). Enter the actual Skill root if discovery finds nothing. Select directories or the entire current list, then click **存储所选 Skill** (Store selected Skills). You can also enter a directory directly for individual storage.

Select all includes only readable items in the current list. Changing the source or conversation search, or rescanning Skills, clears selections. Each item gets its own archive and success/failure result. Successful items are deselected; failed items stay selected for retry. Restore operates on one archive at a time.

```text
storage/
├── conversations/<agent>/<archive-id>.zip
└── skills/<agent>/<archive-id>.zip
```

Copy archives or the entire `storage/` directory to the destination device. In Conversation storage, choose an archive and an existing local project directory to restore into the corresponding assistant. In Skill storage, choose an archive, destination agent, and actual Skill root, then click **恢复 Skill** (Restore Skill).

Contents and paths are validated before restoration. Existing conversation IDs and Skill names are not overwritten; choose a new ID or directory name when needed. Skill instructions and scripts are not automatically executed. Archives are unencrypted and are not uploaded to GitHub. Conversation archives restore native records for the corresponding assistant; use **迁移到目标** (Migrate to target) for conversion between assistants. See [portable storage](docs/portable-storage.md) (Chinese).

```sh
python app/cli.py store-sessions codex <ID1> <ID2>
python app/cli.py store-sessions codex --all
python app/cli.py stored-sessions --agent codex
python app/cli.py restore-session <conversation.zip> --cwd <absolute-local-project-path>
python app/cli.py skills codex
python app/cli.py store-skills codex --all --skills-dir <actual-skill-root>
python app/cli.py stored-skills --agent codex
python app/cli.py restore-skill <skill.zip> --skills-dir <destination-skill-root>
```

### Conversion and Windows / Ubuntu native migration

Select a source conversation and writable target in the web interface, provide a local target project directory when needed, and click **迁移到目标** (Migrate to target). DSH imports write native v0 history without executing historical tool calls. Replace a source working directory from another operating system with a local absolute path.

```sh
python app/cli.py list codex
python app/cli.py transfer codex <session-id> --to claude
python app/cli.py transfer codex <session-id> --to dsh
python app/cli.py export codex <session-id> -o handoff.md
```

For a dual-boot system, mount the Windows partition in Ubuntu, then run:

```sh
python3 app/cli.py windows-users
python3 app/cli.py windows-use "/media/<ubuntu-user>/<windows-volume>/Users/<windows-user>"
bash 启动_AgentRelay.sh
python3 app/cli.py import-windows codex <session-id> --cwd /home/<user>/<project>
```

The web interface keeps Ubuntu sources and adds six read-only Windows sources. Select a Windows conversation, enter an existing Ubuntu project directory, and click **迁到 Ubuntu 对应软件** (Move to the corresponding Ubuntu assistant) to preserve native records. Supported sources include WorkBuddy, Claude, SDK, Codex, DSH v4 / v0 seed, and CodeBuddy CLI/IDE; create the local IDE workspace first. Historical Windows paths are not automatically rewritten.

For Ubuntu → Windows, enter the Windows project path and its mounted path in Ubuntu, then click **迁到 Windows 对应软件** (Move to the corresponding Windows assistant), or run:

```sh
python3 app/cli.py export-windows codex <session-id> --cwd 'D:\project' --project-path /mnt/data/project
```

On Windows, `python app/cli.py ubuntu-use "D:\UbuntuBackup\alice"` selects an accessible Ubuntu user-directory backup; use `python app/cli.py import-ubuntu codex <session-id> --cwd "D:\project"` to import. Windows does not directly read ext4. Both directions preserve source files, reject existing IDs, and do not merge histories continued independently on both devices. A new ID can retain another copy. See [dual-boot instructions](docs/ubuntu-dual-boot.md) and [migration research](docs/session-migration-alternatives.md) (Chinese).

### Configuration and data

Copy `config.example.json` to `config.json` to configure source roots, the port, and browser opening. Directory precedence is: device configuration → shared configuration → `RELAY_<AGENT>_HOME` → assistant environment variable → current user's default directory. Relative roots resolve against the portable folder. DSH respects `DSH_HOME`, WorkBuddy `WORKBUDDY_HOME`, and CodeBuddy `CODEBUDDY_HOME`.

Phase one adds migration previews with preserved/degraded/dropped/unknown categories, consistency tokens, device environment checks, trusted read-only adapter plugins, and daily synthetic format reports. Migration and `restore-session` commands accept `--dry-run` and `--preview-token`; existing direct calls remain compatible. CLI commands `device-config`, `plugins`, and `health --output health-output` expose these features. Native client continuation and latest client versions remain explicitly unverified. See [compatibility evidence](docs/compatibility.md), [adapter API and example](docs/adapters.md), and [portable troubleshooting](docs/troubleshooting.md) (Chinese).

SDK defaults respect `CLAUDE_CONFIG_DIR`; override separately with `agent_homes.claude_sdk` / `RELAY_CLAUDE_SDK_HOME`. It does not inherit a Claude Code-only `RELAY_CLAUDE_HOME`. Supply an assistant's root directory, not its `projects` / `sessions` subdirectory.

`windows_user_home` / `RELAY_WINDOWS_USER_HOME` selects the mounted Windows user directory on Linux only. Temporary `--windows-user` overrides the saved selection. This adds read-only sources and does not change local write targets.

For old configurations pointing `agent_homes.dsh` or `RELAY_DSH_HOME` at `.workbuddy`, move that value to `workbuddy` / `RELAY_WORKBUDDY_HOME`. `dsh` now means DeepSeek Harness and is not silently aliased to WorkBuddy.

CodeBuddy scans CLI and IDE by default. IDE roots are `%LOCALAPPDATA%/CodeBuddyExtension/Data` on Windows, `~/Library/Application Support/CodeBuddyExtension/Data` on macOS, and `~/.config/CodeBuddyExtension/Data` on Linux. An explicit CodeBuddy root scans only that directory, which can be a backed-up `.codebuddy` or IDE `Data` root.

Conversions read the source and write new files to the target assistant's conversation directory without overwriting existing targets. Keep logs, local configuration, runtimes, caches, and real conversation data out of GitHub; repository ignore rules cover these paths.

### Validation

```sh
python -m pip install -r requirements-optional.txt
python -m unittest discover -s tests -v
node --test tests/web.test.cjs
```

As of 2026-10-07, local regression coverage is **104 Python tests (4 skipped on Mac) and 22 web tests**. GitHub Actions tests Python 3.8, 3.12, and 3.14 across Windows, Ubuntu, and macOS in eight combinations (macOS excludes Python 3.8). Browser checks also saved two conversation archives and two Skill archives using temporary samples.

Tests cover conversion, archive round trips, integrity and conflict protection, occupied ports, shutdown waiting, asynchronous lists, and partial batch failures. They use temporary synthetic data without modifying real conversations or executing Skill scripts.

Optional Mac validation: `python3 tests/macos_launch_smoke.py` launches the actual `.app`, probes local sources read-only, verifies HTTP and shutdown, and stops its service. Official DSH native checks are in `tests/dsh_native_smoke.mjs` / `tests/dsh_catalog_smoke.mjs`; see their headers for arguments.

Release builds validate bundled dependencies with an empty `PATH`, DSH import, shared storage roots, port retry, HTTP, and shutdown on all four native platforms. The assembled universal archive is also tested on each platform before publication. CI validates AgentRelay's behavior; actual vendor continuation, permissions, and mounts still need checking in the destination environment.

### Current limitations

- WorkBuddy / Claude / SDK / Codex / CodeBuddy CLI read at most 32 MiB; oversized records may export marked partial content but cannot be converted. Oversized DSH input/decompressed data and CodeBuddy IDE aggregate input are rejected.
- Claude / SDK read the current `parentUuid` main chain, without merging old branches or subagents. Pre-compaction text remains in the original file but is not duplicated into the current migrated context.
- DSH export preserves event history without replaying surface replacement, compaction, seed, or native resume state.
- Generic conversion has four targets: WorkBuddy, DSH, Claude, and Codex. CodeBuddy and SDK are read-only for generic conversion. This restriction does not prevent same-assistant native migration or archive restoration.
- DSH import writes native v0 Zstd logs, validated with 0.1.2-rc.1 and strict official 0.2.1-alpha.1 catalog migration to v4. Historical tool calls are disabled; calls missing results become text rather than pending work. Images and non-native blocks become annotated text. The target working directory must be absolute on the current OS.
- Native DSH migration supports full v4 and verifiable v0 seed records. Migrate a fork's parent first; subagents are not imported separately. CodeBuddy IDE needs a uniquely matching existing native workspace and must be closed during import.
- SDK `stream-json` output is not a native transcript. Applications with persistence disabled or only an external SessionStore may have no default local history.
- CodeBuddy CLI/IDE formats are based on observations from third-party consumers, without vendor-native continuation verification; see [source format notes](docs/source-formats.md) (Chinese).
- Images, encrypted reasoning, and vendor-specific metadata may not be fully preserved. Tool-name conversion neither installs target tools nor converts their argument protocols.
- Codex Desktop may require its own database index; generated JSONL does not guarantee appearance in its conversation list.
- Vendor formats can change. AgentRelay read-back tests do not replace actual continuation checks in the destination assistant.
- `.app` and terminal launch have been tested on an Apple Silicon Mac; Gatekeeper permissions and native continuation depend on the destination device.

### Further documentation (Chinese)

- [User guide](使用说明.md): launch, batch storage, shutdown, configuration, and CLI.
- [Portable storage](docs/portable-storage.md): conversation and Skill archives, restoration, and boundaries.
- [Ubuntu dual boot](docs/ubuntu-dual-boot.md): mounting and native migration in both directions.
- [Source formats](docs/source-formats.md): format references and official sources.
- [Native migration research](docs/session-migration-alternatives.md): related projects and implementation differences.
