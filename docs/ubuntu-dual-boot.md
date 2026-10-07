# Ubuntu 与 Windows 双系统读取会话

同一台设备的 Ubuntu 和 Windows 有不同的用户家目录。Ubuntu 默认的 `~/.codex` 不会自动指向
Windows 的 `C:\Users\用户名\.codex`。先挂载 Windows 分区，再选择 Windows 用户目录即可同时查看两边的会话。

## 1. 准备 Ubuntu

在项目文件夹打开终端：

```bash
# 缺少 Python / venv 时执行；脚本不会自行使用 sudo。
sudo apt install python3 python3-venv
bash Ubuntu首次准备.sh
```

准备脚本将 Python 虚拟环境放在 `${XDG_DATA_HOME:-~/.local/share}/agent-relay/venv`，并安装 DSH
压缩读取需要的 `zstandard`。它不往 Ubuntu 系统 Python 安装包，也不需要 Node.js。
安装依赖需要联网；准备后的会话读取在本地完成。

只读非压缩格式可跳过准备，直接用系统 Python 启动。想指定环境位置时，准备与启动均设置同一值：

```bash
RELAY_VENV=/home/alice/relay-venv bash Ubuntu首次准备.sh
RELAY_VENV=/home/alice/relay-venv bash 启动_AgentRelay.sh --no-browser
```

虚拟环境需在支持 Linux 执行和符号链接的文件系统上。项目本身可以放在 Windows/NTFS 或移动盘，
用 `bash` 运行脚本，无需依赖该盘的脚本执行权限。Linux 虚拟环境不是跨系统便携 Python；
Windows 的 `python.exe` 不能在 Ubuntu 中作为解释器使用。

## 2. 挂载 Windows 分区并探测

在 Ubuntu 文件管理器中点击包含 Windows 用户文件的分区。常见路径是
`/media/Ubuntu用户名/分区名/Users/Windows用户名`；手动挂载到 `/mnt/windows` 的分区也可识别。

```bash
python3 app/cli.py windows-users
```

探测仅查看挂载点及其 `Users` 下的默认 Agent 根目录，不会递归搜索整个磁盘，不会自动选择用户。
多个 Windows 用户会分别列出；选择你实际使用的账号。用户名不是显示昵称时，以探测输出为准。
含空格或中文的路径需加引号。

如果探测没有列出用户，但你已知道实际路径，也可直接执行下一步。
探测只检查默认目录；Windows 中通过 `CODEX_HOME` 等变量改过存储位置的记录，需要另行定位。

## 3. 选择 Windows 用户并启动

将以下示例替换为探测输出中的实际目录，填写到用户这一层，不填 `.codex` 或 `sessions`：

```bash
python3 app/cli.py windows-use "/media/alice/Windows/Users/Alice"
bash 启动_AgentRelay.sh
```

`windows-use` 保留已有配置，向项目根目录 `config.json` 保存 `windows_user_home`。启动后网页增加：

- Windows · WorkBuddy
- Windows · DeepSeek Harness
- Windows · CodeBuddy（含 CLI 与 `AppData/Local/CodeBuddyExtension/Data`）
- Windows · Claude Code
- Windows · Claude Agent SDK
- Windows · OpenAI Codex

Ubuntu 原来的六个来源继续显示；Windows 的六个入口全部只读，支持预览、Markdown 导出和迁出。
页面显示读取路径，SDK 仍明确说明与 Claude Code 共享存储、创建者未知。
浏览不会改写 Windows 会话。只有明确执行反向原生迁移时才向 Windows 存储添加新会话；
程序不会自动复制凭据、挂载磁盘或调整分区权限。

也可以只在这次启动时选择，不改配置：

```bash
bash 启动_AgentRelay.sh --windows-user "/mnt/windows/Users/Alice" --no-browser
```

默认访问 `http://127.0.0.1:8745/`。无桌面环境使用 `--no-browser`；`--port 8746` 可指定端口。
Ctrl+C 停止服务。命令行读取：

```bash
python3 app/cli.py list windows_codex
python3 app/cli.py list windows_claude_sdk
python3 app/cli.py export windows_codex <完整会话ID> -o Windows会话.md
```

命令行读取压缩 DSH 时，用准备环境的解释器（默认 `~/.local/share/agent-relay/venv/bin/python3`），
或通过实际的 `RELAY_VENV` 路径调用，以确保已安装解码器。

## 4. 迁到 Ubuntu Agent

支持直接迁入 Ubuntu 的**对应软件**。操作前关闭 Ubuntu 目标软件，选择 Windows 会话，在“目标工作目录”
填写已存在的 Ubuntu 项目目录，再点击 **“迁到 Ubuntu 对应软件”**。无需另选目标，Windows Codex 会进入
Ubuntu Codex，Windows SDK 会进入 Ubuntu SDK 使用的 Claude 共享存储。

迁入会保留原生记录、未知字段、工具参数及会话原 ID，并调整项目元数据中的 cwd。
同名目标不会覆盖；需要保留两份时点击“生成新 ID”，再执行迁入。
完成后页面显示目标文件、会话 ID 与可用的续聊命令，也可点击“查看 Ubuntu 会话”检查内容。

