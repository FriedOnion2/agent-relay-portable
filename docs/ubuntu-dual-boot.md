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
程序不会自动复制 Windows 凭据、改写 Windows 会话、挂载磁盘或调整分区权限。

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

仅查看和导出不需要转换项目路径。迁出时，必须填写**已存在的 Ubuntu 项目目录**，例如：

```bash
python3 app/cli.py transfer windows_codex <完整会话ID> --to claude --cwd /home/alice/project
```

网页同样在“目标工作目录”填写 `/home/alice/project`。目标只能选择本机 WorkBuddy、Claude、Codex。
这里转换的是会话所属的项目目录；历史工具参数、正文中的 `C:\…` 或其他盘符不会自动替换，
续聊前需自行确认对应文件和工具在 Ubuntu 上可用。
项目目录也可以是 Ubuntu 中已挂载的共享项目路径；不要填写 Windows 盘符路径。

清除选择：

```bash
python3 app/cli.py windows-use --clear
```

保存/清除后重启服务。切回 Windows 或 macOS 时，程序忽略 `windows_user_home`，继续读取当前系统默认来源。
每个 Agent 的原有 `agent_homes` 显式配置仍然生效；请保持它们为空以使用每个系统自己的默认目录。

## 排查

| 现象 | 处理 |
|---|---|
| 未发现 Windows 用户 | 先在文件管理器打开含 `Users` 的 Windows 分区；检查挂载点和用户实际文件夹名 |
| 重启 Ubuntu 后 Windows 入口不可用 | 先重新挂载；挂载点变化时重新执行 `windows-use`；程序保留原路径，不会悄悄切换到其他用户 |
| Windows 分区只读 | 只读挂载足以浏览和导出；无需为了本工具改成可写 |
| NTFS 提示休眠 / 不允许挂载 | 在 Windows 完整关机，并按系统提示关闭快速启动后再进入 Ubuntu；不要强制删除休眠文件 |
| BitLocker 分区打不开 | 先用系统支持的方式解锁、挂载；本工具不解密分区 |
| 权限不足 | 检查 Ubuntu 当前用户能否读取对应文件和目录；用挂载权限解决，无需以 root 运行服务 |
| DSH 提示缺少 zstandard | 运行首次准备，并通过 Linux 启动器或同一虚拟环境中的 Python 读取 |
| 直接双击脚本不执行 | 在项目文件夹打开终端，使用 `bash 启动_AgentRelay.sh` |
| Windows Agent 列表为空 | 默认目录没有对应记录，或 Windows 自定义了存储根目录；检查真实文件位置 |
| 迁出提示项目目录无效 | 填写 Ubuntu 中已存在的绝对目录；原记录中的 Windows cwd 不会用作 Linux 写入路径 |

验证范围：自动测试使用合成 Windows 用户目录，覆盖六来源读取、CLI/IDE、只读保护、原文件不变、
迁出 cwd、配置保留、挂载路径转义、切回 Windows/macOS、Ubuntu Bash 启动及停止。
真实设备上的 NTFS 驱动、BitLocker、挂载权限与原生 Agent 续聊仍需在该双系统设备上检查。
