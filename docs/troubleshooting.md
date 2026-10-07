# 运行与换设备排查

1. 下载 Releases 的 `universal.zip`，完整解压，确认 `runtimes/` 和 `version.json` 存在。不要只复制 BAT 或选择 Source code 包。
2. 检查系统与 CPU：Windows x64、Ubuntu 22.04+ / glibc 2.35+ x64、Mac ARM64 14+ / Intel 15+。Linux 执行 `bash 启动_AgentRelay.sh`，避免移动盘 noexec；运行库在本机缓存解压执行。
3. 启动后打开「环境与兼容」核对数据目录、运行时目录、空间与 Zstandard。总包应显示 Release 内置解释器。`Runtime checksum mismatch` 时重新下载并核对发布 SHA256SUMS；不要修改清单绕过校验。
4. Windows 启动器明确调用系统 Windows PowerShell，并在子进程中加入系统模块路径，兼容从 PowerShell 7 启动；不修改用户全局配置。当前运行版本必须包含这一修复。
5. 端口被占用时尝试后五个端口，以启动输出实际地址为准。关闭旧服务使用网页「退出服务」，单纯关闭网页不会退出。全部候选被占用再更改端口。
6. 目录不可访问时在「环境与兼容」选择实际 Agent 根目录，不填 `projects` / `sessions` 子目录；留空并保存可恢复自动探测。旧显式路径不会静默回退为默认位置。
7. 本机选择存入 `devices/<设备ID>.json`。换设备自动使用另一份配置；保留 `storage/` 即可携带包，新设备填写新项目目录再恢复。同 ID / 同名不覆盖，另存用新 ID / 名称。
8. Windows/Ubuntu 用户目录选择使用 `windows-use` / `ubuntu-use`，仅保存在本机配置。挂载不可读、NTFS 休眠或 Windows 无法读 ext4，见 [双系统说明](ubuntu-dual-boot.md)。不自动安装分区驱动。
9. 只读移动盘可以查看记录；存储面板选择可写目录。设备设置保存失败时把完整总包复制到可写目录。空间不足、权限不足先修复目录条件；失败不会被视为完成。
10. 格式出错运行 `health` 并保留报告；合成样本通过不能证明真实厂商新版可续聊。未知世代、缺消息或损坏记录应保留源副本并停止迁移，不修改原日志绕过检查。

缓存解压中断时，先退出所有 AgentRelay 进程，再删除当前版本缓存后重新启动。Windows：`%LOCALAPPDATA%/AgentRelay/<版本>`；Mac：`~/Library/Caches/AgentRelay/<版本>`；Linux：`${XDG_CACHE_HOME:-~/.cache}/agentrelay/<版本>`。程序不自动清理其他版本或源软件的数据。

社区插件出错可用 `plugins disable <名称>` 后重启服务。文件 hash 改变需审阅后重新 enable；复制设备配置不能代替在新机器上重新批准。Skill 只复制目录，目标软件的依赖和工具接口需要另行设置。
