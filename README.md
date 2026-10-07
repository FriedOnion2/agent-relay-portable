# AgentRelay Portable

在本机浏览、导出和迁移 AI 编程助手的对话，也可以把对话和 Skill 打包到移动盘，在另一台设备恢复。
支持 **WorkBuddy、DeepSeek Harness（DSH）、CodeBuddy、Claude Code、Claude Agent SDK、OpenAI Codex** 六个来源入口，提供中文网页和命令行，适用于 Windows、macOS、Ubuntu / Linux。

应用只监听本机地址，不上传会话，不调用模型。基本功能使用 Python 标准库；DSH 压缩会话读取和通用导入需要可选依赖 `zstandard`。首次安装依赖需要网络。

## 功能概览

- **查看与导出：** 按来源浏览、搜索和预览会话，导出 Markdown。
- **跨软件迁移：** 转换到 WorkBuddy、DSH、Claude Code、Codex 四个可写目标；保留可表达的正文、思考和工具历史。
- **对话跨设备存储：** 单项或勾选多项保存原生 ZIP 包，复制后恢复到对应软件。
- **Skill 跨设备存储：** 保存完整 `SKILL.md`、脚本与资源目录，支持复选框、全选和批量保存。
- **Windows ↔ Ubuntu 原生迁移：** 通过挂载目录或用户目录备份，在同款软件之间搬迁原生记录。
- **启动与退出：** 自动尝试空闲端口；网页「退出服务」可停止后台进程，并等待正在执行的请求结束。

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

## 快速启动

需要 **Python 3.8 或更新版本**。应用运行不需要 Node.js；Node.js 仅用于网页测试。
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

使用启动器所选的 Python 安装可选依赖：

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
目录覆盖优先级为：配置文件 → `RELAY_<AGENT>_HOME` → agent 环境变量 → 当前用户默认目录。
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

截至 2026-10-07，本机回归为 **101 项 Python 测试（Mac 上 4 项跳过）与 22 项网页测试**。
GitHub Actions 在 Windows、Ubuntu 和 macOS 上验证 Python 3.8、3.12、3.14，共 8 组；
macOS 不包含 Python 3.8。批量存储已用浏览器和临时样例实测，分别生成两条对话包与两个 Skill 包。
自动测试覆盖格式转换、存储包往返、完整性与冲突保护、端口占用、退出等待、异步列表及批量部分失败。
测试使用临时合成数据，不修改用户真实会话，也不执行 Skill 脚本。

可选实机验证：`python3 tests/macos_launch_smoke.py` 启动实际 `.app`，只读探测本机来源，
验证 HTTP 和退出接口后停止本次服务。DSH 原生 smoke 脚本与验证范围见 [开发与排查手册](开发过程与排查手册.md)。
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
- [开发与排查手册](开发过程与排查手册.md)：代码地图、验证记录和问题处理。
