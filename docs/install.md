# 下载、安装与启动

Release 总包与源码两种启动方式、端口与退出说明。回到 [README](../README.md)。

## Release 下载即用

当前开发预览版：**v0.4.0-dev.2** · [下载三系统总包](https://github.com/FriedOnion2/agent-relay-portable/releases/download/v0.4.0-dev.2/AgentRelay-v0.4.0-dev.2-universal.zip) · [发布说明与校验文件](https://github.com/FriedOnion2/agent-relay-portable/releases/tag/v0.4.0-dev.2)

普通用户下载 [GitHub Releases](https://github.com/FriedOnion2/agent-relay-portable/releases) 中的
**`AgentRelay-<版本>-universal.zip`**，完整解压后按当前设备运行启动器。一个总包同时包含
Windows x64、Mac Apple Silicon / Intel 和 Linux x64，已内置 Python 与 `zstandard`，无需另装 Python 或 Node.js。
不要选择 GitHub 自动生成的 Source code 压缩包，那是开发源码。

| 当前设备 | Release 启动入口 | 支持范围 |
|---|---|---|
| Windows | `启动_AgentRelay.bat` | Windows 10/11 x64 |
| Mac | `AgentRelay.app` 或 `bash 启动_AgentRelay.command` | Apple Silicon：macOS 14+；Intel：macOS 15+ |
| Linux | `bash 启动_AgentRelay.sh` | Ubuntu 22.04+ / glibc 2.35+ x64 |

总包根目录共用 `config.json`（可选）、`storage/` 与 `index/`。退出服务后把整个总包放在移动盘上，切换设备无需再下载另一系统的版本；导出草稿若在总包之外，另行复制。
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
Ubuntu 首次准备使用用户级虚拟环境，避免系统 pip 的 PEP 668 限制。完整运行时说明见 [runtime/README.txt](../runtime/README.txt)。
缺少解码器时仍会列出 DSH 会话并显示安装提示；损坏、未写完、过大或未知版本的日志会显示读取受限。

Mac `.app` 在 HTTP 就绪后打开浏览器，尊重 `open_browser` 配置。日志优先写入项目 `logs/`，
外置盘禁止写日志时改用 `~/Library/Logs/AgentRelay/`。文稿目录内双击曾出现 Python 探测停住，
可改用终端启动器，并检查 macOS 文件与文件夹访问权限；这不属于已确认根因。