| Windows 来源 | Ubuntu 对应存储与条件 |
|---|---|
| WorkBuddy | 本机 `.workbuddy/projects`，优先复用已有项目目录 |
| Claude Code | 本机 `.claude/projects`，保留原生父链及其他分支；提供 `claude --resume` 命令 |
| Claude Agent SDK | 本机 SDK 配置的 Claude 原生共享存储；由 SDK 应用使用目标会话 ID 设置 `resume` |
| Codex | 本机 `.codex/sessions`，同时迁入对应 `session_index.jsonl` 标题条目；提供 `codex resume` 命令 |
| DSH | 本机 `.dsh/sessions`，完整 v4 原生事件、官方项目编码、独立 Zstd header frame；旧版需先升级 |
| CodeBuddy CLI | 本机 `.codebuddy/projects`，保留原生 JSONL |
| CodeBuddy IDE | 已存在的本机原生工作区，迁入 manifest / messages 并追加工作区 conversations 索引 |

CodeBuddy IDE **先在 Ubuntu 的目标项目创建一条会话，再关闭软件**，让程序复用其真实工作区标识。
缺少或存在多个匹配的工作区会停止导入，避免猜目录编码。多个 profile 匹配时，可显式配置
CodeBuddy 的 Data 根目录。WorkBuddy / CodeBuddy CLI 也优先复用已有原生项目；新目录编码仍需对应软件核对。

命令行示例（会话 ID 取 Windows 来源列表中的完整 ID）：

```bash
python3 app/cli.py import-windows codex <Windows会话ID> --cwd /home/alice/project
python3 app/cli.py import-windows claude <Windows会话ID> --cwd /home/alice/project
python3 app/cli.py import-windows claude_sdk <Windows会话ID> --cwd /home/alice/project
python3 app/cli.py import-windows workbuddy <Windows会话ID> --cwd /home/alice/project
python3 app/cli.py import-windows codebuddy <Windows完整会话ID> --cwd /home/alice/project
~/.local/share/agent-relay/venv/bin/python3 app/cli.py import-windows dsh <Windows完整会话ID> --cwd /home/alice/project
```

`--session-id <新ID>` 可另外存一份；Claude、SDK、Codex 的新 ID 必须是 UUID。
DSH 默认输出 Zstd，目标 DSH 配置为 `compression: none` 时使用 `--dsh-compression none`。
分叉 DSH 会话需先迁入父会话并保留父 ID；子代理会话暂不单独迁入。完整主会话迁入保留事件历史，
不经过 IR 重建，因此与通用导出不重放 surface 状态的限制不同。

**通用跨软件转换**仍可使用原来的目标下拉框或命令：

```bash
python3 app/cli.py transfer windows_codex <完整会话ID> --to claude --cwd /home/alice/project
```

通用转换的目标仍为 WorkBuddy、Claude、Codex。对应软件原生迁入另有独立入口，不开放任意内容写入 DSH/CodeBuddy/SDK。
这里转换的是会话所属的项目目录；历史工具参数、正文中的 `C:\…` 或其他盘符不会自动替换，
续聊前需自行确认对应文件和工具在 Ubuntu 上可用。
项目目录也可以是 Ubuntu 中已挂载的共享项目路径；不要填写 Windows 盘符路径。

迁移保留 Windows 原文件。不会复制登录凭据、配置、图片附件或子代理旁路文件，也不会自动启动模型请求。
Codex Desktop 的数据库索引未自动修改，优先用给出的 CLI 命令恢复；Desktop 是否显示仍需本机软件检查。
CodeBuddy 的格式依据来自已观测文件，自动回读通过不能代替对应版本的真实原生续聊验证。

清除选择：

```bash
python3 app/cli.py windows-use --clear
```

保存/清除后重启服务。切回 Windows 或 macOS 时，程序忽略 `windows_user_home`，继续读取当前系统默认来源。
每个 Agent 的原有 `agent_homes` 显式配置仍然生效；请保持它们为空以使用每个系统自己的默认目录。

## 5. 反向迁回 Windows

先选择 Windows 用户目录（第 3 步），确保目标分区可写，并关闭两端 Agent。
在网页选 **Ubuntu 本机来源**中的会话，填写两个路径：

- Windows 软件使用的真实项目路径，例如 `D:\project`。
- 同一项目在 Ubuntu 中的可访问路径，例如 `/mnt/data/project`。

点击 **“迁到 Windows 对应软件”**。默认保留原生 ID；若 Windows 原会话还在，程序会拒绝覆盖。
点击“生成新 ID”可以保存独立副本。正文和工具参数中的 Ubuntu 路径仍按原样保留。
返回结果显示 Windows 原生存储文件与恢复命令；Claude / Codex 命令使用 PowerShell 语法。
网页“查看 Windows 会话”可回读新增记录。通用跨软件转换使用 Ubuntu 可访问的项目路径。

```bash
python3 app/cli.py export-windows codex <Ubuntu会话ID> \
  --cwd 'D:\project' --project-path /mnt/data/project \
  --session-id 11111111-1111-4111-8111-111111111111
```

