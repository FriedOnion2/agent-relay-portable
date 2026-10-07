一个 ZIP 包包含 **Windows x64、Mac Apple Silicon / Intel、Linux x64**，无需另装 Python、Node.js 或 DSH 解码依赖。下载 `AgentRelay-*-universal.zip` 完整解压，按当前设备运行对应启动器。

各设备共用总包根目录的 `storage/` 和可选 `config.json`，适合移动盘切换。启动器首次只解压当前平台运行库到本机缓存，不下载其他文件。包内仅保留运行文件、配置示例和简短使用说明，未附带测试、开发手册、格式调研或真实数据。

- Windows 10/11 x64：双击 `启动_AgentRelay.bat`。
- Mac Apple Silicon（macOS 14+）/ Intel（macOS 15+）：双击 `AgentRelay.app` 或运行 `bash 启动_AgentRelay.command`。未经过 Apple 公证，系统阻止时按包内 `开始使用.txt` 的首次运行步骤处理。
- Linux x64：Ubuntu 22.04+ / glibc 2.35+，执行 `bash 启动_AgentRelay.sh`。

支持对话与 Skill 复选框、全选和批量存储、跨设备恢复、DSH 通用导入、自动换空闲端口和网页退出服务。退出需点击“退出服务”或在终端按 Ctrl+C，关闭网页不会停止服务。

这是开发预览版。各平台原生打包进程已检查内置依赖、DSH 导入、共享数据目录、HTTP 启动和退出；目标 Agent 的原生续聊与设备权限仍需在实际环境核对。存储包不加密，同 ID/同名不覆盖，不自动执行 Skill 脚本。手动配置的绝对路径在换设备后需要调整。

`SHA256SUMS.txt` 提供总包校验值。GitHub 自动生成的 Source code 压缩包是开发源码；普通用户请选择 **universal.zip**。
