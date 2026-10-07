一个 ZIP 包包含 **Windows x64、Mac Apple Silicon / Intel、Linux x64**，无需另装 Python、Node.js 或 DSH 解码依赖。下载 `AgentRelay-*-universal.zip` 完整解压，按当前设备运行对应启动器。

各设备共用总包根目录的 `storage/` 和可选 `config.json`，适合移动盘切换。启动器首次只解压当前平台运行库到本机缓存，不下载其他文件。包内仅保留运行文件、配置示例和简短使用说明，未附带测试、开发手册、格式调研或真实数据。

- Windows 10/11 x64：双击 `启动_AgentRelay.bat`。
- Mac Apple Silicon（macOS 14+）/ Intel（macOS 15+）：双击 `AgentRelay.app` 或运行 `bash 启动_AgentRelay.command`。未经过 Apple 公证，系统阻止时按包内 `开始使用.txt` 的首次运行步骤处理。
- Linux x64：Ubuntu 22.04+ / glibc 2.35+，执行 `bash 启动_AgentRelay.sh`。

本版完成第一阶段：

- 修复 Windows PowerShell 7 继承模块路径导致总包无法启动；加固 HTTP 就绪与端口探测。
- 新增「环境与兼容」：本机 Agent 目录按设备保存，旧目录失效可重选或恢复自动探测；显示运行时、依赖、写权限和空间。双系统用户目录选择也不再修改共享配置。
- 通用迁移、Windows/Ubuntu 原生迁移、会话包恢复先预览保留、降级、丢弃和未知内容；取消不写，确认后检查源记录、选项与目标是否变化。
- API v1 可信社区单文件读取插件，显式启用、SHA-256 检查、独立进程与超时。支持读取、导出、迁出；换设备重新启用，暂不开放原生写入或存包。
- 六个内置来源合成样本自检、每日三系统 CI 和静态报告，注明覆盖与证据；客户端版本及实际续聊没有依据时显示未知。

保留对话/Skill 批量存储、跨设备恢复、同 ID/同名保护与 ZIP v1 兼容。退出需点击“退出服务”或在终端按 Ctrl+C，关闭网页不会停止服务。插件示例及完整格式/排查说明在仓库 docs/。

这是开发预览版。发布门槛包括四套冻结程序及最终总包：空 PATH、中文/空格便携根、预览一致性、插件 worker/hash、六来源自检、复制存储后会话与完整 Skill 恢复、冲突拒绝、HTTP 与退出。目标 Agent 的实际续聊、依赖及设备权限仍需核对；样本回读不能替代厂商最新版续聊验证。存储包不加密，不自动执行 Skill 脚本，可信插件隔离不是安全沙箱。

`SHA256SUMS.txt` 提供总包校验值。GitHub 自动生成的 Source code 压缩包是开发源码；普通用户请选择 **universal.zip**。