两个路径的分区对应关系由用户明确指定，程序只验证挂载项目可访问与 Windows 路径格式，不猜盘符。
支持相同六来源及 CodeBuddy CLI/IDE；DSH 的 v4、父会话限制仍适用。
CodeBuddy IDE 先在 **Windows** 目标项目创建一条会话并关闭软件，以复用已有原生工作区；
Linux 中仅读到的目标 Windows IDE 工作区须记录 Windows 的盘符路径，不能用挂载路径替代。
Ubuntu→Windows 与 Windows→Ubuntu 都是保留原文件的搬迁，**不提供同 ID 增量合并**。
两端各自继续后的历史需要分别保留，不会自动选择较新文件覆盖另一端。

## 6. 在 Windows 中导入 Ubuntu 用户目录备份

Windows 默认不能直接读取 Ubuntu ext4。可先在 Ubuntu 把需要的 Agent 原生目录复制到共享 NTFS
中的用户目录备份，例如 `D:\UbuntuBackup\alice\.codex`、`.claude`、`.dsh`、`.workbuddy`、`.codebuddy`。
CodeBuddy IDE 保留 `.config/CodeBuddyExtension/Data` 层级。不要混入凭据与账号设置；本工具不会过滤整个 home 备份。

```powershell
python app/cli.py ubuntu-use "D:\UbuntuBackup\alice"
python app/cli.py list ubuntu_codex
python app/cli.py import-ubuntu codex <Ubuntu来源完整会话ID> --cwd "D:\project"
```

重启服务后增加六个 Ubuntu 只读来源，选择会话和现有 Windows 项目目录即可点击对应软件迁移。
`--ubuntu-user` 可临时覆盖；`ubuntu-use --clear` 清除选择。`ubuntu_user_home` 和
`RELAY_UBUNTU_USER_HOME` 仅在 Windows 生效；Linux/macOS 忽略，避免便携配置污染本机来源。
该模式不需要 Linux 挂载项目字段，因为 Windows 能直接验证目标 cwd。

## 排查

| 现象 | 处理 |
|---|---|
| 未发现 Windows 用户 | 先在文件管理器打开含 `Users` 的 Windows 分区；检查挂载点和用户实际文件夹名 |
| 重启 Ubuntu 后 Windows 入口不可用 | 先重新挂载；挂载点变化时重新执行 `windows-use`；程序保留原路径，不会悄悄切换到其他用户 |
| Windows 分区只读 | 浏览和导出可继续；反向写回需要可写挂载，不会自动更改挂载选项 |
| NTFS 提示休眠 / 不允许挂载 | 在 Windows 完整关机，并按系统提示关闭快速启动后再进入 Ubuntu；不要强制删除休眠文件 |
| BitLocker 分区打不开 | 先用系统支持的方式解锁、挂载；本工具不解密分区 |
| 权限不足 | 检查 Ubuntu 当前用户能否读取对应文件和目录；用挂载权限解决，无需以 root 运行服务 |
| DSH 提示缺少 zstandard | 运行首次准备，并通过 Linux 启动器或同一虚拟环境中的 Python 读取 |
| 直接双击脚本不执行 | 在项目文件夹打开终端，使用 `bash 启动_AgentRelay.sh` |
| Windows Agent 列表为空 | 默认目录没有对应记录，或 Windows 自定义了存储根目录；检查真实文件位置 |
| 迁出提示项目目录无效 | 填写 Ubuntu 中已存在的绝对目录；原记录中的 Windows cwd 不会用作 Linux 写入路径 |
| 对应软件导入提示 ID 已存在 | 保留现有会话；网页点击“生成新 ID”或命令行指定新 UUID 再导入 |
| CodeBuddy IDE 没有匹配工作区 | 先在 Ubuntu 目标项目创建一条原生会话、关闭软件，再导入 |
| DSH 旧世代 / 父会话缺失 | 先在 Windows DSH 升级到 v4；分叉会话先迁入父会话，保留父 ID |
| 反向缺少项目路径 | cwd 填 Windows 盘符路径，project_path 填同一项目在 Ubuntu 中的挂载绝对路径 |
| Windows 看不到 Ubuntu 磁盘 | 使用可访问的用户目录备份，或在 Ubuntu 执行 export-windows；程序不安装 ext4 驱动 |

验证范围：自动测试使用合成 Windows 用户目录，覆盖六来源读取、CLI/IDE、只读保护、原文件不变、
迁出 cwd、配置保留、挂载路径转义、切回 Windows/macOS、Ubuntu Bash 启动及停止。
对应软件迁入另覆盖六个来源及 CodeBuddy 两种格式、原生未知字段、父链/事件、标题索引、同名保护与索引失败回滚。
反向测试覆盖六来源与两种 CodeBuddy 格式、Ubuntu IDE 目录布局、Windows 恢复命令引号、
分离的逻辑/挂载路径、源目标重叠拒绝、配置平台隔离及真实 Linux HTTP 往返。
真实设备上的 NTFS 驱动、BitLocker、挂载权限与原生 Agent 续聊仍需在该双系统设备上检查。
