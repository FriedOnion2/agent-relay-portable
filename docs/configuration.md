# 配置与数据

配置文件、设备配置与数据目录。回到 [README](../README.md)。

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

迁移命令和 `restore-session` 支持 `--dry-run` 与 `--preview-token`；旧直接命令保持兼容。预览不会锁住源软件，操作前关闭正在写入会话的客户端。详见 [兼容与迁移预览](compatibility.md)、[插件接口](adapters.md) 和 [换设备排查](troubleshooting.md)。
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
