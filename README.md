# AgentRelay Portable

本地会话迁移工具，提供 **WorkBuddy、DeepSeek Harness（DSH）、CodeBuddy、Claude Code、Claude Agent SDK、OpenAI Codex** 六个来源入口，
可预览、导出 Markdown 或迁移到支持写入的目标。基本功能只使用 Python 标准库；读取 DSH 压缩日志和向 DSH 导入需要 `zstandard`。

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

- **Windows**：双击 `启动_AgentRelay.bat`。
- **macOS**：首次在项目目录运行 `bash Mac首次准备.command`，然后双击 `AgentRelay.app` 或 `启动_AgentRelay.command`。
- **Ubuntu / Linux**：首次运行 `bash Ubuntu首次准备.sh`，再运行 `bash 启动_AgentRelay.sh`；
  无桌面环境加 `--no-browser`。非压缩格式也可直接 `python3 app/cli.py serve`。

**Ubuntu / Windows 双系统：** 在 Ubuntu 挂载 Windows 分区后执行：

```bash
python3 app/cli.py windows-users
python3 app/cli.py windows-use "/media/Ubuntu用户名/Windows分区/Users/Windows用户名"
bash 启动_AgentRelay.sh
```

网页同时保留 Ubuntu 来源，并新增六个 **Windows 只读来源**，可浏览、导出和迁出。
选择 Windows 会话、填写 Ubuntu 项目目录，点击 **“迁到 Ubuntu 对应软件”** 可保留原生记录迁入同款软件。
支持 WorkBuddy、Claude、SDK、Codex、DSH v4、CodeBuddy CLI/IDE；IDE 需先创建本机工作区。
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

**跨设备对话存储：** 网页点击“存储此会话”，包按 Agent 保存到 `storage/conversations/`。
复制包或整个 storage 文件夹到另一设备后，通过“对话存储”指定本机项目目录，恢复到对应软件。
CLI 支持 `store-sessions <agent> <ID>` / `--all`、`stored-sessions`、`restore-session <包.zip> --cwd <目录>`。
文件恢复前校验，已有 ID 不覆盖。详见 [便携存储说明](docs/portable-storage.md)。

需要 Python **3.8 或更新版本**。Windows 可将完整的嵌入式 Python 解压到 `runtime/python/`。
也可通过 `RELAY_PYTHON` 指定解释器。默认网址为 `http://127.0.0.1:8745/`。

macOS 首次准备会在 `runtime/macos-<架构>/` 创建独立 Python 环境并安装 DSH 解码依赖；两个 Mac 启动器自动优先使用此环境。安装失败可运行 `bash Mac安装依赖.command` 重试，换机器后也应重新准备。该环境依赖本机 Python，不属于免安装运行时。

`.app` 优先将日志写入项目 `logs/`；若 macOS 禁止应用写入外置盘，自动改用 `~/Library/Logs/AgentRelay/`。服务确认 HTTP 就绪后才打开浏览器，并尊重 `open_browser` 配置。

DSH 默认保存压缩会话。使用启动器所选的 Python 安装一次可选依赖：

```sh
python -m pip install -r requirements-optional.txt
```

Ubuntu 推荐使用上述首次准备脚本，依赖放入用户级虚拟环境，兼容系统 Python 的 PEP 668 限制。

缺少解码器时仍会列出 DSH 会话并显示安装提示；损坏、未写完、过大或未知版本日志会显示读取受限，避免迁移不完整数据。

```sh
python app/cli.py doctor
python app/cli.py list codex
python app/cli.py list claude_sdk
python app/cli.py transfer codex <session-id> --to claude
python app/cli.py transfer codex <session-id> --to dsh
python app/cli.py export codex <session-id> -o handoff.md
```

详细步骤见 [使用说明](使用说明.md)。

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

Python 测试覆盖原有三个目标之间的六个迁移方向、向 DSH 导入、独立来源路径、DSH 世代/压缩/工具结果、
CodeBuddy CLI/IDE 消息顺序与缺失文件、SDK 共享目录、Claude 主链/压缩边界、RAW 保留、截断拦截，
以及原有文本、HTTP 和配置回归。Claude / SDK / DSH 会话摘要缓存会在文件变化时失效。
另覆盖双系统六来源读取、Windows 原文件不变、只读保护、原生 cwd、配置和 Ubuntu 启动器 HTTP 验证。
Node.js 仅用于网页回归测试，运行应用不需要 Node.js。
所有测试均使用临时合成数据，不修改真实会话目录。

macOS 原生启动回归可运行 `python3 tests/macos_launch_smoke.py`，会启动实际 `.app`，只读探测本机会话来源，并在检查后停止本次启动的服务。

GitHub Actions 在 Windows、Linux 和 macOS 上运行测试，包含 Python 3.8、3.12 和 3.14；
macOS 的 Python 3.8 因 runner 架构限制不在矩阵中。

## 当前限制

- WorkBuddy / Claude / SDK / Codex / CodeBuddy CLI 最多读取 32 MiB，超出时可导出带标记的部分内容，迁移会停止；DSH 普通/解压数据与 CodeBuddy IDE 总读取量超过限制会拒绝读取。
- Claude / SDK 默认读取当前 parentUuid 主链，不合并旧分支与子代理；压缩前的旧原文仍在原文件中，但不作为当前上下文重复迁移。
- DSH 导出保留事件历史，不重放 surface replacement、compaction、seed 或 native resume 状态。
- 网页及 CLI 提供 WorkBuddy、DSH、Claude、Codex 四个迁移目标；CodeBuddy、SDK 仍只读。
- DSH 导入写入 v0 原生 Zstd 日志，兼容本机 0.1.2-rc.1，亦已通过官方 0.2.1-alpha.1 格式目录严格迁移到 v4 的验证。导入历史会关闭工具调用；缺失结果的工具调用保留为文字，不作为待执行工作。图片及非原生内容块降级为标注文本。目标工作目录必须是当前系统的绝对路径。
- CodeBuddy/SDK 的通用转换目标限制不影响“Windows → Ubuntu 对应软件”的原生文件迁入；后者保留原生记录，
  不合成任意来源的 DSH/CodeBuddy/SDK 日志。DSH 需完整 v4，分叉先迁父会话，子代理不单独迁入；
  CodeBuddy IDE 需唯一匹配的已有原生工作区，并在关闭软件后导入。
- SDK 自行保存的 stream-json 输出不是 native transcript；关闭 persistence 或仅使用外部 SessionStore 的应用可能没有默认本地历史。
- CodeBuddy CLI/IDE 格式来自第三方消费者观测，未获得厂商原生续聊协议验证；格式依据见 [来源格式说明](docs/source-formats.md)。
- 图片、加密思考及厂商特有元数据不能保证完整保留。
- 工具名转换不会安装目标工具，也不会转换各家工具的参数协议。
- Codex Desktop 可能需要自己的数据库索引；生成 JSONL 不保证会话自动出现在桌面列表。
- 目标 agent 的格式可能变化，程序回读测试通过不能替代目标 agent 的实际续聊验证。
- `.app` 与终端启动已在 Apple Silicon Mac 上实测；其他机器的 Gatekeeper 权限和目标工具原生续聊仍需验证。
